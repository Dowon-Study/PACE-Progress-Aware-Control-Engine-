#include "pace/validator.h"
#include <math.h>
#include <string.h>

void pace_validator_init(pace_validator_t *v) { memset(v, 0, sizeof *v); }

static const char *names[] = { "NONE", "HEADER", "RANGE_POS", "RANGE_VEL", "RANGE_ACC", "WORKSPACE", "EXPIRED", "SEQ_ORDER", "TOO_OLD", "DEVIATION", "CONFIDENCE", "NO_OVERLAP" };
const char *pace_reject_name(pace_reject_t r) { return (unsigned)r < sizeof names / sizeof *names ? names[r] : "?"; }

static pace_reject_t check(const pace_validator_t *v, const pace_config_t *cfg, const pace_msg_t *m,
                           const pace_robot_state_t *st, const pace_hal_limits_t *lim, uint64_t now_ns, uint64_t t_eval_ns)
{
    /* 0) 헤더 */
    if (!pace_msg_valid_header(m)) return PACE_REJ_HEADER;
    if (m->hdr.type != PACE_MSG_PATH && m->hdr.type != PACE_MSG_PATH_S) return PACE_REJ_NONE;   /* PARAM/EVENT/CONTRACT 는 헤더만 */
    int is_s = m->hdr.type == PACE_MSG_PATH_S;
    if (m->hdr.space != PACE_SPACE_JOINT || m->hdr.n_points < 2 || m->hdr.dof == 0 || m->hdr.dof != lim->dof) return PACE_REJ_HEADER;
    uint16_t n = m->hdr.n_points, d = m->hdr.dof;
    const float (*pts)[PACE_MAX_DOF] = is_s ? m->body.path_s.pts : m->body.path.pts;
    float dt;
    if (is_s) {
        if (!(m->body.path_s.s1 > m->body.path_s.s0) || !(m->body.path_s.sdot_nominal > 1e-6f)) return PACE_REJ_HEADER;
        dt = (m->body.path_s.s1 - m->body.path_s.s0) / (float)(n - 1) / m->body.path_s.sdot_nominal;
        if (dt * 1e9f < (float)cfg->val_dt_min_ns || dt * 1e9f > (float)cfg->val_dt_max_ns) return PACE_REJ_HEADER;
    } else {
        const pace_path_t *p = &m->body.path;
        if (p->dt_ns < cfg->val_dt_min_ns || p->dt_ns > cfg->val_dt_max_ns) return PACE_REJ_HEADER;
        dt = (float)p->dt_ns * 1e-9f;
    }

    /* 1) 범위: 위치 한계(여유), 인접 차분 속도, 2차 차분 가속도. NaN 도 여기서 걸린다 */
    for (uint16_t i = 0; i < n; ++i)
        for (uint16_t j = 0; j < d; ++j) {
            float q = pts[i][j];
            if (!(q >= lim->q_min[j] + cfg->val_limit_margin && q <= lim->q_max[j] - cfg->val_limit_margin)) return PACE_REJ_RANGE_POS;
        }
    for (uint16_t i = 1; i < n; ++i)
        for (uint16_t j = 0; j < d; ++j) {
            float v = (pts[i][j] - pts[i - 1][j]) / dt;
            if (!(fabsf(v) <= lim->qd_max[j])) return PACE_REJ_RANGE_VEL;
            if (i >= 2) { float a = (pts[i][j] - 2 * pts[i - 1][j] + pts[i - 2][j]) / (dt * dt); if (!(fabsf(a) <= lim->qdd_max[j])) return PACE_REJ_RANGE_ACC; }
        }

    /* 2) 시간 */
    if (pace_msg_expired(m, now_ns)) return PACE_REJ_EXPIRED;
    unsigned sup = m->hdr.supplier < 8 ? m->hdr.supplier : 0;
    if (v->last_seq[sup] != 0 && m->hdr.seq <= v->last_seq[sup]) return PACE_REJ_SEQ_ORDER;
    if (!is_s) {
        const pace_path_t *p = &m->body.path;
        uint64_t t_end = p->t0_ns + (uint64_t)(n - 1) * p->dt_ns;
        if (t_end <= now_ns) return PACE_REJ_TOO_OLD;
        if (p->t0_ns + cfg->val_t0_past_max_ns < now_ns) return PACE_REJ_TOO_OLD;
        if (p->t0_ns > now_ns + cfg->val_t0_future_max_ns) return PACE_REJ_TOO_OLD;
    } else {
        if (m->hdr.t_gen_ns + cfg->val_t0_past_max_ns < now_ns) return PACE_REJ_TOO_OLD;   /* PATH_S: 생성 시각 기준 신선도 */
    }

    /* 3) 유효성: 신뢰도 하한, (PATH, 실측 유효 시) "재생 시각에 해당하는 점" 과 실측의 거리. PATH_S 와 투영 정책은 접합기가 거리 판정 */
    float conf_min = m->hdr.supplier == PACE_SUPPLIER_LOCAL ? cfg->val_conf_min_local : cfg->val_conf_min_ai;
    if (m->hdr.confidence < conf_min) return PACE_REJ_CONFIDENCE;
    if (!is_s && (st->valid & 1)) {
        const pace_path_t *p = &m->body.path;
        uint64_t te = t_eval_ns ? t_eval_ns : now_ns;
        uint64_t i0 = te > p->t0_ns ? (te - p->t0_ns) / p->dt_ns : 0; if (i0 > (uint64_t)n - 1) i0 = n - 1;
        float thr = cfg->val_dev_max * (0.5f + 0.5f * m->hdr.confidence);
        for (uint16_t j = 0; j < d; ++j) if (!(fabsf(pts[i0][j] - st->q[j]) <= thr)) return PACE_REJ_DEVIATION;
    }
    return PACE_REJ_NONE;
}

pace_reject_t pace_validate(pace_validator_t *v, const pace_config_t *cfg, const pace_msg_t *m,
                            const pace_robot_state_t *st, const pace_hal_limits_t *lim, uint64_t now_ns, uint64_t t_eval_ns)
{
    pace_reject_t r = check(v, cfg, m, st, lim, now_ns, t_eval_ns);
    if (r == PACE_REJ_NONE) {
        v->accepted++; v->consecutive_rejects = 0;
        unsigned sup = m->hdr.supplier < 8 ? m->hdr.supplier : 0; if (m->hdr.type == PACE_MSG_PATH || m->hdr.type == PACE_MSG_PATH_S) v->last_seq[sup] = m->hdr.seq;
    } else { v->rejected++; v->consecutive_rejects++; v->reject_count[r < 16 ? r : 0]++; }
    return r;
}
