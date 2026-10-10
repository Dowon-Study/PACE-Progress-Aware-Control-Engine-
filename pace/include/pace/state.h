/*
 * 실시간 제어 계층 내부 상태 구조체 (docs/IDEA_FIXED.md 5절, 9절)
 *  - 로봇 실측 상태 (HAL read 결과)
 *  - HAL 공통 데이터 구조: 한계값, 능력, 정지 3단계
 *  - 매 틱 계측 레코드 (락프리 링버퍼에 기록)
 */
#ifndef PACE_STATE_H
#define PACE_STATE_H

#include <stdint.h>
#include "pace/msg.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 로봇 실측 상태. HAL read 가 채우고 검증기·접합기·감시기가 읽는다. */
typedef struct {
    uint64_t t_ns;                      /* 이 상태가 유효한 시각 (HAL 이 보고; 로봇마다 다른 "지금"을 흡수) */
    uint16_t dof;
    uint16_t valid;                     /* 비트: 1 q, 2 qd, 4 qdd, 8 tau, 16 tool_pose */
    uint32_t hal_fault;                 /* 0 정상, 그 외 HAL 백엔드 폴트 코드 */
    float q[PACE_MAX_DOF];
    float qd[PACE_MAX_DOF];
    float qdd[PACE_MAX_DOF];
    float tau[PACE_MAX_DOF];
    float tool_pose[PACE_TOOL_POSE_DIM];
    float tool_force;                   /* 툴 접촉력 크기 (N), valid 비트 32 */
} pace_robot_state_t;

/* HAL 이 노출하는 로봇별 공통 데이터 구조 (한계·능력). 범위 검증기와 상태 감시기가 읽는다. */
typedef struct {
    uint16_t dof;
    uint16_t accepts_position;          /* 능력 선언 */
    uint16_t accepts_velocity;
    uint16_t accepts_effort;
    uint32_t native_period_ns;          /* 로봇 고유 제어 주기 (재샘플링 판단) */
    uint32_t read_wcet_ns;              /* HAL read/write 의 RT 계약: 보고된 최악 실행 시간 */
    uint32_t write_wcet_ns;
    float q_min[PACE_MAX_DOF];
    float q_max[PACE_MAX_DOF];
    float qd_max[PACE_MAX_DOF];
    float qdd_max[PACE_MAX_DOF];
    float jerk_max[PACE_MAX_DOF];
    float tau_max[PACE_MAX_DOF];
    float workspace_min[3];             /* 툴 끝 허용 영역 (m) */
    float workspace_max[3];
} pace_hal_limits_t;

/* HAL 폴트 코드 (pace_robot_state_t.hal_fault 비트) */
enum { PACE_HALF_NONE = 0, PACE_HALF_DRIVE = 1u << 0 /* 드라이브/버스 폴트 */, PACE_HALF_COMM = 1u << 1 /* 통신 두절 */, PACE_HALF_ESTOP_LATCHED = 1u << 8 /* 비상 정지 체결 상태 */ };

/* HAL 정지 3단계 (의미를 표준화) */
typedef enum {
    PACE_STOP_DECEL = 1,   /* 저크 제한 감속 정지 (서보 유지) */
    PACE_STOP_HOLD  = 2,   /* 현재 위치 유지, 토크 유지 */
    PACE_STOP_ESTOP = 3,   /* 비상 정지 (브레이크/전원 차단, 로봇 정의) */
} pace_stop_level_t;

/* 실시간 루프 동작 모드 (예외 사다리) */
typedef enum {
    PACE_MODE_INIT     = 0,
    PACE_MODE_NORMAL   = 1,
    PACE_MODE_PACING   = 2,   /* 버퍼 여유 부족 → 감속 진행 */
    PACE_MODE_LOCAL    = 3,   /* 로컬 연속 정책 청크 사용 중 */
    PACE_MODE_EXTRAP   = 4,   /* 규칙 외삽 사용 중 */
    PACE_MODE_HOLD     = 5,
    PACE_MODE_STOPPED  = 6,
    PACE_MODE_RECOVER  = 7,   /* 복귀 블렌딩 중 */
} pace_mode_t;

/* 검증 거부 사유 */
typedef enum {
    PACE_REJ_NONE         = 0,
    PACE_REJ_HEADER       = 1,
    PACE_REJ_RANGE_POS    = 2,
    PACE_REJ_RANGE_VEL    = 3,
    PACE_REJ_RANGE_ACC    = 4,
    PACE_REJ_WORKSPACE    = 5,
    PACE_REJ_EXPIRED      = 6,
    PACE_REJ_SEQ_ORDER    = 7,
    PACE_REJ_TOO_OLD      = 8,
    PACE_REJ_DEVIATION    = 9,
    PACE_REJ_CONFIDENCE   = 10,
    PACE_REJ_NO_OVERLAP   = 11,  /* PATH_S: s 구간이 현재 진행도를 포함하지 않음 */
} pace_reject_t;

/* 상태 감시기 판정 */
typedef enum {
    PACE_MON_OK    = 0,
    PACE_MON_SLOW  = 1,
    PACE_MON_STOP  = 2,
} pace_monitor_verdict_t;

/* 감시기 트리거 비트 (정지의 물리적 이유 — 로그에 그대로 남는다) */
enum {
    PACE_TRIG_JOINT_LIMIT   = 1u << 0,
    PACE_TRIG_VEL_LIMIT     = 1u << 1,
    PACE_TRIG_ACC_LIMIT     = 1u << 2,
    PACE_TRIG_WORKSPACE     = 1u << 3,
    PACE_TRIG_DEVIATION     = 1u << 4,   /* 선 이탈도 초과 */
    PACE_TRIG_TRACK_ERR     = 1u << 5,   /* 추종 오차 초과 */
    PACE_TRIG_EXTRAP_CAP    = 1u << 6,   /* 외삽 거리/시간 상한 */
    PACE_TRIG_HAL_FAULT     = 1u << 7,
    PACE_TRIG_BLIND         = 1u << 8,   /* AI 사망 + 눈 없음 */
    PACE_TRIG_EVENT         = 1u << 9,   /* 상위 EVENT */
    PACE_TRIG_BUFFER_LOW    = 1u << 10,  /* 감속 트리거 */
    PACE_TRIG_EYE_STALE     = 1u << 11,  /* 감속 트리거 */
    PACE_TRIG_ESTOP_LATCH   = 1u << 12,  /* 비상 정지 체결됨 (운영자 리셋 전까지 재개 없음) */
    PACE_TRIG_CONTACT       = 1u << 13,  /* 툴 접촉력 > 감속 문턱 (감속 트리거), > 정지 문턱이면 STOP */
};

/* 루프 단계 인덱스 (stage_ns[]) */
enum {
    PACE_ST_WAKE = 0, PACE_ST_READ, PACE_ST_SELECT, PACE_ST_VALIDATE, PACE_ST_SPLICE,
    PACE_ST_PACE, PACE_ST_COMMAND, PACE_ST_MONITOR, PACE_ST_WRITE, PACE_ST_LOG, PACE_ST_COUNT
};

/* 매 틱 계측 레코드 (128바이트). 실시간 루프가 쓰고 측정 프로세스가 읽는다. */
typedef struct {
    uint64_t tick;
    uint64_t t_sched_ns;                /* 깨어나야 했던 시각 */
    uint64_t t_wake_ns;                 /* 실제 깨어난 시각 (지터 = t_wake - t_sched) */
    uint32_t stage_ns[PACE_ST_COUNT];   /* 단계별 소요 (WCET 산출) */
    uint64_t chunk_seq;                 /* 이 틱에 사용 중인 청크 시퀀스 */
    uint64_t chunk_t_gen_ns;            /* 그 청크의 생성 시각 (E2E = 첫 반영 틱 - t_gen) */
    float    progress_s;
    float    deviation;                 /* 기준 경로/선 대비 이탈도 */
    float    speed_scale;
    float    buffer_margin_ms;
    uint16_t mode;                      /* pace_mode_t */
    uint16_t supplier;                  /* 사용 중인 공급자 */
    uint16_t reject;                    /* 이 틱에 거부가 있었다면 사유 */
    uint16_t monitor;                   /* pace_monitor_verdict_t */
    uint32_t triggers;                  /* 감시기 트리거 비트 */
    uint16_t stop_level;                /* 이 틱에 HAL 로 보낸 정지 단계 (0 정상, pace_stop_level_t) */
    uint16_t arc_on;                    /* 공정 출력: 아크 ON(1)/OFF(0) — 용접 규칙: 정지 램프 시작과 동시에 OFF */
    uint16_t arc_power_pct;             /* 공정 파라미터: 아크 출력 % (PARAM params[0], 공정 상태 추론기가 조정) */
    uint16_t tool_force_cN;             /* 툴 접촉력 (0.01 N 단위) */
    uint8_t  _pad[12];
} pace_tick_record_t;

PACE_STATIC_ASSERT(sizeof(pace_tick_record_t) == 128, "pace_tick_record_t must be 128 bytes");

#ifdef __cplusplus
}
#endif
#endif /* PACE_STATE_H */
