#include "pace/refbuf.h"
#include <math.h>
#include <string.h>

static const char *pnames[] = { "timeidx", "immediate", "progress" };
const char *pace_policy_name(pace_policy_t p) { return (unsigned)p < 3 ? pnames[p] : "?"; }

void pace_refbuf_init(pace_refbuf_t *r, pace_policy_t policy)
{
    memset(r, 0, sizeof *r); r->policy = policy; r->dev_max = 0.15f; r->blend_ns = 150000000ull; r->blend_rate = 0.2f; r->blend_dur_ns = 150000000ull; r->search_back_pts = 10; r->search_fwd_pts = 25;
    r->ext_enable = false; r->ext_max_ns = 400000000ull; r->ext_max_rad = 0.05f;
}

static inline bool is_s(const pace_msg_t *m) { return m->hdr.type == PACE_MSG_PATH_S; }
static inline uint16_t npts(const pace_msg_t *m) { return m->hdr.n_points; }
static inline const float *pt(const pace_msg_t *m, uint32_t i) { return is_s(m) ? m->body.path_s.pts[i] : m->body.path.pts[i]; }

/* 청크 내 실수 인덱스 x 에서 보간 */
static void interp(const pace_msg_t *m, double x, float *q, float *qd, double dt_s)
{
    uint16_t n = npts(m), d = m->hdr.dof;
    if (x <= 0) { memcpy(q, pt(m, 0), d * sizeof(float)); memset(qd, 0, d * sizeof(float)); return; }
    if (x >= n - 1) { memcpy(q, pt(m, n - 1), d * sizeof(float)); memset(qd, 0, d * sizeof(float)); return; }
    uint32_t i = (uint32_t)x; float a = (float)(x - i), inv = (float)(1.0 / dt_s);
    const float *p0 = pt(m, i), *p1 = pt(m, i + 1);
    for (uint16_t j = 0; j < d; ++j) { q[j] = p0[j] + a * (p1[j] - p0[j]); qd[j] = (p1[j] - p0[j]) * inv; }
}

/* PATH: 점 간격(초). PATH_S: s 간격을 명목 속도로 나눈 시간 간격 */
static double point_dt_s(const pace_msg_t *m)
{
    if (!is_s(m)) return m->body.path.dt_ns * 1e-9;
    uint16_t n = npts(m); double ds = n > 1 ? (m->body.path_s.s1 - m->body.path_s.s0) / (n - 1) : 0.0;
    double sdot = m->body.path_s.sdot_nominal > 1e-6f ? m->body.path_s.sdot_nominal : 1e-6;
    return ds / sdot;
}

static float dist_inf(const float *a, const float *b, uint16_t d) { float m = 0; for (uint16_t j = 0; j < d; ++j) { float x = fabsf(a[j] - b[j]); if (x > m) m = x; } return m; }

bool pace_refbuf_adopt(pace_refbuf_t *r, const pace_msg_t *m, uint64_t tick, uint64_t now_ns, uint64_t t_play_ns,
                       const float *q_cmd_prev, const float *q_meas)
{
    uint16_t d = m->hdr.dof, n = npts(m);
    if (r->policy == PACE_POLICY_TIMEIDX) {
        if (is_s(m)) return false;                                   /* 시간 인덱스는 PATH_S 를 재생할 수 없음 (정책 한계) */
        if (!r->valid || t_play_ns >= m->body.path.t0_ns) { r->chunk = *m; r->valid = true; r->adopted_tick = tick; r->adopted_t_ns = now_ns; r->next_valid = false; }
        else { r->next = *m; r->next_valid = true; r->next_tick = tick; r->next_t_ns = now_ns; }
        r->splices++; return true;
    }
    double start;
    if (r->policy == PACE_POLICY_IMMEDIATE) {
        start = 0.0; r->last_proj_dist = q_meas ? dist_inf(pt(m, 0), q_meas, d) : 0.0f;
    } else {
        /* PROGRESS: 예상 인덱스(타임스탬프) 주변 창에서 실측에 가장 가까운 점 */
        double expect;
        if (is_s(m)) { double ds = n > 1 ? (m->body.path_s.s1 - m->body.path_s.s0) / (n - 1) : 1.0; expect = r->valid ? (r->s_play - m->body.path_s.s0) / ds : 0.0; }
        else { double dts = point_dt_s(m); expect = ((double)now_ns - (double)m->body.path.t0_ns) * 1e-9 / dts; }
        if (expect < 0) { expect = 0; }
        if (expect > n - 1) { expect = n - 1; }
        int lo = (int)expect - (int)r->search_back_pts, hi = (int)expect + (int)r->search_fwd_pts; if (lo < 0) lo = 0; if (hi > n - 1) hi = n - 1;
        int best = lo; float bd = 1e30f;
        if (q_meas) for (int i = lo; i <= hi; ++i) { float dd = dist_inf(pt(m, i), q_meas, d); if (dd < bd) { bd = dd; best = i; } }
        else { best = (int)expect; bd = 0; }
        /* 인접 점 사이 선형 보간으로 투영 정밀화 (1차원 최소화) */
        double x = best;
        if (q_meas && best + 1 <= hi) { const float *a = pt(m, best), *b = pt(m, best + 1); double num = 0, den = 0; for (uint16_t j = 0; j < d; ++j) { double e = b[j] - a[j]; num += (q_meas[j] - a[j]) * e; den += e * e; } if (den > 1e-12) { double t = num / den; if (t > 0 && t < 1) x = best + t; } }
        r->last_proj_dist = bd; r->last_proj_idx = x;
        if (bd > r->dev_max) { r->no_overlap++; return false; }
        start = x;
    }
    /* 접합: 현재 명령과 시작점의 차이를 오프셋으로 → blend_ns 동안 감쇠 (단순 평균이 아닌 오프셋 재적합) */
    float q0[PACE_MAX_DOF], qd0[PACE_MAX_DOF]; interp(m, start, q0, qd0, point_dt_s(m));
    float jump = 0; for (uint16_t j = 0; j < d; ++j) { r->blend_off[j] = q_cmd_prev ? q_cmd_prev[j] - q0[j] : 0.0f; float a = fabsf(r->blend_off[j]); if (a > jump) jump = a; }
    r->last_splice_jump = jump; r->blend_t0_ns = now_ns;
    r->blend_dur_ns = r->blend_ns; if (r->blend_rate > 0) { double need = (double)jump / r->blend_rate * 1e9; if (need > (double)r->blend_dur_ns) r->blend_dur_ns = (uint64_t)need; }   /* 사다리 ⑤: 복귀 접합은 차이에 비례해 길게 */
    r->chunk = *m; r->valid = true; r->adopted_tick = tick; r->adopted_t_ns = now_ns; r->next_valid = false;
    r->ext_active = r->ext_capped = false; r->ext_t_s = 0;
    r->idx_play = start;
    if (is_s(m)) { double ds = n > 1 ? (m->body.path_s.s1 - m->body.path_s.s0) / (n - 1) : 0.0; r->s_play = m->body.path_s.s0 + start * ds; }
    r->splices++;
    return true;
}

void pace_refbuf_tick(pace_refbuf_t *r, uint64_t t_play_ns, uint64_t dt_ns, float speed)
{
    if (!r->valid) return;
    if (r->policy == PACE_POLICY_TIMEIDX) {
        if (r->next_valid && t_play_ns >= r->next.body.path.t0_ns) { r->chunk = r->next; r->adopted_tick = r->next_tick; r->adopted_t_ns = r->next_t_ns; r->next_valid = false; r->promotions++; }
        return;
    }
    double dts = point_dt_s(&r->chunk); uint16_t n = npts(&r->chunk);
    double adv = (dt_ns * 1e-9) * speed / dts;
    if (r->idx_play + adv >= n - 1) {
        double over = (r->idx_play + adv) - (n - 1); r->idx_play = n - 1;
        if (r->ext_enable && n >= 2 && !r->ext_capped) {
            if (!r->ext_active) { r->ext_active = true; r->ext_count++; const float *a = pt(&r->chunk, n - 2), *b = pt(&r->chunk, n - 1); for (uint16_t j = 0; j < r->chunk.hdr.dof; ++j) r->ext_v[j] = (float)((b[j] - a[j]) / dts); }
            r->ext_t_s += over * dts;
            float moved = 0; for (uint16_t j = 0; j < r->chunk.hdr.dof; ++j) { float x = fabsf(r->ext_v[j]) * (float)r->ext_t_s; if (x > moved) moved = x; }
            if (r->ext_t_s * 1e9 > (double)r->ext_max_ns || moved > r->ext_max_rad) r->ext_capped = true;   /* 상한: 이후 유지 */
        }
    } else r->idx_play += adv;
    if (is_s(&r->chunk)) { double ds = n > 1 ? (r->chunk.body.path_s.s1 - r->chunk.body.path_s.s0) / (n - 1) : 0.0; r->s_play = r->chunk.body.path_s.s0 + r->idx_play * ds; }
}

bool pace_refbuf_eval(const pace_refbuf_t *r, uint64_t t_play_ns, uint64_t now_ns, float *q, float *qd, uint16_t *dof)
{
    if (!r->valid) return false;
    const pace_msg_t *m = &r->chunk; *dof = m->hdr.dof;
    if (r->policy == PACE_POLICY_TIMEIDX) {
        double x = ((double)t_play_ns - (double)m->body.path.t0_ns) * 1e-9 / point_dt_s(m);
        interp(m, x, q, qd, point_dt_s(m)); return true;
    }
    interp(m, r->idx_play, q, qd, point_dt_s(m));
    if (r->ext_active) {   /* 끝점 + 외삽 속도 × 시간 (상한에 걸리면 그 시점에서 멈춘 값 유지) */
        double tcap = r->ext_t_s;
        if (r->ext_capped) { double tmax = r->ext_max_ns * 1e-9; float vmax = 0; for (uint16_t j = 0; j < *dof; ++j) if (fabsf(r->ext_v[j]) > vmax) vmax = fabsf(r->ext_v[j]); if (vmax > 1e-9f) { double td = r->ext_max_rad / vmax; if (td < tmax) tmax = td; } if (tcap > tmax) tcap = tmax; }
        for (uint16_t j = 0; j < *dof; ++j) { q[j] += (float)(r->ext_v[j] * tcap); qd[j] = r->ext_capped ? 0.0f : r->ext_v[j]; }
    }
    if (r->blend_dur_ns) {   /* 오프셋 감쇠 (코사인), 길이는 접합 점프에 비례 */
        double tau = (double)(now_ns - r->blend_t0_ns) / (double)r->blend_dur_ns;
        if (tau < 1.0) { float w = (float)(0.5 + 0.5 * cos(M_PI * tau)); for (uint16_t j = 0; j < *dof; ++j) q[j] += w * r->blend_off[j]; }
    }
    return true;
}

bool pace_refbuf_eval_ahead(const pace_refbuf_t *r, uint64_t t_play_ns, uint64_t ahead_ns, float *q, float *qd, uint16_t *dof)
{
    if (!r->valid) return false;
    const pace_msg_t *m = &r->chunk; *dof = m->hdr.dof; double dts = point_dt_s(m);
    double x = r->policy == PACE_POLICY_TIMEIDX ? ((double)t_play_ns + ahead_ns - (double)m->body.path.t0_ns) * 1e-9 / dts : r->idx_play + ahead_ns * 1e-9 / dts;
    interp(m, x, q, qd, dts); return true;
}

uint64_t pace_refbuf_remaining_ns(const pace_refbuf_t *r, uint64_t t_play_ns)
{
    if (!r->valid || npts(&r->chunk) == 0) return 0;
    const pace_msg_t *m = &r->chunk; uint16_t n = npts(m); double dts = point_dt_s(m);
    if (r->policy == PACE_POLICY_TIMEIDX) { uint64_t end = m->body.path.t0_ns + (uint64_t)((n - 1) * dts * 1e9); return end > t_play_ns ? end - t_play_ns : 0; }
    double rem = ((n - 1) - r->idx_play) * dts; return rem > 0 ? (uint64_t)(rem * 1e9) : 0;
}
