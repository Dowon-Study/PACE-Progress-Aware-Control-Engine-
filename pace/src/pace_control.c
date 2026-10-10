/*
 * 1kHz 실시간 제어 루프 — 4단계 (docs/IDEA_FIXED.md 5절 ①~⑩ 중 ⑤접합·⑥페이싱은 자리만)
 *  매 틱: 틱 대기 → HAL read → 큐 폴링 → 3단계 검증 → 참조 버퍼(시간 인덱스 재생) → 속도 배율 → 명령 생성(변화율 제한)
 *        → 상태 감시기(룩어헤드) → HAL write → 계측
 *  격리 코어, SCHED_FIFO, mlockall, 루프 내 할당·ROS 2 없음. trace 는 루프 전 미리 잡은 배열에 쓰고 종료 후 파일로.
 */
#define _GNU_SOURCE
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pace/shm.h"
#include "pace/hal.h"
#include "pace/rt.h"
#include "pace/config.h"
#include "pace/refbuf.h"
#include "pace/validator.h"
#include "pace/monitor.h"
#include "pace/kin.h"
#include "pace/refpath.h"

static volatile sig_atomic_t running = 1;
static void on_sig(int s) { (void)s; running = 0; }

typedef struct { uint64_t n, sum, max, min; uint64_t hist[2001]; } stat_t;
static void stat_add(stat_t *s, uint64_t v) { s->n++; s->sum += v; if (v > s->max) s->max = v; if (s->n == 1 || v < s->min) s->min = v; uint64_t b = v / 1000; if (b > 2000) b = 2000; s->hist[b]++; }
static uint64_t stat_pct(const stat_t *s, double p) { uint64_t target = (uint64_t)(p * s->n + 0.5), acc = 0; for (int b = 0; b <= 2000; ++b) { acc += s->hist[b]; if (acc >= target) return (uint64_t)b * 1000; } return 2000000; }
static void stat_json(const char *k, const stat_t *s, FILE *f) { fprintf(f, "\"%s\":{\"n\":%llu,\"min_us\":%.1f,\"avg_us\":%.1f,\"p50_us\":%.0f,\"p99_us\":%.0f,\"p999_us\":%.0f,\"max_us\":%.1f}", k, (unsigned long long)s->n, s->min / 1e3, s->n ? s->sum / 1e3 / s->n : 0.0, stat_pct(s, 0.50) / 1e3, stat_pct(s, 0.99) / 1e3, stat_pct(s, 0.999) / 1e3, s->max / 1e3); }

/* trace 레코드 (루프 전 할당) */
typedef struct { uint64_t t_ns; float q_cmd[PACE_MAX_DOF]; float q_meas[PACE_MAX_DOF]; float tool[7]; float speed; uint16_t mode, monitor; } trace_t;

static void write_trace_npz(const char *path, const trace_t *tr, uint64_t n, uint16_t dof)
{
    /* 간단한 .npz 대신 numpy 가 읽는 .npy 여러 개를 zip 없이 쓰기 어렵다 → 평문 바이너리 + 헤더 JSON 을 .npz 로 가장하지 않고 .bin 으로 쓰고 Python 이 변환 */
    (void)dof; FILE *f = fopen(path, "wb"); if (!f) return;
    fwrite(&n, sizeof n, 1, f); uint32_t d = dof, sz = sizeof(trace_t); fwrite(&d, 4, 1, f); fwrite(&sz, 4, 1, f);
    fwrite(tr, sizeof(trace_t), n, f); fclose(f);
}

int main(int argc, char **argv)
{
    const char *shm_name = "/pace", *simlink = "/pace_sim", *traj = "hold", *cfg_path = NULL, *trace_path = NULL, *policy_s = "progress", *refpath_file = NULL, *kin_model = NULL, *hal_name = "sim", *urdf_path = NULL;
    double transit_s = 3.0;
    int cpu = 4, prio = 99, duration_s = 20, no_rt = 0, verbose = 0;
    uint64_t period_ns = 1000000; double amp = 0.3, freq = 0.25;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--shm") && i + 1 < argc) shm_name = argv[++i];
        else if (!strcmp(argv[i], "--simlink") && i + 1 < argc) simlink = argv[++i];
        else if (!strcmp(argv[i], "--cpu") && i + 1 < argc) cpu = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--prio") && i + 1 < argc) prio = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--duration") && i + 1 < argc) duration_s = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--period-ns") && i + 1 < argc) period_ns = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--traj") && i + 1 < argc) traj = argv[++i];        /* hold | sine (공급자 없이 자체 테스트) */
        else if (!strcmp(argv[i], "--amp") && i + 1 < argc) amp = atof(argv[++i]);
        else if (!strcmp(argv[i], "--freq") && i + 1 < argc) freq = atof(argv[++i]);
        else if (!strcmp(argv[i], "--config") && i + 1 < argc) cfg_path = argv[++i];
        else if (!strcmp(argv[i], "--trace") && i + 1 < argc) trace_path = argv[++i];
        else if (!strcmp(argv[i], "--policy") && i + 1 < argc) policy_s = argv[++i];   /* timeidx | immediate | progress */
        else if (!strcmp(argv[i], "--refpath") && i + 1 < argc) refpath_file = argv[++i];   /* 기준 경로 모드: 교시 경로 파일 (툴 공간) + CORRECTION */
        else if (!strcmp(argv[i], "--kin-model") && i + 1 < argc) kin_model = argv[++i];    /* 운동학용 모델 XML (기준 경로 모드 필수) */
        else if (!strcmp(argv[i], "--transit") && i + 1 < argc) transit_s = atof(argv[++i]);
        else if (!strcmp(argv[i], "--hal") && i + 1 < argc) hal_name = argv[++i];           /* sim (공유메모리 락스텝) | ros2 (ros2_control hardware_interface 플러그인) */
        else if (!strcmp(argv[i], "--urdf") && i + 1 < argc) urdf_path = argv[++i];         /* --hal ros2: <ros2_control> 태그가 든 URDF */
        else if (!strcmp(argv[i], "--no-rt")) no_rt = 1;
        else if (!strcmp(argv[i], "--verbose")) verbose = 1;
    }
    signal(SIGINT, on_sig); signal(SIGTERM, on_sig);

    /* ---- 비실시간 초기화 ---- */
    pace_config_t cfg; pace_config_defaults(&cfg);
    if (cfg_path) { int r = pace_config_load(&cfg, cfg_path); if (r) { fprintf(stderr, "config load failed (%d)\n", r); return 1; } }
    pace_config_print(&cfg, stderr);
    pace_shm_t shm; int r = pace_shm_create(shm_name, &shm);
    if (r) { fprintf(stderr, "shm create failed %d\n", r); return 1; }
    pace_hal_t *hal = NULL; const char *hal_arg = simlink;
    if (!strcmp(hal_name, "sim")) hal = pace_hal_sim_shm_create();
#ifdef PACE_HAVE_ROS2
    else if (!strcmp(hal_name, "ros2")) { hal = pace_hal_ros2_create(); hal_arg = urdf_path; if (!urdf_path) { fprintf(stderr, "--hal ros2 needs --urdf\n"); return 1; } }
#endif
    if (!hal) { fprintf(stderr, "unknown/unavailable HAL '%s'\n", hal_name); return 1; }
    if ((r = hal->init(hal, hal_arg)) != 0) { fprintf(stderr, "hal init failed %d (sim: pace_sim 이 먼저 떠 있어야 합니다)\n", r); return 1; }
    fprintf(stderr, "[ctl] hal=%s\n", hal->name);
    pace_robot_state_t st; memset(&st, 0, sizeof st);
    uint64_t t_deadline = pace_now_ns() + 3000000000ull;
    while (hal->read(hal, &st) != 0 && pace_now_ns() < t_deadline) pace_sleep_until_ns(pace_now_ns() + 1000000);
    if (st.hal_fault) { fprintf(stderr, "no initial state from sim\n"); return 1; }
    const pace_hal_limits_t *lim = hal->limits(hal); pace_shm_write_limits(&shm, lim);
    uint16_t dof = st.dof; float q0[PACE_MAX_DOF]; memcpy(q0, st.q, sizeof q0);
    fprintf(stderr, "[ctl] dof=%u q0=[%.3f %.3f %.3f ...] lim qd_max[0]=%.2f traj=%s cpu=%d prio=%d duration=%ds\n", dof, q0[0], q0[1], q0[2], lim->qd_max[0], traj, cpu, prio, duration_s);

    /* 기준 경로 모드 (7단계): 툴 공간 교시 경로 + CORRECTION. 운동학은 MuJoCo 모델(물리 없이)로 */
    pace_kin_t *kin = NULL; static pace_refpath_t rp; int refmode = 0;
    float q_start[PACE_MAX_DOF]; memcpy(q_start, q0, sizeof q_start);
    if (refpath_file) {
        if (!kin_model) { fprintf(stderr, "--refpath 에는 --kin-model 이 필요합니다\n"); return 1; }
        char kerr[256]; kin = pace_kin_create(kin_model, "tool", kerr, sizeof kerr); if (!kin) { fprintf(stderr, "kin: %s\n", kerr); return 1; }
        if (pace_refpath_load(&rp, refpath_file) != 0) { fprintf(stderr, "refpath load failed: %s\n", refpath_file); return 1; }
        /* 시작 자세: 경로 시작점(s=0, 간격·진행각 적용) 의 IK 를 홈에서 출발해 비실시간으로 충분히 수렴 */
        float p0[3], t0v[3], n0[3], R0[9]; pace_refpath_eval(&rp, 0.0f, p0, t0v, n0); p0[2] += rp.standoff; pace_kin_tool_rotation(t0v, rp.travel_angle, R0);
        float ep, er; pace_kin_ik(kin, q0, p0, R0, 300, 1e-6f, q_start, &ep, &er);
        fprintf(stderr, "[ctl] refpath: n=%u length=%.3fm sdot=%.4f standoff=%.3f travel=%.1fdeg | start IK err %.3fmm %.4frad | transit %.1fs\n", rp.n, pace_refpath_length(&rp), rp.sdot_nominal, rp.standoff, rp.travel_angle * 57.3f, ep * 1e3f, er, transit_s);
        if (ep > 2e-3f) { fprintf(stderr, "start pose unreachable\n"); return 1; }
        refmode = 1;
    }
    const uint64_t total_ticks = (uint64_t)duration_s * 1000000000ull / period_ns;
    trace_t *trace = NULL; if (trace_path) { trace = calloc(total_ticks + 1, sizeof(trace_t)); for (uint64_t i = 0; i < total_ticks + 1; i += 4096 / sizeof(trace_t)) trace[i].t_ns = 0; }

    pace_rt_config_t rcfg = { .cpu = no_rt ? -1 : cpu, .priority = no_rt ? 0 : prio, .lock_memory = !no_rt, .dma_latency = !no_rt, .ftz_daz = true };
    pace_rt_result_t rt = pace_rt_setup(&rcfg);
    fprintf(stderr, "[ctl] rt: affinity=%d sched=%d mlock=%d dma_latency=%d ftz=%d\n", rt.affinity, rt.sched, rt.mlock, rt.dma, rt.ftz);

    /* ---- 실시간 상태 ---- */
    pace_policy_t policy = !strcmp(policy_s, "timeidx") ? PACE_POLICY_TIMEIDX : !strcmp(policy_s, "immediate") ? PACE_POLICY_IMMEDIATE : PACE_POLICY_PROGRESS;
    pace_refbuf_t ref; pace_refbuf_init(&ref, policy); ref.dev_max = cfg.val_dev_max * 2.0f;
    ref.blend_rate = cfg.splice_blend_rate; ref.ext_enable = cfg.ext_enable && policy != PACE_POLICY_TIMEIDX; ref.ext_max_ns = cfg.ext_max_ns; ref.ext_max_rad = cfg.ext_max_rad;
    fprintf(stderr, "[ctl] policy=%s\n", pace_policy_name(policy));
    pace_validator_t val; pace_validator_init(&val); pace_monitor_t mon; pace_monitor_init(&mon);
    stat_t s_wake = {0}, s_exec = {0}, s_val = {0}, s_mon = {0};
    uint64_t metrics_drops = 0, msgs_seen[PACE_SHM_NQUEUES] = {0}, last_valid_chunk_ns = 0, chunk_adopt_count = 0, arrivals_ewma_ns = 100000000ull, arrivals_dev_ns = 20000000ull, last_arrival_ns = 0, ref_exhausted_since = 0;
    float speed_pace = 1.0f;
    /* 기준 경로 모드 상태 */
    double s_play = 0.0; int ref_end = 0; uint64_t transit_ticks = (uint64_t)(transit_s * 1e9 / period_ns);
    pace_msg_t corr; int corr_valid = 0; uint64_t corr_t_recv = 0, corr_seq_last = 0; float corr_cur[3] = {0, 0, 0}, corr_prev[3] = {0, 0, 0}; uint64_t corr_blend_t0 = 0; uint64_t corr_count = 0, corr_rej = 0, corr_ignored = 0;
    float q_ik[PACE_MAX_DOF]; memcpy(q_ik, q_start, sizeof q_ik); float ik_err_pos = 0, ik_err_rot = 0; uint64_t ik_ns_max = 0;
    pace_tick_record_t rec; pace_msg_t msg; pace_contract_t contract; memset(&contract, 0, sizeof contract); uint32_t n_unclean = 0;
    float q_cmd[PACE_MAX_DOF], qd_cmd[PACE_MAX_DOF], q_prev[PACE_MAX_DOF], qd_prev[PACE_MAX_DOF], q_ref[PACE_MAX_DOF], qd_ref[PACE_MAX_DOF];
    memcpy(q_cmd, q0, sizeof q_cmd); memcpy(q_prev, q0, sizeof q_prev); memset(qd_prev, 0, sizeof qd_prev); memset(qd_cmd, 0, sizeof qd_cmd);
    float speed_scale = 1.0f, speed_param = 1.0f; int event_stop = 0; pace_mode_t mode = PACE_MODE_INIT; int stop_sent = 0;
    /* 정지 사다리(시나리오 ④): STOP 판정 → DECEL(램프) → HOLD(정지 후) → ESTOP(판정이 stop_estop_after_ns 넘게 지속). ESTOP 은 체결되면 재개 없음 */
    uint64_t stop_since = 0; int estop_latched = 0; uint16_t stop_level = 0, arc_on = 0; uint64_t arc_off_count = 0, decel_ticks = 0, hold_ticks = 0, estop_ticks = 0;
    /* HAL RT 계약 측정: read/write 실제 소요 vs 백엔드가 선언한 WCET */
    uint64_t hal_read_max = 0, hal_write_max = 0, hal_read_viol = 0, hal_write_viol = 0, reanchor_count = 0;
    /* 로컬 감독 계층(9단계): LOCAL 청크 슬롯 (AI 참조가 바닥났을 때만 채택 = 사다리 ②), 감속 조언 */
    pace_msg_t local_chunk; int local_valid = 0; uint64_t local_seq_adopted = 0, local_adopt_count = 0, local_ticks = 0, local_seen = 0, local_expired = 0;
    float speed_advisor = 1.0f; uint64_t advisor_t = 0, advisor_count = 0;
    float h_force = 0.0f; uint64_t contact_last_ns = 0, contact_ticks = 0; uint16_t arc_power_pct = 100;   /* 접촉 시 스탠드오프 상승, 공정 파라미터 */
    const double dt_s = period_ns * 1e-9, two_pi_f = 2.0 * M_PI * freq; const int self_traj = strcmp(traj, "hold") != 0;
    uint64_t t_start = pace_now_ns() + 2 * period_ns, t_play = t_start;

    for (uint64_t tick = 0; running && tick < total_ticks; ++tick) {
        uint64_t t_sched = t_start + tick * period_ns;
        pace_sleep_until_ns(t_sched);
        uint64_t t_wake = pace_now_ns(), t_prev = t_wake, t;
        memset(&rec, 0, sizeof rec); rec.tick = tick; rec.t_sched_ns = t_sched; rec.t_wake_ns = t_wake; rec.stage_ns[PACE_ST_WAKE] = (uint32_t)(t_wake - t_sched);

        /* ② 상태 읽기 */
        int fault = hal->read(hal, &st);                                   /* read 실패 (백엔드 무응답) */
        int hal_fault = fault || st.hal_fault;                            /* + 백엔드가 보고한 폴트 비트 (드라이브, 통신, ESTOP 체결) */
        if (!fault && kin && !(st.valid & 16) && (st.valid & 1)) { float qt[4], r9[9]; pace_kin_fk(kin, st.q, st.tool_pose, qt, r9); memcpy(st.tool_pose + 3, qt, sizeof qt); st.valid |= 16; }   /* HAL 이 툴 자세를 안 주면(ros2_control 등) 운동학으로 보충 → 작업 영역 감시 유지 */
        t = pace_now_ns(); rec.stage_ns[PACE_ST_READ] = (uint32_t)(t - t_prev); t_prev = t;
        if (rec.stage_ns[PACE_ST_READ] > hal_read_max) hal_read_max = rec.stage_ns[PACE_ST_READ]; if (lim->read_wcet_ns && rec.stage_ns[PACE_ST_READ] > lim->read_wcet_ns) hal_read_viol++;

        /* ③④ 큐 폴링 + 검증 (모든 큐, 모든 메시지. PATH 는 마지막 통과분을 채택) */
        pace_reject_t last_rej = PACE_REJ_NONE; pace_robot_state_t st_val = st; if (policy == PACE_POLICY_PROGRESS) st_val.valid &= ~1u;   /* 투영 정책: 거리 판정은 접합기가 */
        for (unsigned q = 0; q < PACE_SHM_NQUEUES; ++q) {
            while (pace_spsc_pop(shm.queue[q], &msg)) {
                msgs_seen[q]++;
                pace_reject_t rj = pace_validate(&val, &cfg, &msg, &st_val, lim, t_wake, ref.valid ? t_play : 0);
                if (rj != PACE_REJ_NONE) { last_rej = rj; continue; }
                if ((msg.hdr.type == PACE_MSG_PATH || msg.hdr.type == PACE_MSG_PATH_S) && msg.hdr.supplier == PACE_SUPPLIER_LOCAL) {
                    if (cfg.local_enable) { local_chunk = msg; local_valid = 1; local_seen++; }      /* 슬롯에만 보관. 채택은 AI 참조가 바닥났을 때 */
                } else if (msg.hdr.type == PACE_MSG_PATH || msg.hdr.type == PACE_MSG_PATH_S) {
                    if (!pace_refbuf_adopt(&ref, &msg, tick, t_wake, t_play, q_prev, (st.valid & 1) ? st.q : NULL)) { last_rej = PACE_REJ_NO_OVERLAP; val.rejected++; val.accepted--; val.reject_count[PACE_REJ_NO_OVERLAP]++; continue; }
                    chunk_adopt_count++;
                    if (last_arrival_ns) { uint64_t ia = t_wake - last_arrival_ns; uint64_t dev = ia > arrivals_ewma_ns ? ia - arrivals_ewma_ns : arrivals_ewma_ns - ia; arrivals_ewma_ns = (arrivals_ewma_ns * 7 + ia) / 8; arrivals_dev_ns = (arrivals_dev_ns * 7 + dev) / 8; }
                    last_arrival_ns = t_wake; last_valid_chunk_ns = t_wake;
                } else if (msg.hdr.type == PACE_MSG_CORRECTION && refmode) {
                    if (mon.verdict == PACE_MON_STOP) { corr_ignored++; continue; }   /* 정지 중엔 목표를 움직이지 않는다 (보정은 버림, 복귀 후 새 보정부터) */
                    /* 보정 검증: 범위, 순서, 직전 보정 대비 점프. 통과 시 블렌딩 시작 */
                    const pace_correction_t *c = &msg.body.correction; uint16_t n = msg.hdr.n_points; const float *v = c->pts[n ? n - 1 : 0];   /* 마지막(최신) 샘플 */
                    pace_reject_t cr = PACE_REJ_NONE;
                    if (n == 0 || !(fabsf(v[0]) <= cfg.corr_lat_max) || !(fabsf(v[1]) <= cfg.corr_h_max) || !(fabsf(v[2]) <= cfg.corr_ang_max)) cr = PACE_REJ_RANGE_POS;
                    else if (corr_seq_last && msg.hdr.seq <= corr_seq_last) cr = PACE_REJ_SEQ_ORDER;
                    else if (fabsf(v[0] - corr_cur[0]) > cfg.corr_jump_max || fabsf(v[1] - corr_cur[1]) > cfg.corr_jump_max) cr = PACE_REJ_DEVIATION;   /* 첫 보정도 0 기준으로 점프 제한 */
                    if (cr != PACE_REJ_NONE) { last_rej = cr; corr_rej++; val.rejected++; val.accepted--; val.reject_count[cr]++; continue; }
                    memcpy(corr_prev, corr_cur, sizeof corr_prev); corr = msg; corr_valid = 1; corr_t_recv = t_wake; corr_seq_last = msg.hdr.seq; corr_blend_t0 = t_wake; corr_count++;
                    for (int kq = 0; kq < 3; ++kq) corr_cur[kq] = v[kq];
                } else if (msg.hdr.type == PACE_MSG_PARAM && msg.hdr.supplier == PACE_SUPPLIER_LOCAL) {
                    if (cfg.local_enable) { speed_advisor = msg.body.param.speed_scale < 0.1f ? 0.1f : msg.body.param.speed_scale > 1.0f ? 1.0f : msg.body.param.speed_scale; advisor_t = t_wake; advisor_count++; }   /* 감속 조언기: 제안은 상한으로만 작용 */
                } else if (msg.hdr.type == PACE_MSG_PARAM) {
                    if (msg.body.param.speed_scale >= 0) speed_param = msg.body.param.speed_scale > 1.5f ? 1.5f : msg.body.param.speed_scale;   /* 음수 = 속도 변경 없음 */
                    if (msg.body.param.n_params >= 1) { float ap = msg.body.param.params[0]; arc_power_pct = (uint16_t)(ap < 0 ? 0 : ap > 1 ? 100 : ap * 100.0f + 0.5f); }   /* params[0] = 아크 출력 비율 (공정 상태 추론기) */
                } else if (msg.hdr.type == PACE_MSG_EVENT) {
                    if (msg.body.event.code == PACE_EVT_ESTOP || msg.body.event.code == PACE_EVT_DEFECT || msg.body.event.code == PACE_EVT_PAUSE) event_stop = 1;
                    else if (msg.body.event.code == PACE_EVT_RESUME) event_stop = 0;
                }
            }
        }
        t = pace_now_ns(); rec.stage_ns[PACE_ST_SELECT] = 0; rec.stage_ns[PACE_ST_VALIDATE] = (uint32_t)(t - t_prev); t_prev = t;

        /* ⑤ 참조 평가 */
        if (!self_traj) t_play = t_wake;
        uint16_t rdof = dof; int have_ref = 0;
        if (refmode) {
            /* 기준 경로 모드: (접근) 홈 → 시작 자세 코사인 블렌딩, 그 후 s 재생 + 보정 + IK */
            if (tick < transit_ticks) {
                double a = 0.5 - 0.5 * cos(M_PI * (double)tick / (double)transit_ticks);
                for (int j = 0; j < dof; ++j) { q_ref[j] = (float)(q0[j] + a * (q_start[j] - q0[j])); qd_ref[j] = 0; }
                have_ref = 1;
            } else {
                float p[3], tv[3], nv[3], R[9]; ref_end = pace_refpath_eval(&rp, (float)s_play, p, tv, nv);
                /* 보정 적용 (블렌딩: 이전 값 → 새 값 코사인) */
                float lat = corr_cur[0], h = corr_cur[1];
                if (corr_valid && cfg.corr_blend_ns) { double tau = (double)(t_wake - corr_blend_t0) / (double)cfg.corr_blend_ns; if (tau < 1.0) { float w = (float)(0.5 + 0.5 * cos(M_PI * tau)); lat = corr_cur[0] + w * (corr_prev[0] - corr_cur[0]); h = corr_cur[1] + w * (corr_prev[1] - corr_cur[1]); } }
                /* 접촉력 → 스탠드오프 상승 (센서 기반 경로 조정): 접촉 중이면 lift 까지 올리고, 해제 뒤 hold 시간 지나면 내린다 (200ms 램프) */
                { int contact = (st.valid & 32) && st.tool_force > cfg.mon_force_slow; if (contact) { contact_last_ns = t_wake; contact_ticks++; }
                  float h_tgt = (contact || (contact_last_ns && t_wake - contact_last_ns < cfg.corr_force_hold_ns)) ? cfg.corr_force_lift : 0.0f;
                  float hstep = cfg.corr_force_lift * (float)dt_s / 0.2f; h_force += fmaxf(-hstep, fminf(hstep, h_tgt - h_force)); }
                for (int kq = 0; kq < 3; ++kq) p[kq] += lat * nv[kq]; p[2] += rp.standoff + h + h_force;
                pace_kin_tool_rotation(tv, rp.travel_angle, R);
                uint64_t ik0 = pace_now_ns(); pace_kin_ik(kin, q_ik, p, R, (int)cfg.ik_iters, 1e-6f, q_ik, &ik_err_pos, &ik_err_rot); uint64_t ikd = pace_now_ns() - ik0; if (ikd > ik_ns_max) ik_ns_max = ikd;
                for (int j = 0; j < dof; ++j) { qd_ref[j] = (q_ik[j] - q_ref[j]) / (float)dt_s; q_ref[j] = q_ik[j]; }
                have_ref = !ref_end;
                if (ref_end || mode == PACE_MODE_STOPPED) { memcpy(q_ref, q_prev, sizeof q_ref); memset(qd_ref, 0, sizeof qd_ref); }   /* 경로 끝 또는 정지 중: 목표 동결 (복귀는 RECOVER 전이 뒤 다음 틱부터) */
            }
        } else if (self_traj) {                                              /* 공급자 없는 자체 테스트 궤적 */
            double tt = (double)(tick * period_ns) * 1e-9;
            for (int j = 0; j < dof; ++j) { double a = amp * (j % 2 == 0 ? 1.0 : 0.5), ph = 0.7 * j; q_ref[j] = (float)(q0[j] + a * sin(two_pi_f * tt + ph)); qd_ref[j] = (float)(a * two_pi_f * cos(two_pi_f * tt + ph)); }
            have_ref = 1;
        } else {
            pace_refbuf_tick(&ref, t_play, period_ns, policy == PACE_POLICY_TIMEIDX ? 1.0f : speed_scale);   /* 페이싱: 투영·즉시 정책은 재생 속도로, 시간 인덱스는 불가 */
            /* 사다리 ②: AI 참조가 바닥났으면(또는 LOCAL 재생이 끝나가면) 로컬 연속 정책 청크로 접합. 마지막 AI 청크 뒤 local_max_ns 까지만 */
            if (cfg.local_enable && local_valid && ref.valid && policy != PACE_POLICY_TIMEIDX) {
                int ai_playing = ref.chunk.hdr.supplier != PACE_SUPPLIER_LOCAL; uint64_t remain = pace_refbuf_remaining_ns(&ref, t_play);
                uint64_t since_ai = last_arrival_ns ? t_wake - last_arrival_ns : 0;
                int want = ai_playing ? (remain == 0) : (remain < cfg.local_resplice_ns);
                if (want && local_chunk.hdr.seq != local_seq_adopted) {
                    if (since_ai > cfg.local_max_ns || t_wake > local_chunk.hdr.t_valid_until_ns) local_expired++;
                    else if (pace_refbuf_adopt(&ref, &local_chunk, tick, t_wake, t_play, q_prev, (st.valid & 1) ? st.q : NULL)) { local_seq_adopted = local_chunk.hdr.seq; local_adopt_count++; }
                }
            }
            if (pace_refbuf_eval(&ref, t_play, t_wake, q_ref, qd_ref, &rdof)) { have_ref = 1; if (ref.chunk.hdr.supplier == PACE_SUPPLIER_LOCAL) local_ticks++; }
            else { memcpy(q_ref, q_prev, sizeof q_ref); memset(qd_ref, 0, sizeof qd_ref); }   /* 참조 없음: 현재 명령 유지 */
        }
        t = pace_now_ns(); rec.stage_ns[PACE_ST_SPLICE] = (uint32_t)(t - t_prev); t_prev = t;

        /* ⑧ 상태 감시기 (명령 생성 전에 판정 → 이번 틱 속도에 반영) */
        { int exhausted = !self_traj && !refmode && ref.valid && pace_refbuf_remaining_ns(&ref, t_play) == 0 && (!ref.ext_active || ref.ext_capped);
          if (exhausted) { if (!ref_exhausted_since) ref_exhausted_since = t_wake; } else ref_exhausted_since = 0; }
        uint64_t eye_age = (refmode && corr_valid) ? t_wake - corr_t_recv : 0;
        pace_monitor_verdict_t verdict = pace_monitor_step(&mon, &cfg, &st, lim, &ref, t_play, t_wake, (self_traj || refmode) ? t_wake : last_valid_chunk_ns, q_prev, hal_fault, event_stop, ref_exhausted_since, eye_age, cfg.corr_stale_slow_ns);
        t = pace_now_ns(); rec.stage_ns[PACE_ST_MONITOR] = (uint32_t)(t - t_prev); t_prev = t;

        /* ⑥ 속도 배율: 목표 = min(PARAM, 감시기) 로 램프 (저크 제한 감속의 자리) */
        /* 버퍼 여유 기반 페이싱: 남은 참조가 "다음 청크 예상 도착 + 여유" 까지 버티도록 재생 속도를 낮춘다 (시간 인덱스는 불가) */
        speed_pace = 1.0f;
        if (cfg.pace_enable && policy != PACE_POLICY_TIMEIDX && ref.valid && last_arrival_ns) {
            double t_rem = pace_refbuf_remaining_ns(&ref, t_play) * 1e-9;
            double since = (t_wake - last_arrival_ns) * 1e-9, ia = arrivals_ewma_ns * 1e-9 + cfg.pace_jitter_k * arrivals_dev_ns * 1e-9;
            double t_exp = ia > since ? ia - since : since - ia;                       /* 다음 청크까지 예상 시간. 기한을 넘기면 '이미 기다린 만큼 더' (보수적) */
            double need = t_exp + cfg.pace_margin_target_ns * 1e-9;
            if (need > 1e-3) { double v = t_rem / need; speed_pace = (float)(v > 1.0 ? 1.0 : v < cfg.pace_vmin ? cfg.pace_vmin : v); }
        }
        int local_playing = !refmode && ref.valid && ref.chunk.hdr.supplier == PACE_SUPPLIER_LOCAL;
        if (local_playing) speed_pace = cfg.local_speed;                                  /* LOCAL 재생 중엔 AI 도착 기반 페이싱 대신 로컬 상한 */
        float target = verdict == PACE_MON_STOP ? 0.0f : speed_param;
        if (advisor_t && t_wake - advisor_t < cfg.advisor_stale_ns) target = fminf(target, speed_advisor);   /* 감속 조언기 제안 (상한) */
        if (refmode) { if (verdict == PACE_MON_SLOW) target = fminf(target, cfg.mon_slow_scale); }
        else if (policy != PACE_POLICY_TIMEIDX) { target = fminf(target, speed_pace); if (!cfg.pace_enable && verdict == PACE_MON_SLOW) target = fminf(target, cfg.mon_slow_scale); }
        float step = cfg.cmd_speed_ramp_per_s * (float)dt_s;
        speed_scale += fmaxf(-step, fminf(step, target - speed_scale));
        if (refmode && tick >= transit_ticks && !ref_end) s_play += rp.sdot_nominal * dt_s * speed_scale;   /* 진행도 전진 = 페이싱 (툴 공간) */
        /* 4단계 기준선(시간 인덱스): 재생 시각 = 벽시계. 페이싱 불가 → SLOW 는 기록만. 5단계 진행도 접합에서 t_play 가 진행도로 바뀐다 */
        rec.stage_ns[PACE_ST_PACE] = 0;

        /* ⑦ 명령 생성: 참조를 속도·가속도 한계로 변화율 제한 (저크 제한 간이판) */
        for (int j = 0; j < dof; ++j) {
            float v_des = (q_ref[j] - q_prev[j]) / (float)dt_s;                              /* 이번 틱에 필요한 속도 */
            float vcap = (verdict == PACE_MON_STOP) ? fmaxf(speed_scale, 0.0f) : (refmode && speed_scale < 0.999f) ? fmaxf(speed_scale, 0.05f) : 1.0f;   /* 속도 한계 축소는 정지 램프와 (기준 경로 모드의) 복귀 램프에만. 관절별 캡으로 페이싱하면 경로가 뒤틀린다 → 시간 인덱스는 속도 지령을 무시(기록만) */
            float v_max = lim->qd_max[j] * cfg.cmd_qd_frac * vcap, a_max = lim->qdd_max[j] * cfg.cmd_qdd_frac * (float)dt_s;
            float v = fmaxf(-v_max, fminf(v_max, v_des)); v = fmaxf(qd_prev[j] - a_max, fminf(qd_prev[j] + a_max, v));
            q_cmd[j] = q_prev[j] + v * (float)dt_s; qd_cmd[j] = v;
        }
        t = pace_now_ns(); rec.stage_ns[PACE_ST_COMMAND] = (uint32_t)(t - t_prev); t_prev = t;

        /* 모드 */
        int moving = 0; for (int j = 0; j < dof; ++j) if (fabsf(qd_cmd[j]) > 1e-3f) moving = 1;   /* 정지 판정: 관절 속도 명령 1 mrad/s 미만 */
        if (refmode && verdict != PACE_MON_STOP && tick < transit_ticks) mode = PACE_MODE_RECOVER;
        else if (refmode && verdict != PACE_MON_STOP && ref_end) mode = PACE_MODE_HOLD;
        else if (verdict == PACE_MON_STOP && !moving) mode = PACE_MODE_STOPPED;
        else if (verdict == PACE_MON_STOP) mode = PACE_MODE_HOLD;                       /* 정지 램프 중 */
        else if (!have_ref || ref_exhausted_since) mode = PACE_MODE_HOLD;               /* 참조 바닥 → 유지 (t_dead 뒤 정지) */
        else if (ref.ext_active) mode = PACE_MODE_EXTRAP;
        else if (local_playing) mode = PACE_MODE_LOCAL;
        else if (speed_pace < 0.999f) mode = PACE_MODE_PACING;
        else if (speed_scale < target - 1e-3f) mode = PACE_MODE_RECOVER;
        else mode = PACE_MODE_NORMAL;

        /* 정지 사다리 상태 */
        if (verdict == PACE_MON_STOP) { if (!stop_since && (refmode || last_valid_chunk_ns)) stop_since = t_wake; } else stop_since = 0;   /* 작업 시작 전(첫 청크 대기, BLIND) 은 비상 정지 카운트 대상이 아니다 */
        if (stop_since && t_wake - stop_since > cfg.stop_estop_after_ns && !estop_latched) { estop_latched = 1; fprintf(stderr, "[ctl] ESTOP latched at tick %llu (STOP persisted %.1fs, trig=0x%x)\n", (unsigned long long)tick, (t_wake - stop_since) * 1e-9, mon.triggers); }
        if (estop_latched) { mode = PACE_MODE_STOPPED; mon.triggers |= PACE_TRIG_ESTOP_LATCH; }
        stop_level = estop_latched ? PACE_STOP_ESTOP : mode == PACE_MODE_STOPPED ? PACE_STOP_HOLD : verdict == PACE_MON_STOP ? PACE_STOP_DECEL : 0;
        /* 공정 출력(아크): 용접 구간에서 정지 판정이 없을 때만 ON. 정지 램프 시작과 동시에 OFF (용접 규칙: 멈추면서 아크를 켜두지 않는다) */
        { uint16_t want_arc = refmode ? (tick >= transit_ticks && !ref_end && verdict != PACE_MON_STOP && !estop_latched) : (have_ref && verdict != PACE_MON_STOP && !estop_latched && mode != PACE_MODE_HOLD && mode != PACE_MODE_STOPPED);
          if (arc_on && !want_arc) arc_off_count++; arc_on = want_arc; }
        if (stop_level == PACE_STOP_DECEL) decel_ticks++; else if (stop_level == PACE_STOP_HOLD) hold_ticks++; else if (stop_level == PACE_STOP_ESTOP) estop_ticks++;

        /* ⑨ HAL write (정지 단계는 HAL 공통 의미: DECEL = 램프 위치 명령, HOLD = 위치 유지, ESTOP = 브레이크 체결) */
        if (!fault) {
            if (estop_latched) hal->stop(hal, tick + 1, PACE_STOP_ESTOP);                                  /* 매 틱 반복 (락스텝 백엔드가 멈추지 않도록, 의미는 멱등) */
            else if (mode == PACE_MODE_STOPPED) { hal->stop(hal, tick + 1, PACE_STOP_HOLD); stop_sent = 1; }   /* 유지도 매 틱 반복: 백엔드 의미는 '현재 위치 유지' (멱등) */
            else { hal->write(hal, tick + 1, mode, q_cmd, qd_cmd, dof); stop_sent = 0; }
        }
        t = pace_now_ns(); rec.stage_ns[PACE_ST_WRITE] = (uint32_t)(t - t_prev); t_prev = t;
        if (rec.stage_ns[PACE_ST_WRITE] > hal_write_max) hal_write_max = rec.stage_ns[PACE_ST_WRITE]; if (lim->write_wcet_ns && rec.stage_ns[PACE_ST_WRITE] > lim->write_wcet_ns) hal_write_viol++;

        /* ⑩ 계측 */
        rec.mode = mode; rec.supplier = ref.valid ? ref.chunk.hdr.supplier : PACE_SUPPLIER_UNKNOWN; rec.reject = last_rej; rec.monitor = verdict; rec.triggers = mon.triggers; rec.stop_level = stop_level; rec.arc_on = arc_on; rec.arc_power_pct = arc_on ? arc_power_pct : 0; rec.tool_force_cN = (uint16_t)((st.valid & 32) ? fminf(st.tool_force, 600.0f) * 100.0f : 0);
        rec.chunk_seq = ref.valid ? ref.chunk.hdr.seq : 0; rec.chunk_t_gen_ns = ref.valid ? ref.chunk.hdr.t_gen_ns : 0;
        rec.speed_scale = speed_scale; rec.progress_s = refmode ? (float)s_play : policy == PACE_POLICY_TIMEIDX ? (float)((double)(t_play - t_start) * 1e-9) : (float)(ref.valid && ref.chunk.hdr.type == PACE_MSG_PATH_S ? ref.s_play : ref.idx_play);
        { uint64_t remain = pace_refbuf_remaining_ns(&ref, t_play); double since = last_arrival_ns ? (double)(t_wake - last_arrival_ns) : 0.0, ia = (double)arrivals_ewma_ns + cfg.pace_jitter_k * (double)arrivals_dev_ns; double expect = ia > since ? ia - since : 0.0; rec.buffer_margin_ms = (float)(((double)remain - expect) * 1e-6); rec.deviation = refmode ? corr_cur[0] : ref.last_proj_dist; }
        pace_shm_write_state(&shm, &st);
        if (!(mode == PACE_MODE_NORMAL && rec.supplier == PACE_SUPPLIER_AI && verdict == PACE_MON_OK && stop_level == 0 && last_rej == PACE_REJ_NONE)) n_unclean++;
        if ((tick % 10) == 0) {   /* 10 ms 마다 (seqlock 72 B 복사) — 실행 상태 필드는 온라인 학습의 라벨 거름망용 */
            contract.progress_s = rec.progress_s; contract.speed_scale = speed_scale; contract.buffer_margin_ns = (int64_t)(rec.buffer_margin_ms * 1e6); contract.next_deadline_ns = t_play + pace_refbuf_remaining_ns(&ref, t_play);
            contract.t_ns = t_wake; contract.mode = (uint16_t)mode; contract.supplier = rec.supplier; contract.monitor = (uint16_t)verdict; contract.stop_level = stop_level; contract.n_reject = (uint32_t)val.rejected; contract.n_unclean = n_unclean;
            pace_shm_write_contract(&shm, &contract);
        }
        if (trace) { trace_t *tr = &trace[tick]; tr->t_ns = t_sched; memcpy(tr->q_cmd, q_cmd, sizeof tr->q_cmd); memcpy(tr->q_meas, st.q, sizeof tr->q_meas); memcpy(tr->tool, st.tool_pose, sizeof tr->tool); tr->speed = speed_scale; tr->mode = mode; tr->monitor = verdict; }
        t = pace_now_ns(); rec.stage_ns[PACE_ST_LOG] = (uint32_t)(t - t_prev);
        if (!pace_shm_push_record(&shm, &rec)) metrics_drops++;
        { int displaced = 0; if (mode == PACE_MODE_STOPPED && (st.valid & 1)) for (int j = 0; j < dof; ++j) if (fabsf(st.q[j] - q_cmd[j]) > 0.5f * cfg.mon_track_err_max) displaced = 1;
          if (displaced) { memcpy(q_prev, st.q, sizeof q_prev); memcpy(q_cmd, st.q, sizeof q_cmd); memset(qd_prev, 0, sizeof qd_prev); reanchor_count++; }   /* 정지 중 로봇이 밀려났으면 명령을 실측 위치에 재고정 (사다리 ⑤: 복귀는 실측 위치에서 시작) */
          else { memcpy(q_prev, q_cmd, sizeof q_prev); memcpy(qd_prev, qd_cmd, sizeof qd_prev); } }
        stat_add(&s_wake, t_wake - t_sched); stat_add(&s_exec, t - t_wake); stat_add(&s_val, rec.stage_ns[PACE_ST_VALIDATE]); stat_add(&s_mon, rec.stage_ns[PACE_ST_MONITOR]);
        if (verbose && (tick % 1000) == 0) fprintf(stderr, "[ctl] t=%llus mode=%d verdict=%d trig=0x%x speed=%.2f chunk=%llu acc=%llu rej=%llu margin=%.0fms\n", (unsigned long long)(tick / 1000), mode, verdict, mon.triggers, speed_scale, (unsigned long long)rec.chunk_seq, (unsigned long long)val.accepted, (unsigned long long)val.rejected, rec.buffer_margin_ms);
    }

    hal->stop(hal, total_ticks + 1, estop_latched ? PACE_STOP_ESTOP : PACE_STOP_HOLD);
    pace_rt_teardown(&rt);
    if (trace) { write_trace_npz(trace_path, trace, total_ticks, dof); free(trace); }
    printf("{\"kernel\":\"%s\",\"policy\":\"%s\",\"cpu\":%d,\"prio\":%d,\"ticks\":%llu,\"splices\":%llu,\"no_overlap\":%llu,", no_rt ? "no-rt" : "rt", pace_policy_name(policy), cpu, prio, (unsigned long long)s_wake.n, (unsigned long long)ref.splices, (unsigned long long)ref.no_overlap);
    stat_json("wake_latency", &s_wake, stdout); printf(","); stat_json("loop_exec", &s_exec, stdout); printf(","); stat_json("validate", &s_val, stdout); printf(","); stat_json("monitor", &s_mon, stdout); printf(",");
    printf("\"hal\":{\"name\":\"%s\",\"dof\":%u,\"read_max_us\":%.1f,\"write_max_us\":%.1f,\"read_wcet_us\":%.1f,\"write_wcet_us\":%.1f,\"read_viol\":%llu,\"write_viol\":%llu,\"backend_lag_ticks\":%llu},", hal->name, lim->dof, hal_read_max / 1e3, hal_write_max / 1e3, lim->read_wcet_ns / 1e3, lim->write_wcet_ns / 1e3, (unsigned long long)hal_read_viol, (unsigned long long)hal_write_viol, (unsigned long long)hal->backend_lag_ticks(hal));
    printf("\"local\":{\"enabled\":%u,\"chunks_seen\":%llu,\"adopted\":%llu,\"expired\":%llu,\"ticks\":%llu,\"advisor_msgs\":%llu},", cfg.local_enable, (unsigned long long)local_seen, (unsigned long long)local_adopt_count, (unsigned long long)local_expired, (unsigned long long)local_ticks, (unsigned long long)advisor_count);
    printf("\"stop_ladder\":{\"decel_ticks\":%llu,\"hold_ticks\":%llu,\"estop_ticks\":%llu,\"estop_latched\":%d,\"arc_off_events\":%llu,\"reanchor_ticks\":%llu,\"contact_ticks\":%llu},", (unsigned long long)decel_ticks, (unsigned long long)hold_ticks, (unsigned long long)estop_ticks, estop_latched, (unsigned long long)arc_off_count, (unsigned long long)reanchor_count, (unsigned long long)contact_ticks);
    if (refmode) printf("\"refpath\":{\"corrections\":%llu,\"corr_rejected\":%llu,\"corr_ignored_stop\":%llu,\"ik_max_us\":%.1f,\"ik_err_pos_mm\":%.3f,\"s_end\":%.4f},", (unsigned long long)corr_count, (unsigned long long)corr_rej, (unsigned long long)corr_ignored, ik_ns_max / 1e3, ik_err_pos * 1e3f, s_play);
    printf("\"extrapolations\":%llu,\"chunks_adopted\":%llu,\"validator\":{\"accepted\":%llu,\"rejected\":%llu,\"by_reason\":{", (unsigned long long)ref.ext_count, (unsigned long long)chunk_adopt_count, (unsigned long long)val.accepted, (unsigned long long)val.rejected);
    int first = 1; for (int k = 1; k < 12; ++k) if (val.reject_count[k]) { printf("%s\"%s\":%llu", first ? "" : ",", pace_reject_name(k), (unsigned long long)val.reject_count[k]); first = 0; }
    printf("}},\"monitor_stop_ticks\":%llu,\"monitor_slow_ticks\":%llu,\"metrics_drops\":%llu,\"msgs_seen\":[%llu,%llu,%llu,%llu]}\n",
           (unsigned long long)mon.stop_count, (unsigned long long)mon.slow_count, (unsigned long long)metrics_drops, (unsigned long long)msgs_seen[0], (unsigned long long)msgs_seen[1], (unsigned long long)msgs_seen[2], (unsigned long long)msgs_seen[3]);
    fflush(stdout);                                   /* 요약은 백엔드 종료 전에 확정 (종료 중 크래시로 잃지 않도록) */
    hal->shutdown(hal); pace_shm_close(&shm);
    return 0;
}
