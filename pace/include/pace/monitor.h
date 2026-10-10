/* 상태 감시기: 실측 + 룩어헤드 명령으로 물리 한계·추종·맹목 상태를 보고 OK/SLOW/STOP 판정. 규칙만. 정지의 유일한 결정자. */
#ifndef PACE_MONITOR_H
#define PACE_MONITOR_H
#include "pace/state.h"
#include "pace/config.h"
#include "pace/refbuf.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    pace_monitor_verdict_t verdict;
    uint32_t triggers;             /* 이번 틱 트리거 비트 */
    uint32_t ticks_in_verdict;     /* 히스테리시스용 */
    pace_monitor_verdict_t pending; uint32_t pending_ticks;
    uint64_t stop_count, slow_count;
} pace_monitor_t;

void pace_monitor_init(pace_monitor_t *m);
/* t_play: 참조 재생 시각, last_valid_chunk_ns: 마지막 유효 청크 채택 시각(0 = 없음), q_cmd_prev: 직전 명령 */
pace_monitor_verdict_t pace_monitor_step(pace_monitor_t *m, const pace_config_t *cfg, const pace_robot_state_t *st, const pace_hal_limits_t *lim,
                                         const pace_refbuf_t *ref, uint64_t t_play_ns, uint64_t now_ns, uint64_t last_valid_chunk_ns,
                                         const float *q_cmd_prev, int hal_fault, int event_stop, uint64_t ref_exhausted_since_ns, uint64_t eye_age_ns, uint64_t eye_stale_ns);
/* eye_age_ns: 마지막 유효 보정 이후 경과 (0 = 눈 안 씀), eye_stale_ns: 이보다 낡으면 EYE_STALE(SLOW) */
/* ref_exhausted_since_ns: 참조(외삽 포함)가 바닥난 시각, 0 = 참조 있음 */
#ifdef __cplusplus
}
#endif
#endif
