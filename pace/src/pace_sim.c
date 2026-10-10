/*
 * MuJoCo 시뮬레이터 프로세스 (비실시간, 일반 코어). 제어기와 공유메모리 락스텝.
 *  - 제어기가 보낸 명령 틱마다 정확히 1ms 분량을 적분한다 (벽시계는 제어기가 쥔다)
 *  - 모델의 위치 액추에이터가 관절과 1:1 이라고 가정 (ctrl[j] = q_cmd[j]). 액추에이터가 없으면 운동학적으로 qpos 를 직접 설정.
 */
#define _GNU_SOURCE
#include <mujoco/mujoco.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pace/sim_link.h"
#include "pace/rt.h"

static volatile sig_atomic_t running = 1;
static void on_sig(int s) { (void)s; running = 0; }

int main(int argc, char **argv)
{
    const char *model_path = "models/arm6_test.xml", *link_name = "/pace_sim";
    int cpu = -1; double timestep = 0.001; int verbose = 0, gravcomp = 1; double ff_tau = 0.2;
    double dist_at = -1, dist_dur = 0.5, dist_tau = 40.0; int dist_joint = 1;   /* 외란: 시뮬 시간 dist_at 부터 dist_dur 동안 관절 dist_joint 에 토크 dist_tau 추가 */
    double fault_at = -1, fault_dur = 1.0;
    const char *init_q = NULL;                                                     /* 초기 관절 자세 (키프레임 대신): "q0 q1 ..." */                                         /* HAL 폴트 주입: 시뮬 시간 fault_at 부터 fault_dur 동안 드라이브 폴트 보고 (상태는 계속 보고) */
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--model") && i + 1 < argc) model_path = argv[++i];
        else if (!strcmp(argv[i], "--simlink") && i + 1 < argc) link_name = argv[++i];
        else if (!strcmp(argv[i], "--cpu") && i + 1 < argc) cpu = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--timestep") && i + 1 < argc) timestep = atof(argv[++i]);
        else if (!strcmp(argv[i], "--verbose")) verbose = 1;
        else if (!strcmp(argv[i], "--no-gravcomp")) gravcomp = 0;
        else if (!strcmp(argv[i], "--ff-tau") && i + 1 < argc) ff_tau = atof(argv[++i]);
        else if (!strcmp(argv[i], "--disturb-at") && i + 1 < argc) dist_at = atof(argv[++i]);
        else if (!strcmp(argv[i], "--disturb-dur") && i + 1 < argc) dist_dur = atof(argv[++i]);
        else if (!strcmp(argv[i], "--disturb-tau") && i + 1 < argc) dist_tau = atof(argv[++i]);
        else if (!strcmp(argv[i], "--disturb-joint") && i + 1 < argc) dist_joint = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--fault-at") && i + 1 < argc) fault_at = atof(argv[++i]);
        else if (!strcmp(argv[i], "--fault-dur") && i + 1 < argc) fault_dur = atof(argv[++i]);
        else if (!strcmp(argv[i], "--init-q") && i + 1 < argc) init_q = argv[++i];
    }
    signal(SIGINT, on_sig); signal(SIGTERM, on_sig);
    if (cpu >= 0) { cpu_set_t s; CPU_ZERO(&s); CPU_SET(cpu, &s); sched_setaffinity(0, sizeof s, &s); }

    char err[512];
    mjModel *m = mj_loadXML(model_path, NULL, err, sizeof err);
    if (!m) { fprintf(stderr, "model load failed: %s\n", err); return 1; }
    m->opt.timestep = timestep;
    mjData *d = mj_makeData(m);
    int substeps = (int)(0.001 / timestep + 0.5); if (substeps < 1) substeps = 1;
    int dof = m->nv < (int)PACE_MAX_DOF ? m->nv : (int)PACE_MAX_DOF;
    int tool_site = mj_name2id(m, mjOBJ_SITE, "tool");
    int touch = mj_name2id(m, mjOBJ_SENSOR, "tip_touch"); int touch_adr = touch >= 0 ? m->sensor_adr[touch] : -1;   /* 토치 끝 접촉력 센서 (HAL 센서 백엔드) */
    int kinematic = (m->nu == 0);
    if (dist_at >= 0) fprintf(stderr, "[sim] disturbance: joint %d, +%.1f Nm, t=%.1f..%.1f s (sim time)\n", dist_joint, dist_tau, dist_at, dist_at + dist_dur);
    fprintf(stderr, "[sim] model=%s nq=%ld nv=%ld nu=%ld dof=%d timestep=%.4f substeps=%d tool_site=%d gravcomp=%d %s\n",
            model_path, (long)m->nq, (long)m->nv, (long)m->nu, dof, timestep, substeps, tool_site, gravcomp, kinematic ? "(kinematic)" : "");

    pace_sim_link_t *L; int r = pace_sim_link_create(link_name, &L);
    if (r) { fprintf(stderr, "sim link create failed %d\n", r); return 1; }

    /* 키프레임 초기화: weld_home > home > 0 */
    { int key = mj_name2id(m, mjOBJ_KEY, "weld_home"); if (key < 0) key = mj_name2id(m, mjOBJ_KEY, "home");
      if (key >= 0) { mj_resetDataKeyframe(m, d, key); fprintf(stderr, "[sim] keyframe %d applied\n", key); } }
    if (init_q) { const char *p = init_q; for (int j = 0; j < m->nq && *p; ++j) { char *e; double v = strtod(p, &e); if (e == p) break; d->qpos[j] = v; if (j < m->nu) d->ctrl[j] = v; p = e; } fprintf(stderr, "[sim] init-q applied\n"); }
    /* 초기 상태 발행 (tick 0) → 제어기가 q0 를 읽을 수 있게 */
    mj_forward(m, d);
    pace_sim_state_t S; memset(&S, 0, sizeof S);
    S.st.dof = (uint16_t)dof; S.st.valid = 1 | 2 | 4 | 8 | (tool_site >= 0 ? 16 : 0);
    /* 로봇별 한계값: 관절 범위는 모델, 속도·가속도·저크·작업영역은 <custom><numeric> (없으면 보수적 기본값) */
    { pace_hal_limits_t *L = &S.limits; memset(L, 0, sizeof *L);
      L->dof = (uint16_t)dof; L->accepts_position = 1; L->accepts_velocity = 1; L->native_period_ns = 1000000; L->read_wcet_ns = 20000; L->write_wcet_ns = 20000;
      for (int j = 0; j < dof; ++j) {
        int jid = m->dof_jntid[j]; int limited = m->jnt_limited[jid];
        L->q_min[j] = limited ? (float)m->jnt_range[2 * jid] : -6.283f; L->q_max[j] = limited ? (float)m->jnt_range[2 * jid + 1] : 6.283f;
        L->qd_max[j] = 3.14f; L->qdd_max[j] = 20.0f; L->jerk_max[j] = 500.0f; L->tau_max[j] = (j < m->nu && m->actuator_forcelimited[j]) ? (float)m->actuator_forcerange[2 * j + 1] : 150.0f; }
      int id;
      if ((id = mj_name2id(m, mjOBJ_NUMERIC, "qd_max")) >= 0)  for (int j = 0; j < dof && j < m->numeric_size[id]; ++j) L->qd_max[j]  = (float)m->numeric_data[m->numeric_adr[id] + j];
      if ((id = mj_name2id(m, mjOBJ_NUMERIC, "qdd_max")) >= 0) for (int j = 0; j < dof && j < m->numeric_size[id]; ++j) L->qdd_max[j] = (float)m->numeric_data[m->numeric_adr[id] + j];
      if ((id = mj_name2id(m, mjOBJ_NUMERIC, "jerk_max")) >= 0) for (int j = 0; j < dof && j < m->numeric_size[id]; ++j) L->jerk_max[j] = (float)m->numeric_data[m->numeric_adr[id] + j];
      if ((id = mj_name2id(m, mjOBJ_NUMERIC, "workspace")) >= 0 && m->numeric_size[id] >= 6) { for (int k = 0; k < 3; ++k) { L->workspace_min[k] = (float)m->numeric_data[m->numeric_adr[id] + k]; L->workspace_max[k] = (float)m->numeric_data[m->numeric_adr[id] + 3 + k]; } }
      else { for (int k = 0; k < 3; ++k) { L->workspace_min[k] = -2.0f; L->workspace_max[k] = 2.0f; } }
      fprintf(stderr, "[sim] limits: q[0]=[%.2f,%.2f] qd_max[0]=%.2f qdd_max[0]=%.1f workspace z=[%.2f,%.2f]\n", L->q_min[0], L->q_max[0], L->qd_max[0], L->qdd_max[0], L->workspace_min[2], L->workspace_max[2]); }
    for (int j = 0; j < dof; ++j) { S.st.q[j] = (float)d->qpos[j]; S.st.qd[j] = (float)d->qvel[j]; }
    if (tool_site >= 0) { for (int k = 0; k < 3; ++k) S.st.tool_pose[k] = (float)d->site_xpos[3 * tool_site + k]; double q[4]; mju_mat2Quat(q, d->site_xmat + 9 * tool_site); for (int k = 0; k < 4; ++k) S.st.tool_pose[3 + k] = (float)q[k]; }
    S.st.t_ns = pace_now_ns(); S.t_state_ns = S.st.t_ns;
    pace_sim_link_write_state(L, &S);

    uint32_t last_tick = 0; uint64_t steps = 0, late = 0, step_max = 0, step_sum = 0;
    pace_sim_cmd_t C; int estop_latched = 0; double q_hold[PACE_MAX_DOF] = {0}; uint32_t last_stop_level = 0;
    if (fault_at >= 0) fprintf(stderr, "[sim] HAL fault injection: t=%.1f..%.1f s (sim time)\n", fault_at, fault_at + fault_dur);
    while (running) {
        if (!pace_sim_link_wait_cmd(L, last_tick, 200000000ull, &C)) continue;   /* 200ms 타임아웃 → running 확인 */
        last_tick = (uint32_t)C.tick;
        uint64_t t0 = pace_now_ns();
        /* HAL 정지 3단계 의미 (이 백엔드의 정의):
         *  DECEL(1) = 제어기가 램프로 내리는 위치 명령을 그대로 따른다 (서보 유지)
         *  HOLD(2)  = 마지막 위치를 유지한다 (q_cmd 무시)
         *  ESTOP(3) = 브레이크 체결: 그 순간 위치를 잠그고 이후 모든 명령을 무시, 상태에 ESTOP_LATCHED 폴트 비트를 올린다 (리셋 = 프로세스 재시작) */
        if (C.stop_level == PACE_STOP_ESTOP && !estop_latched) { estop_latched = 1; for (int j = 0; j < dof; ++j) q_hold[j] = d->qpos[j]; fprintf(stderr, "[sim] ESTOP latched at tick %llu (sim t=%.3f)\n", (unsigned long long)C.tick, d->time); }
        if (C.stop_level == PACE_STOP_HOLD && last_stop_level != PACE_STOP_HOLD && !estop_latched) for (int j = 0; j < dof; ++j) q_hold[j] = d->qpos[j];   /* HOLD 진입 순간의 위치를 잠근다 (매 틱 갱신하면 서보 강성이 0 이 됨) */
        if (C.stop_level != last_stop_level) { if (C.stop_level && C.stop_level != PACE_STOP_ESTOP) fprintf(stderr, "[sim] stop level %u at tick %llu\n", C.stop_level, (unsigned long long)C.tick); last_stop_level = C.stop_level; }
        int hold = estop_latched || C.stop_level == PACE_STOP_HOLD;
        if (kinematic) { for (int j = 0; j < dof; ++j) d->qpos[j] = hold ? q_hold[j] : C.q_cmd[j]; }
        else { for (int j = 0; j < dof && j < m->nu; ++j) d->ctrl[j] = hold ? q_hold[j] : C.q_cmd[j] + ff_tau * C.qd_cmd[j]; }
        for (int s = 0; s < substeps; ++s) {
            /* 이상적 중력·코리올리 보상: 실제 산업용 제어기의 피드포워드. 직전 스텝의 qfrc_bias 사용 (1 서브스텝 지연) */
            if (gravcomp) for (int j = 0; j < m->nv; ++j) d->qfrc_applied[j] = d->qfrc_bias[j];
            else for (int j = 0; j < m->nv; ++j) d->qfrc_applied[j] = 0;
            if (dist_at >= 0 && d->time >= dist_at && d->time < dist_at + dist_dur && dist_joint < m->nv) d->qfrc_applied[dist_joint] += dist_tau;   /* 외란 토크 펄스 */
            mj_step(m, d);
        }
        if (kinematic) mj_forward(m, d);
        uint64_t t1 = pace_now_ns();
        uint32_t step_ns = (uint32_t)(t1 - t0);
        if (atomic_load_explicit(&L->futex_tick, memory_order_acquire) != last_tick) late++;   /* 스텝 중 다음 명령 도착 */
        S.tick = C.tick; S.t_state_ns = t1; S.sim_time_ns = (uint64_t)(d->time * 1e9); S.step_ns = step_ns; S.late = (uint32_t)late;
        S.st.t_ns = t1; S.st.hal_fault = 0;
        if (touch_adr >= 0) { S.st.tool_force = (float)d->sensordata[touch_adr]; S.st.valid |= 32; }
        if (fault_at >= 0 && d->time >= fault_at && d->time < fault_at + fault_dur) S.st.hal_fault |= PACE_HALF_DRIVE;
        if (estop_latched) S.st.hal_fault |= PACE_HALF_ESTOP_LATCHED;
        for (int j = 0; j < dof; ++j) { S.st.q[j] = (float)d->qpos[j]; S.st.qd[j] = (float)d->qvel[j]; S.st.qdd[j] = (float)d->qacc[j]; S.st.tau[j] = (j < m->nu) ? (float)d->actuator_force[j] : 0.0f; }
        if (tool_site >= 0) { for (int k = 0; k < 3; ++k) S.st.tool_pose[k] = (float)d->site_xpos[3 * tool_site + k]; double q[4]; mju_mat2Quat(q, d->site_xmat + 9 * tool_site); for (int k = 0; k < 4; ++k) S.st.tool_pose[3 + k] = (float)q[k]; }
        pace_sim_link_write_state(L, &S);
        steps++; step_sum += step_ns; if (step_ns > step_max) step_max = step_ns;
        if (verbose && (steps % 1000) == 0) fprintf(stderr, "[sim] tick=%llu step_avg=%.1fus step_max=%.1fus late=%llu\n", (unsigned long long)C.tick, step_sum / 1e3 / steps, step_max / 1e3, (unsigned long long)late);
    }
    fprintf(stderr, "[sim] done: steps=%llu step_avg=%.1fus step_max=%.1fus late=%llu (%.3f%%)\n",
            (unsigned long long)steps, steps ? step_sum / 1e3 / steps : 0.0, step_max / 1e3, (unsigned long long)late, steps ? 100.0 * late / steps : 0.0);
    pace_sim_link_close(L); mj_deleteData(d); mj_deleteModel(m);
    return 0;
}
