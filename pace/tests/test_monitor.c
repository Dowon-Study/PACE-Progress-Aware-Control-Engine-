#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "pace/monitor.h"

int main(void)
{
    pace_config_t cfg; pace_config_defaults(&cfg); cfg.mon_hysteresis_ticks = 3;
    pace_hal_limits_t lim; memset(&lim, 0, sizeof lim); lim.dof = 2; for (int j = 0; j < 2; ++j) { lim.q_min[j] = -1.0f; lim.q_max[j] = 1.0f; lim.qd_max[j] = 1.0f; lim.qdd_max[j] = 10.0f; }
    for (int k = 0; k < 3; ++k) { lim.workspace_min[k] = -1.0f; lim.workspace_max[k] = 1.0f; }
    pace_robot_state_t st; memset(&st, 0, sizeof st); st.dof = 2; st.valid = 1 | 2 | 16;
    pace_refbuf_t ref; pace_refbuf_init(&ref, PACE_POLICY_TIMEIDX); pace_monitor_t mon; pace_monitor_init(&mon);
    uint64_t now = 10000000000ull; float prev[2] = {0, 0};
    /* 유효 청크 없음 → BLIND → STOP */
    assert(pace_monitor_step(&mon, &cfg, &st, &lim, &ref, now, now, 0, prev, 0, 0, 0, 0, 0) == PACE_MON_STOP && (mon.triggers & PACE_TRIG_BLIND));
    /* 정상 청크 (느린 램프), 방금 채택 → OK 로 내려가려면 히스테리시스 3틱 */
    pace_msg_t m; memset(&m, 0, sizeof m); pace_msg_init(&m, PACE_MSG_PATH, PACE_SUPPLIER_AI, 1, now, now + 5000000000ull, 1.0f);
    m.hdr.space = PACE_SPACE_JOINT; m.hdr.dof = 2; m.hdr.n_points = 50; m.body.path.t0_ns = now; m.body.path.dt_ns = 20000000ull;
    for (int i = 0; i < 50; ++i) { m.body.path.pts[i][0] = 0.001f * i; m.body.path.pts[i][1] = 0; }
    pace_refbuf_adopt(&ref, &m, 1, now, now, NULL, NULL);
    pace_monitor_verdict_t v = PACE_MON_STOP;
    for (int t = 0; t < 3; ++t) { v = pace_monitor_step(&mon, &cfg, &st, &lim, &ref, now, now, now, prev, 0, 0, 0, 0, 0); }
    assert(v == PACE_MON_OK && mon.triggers == 0);
    /* 룩어헤드: 50ms 뒤 명령이 한계 90% 를 넘도록 청크 수정 → STOP 즉시 */
    for (int i = 1; i < 50; ++i) m.body.path.pts[i][0] = 0.95f; pace_refbuf_adopt(&ref, &m, 2, now, now, NULL, NULL);   /* 20ms 뒤 점이 한계 90% 초과 */
    assert(pace_monitor_step(&mon, &cfg, &st, &lim, &ref, now, now, now, prev, 0, 0, 0, 0, 0) == PACE_MON_STOP && (mon.triggers & PACE_TRIG_JOINT_LIMIT));
    /* 정상 청크로 복귀 + 추종 오차 */
    for (int i = 0; i < 50; ++i) m.body.path.pts[i][0] = 0; pace_refbuf_adopt(&ref, &m, 3, now, now, NULL, NULL);
    for (int t = 0; t < 3; ++t) { v = pace_monitor_step(&mon, &cfg, &st, &lim, &ref, now, now, now, prev, 0, 0, 0, 0, 0); }
    assert(v == PACE_MON_OK);
    st.q[1] = 0.5f; assert(pace_monitor_step(&mon, &cfg, &st, &lim, &ref, now, now, now, prev, 0, 0, 0, 0, 0) == PACE_MON_STOP && (mon.triggers & PACE_TRIG_TRACK_ERR)); st.q[1] = 0;
    /* 작업 영역 */
    for (int t = 0; t < 3; ++t) { pace_monitor_step(&mon, &cfg, &st, &lim, &ref, now, now, now, prev, 0, 0, 0, 0, 0); }
    st.tool_pose[2] = 1.5f; assert(pace_monitor_step(&mon, &cfg, &st, &lim, &ref, now, now, now, prev, 0, 0, 0, 0, 0) == PACE_MON_STOP && (mon.triggers & PACE_TRIG_WORKSPACE)); st.tool_pose[2] = 0;
    /* 버퍼 부족 → SLOW: 재생 시각을 끝 150ms 전으로 */
    for (int t = 0; t < 3; ++t) { pace_monitor_step(&mon, &cfg, &st, &lim, &ref, now, now, now, prev, 0, 0, 0, 0, 0); }
    uint64_t t_play = now + 49 * 20000000ull - 150000000ull;
    assert(pace_monitor_step(&mon, &cfg, &st, &lim, &ref, t_play, now, now, prev, 0, 0, 0, 0, 0) == PACE_MON_SLOW && (mon.triggers & PACE_TRIG_BUFFER_LOW));
    /* HAL 폴트, EVENT */
    assert(pace_monitor_step(&mon, &cfg, &st, &lim, &ref, now, now, now, prev, 1, 0, 0, 0, 0) == PACE_MON_STOP && (mon.triggers & PACE_TRIG_HAL_FAULT));
    assert(pace_monitor_step(&mon, &cfg, &st, &lim, &ref, now, now, now, prev, 0, 1, 0, 0, 0) == PACE_MON_STOP && (mon.triggers & PACE_TRIG_EVENT));
    printf("monitor OK (stop=%llu slow=%llu)\n", (unsigned long long)mon.stop_count, (unsigned long long)mon.slow_count);
    return 0;
}
