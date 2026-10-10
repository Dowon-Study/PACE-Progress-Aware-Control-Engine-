#undef NDEBUG
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "pace/validator.h"

static pace_hal_limits_t lim; static pace_robot_state_t st; static pace_config_t cfg;
static void mk(pace_msg_t *m, uint64_t seq, uint64_t t0, uint64_t dt, int n, float q0, float slope, float conf)
{
    memset(m, 0, sizeof *m); pace_msg_init(m, PACE_MSG_PATH, PACE_SUPPLIER_AI, seq, t0 - 50000000ull, t0 + 3000000000ull, conf);
    m->hdr.space = PACE_SPACE_JOINT; m->hdr.dof = 6; m->hdr.n_points = (uint16_t)n; m->body.path.t0_ns = t0; m->body.path.dt_ns = dt;
    for (int i = 0; i < n; ++i) for (int j = 0; j < 6; ++j) m->body.path.pts[i][j] = q0 + slope * i * (dt * 1e-9f);
}
int main(void)
{
    pace_config_defaults(&cfg);
    memset(&lim, 0, sizeof lim); lim.dof = 6; for (int j = 0; j < 6; ++j) { lim.q_min[j] = -3.0f; lim.q_max[j] = 3.0f; lim.qd_max[j] = 2.0f; lim.qdd_max[j] = 10.0f; }
    memset(&st, 0, sizeof st); st.dof = 6; st.valid = 1 | 2;   /* 현재 q = 0 */
    pace_validator_t v; pace_validator_init(&v); pace_msg_t m; uint64_t now = 10000000000ull;
    /* 정상 */
    mk(&m, 1, now + 50000000ull, 20000000ull, 50, 0.0f, 0.5f, 0.9f); assert(pace_validate(&v, &cfg, &m, &st, &lim, now, 0) == PACE_REJ_NONE);
    /* 시퀀스 역전 */
    mk(&m, 1, now + 50000000ull, 20000000ull, 50, 0.0f, 0.5f, 0.9f); assert(pace_validate(&v, &cfg, &m, &st, &lim, now, 0) == PACE_REJ_SEQ_ORDER);
    /* 범위 밖 위치 */
    mk(&m, 2, now + 50000000ull, 20000000ull, 50, 2.99f, 0.0f, 0.9f); assert(pace_validate(&v, &cfg, &m, &st, &lim, now, 0) == PACE_REJ_RANGE_POS);
    /* NaN */
    mk(&m, 3, now + 50000000ull, 20000000ull, 50, 0.0f, 0.0f, 0.9f); m.body.path.pts[7][2] = NAN; assert(pace_validate(&v, &cfg, &m, &st, &lim, now, 0) == PACE_REJ_RANGE_POS);
    /* 속도 초과 (점프) */
    mk(&m, 4, now + 50000000ull, 20000000ull, 50, 0.0f, 0.0f, 0.9f); m.body.path.pts[10][0] = 0.5f; assert(pace_validate(&v, &cfg, &m, &st, &lim, now, 0) == PACE_REJ_RANGE_VEL);
    /* 가속도 초과 (속도는 허용, 가속만 큼): 0, 0.02, 0.06 → v=1,2  a=50 */
    mk(&m, 5, now + 50000000ull, 20000000ull, 50, 0.0f, 0.0f, 0.9f); m.body.path.pts[1][0] = 0.02f; m.body.path.pts[2][0] = 0.06f; for (int i = 3; i < 50; ++i) m.body.path.pts[i][0] = 0.06f + 0.0f;
    assert(pace_validate(&v, &cfg, &m, &st, &lim, now, 0) == PACE_REJ_RANGE_ACC);
    /* 만료 */
    mk(&m, 6, now + 50000000ull, 20000000ull, 50, 0.0f, 0.5f, 0.9f); m.hdr.t_valid_until_ns = now - 1; assert(pace_validate(&v, &cfg, &m, &st, &lim, now, 0) == PACE_REJ_EXPIRED);
    /* 전부 과거 */
    mk(&m, 7, now - 5000000000ull, 20000000ull, 50, 0.0f, 0.0f, 0.9f); m.hdr.t_valid_until_ns = now + 3000000000ull; assert(pace_validate(&v, &cfg, &m, &st, &lim, now, 0) == PACE_REJ_TOO_OLD);
    /* 너무 먼 미래 */
    mk(&m, 8, now + 2000000000ull, 20000000ull, 50, 0.0f, 0.0f, 0.9f); assert(pace_validate(&v, &cfg, &m, &st, &lim, now, 0) == PACE_REJ_TOO_OLD);
    /* 저신뢰 */
    mk(&m, 9, now + 50000000ull, 20000000ull, 50, 0.0f, 0.0f, 0.1f); assert(pace_validate(&v, &cfg, &m, &st, &lim, now, 0) == PACE_REJ_CONFIDENCE);
    /* 이탈: 현재 q=0 인데 청크는 0.5 에서 시작 */
    mk(&m, 10, now + 50000000ull, 20000000ull, 50, 0.5f, 0.0f, 0.9f); assert(pace_validate(&v, &cfg, &m, &st, &lim, now, 0) == PACE_REJ_DEVIATION);
    /* 늦게 도착한 청크: t0 는 300ms 전이지만 "지금 시각에 해당하는 점" 이 현재 q 근처면 통과 (슬로프 0.1 → 300ms 뒤 0.03) */
    mk(&m, 11, now - 300000000ull, 20000000ull, 50, 0.0f, 0.1f, 0.9f); st.q[0] = 0.03f; assert(pace_validate(&v, &cfg, &m, &st, &lim, now, 0) == PACE_REJ_NONE); st.q[0] = 0;
    /* PARAM 은 헤더만 */
    pace_msg_t pm; memset(&pm, 0, sizeof pm); pace_msg_init(&pm, PACE_MSG_PARAM, PACE_SUPPLIER_OPERATOR, 1, now, now + 1000000000ull, 1.0f); pm.body.param.speed_scale = 0.5f;
    assert(pace_validate(&v, &cfg, &pm, &st, &lim, now, 0) == PACE_REJ_NONE);
    printf("validator OK: accepted=%llu rejected=%llu\n", (unsigned long long)v.accepted, (unsigned long long)v.rejected);
    assert(v.accepted == 3 && v.rejected == 10);
    return 0;
}
