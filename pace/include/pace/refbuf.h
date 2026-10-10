/*
 * 참조 버퍼 + 반영 정책 (docs/IDEA_FIXED.md 5절 ⑤, 9절 비교 실험)
 *
 *  정책           새 청크 채택 시 "어디서부터"            재생 전진                       페이싱
 *  ─────────────  ─────────────────────────────────────  ─────────────────────────────  ──────
 *  TIMEIDX        시각 t0 가 되면 승격, 점 = 벽시계 인덱스  벽시계                           불가 (4단계 기준선 = 궤적 추적)
 *  IMMEDIATE      즉시, 첫 점부터                        내부 인덱스 += dt·speed          가능 (도착 즉시 반영 기준선)
 *  PROGRESS       실측 상태를 청크에 투영한 점부터          내부 인덱스/진행도 += dt·speed   가능 (진행도 접합, 경로 추종)
 *
 *  PROGRESS 투영: 타임스탬프로 예상 인덱스를 잡고 그 주변 창에서 실측 q 와 가장 가까운 점. 뒤로 가지 않음(단조).
 *  최소 거리가 dev_max 를 넘으면 채택 거부(NO_OVERLAP). 접합 시 현재 명령과 청크 점의 차이를 오프셋으로 두고 blend_ns 동안 감쇠.
 *  PATH_S 청크는 진행도 s 로 재생: s_play += sdot_nominal·dt·speed, 투영은 s 축에서.
 */
#ifndef PACE_REFBUF_H
#define PACE_REFBUF_H
#include <stdbool.h>
#include "pace/msg.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef enum { PACE_POLICY_TIMEIDX = 0, PACE_POLICY_IMMEDIATE = 1, PACE_POLICY_PROGRESS = 2 } pace_policy_t;

typedef struct {
    pace_policy_t policy;
    float    dev_max;          /* 투영 최소 거리 허용 (rad, 축 최대) */
    uint64_t blend_ns;         /* 접합 오프셋 감쇠 최소 시간 */
    float    blend_rate;       /* 차이 비례 블렌딩: 감쇠 시간 = max(blend_ns, 접합 점프 / blend_rate) (rad/s). 0 이면 고정 시간 */
    uint64_t blend_dur_ns;     /* 이번 접합의 실제 감쇠 시간 */
    uint32_t search_back_pts, search_fwd_pts;   /* 투영 탐색 창 (예상 인덱스 기준 점 수) */

    bool     valid;
    pace_msg_t chunk;          /* 현재 재생 중인 청크 */
    uint64_t adopted_tick, adopted_t_ns;
    /* TIMEIDX 대기 슬롯 */
    bool     next_valid; pace_msg_t next; uint64_t next_tick, next_t_ns; uint64_t promotions;
    /* IMMEDIATE / PROGRESS 재생 상태 */
    double   idx_play;         /* PATH: 청크 내 실수 인덱스 */
    double   s_play;           /* PATH_S: 진행도 */
    float    blend_off[PACE_MAX_DOF]; uint64_t blend_t0_ns;
    /* 규칙 외삽 (참조가 바닥났을 때 마지막 속도 방향으로 짧게 연장) */
    bool     ext_enable; uint64_t ext_max_ns; float ext_max_rad;
    bool     ext_active, ext_capped;   /* 외삽 중 / 상한 도달(유지로 전환) */
    double   ext_t_s;                  /* 누적 외삽 시간 (재생 속도 반영) */
    float    ext_v[PACE_MAX_DOF];      /* 외삽 속도 (마지막 구간 속도) */
    uint64_t ext_count;
    /* 진단 */
    uint64_t splices;          /* 접합 횟수 */
    float    last_proj_dist;   /* 마지막 투영 거리 */
    float    last_splice_jump; /* 접합 시 명령 불연속 크기 (블렌딩 전) */
    double   last_proj_idx;
    uint64_t no_overlap;
} pace_refbuf_t;

void pace_refbuf_init(pace_refbuf_t *r, pace_policy_t policy);
/* 채택. q_cmd_prev: 현재 명령(블렌딩 기준), q_meas: 실측(투영 기준). 반환 false = NO_OVERLAP (채택 거부) */
bool pace_refbuf_adopt(pace_refbuf_t *r, const pace_msg_t *m, uint64_t tick, uint64_t now_ns, uint64_t t_play_ns,
                       const float *q_cmd_prev, const float *q_meas);
/* 매 틱: TIMEIDX 승격 / IMMEDIATE·PROGRESS 재생 전진 (dt_ns × speed) */
void pace_refbuf_tick(pace_refbuf_t *r, uint64_t t_play_ns, uint64_t dt_ns, float speed);
/* 현재 참조 평가 (블렌딩 오프셋 포함). 유효 청크 없으면 false */
bool pace_refbuf_eval(const pace_refbuf_t *r, uint64_t t_play_ns, uint64_t now_ns, float *q, float *qd, uint16_t *dof);
/* ahead_ns 뒤의 참조 (감시기 룩어헤드). TIMEIDX: 벽시계+ahead, 그 외: 인덱스 전진 */
bool pace_refbuf_eval_ahead(const pace_refbuf_t *r, uint64_t t_play_ns, uint64_t ahead_ns, float *q, float *qd, uint16_t *dof);
/* 남은 참조 시간 (ns) */
uint64_t pace_refbuf_remaining_ns(const pace_refbuf_t *r, uint64_t t_play_ns);
const char *pace_policy_name(pace_policy_t p);
#ifdef __cplusplus
}
#endif
#endif
