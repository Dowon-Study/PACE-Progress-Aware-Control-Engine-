/*
 * PACE 공통 메시지 규격 (docs/IDEA_FIXED.md 4절)
 *
 * 모든 계층(AI 추론 / 로컬 감독 / 실시간 제어 / HAL)이 이 하나의 고정 크기 구조체로 통신한다.
 *  - POD, 포인터 없음, 고정 크기 → 공유메모리에 그대로 복사 가능, 실시간 루프에서 할당 없음
 *  - 모든 시각은 CLOCK_MONOTONIC 나노초 (제어기 PC 시계 기준). 두 PC 구성에서는 PTP 로 동기화된 시계.
 *  - 레이아웃은 pace_py/msg.py 의 ctypes 미러와 바이트 단위로 일치해야 한다 (tests/test_layout 가 검사).
 */
#ifndef PACE_MSG_H
#define PACE_MSG_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* C/C++ 공용 정적 단언 (C++ 어댑터가 이 헤더를 포함한다) */
#ifdef __cplusplus
#define PACE_STATIC_ASSERT(c, m) static_assert(c, m)
#else
#define PACE_STATIC_ASSERT(c, m) _Static_assert(c, m)
#endif
#ifdef __cplusplus
extern "C" {
#endif

#define PACE_MSG_MAGIC      0x50414345u   /* 'PACE' */
#define PACE_MSG_VERSION    1u
#define PACE_MAX_DOF        8u            /* 관절 공간 최대 축 수 (툴 공간 포즈 7값도 이 폭에 담는다) */
#define PACE_MAX_POINTS     256u          /* 청크 최대 점 수 */
#define PACE_MAX_PARAMS     16u           /* PARAM 벡터 최대 길이 */
#define PACE_TOOL_POSE_DIM  7u            /* x y z qx qy qz qw */

/* 메시지 종류 */
typedef enum {
    PACE_MSG_NONE        = 0,
    PACE_MSG_PATH        = 1,   /* 시간 매개화 경로 p(t)          — 기존 VLA/ACT 호환 */
    PACE_MSG_PATH_S      = 2,   /* 진행도 매개화 경로 p(s)        — 확정 아이디어의 공식 형식 */
    PACE_MSG_CORRECTION  = 3,   /* 기준 경로 대비 보정 흐름        — 용접선 센서/비전 보정 */
    PACE_MSG_PARAM       = 4,   /* 속도 배율, 공정 파라미터        — 속도 지령, 적응제어 */
    PACE_MSG_EVENT       = 5,   /* 끝 / 중단 / 재개 / 결함         — 비주기 */
    PACE_MSG_CONTRACT    = 6,   /* 역방향: 제어기 → 상위 시간 계약 */
} pace_msg_type_t;

/* 경로 점이 어느 공간의 값인지 */
typedef enum {
    PACE_SPACE_JOINT = 0,       /* 관절 위치 [dof] */
    PACE_SPACE_TOOL  = 1,       /* 툴 끝 포즈 [7] = x y z qx qy qz qw */
} pace_space_t;

/* 공급자 ID (참조 선택 우선순위와 검증 문턱에 쓰인다) */
typedef enum {
    PACE_SUPPLIER_UNKNOWN   = 0,
    PACE_SUPPLIER_AI        = 1,   /* AI 추론 계층 (큰 모델) */
    PACE_SUPPLIER_LOCAL     = 2,   /* 로컬 감독 계층 연속 정책 */
    PACE_SUPPLIER_EYE       = 3,   /* 로컬 작은 눈 (용접선 검출) */
    PACE_SUPPLIER_RULE      = 4,   /* 실시간 계층 규칙 외삽 (내부) */
    PACE_SUPPLIER_TEACH     = 5,   /* 교시/CAD 기준 경로 */
    PACE_SUPPLIER_OPERATOR  = 6,   /* 사람/상위 시스템 */
    PACE_SUPPLIER_CONTROL   = 7,   /* 실시간 제어 계층 (역방향 메시지의 발신자) */
} pace_supplier_t;

/* EVENT 코드 */
typedef enum {
    PACE_EVT_NONE      = 0,
    PACE_EVT_SEAM_END  = 1,   /* 용접선 끝 */
    PACE_EVT_PAUSE     = 2,   /* 중단 요청 (감속 후 유지) */
    PACE_EVT_RESUME    = 3,   /* 재개 */
    PACE_EVT_DEFECT    = 4,   /* 결함 감지 → 정지 */
    PACE_EVT_ESTOP     = 5,   /* 비상 정지 */
} pace_event_code_t;

/* 헤더: 64바이트 고정 */
typedef struct {
    uint32_t magic;             /* PACE_MSG_MAGIC */
    uint16_t version;           /* PACE_MSG_VERSION */
    uint16_t type;              /* pace_msg_type_t */
    uint64_t seq;               /* 공급자별 단조 증가 시퀀스 번호 (순서 검증) */
    uint64_t t_gen_ns;          /* 생성 시각 (추론 시작 시 읽은 관측의 시각) */
    uint64_t t_valid_until_ns;  /* 유효기간 만료 시각 (이후 도착/사용 금지) */
    float    confidence;        /* 0..1, 공급자가 보고한 신뢰도 */
    uint16_t supplier;          /* pace_supplier_t */
    uint16_t space;             /* pace_space_t (PATH/PATH_S 에서 의미) */
    uint16_t dof;               /* 점 하나의 유효 값 개수 (관절 수 또는 7) */
    uint16_t n_points;          /* 유효 점 수 (<= PACE_MAX_POINTS) */
    uint32_t flags;             /* 예약 */
    uint8_t  _pad[16];          /* 64바이트 정렬 */
} pace_msg_header_t;

/* PATH: 시간 매개화. 점 i 의 시각 = t0_ns + i * dt_ns.
 * t0_ns 는 보통 t_gen_ns + 예상 지연 (미래 시점 겨냥). */
typedef struct {
    uint64_t t0_ns;
    uint64_t dt_ns;
    float    pts[PACE_MAX_POINTS][PACE_MAX_DOF];
} pace_path_t;

/* PATH_S: 진행도 매개화. 점 i 의 진행도 = s0 + i * (s1 - s0) / (n_points - 1).
 * s 는 기준 경로 위 호 길이(미터) 또는 정규화 진행도 — ref_id 가 가리키는 기준 경로 정의를 따른다. */
typedef struct {
    float    s0;
    float    s1;
    uint32_t ref_id;            /* 기준 경로 식별자 */
    float    sdot_nominal;      /* 명목 진행 속도 (s 단위/초). 제어기 페이싱의 기준 */
    float    pts[PACE_MAX_POINTS][PACE_MAX_DOF];
} pace_path_s_t;

/* CORRECTION: 기준 경로 대비 보정 흐름. 점 i 의 진행도 = s0 + i * ds (또는 시각 = t0 + i*dt, by_time 플래그).
 * 각 점 = (가로 오프셋 m, 높이 오프셋 m, 각도 오프셋 rad, 예비) */
typedef struct {
    float    s0;
    float    ds;
    uint64_t t0_ns;
    uint64_t dt_ns;
    uint32_t ref_id;
    uint32_t by_time;           /* 0: s 기준, 1: t 기준 */
    float    pts[PACE_MAX_POINTS][4];
} pace_correction_t;

/* PARAM: 속도 배율과 공정 파라미터 */
typedef struct {
    float    speed_scale;       /* 0..1.5, 진행 속도 배율 제안 (페이싱의 min 입력 중 하나) */
    uint32_t n_params;
    float    params[PACE_MAX_PARAMS];   /* 전류, 전압, 송급속도, 위빙폭 ... 의미는 공정 정의에 따름 */
} pace_param_t;

/* EVENT */
typedef struct {
    uint32_t code;              /* pace_event_code_t */
    uint32_t arg;
} pace_event_t;

/* CONTRACT (역방향, 제어기 → 상위): 2단계 "양방향 시간 계약"의 자리. 1단계에서도 기록은 한다. */
typedef struct {
    int64_t  buffer_margin_ns;  /* 남은 경로 시간 - 예상 도착 시간 */
    uint64_t next_deadline_ns;  /* 이 시각까지 새 청크가 필요 */
    uint64_t latency_p50_ns;    /* 실측 E2E 지연 분위수 */
    uint64_t latency_p95_ns;
    uint64_t latency_p99_ns;
    float    progress_s;        /* 현재 진행도 */
    float    speed_scale;       /* 현재 적용 중인 속도 배율 */
    /* 실행 상태: 보조 판단 계층의 온라인 학습이 '검증을 통과해 실제로 실행된 AI 구간'만 고르는 데 쓴다 */
    uint64_t t_ns;              /* 이 계약을 쓴 시각 (CLOCK_MONOTONIC, 루프 깨어남 시각) */
    uint16_t mode;              /* pace_mode_t */
    uint16_t supplier;          /* 지금 재생 중인 청크의 공급자 (pace_supplier_t) */
    uint16_t monitor;           /* 안전 감시기 판정 (0 OK, 1 SLOW, 2 STOP) */
    uint16_t stop_level;        /* 0 또는 pace_stop_level_t */
    uint32_t n_reject;          /* 누적 거부 수 */
    uint32_t n_unclean;         /* 누적 '깨끗하지 않은' 틱 수: NORMAL · 공급자 AI · 감시 OK · 정지 0 · 거부 0 중 하나라도 아닌 틱 */
} pace_contract_t;

typedef struct {
    pace_msg_header_t hdr;
    union {
        pace_path_t        path;
        pace_path_s_t      path_s;
        pace_correction_t  correction;
        pace_param_t       param;
        pace_event_t       event;
        pace_contract_t    contract;
    } body;
} pace_msg_t;

/* 레이아웃 고정 검사 (ABI 가 바뀌면 컴파일 에러로 알린다) */
PACE_STATIC_ASSERT(sizeof(pace_msg_header_t) == 64, "pace_msg_header_t must be 64 bytes");
PACE_STATIC_ASSERT(sizeof(pace_path_t) == 16 + PACE_MAX_POINTS * PACE_MAX_DOF * 4, "pace_path_t size");
PACE_STATIC_ASSERT(sizeof(pace_msg_t) == 64 + sizeof(pace_path_t), "pace_msg_t size (union largest = path)");
PACE_STATIC_ASSERT(offsetof(pace_msg_t, body) == 64, "body offset");
PACE_STATIC_ASSERT(sizeof(pace_contract_t) == 72, "pace_contract_t size (Python 미러 pace_py/msg.py Contract 와 같아야 함)");

/* ---- 헬퍼 (인라인, 할당 없음) ---- */

static inline void pace_msg_init(pace_msg_t *m, pace_msg_type_t type, pace_supplier_t supplier,
                                 uint64_t seq, uint64_t t_gen_ns, uint64_t t_valid_until_ns, float confidence)
{
    m->hdr.magic = PACE_MSG_MAGIC;
    m->hdr.version = PACE_MSG_VERSION;
    m->hdr.type = (uint16_t)type;
    m->hdr.seq = seq;
    m->hdr.t_gen_ns = t_gen_ns;
    m->hdr.t_valid_until_ns = t_valid_until_ns;
    m->hdr.confidence = confidence;
    m->hdr.supplier = (uint16_t)supplier;
    m->hdr.space = 0; m->hdr.dof = 0; m->hdr.n_points = 0; m->hdr.flags = 0;
    for (size_t i = 0; i < sizeof m->hdr._pad; ++i) m->hdr._pad[i] = 0;
}

static inline bool pace_msg_valid_header(const pace_msg_t *m)
{
    return m->hdr.magic == PACE_MSG_MAGIC && m->hdr.version == PACE_MSG_VERSION
        && m->hdr.type >= PACE_MSG_PATH && m->hdr.type <= PACE_MSG_CONTRACT
        && m->hdr.n_points <= PACE_MAX_POINTS && m->hdr.dof <= PACE_MAX_DOF
        && m->hdr.confidence >= 0.0f && m->hdr.confidence <= 1.0f;
}

static inline bool pace_msg_expired(const pace_msg_t *m, uint64_t now_ns)
{
    return now_ns > m->hdr.t_valid_until_ns;
}

/* PATH 의 점 i 시각 */
static inline uint64_t pace_path_time_ns(const pace_msg_t *m, uint32_t i)
{
    return m->body.path.t0_ns + (uint64_t)i * m->body.path.dt_ns;
}

/* PATH_S 의 점 i 진행도 */
static inline float pace_path_s_at(const pace_msg_t *m, uint32_t i)
{
    uint32_t n = m->hdr.n_points;
    if (n < 2) return m->body.path_s.s0;
    return m->body.path_s.s0 + (m->body.path_s.s1 - m->body.path_s.s0) * (float)i / (float)(n - 1);
}

#ifdef __cplusplus
}
#endif
#endif /* PACE_MSG_H */
