#include "pace/monitor.h"
#include <math.h>
#include <string.h>

void pace_monitor_init(pace_monitor_t *m) { memset(m, 0, sizeof *m); m->verdict = PACE_MON_OK; m->pending = PACE_MON_OK; }

pace_monitor_verdict_t pace_monitor_step(pace_monitor_t *m, const pace_config_t *cfg, const pace_robot_state_t *st, const pace_hal_limits_t *lim,
                                         const pace_refbuf_t *ref, uint64_t t_play_ns, uint64_t now_ns, uint64_t last_valid_chunk_ns,
                                         const float *q_cmd_prev, int hal_fault, int event_stop, uint64_t ref_exhausted_since_ns, uint64_t eye_age_ns, uint64_t eye_stale_ns)
{
    uint32_t trig = 0; uint16_t d = lim->dof; float f = cfg->mon_limit_frac;
    if (hal_fault) trig |= PACE_TRIG_HAL_FAULT;
    if (event_stop) trig |= PACE_TRIG_EVENT;
    /* 실측 한계 */
    for (uint16_t j = 0; j < d; ++j) {
        float span = lim->q_max[j] - lim->q_min[j], c = 0.5f * (lim->q_max[j] + lim->q_min[j]);
        if (fabsf(st->q[j] - c) > f * 0.5f * span) trig |= PACE_TRIG_JOINT_LIMIT;
        if ((st->valid & 2) && fabsf(st->qd[j]) > f * lim->qd_max[j]) trig |= PACE_TRIG_VEL_LIMIT;
    }
    /* 작업 영역 (툴 위치) */
    if (st->valid & 16) for (int k = 0; k < 3; ++k) if (st->tool_pose[k] < lim->workspace_min[k] || st->tool_pose[k] > lim->workspace_max[k]) trig |= PACE_TRIG_WORKSPACE;
    /* 추종 오차 */
    if (q_cmd_prev && (st->valid & 1)) for (uint16_t j = 0; j < d; ++j) if (fabsf(st->q[j] - q_cmd_prev[j]) > cfg->mon_track_err_max) trig |= PACE_TRIG_TRACK_ERR;
    /* 룩어헤드: 앞으로 재생될 명령이 한계에 닿는가 */
    if (ref->valid) {
        float q[PACE_MAX_DOF], qd[PACE_MAX_DOF]; uint16_t dd;
        for (uint32_t k = 1; k <= cfg->mon_lookahead_steps; ++k) {
            if (!pace_refbuf_eval_ahead(ref, t_play_ns, k * cfg->mon_lookahead_dt_ns, q, qd, &dd)) break;
            for (uint16_t j = 0; j < dd; ++j) {
                float span = lim->q_max[j] - lim->q_min[j], c = 0.5f * (lim->q_max[j] + lim->q_min[j]);
                if (fabsf(q[j] - c) > f * 0.5f * span) trig |= PACE_TRIG_JOINT_LIMIT;
                if (fabsf(qd[j]) > f * lim->qd_max[j]) trig |= PACE_TRIG_VEL_LIMIT;
            }
        }
        if (pace_refbuf_remaining_ns(ref, t_play_ns) < cfg->mon_buffer_low_ns) trig |= PACE_TRIG_BUFFER_LOW;
    }
    /* 맹목: 처음부터 청크가 없거나, 참조(외삽 포함)가 바닥난 채 t_dead 경과 (사다리: 유지 → 정지) */
    if (last_valid_chunk_ns == 0 || (ref_exhausted_since_ns && now_ns - ref_exhausted_since_ns > cfg->mon_t_dead_ns)) trig |= PACE_TRIG_BLIND;

    if (eye_age_ns && eye_stale_ns && eye_age_ns > eye_stale_ns) trig |= PACE_TRIG_EYE_STALE;
    /* 접촉력: 감속 문턱 → SLOW, 정지 문턱 → STOP (센서 기반 이동속도 조정) */
    if ((st->valid & 32) && st->tool_force > cfg->mon_force_slow) trig |= PACE_TRIG_CONTACT;
    if ((st->valid & 32) && st->tool_force > cfg->mon_force_stop) trig |= PACE_TRIG_WORKSPACE;   /* 과도 접촉 = 작업 영역 위반과 같은 등급으로 정지 */
    const uint32_t STOP_MASK = PACE_TRIG_JOINT_LIMIT | PACE_TRIG_VEL_LIMIT | PACE_TRIG_ACC_LIMIT | PACE_TRIG_WORKSPACE | PACE_TRIG_DEVIATION |
                               PACE_TRIG_TRACK_ERR | PACE_TRIG_EXTRAP_CAP | PACE_TRIG_HAL_FAULT | PACE_TRIG_BLIND | PACE_TRIG_EVENT;
    pace_monitor_verdict_t want = (trig & STOP_MASK) ? PACE_MON_STOP : (trig & (PACE_TRIG_BUFFER_LOW | PACE_TRIG_EYE_STALE | PACE_TRIG_CONTACT)) ? PACE_MON_SLOW : PACE_MON_OK;
    /* 히스테리시스: 더 안전한 쪽(STOP)으로는 즉시, 덜 안전한 쪽으로는 N틱 유지 후 */
    if (want >= m->verdict) { m->verdict = want; m->pending = want; m->pending_ticks = 0; }
    else { if (m->pending != want) { m->pending = want; m->pending_ticks = 0; } if (++m->pending_ticks >= cfg->mon_hysteresis_ticks) { m->verdict = want; m->pending_ticks = 0; } }
    m->triggers = trig;
    if (m->verdict == PACE_MON_STOP) m->stop_count++; else if (m->verdict == PACE_MON_SLOW) m->slow_count++;
    return m->verdict;
}
