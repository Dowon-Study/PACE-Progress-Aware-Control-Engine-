/* 3단계 검증기: 헤더 → 범위 → 시간 → 유효성. 할당 없음, 상태는 공급자별 마지막 시퀀스와 카운터뿐. */
#ifndef PACE_VALIDATOR_H
#define PACE_VALIDATOR_H
#include "pace/msg.h"
#include "pace/state.h"
#include "pace/config.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uint64_t last_seq[8];          /* 공급자별 (pace_supplier_t 인덱스) */
    uint64_t accepted, rejected;
    uint64_t reject_count[16];     /* pace_reject_t 별 */
    uint32_t consecutive_rejects;
} pace_validator_t;

void pace_validator_init(pace_validator_t *v);
/* 반환 PACE_REJ_NONE 이면 통과. 통과 시 last_seq 갱신 */
/* now_ns: 시간 검증 기준(벽시계), t_eval_ns: 유효성 검증에서 실측과 비교할 청크 시각(참조 재생 시각; 0 이면 now 사용) */
pace_reject_t pace_validate(pace_validator_t *v, const pace_config_t *cfg, const pace_msg_t *m,
                            const pace_robot_state_t *st, const pace_hal_limits_t *lim, uint64_t now_ns, uint64_t t_eval_ns);
const char *pace_reject_name(pace_reject_t r);
#ifdef __cplusplus
}
#endif
#endif
