/* 실시간 루프 파라미터 (전부 설정 파일 key = value 로 바꿀 수 있음, 벤치마크 스윕용) */
#ifndef PACE_CONFIG_H
#define PACE_CONFIG_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    /* 검증기 */
    float    val_limit_margin;        /* 관절 한계 여유 (rad) */
    float    val_dev_max;             /* 유효성: 첫 점 vs 실측 최대 차이 (rad, 신뢰도 1 기준) */
    float    val_conf_min_ai;         /* 공급자별 최소 신뢰도 */
    float    val_conf_min_local;
    uint64_t val_t0_past_max_ns;      /* t0 가 현재보다 이만큼 이상 과거면 TOO_OLD */
    uint64_t val_t0_future_max_ns;    /* t0 가 현재보다 이만큼 이상 미래면 거부 */
    uint64_t val_dt_min_ns, val_dt_max_ns;
    /* 감시기 */
    float    mon_limit_frac;          /* 한계의 이 비율에 닿으면 STOP (0.9) */
    float    mon_track_err_max;       /* 추종 오차 (rad) */
    uint32_t mon_lookahead_steps;     /* 룩어헤드 점 수 */
    uint64_t mon_lookahead_dt_ns;     /* 룩어헤드 간격 */
    uint64_t mon_t_dead_ns;           /* 참조가 바닥난(유지) 상태로 이 시간 지나면 BLIND → 정지 (처음부터 청크가 없을 때도 적용) */
    uint64_t mon_buffer_low_ns;       /* 남은 참조가 이보다 짧으면 SLOW */
    float    mon_slow_scale;          /* SLOW 속도 배율 */
    uint32_t mon_hysteresis_ticks;    /* 판정 전환 최소 유지 틱 */
    uint64_t stop_estop_after_ns;     /* 정지 판정이 이 시간 넘게 지속되면 HAL 비상 정지(3단계) 체결 */
    /* 로컬 감독 계층 (9단계): 연속 정책 청크(supplier=LOCAL) 와 감속 조언기(PARAM, supplier=LOCAL) */
    uint32_t local_enable;            /* 0 이면 LOCAL 청크를 버림 (6단계 기준선) */
    uint64_t local_max_ns;            /* 마지막 AI 청크 뒤 이 시간까지만 LOCAL 청크 채택 (그 뒤 외삽→유지→정지) */
    uint64_t local_resplice_ns;       /* LOCAL 재생 중 남은 참조가 이보다 짧으면 다음 LOCAL 청크로 접합 */
    float    local_speed;             /* LOCAL 청크 재생 속도 상한 */
    uint64_t advisor_stale_ns;        /* 조언이 이보다 오래되면 무시 */
    /* 접촉력 (센서 기반 속도·스탠드오프 조정) */
    float    mon_force_slow;          /* 툴 접촉력이 이보다 크면 SLOW (N) */
    float    mon_force_stop;          /* 이보다 크면 STOP (N) */
    float    corr_force_lift;         /* 접촉 시 스탠드오프 추가 상승 (m, 기준 경로 모드) */
    uint64_t corr_force_hold_ns;      /* 접촉 해제 뒤 상승 유지 시간 */
    float    splice_blend_rate;       /* 접합 차이 비례 블렌딩 속도 (rad/s), 0 = 고정 150ms */
    /* 페이싱 (버퍼 여유 기반) */
    uint32_t pace_enable;             /* 0: 끔 (4단계 동작), 1: 켬 */
    uint64_t pace_margin_target_ns;   /* 다음 청크 예상 도착 뒤에도 남겨둘 참조 시간 */
    float    pace_vmin;               /* 페이싱 최저 속도 배율 */
    float    pace_jitter_k;           /* 예상 도착 = EWMA + k × 편차 */
    /* 규칙 외삽 */
    uint32_t ext_enable;
    uint64_t ext_max_ns;              /* 외삽 최대 시간 */
    float    ext_max_rad;             /* 외삽 최대 관절 이동 (축 최대) */
    /* 기준 경로 + CORRECTION (7단계) */
    float    corr_lat_max, corr_h_max, corr_ang_max;   /* 보정 범위 한계 (m, m, rad) */
    float    corr_jump_max;           /* 연속 보정 간 최대 변화 (m) → 초과 시 DEVIATION */
    uint64_t corr_stale_slow_ns;      /* 보정이 이만큼 낡으면 EYE_STALE → SLOW */
    uint64_t corr_blend_ns;           /* 새 보정값으로 옮겨가는 블렌딩 시간 */
    uint32_t ik_iters;                /* 틱당 IK 반복 */
    /* 명령 생성 */
    float    cmd_speed_ramp_per_s;    /* 속도 배율 변화율 (1/s) */
    float    cmd_qd_frac, cmd_qdd_frac;   /* 명령 변화율 제한 = 한계 × 비율 */
} pace_config_t;

void pace_config_defaults(pace_config_t *c);
int  pace_config_load(pace_config_t *c, const char *path);   /* 0 성공, 음수 errno, 양수 = 파싱 실패 줄 번호 */
void pace_config_print(const pace_config_t *c, void *file);
#ifdef __cplusplus
}
#endif
#endif
