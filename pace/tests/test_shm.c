#undef NDEBUG   /* 테스트는 Release 빌드에서도 assert 를 살린다 (초기화 호출이 assert 안에 있음) */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "pace/shm.h"

int main(void)
{
    const char *name = "/pace_test_shm";
    pace_shm_t a, b;
    assert(pace_shm_create(name, &a) == 0);
    assert(pace_shm_open(name, &b) == 0);           /* 다른 프로세스 역할 */
    assert(a.size == b.size && a.size == pace_shm_total_bytes());

    /* 큐: a(생산자) → b(소비자) */
    pace_msg_t m; memset(&m, 0, sizeof m);
    pace_msg_init(&m, PACE_MSG_PATH_S, PACE_SUPPLIER_AI, 42, 1000, 2000, 0.9f);
    m.hdr.space = PACE_SPACE_TOOL; m.hdr.dof = 7; m.hdr.n_points = 3;
    m.body.path_s.s0 = 0.10f; m.body.path_s.s1 = 0.30f; m.body.path_s.ref_id = 1;
    for (int i = 0; i < 3; ++i) for (int d = 0; d < 7; ++d) m.body.path_s.pts[i][d] = (float)(i * 10 + d);
    assert(pace_msg_valid_header(&m));
    assert(pace_shm_push_msg(&a, PACE_Q_AI, &m));
    pace_msg_t o; assert(pace_shm_pop_msg(&b, PACE_Q_AI, &o));
    assert(o.hdr.seq == 42 && o.hdr.type == PACE_MSG_PATH_S && o.body.path_s.pts[2][6] == 26.0f);
    assert(pace_path_s_at(&o, 1) > 0.199f && pace_path_s_at(&o, 1) < 0.201f);
    assert(!pace_msg_expired(&o, 1500) && pace_msg_expired(&o, 2001));
    assert(!pace_shm_pop_msg(&b, PACE_Q_AI, &o));
    assert(!pace_shm_pop_msg(&b, PACE_Q_LOCAL, &o));  /* 다른 큐는 비어 있음 */

    /* 상태 seqlock: b(실시간 루프 역할) → a */
    pace_robot_state_t st; memset(&st, 0, sizeof st); st.t_ns = 777; st.dof = 6; st.q[5] = 1.5f; st.valid = 1;
    pace_shm_write_state(&b, &st);
    pace_robot_state_t rs; assert(pace_shm_read_state(&a, &rs)); assert(rs.t_ns == 777 && rs.q[5] == 1.5f);

    /* 한계값, 계약 */
    pace_hal_limits_t lim; memset(&lim, 0, sizeof lim); lim.dof = 6; lim.qd_max[0] = 3.14f; pace_shm_write_limits(&b, &lim);
    pace_hal_limits_t rl; assert(pace_shm_read_limits(&a, &rl)); assert(rl.qd_max[0] == 3.14f);
    pace_contract_t c = { .buffer_margin_ns = -5000000, .next_deadline_ns = 123, .progress_s = 0.5f }; pace_shm_write_contract(&b, &c);
    pace_contract_t rc; assert(pace_shm_read_contract(&a, &rc)); assert(rc.buffer_margin_ns == -5000000);

    /* 계측 링: 65536 개 채우기 → 가득 → 비우기 */
    pace_tick_record_t rec; memset(&rec, 0, sizeof rec);
    for (uint32_t i = 0; i < PACE_SHM_METRICS_CAP; ++i) { rec.tick = i; assert(pace_shm_push_record(&b, &rec)); }
    assert(!pace_shm_push_record(&b, &rec));
    for (uint32_t i = 0; i < PACE_SHM_METRICS_CAP; ++i) { assert(pace_shm_pop_record(&a, &rec)); assert(rec.tick == i); }

    /* 프레임 */
    static pace_frame_t f; f.t_ns = 9; f.seq = 1; f.width = 64; f.height = 48; f.channels = 3; f.data[64*48*3-1] = 200;
    pace_shm_write_frame(&a, &f);
    static pace_frame_t rf; assert(pace_shm_read_frame(&b, &rf)); assert(rf.width == 64 && rf.data[64*48*3-1] == 200);

    printf("shm OK: total=%zu bytes (%.1f MB)\n", a.size, a.size / 1048576.0);
    pace_shm_close(&a); pace_shm_close(&b); pace_shm_unlink(name);
    return 0;
}
