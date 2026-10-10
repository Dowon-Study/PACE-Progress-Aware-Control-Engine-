#undef NDEBUG
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "pace/refbuf.h"
static void mk(pace_msg_t *m, uint64_t t0, uint64_t dt, int n, float slope) {
    memset(m, 0, sizeof *m); pace_msg_init(m, PACE_MSG_PATH, PACE_SUPPLIER_AI, 1, t0, t0 + 10000000000ull, 1.0f);
    m->hdr.space = PACE_SPACE_JOINT; m->hdr.dof = 2; m->hdr.n_points = (uint16_t)n; m->body.path.t0_ns = t0; m->body.path.dt_ns = dt;
    for (int i = 0; i < n; ++i) { m->body.path.pts[i][0] = slope * i; m->body.path.pts[i][1] = 10.0f - slope * i; } }
int main(void)
{
    float q[8], qd[8]; uint16_t d; pace_msg_t m;
    /* --- TIMEIDX: 벽시계 재생, 끝 유지, 대기 슬롯 승격 --- */
    pace_refbuf_t r; pace_refbuf_init(&r, PACE_POLICY_TIMEIDX);
    assert(!pace_refbuf_eval(&r, 0, 0, q, qd, &d));
    mk(&m, 1000000000ull, 100000000ull, 3, 1.0f);
    assert(pace_refbuf_adopt(&r, &m, 5, 999, 0, NULL, NULL));
    assert(pace_refbuf_eval(&r, 500000000ull, 0, q, qd, &d) && d == 2 && q[0] == 0.0f);
    assert(pace_refbuf_eval(&r, 1050000000ull, 0, q, qd, &d) && fabsf(q[0] - 0.5f) < 1e-6 && fabsf(qd[0] - 10.0f) < 1e-3);
    assert(pace_refbuf_eval(&r, 9000000000ull, 0, q, qd, &d) && q[0] == 2.0f && qd[0] == 0.0f);
    assert(pace_refbuf_remaining_ns(&r, 1000000000ull) == 200000000ull);
    pace_msg_t m2; mk(&m2, 1500000000ull, 100000000ull, 3, 2.0f); m2.hdr.seq = 2;
    assert(pace_refbuf_adopt(&r, &m2, 6, 1100000000ull, 1100000000ull, NULL, NULL) && r.next_valid);   /* t0 미래 → 대기 */
    pace_refbuf_tick(&r, 1200000000ull, 1000000, 1.0f); assert(r.next_valid && r.chunk.hdr.seq == 1);
    pace_refbuf_tick(&r, 1500000000ull, 1000000, 1.0f); assert(!r.next_valid && r.chunk.hdr.seq == 2 && r.promotions == 1);
    /* --- PROGRESS: 투영 접합 + 페이싱 + 블렌딩 --- */
    pace_refbuf_t p; pace_refbuf_init(&p, PACE_POLICY_PROGRESS); p.blend_ns = 100000000ull; p.dev_max = 0.5f;
    mk(&m, 2000000000ull, 20000000ull, 50, 0.1f);                       /* 점 i: q0 = 0.1 i (20ms 간격) → 5 rad/s */
    float q_meas[2] = { 1.0f, 9.0f }, q_cmd[2] = { 1.02f, 8.98f };      /* 로봇은 점 10 근처 (+0.02 오프셋) */
    uint64_t now = 2000000000ull + 400000000ull;                        /* 벽시계로는 점 20 시각이지만 로봇은 늦어서 점 10 */
    assert(pace_refbuf_adopt(&p, &m, 1, now, now, q_cmd, q_meas));
    assert(fabs(p.last_proj_idx - 10.0) < 0.01 && p.last_proj_dist < 1e-6 && fabsf(p.last_splice_jump - 0.02f) < 1e-6);
    assert(pace_refbuf_eval(&p, now, now, q, qd, &d) && fabsf(q[0] - 1.02f) < 1e-5);       /* 블렌딩 시작: 오프셋 100% */
    assert(pace_refbuf_eval(&p, now, now + 100000000ull, q, qd, &d) && fabsf(q[0] - 1.0f) < 1e-5);   /* 100ms 뒤: 오프셋 0 */
    pace_refbuf_tick(&p, now, 20000000ull, 0.5f);                       /* 20ms 를 반속으로 → 인덱스 +0.5 */
    assert(fabs(p.idx_play - 10.5) < 1e-9);
    assert(pace_refbuf_eval_ahead(&p, now, 40000000ull, q, qd, &d) && fabsf(q[0] - 1.25f) < 1e-5);   /* 룩어헤드 40ms = +2 점 */
    /* 투영 거리 초과 → NO_OVERLAP */
    float far[2] = { 4.0f, 9.0f };   /* 창 안 최소 거리 1.5 > dev_max 0.5 */ assert(!pace_refbuf_adopt(&p, &m, 2, now, now, q_cmd, far) && p.no_overlap == 1 && p.chunk.hdr.seq == 1);
    /* --- PATH_S --- */
    pace_msg_t ms; memset(&ms, 0, sizeof ms); pace_msg_init(&ms, PACE_MSG_PATH_S, PACE_SUPPLIER_AI, 3, now, now + 5000000000ull, 1.0f);
    ms.hdr.space = PACE_SPACE_JOINT; ms.hdr.dof = 2; ms.hdr.n_points = 11; ms.body.path_s.s0 = 0.10f; ms.body.path_s.s1 = 0.20f; ms.body.path_s.sdot_nominal = 0.01f;  /* 10mm/s → 점 간격 1초 */
    for (int i = 0; i < 11; ++i) { ms.body.path_s.pts[i][0] = 1.0f + 0.1f * i; ms.body.path_s.pts[i][1] = 9.0f; }
    float qm[2] = { 1.3f, 9.0f };
    assert(pace_refbuf_adopt(&p, &ms, 3, now, now, qm, qm) && fabs(p.s_play - 0.13) < 1e-6);
    pace_refbuf_tick(&p, now, 500000000ull, 1.0f); assert(fabs(p.s_play - 0.135) < 1e-6);          /* 0.5s × 10mm/s = 5mm */
    assert(pace_refbuf_eval(&p, now, now + 1000000000ull, q, qd, &d) && fabsf(q[0] - 1.35f) < 1e-5);
    assert(pace_refbuf_remaining_ns(&p, now) == 6500000000ull);
    /* IMMEDIATE: 첫 점부터, 오프셋 = 현재 명령 - 첫 점 */
    pace_refbuf_t im; pace_refbuf_init(&im, PACE_POLICY_IMMEDIATE); mk(&m, now, 20000000ull, 50, 0.1f);
    assert(pace_refbuf_adopt(&im, &m, 1, now, now, q_cmd, q_meas) && im.idx_play == 0.0 && fabsf(im.last_splice_jump - 1.02f) < 1e-6);
    /* --- 규칙 외삽: 끝에 닿으면 마지막 속도로 연장, 시간/거리 상한 후 유지 --- */
    pace_refbuf_t ex; pace_refbuf_init(&ex, PACE_POLICY_PROGRESS); ex.blend_ns = 0; ex.ext_enable = true; ex.ext_max_ns = 300000000ull; ex.ext_max_rad = 2.0f;   /* 거리 상한은 넉넉히 → 시간 상한(300ms)이 먼저 */
    mk(&m, now, 20000000ull, 11, 0.1f);                                 /* 0..1.0 rad, 5 rad/s, 200ms 길이 */
    float z[2] = { 0, 10 }; assert(pace_refbuf_adopt(&ex, &m, 1, now, now, z, z));
    for (int k = 0; k < 400; ++k) pace_refbuf_tick(&ex, now, 1000000ull, 1.0f);      /* 400ms 전진: 200ms 재생 + 200ms 외삽 */
    assert(ex.ext_active && !ex.ext_capped && fabs(ex.ext_t_s - 0.2) < 1e-6);
    assert(pace_refbuf_eval(&ex, now, now, q, qd, &d) && fabsf(q[0] - 2.0f) < 1e-4 && fabsf(qd[0] - 5.0f) < 1e-4);   /* 1.0 + 5·0.2 */
    for (int k = 0; k < 200; ++k) pace_refbuf_tick(&ex, now, 1000000ull, 1.0f);      /* 외삽 300ms 상한 도달 */
    assert(ex.ext_capped && pace_refbuf_eval(&ex, now, now, q, qd, &d) && fabsf(q[0] - 2.5f) < 1e-3 && qd[0] == 0.0f);
    assert(pace_refbuf_remaining_ns(&ex, now) == 0);
    pace_msg_t m3; mk(&m3, now, 20000000ull, 11, 0.1f); m3.hdr.seq = 9; for (int i = 0; i < 11; ++i) { m3.body.path.pts[i][0] += 2.0f; m3.body.path.pts[i][1] -= 2.0f; }   /* 로봇(2.5, 7.5)을 덮는 청크 */
    float z2[2] = { 2.5f, 7.5f };
    assert(pace_refbuf_adopt(&ex, &m3, 2, now, now, z2, z2) && !ex.ext_active && ex.ext_count == 1);   /* 새 청크 → 외삽 해제 */
    printf("refbuf OK (timeidx/progress/path_s/immediate/extrap)\n"); return 0;
}
