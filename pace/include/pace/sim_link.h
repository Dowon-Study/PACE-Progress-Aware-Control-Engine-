/*
 * 제어기 ↔ 시뮬레이터 프로세스 락스텝 링크 (HAL "sim_shm" 백엔드의 전송 계층)
 *
 *  제어기(1kHz, 격리 코어)        시뮬 프로세스(일반 코어, 비실시간)
 *  ───────────────────────        ──────────────────────────────────
 *  cmd 에 tick, q_cmd 기록   ──►  futex 로 깨어남 → cmd 읽기 → mj_step (1ms 분량) → state 기록
 *  futex_tick 증가 + WAKE
 *  다음 틱에 state 읽기     ◄──   (한 틱 늦은 상태를 읽는 것이 정상: 실 로봇의 센서 지연과 같음)
 *
 *  제어기는 절대 기다리지 않는다. 시뮬이 늦으면 지난 상태를 다시 읽고 lag 를 기록한다.
 *  모든 시각은 제어기 PC CLOCK_MONOTONIC.
 */
#ifndef PACE_SIM_LINK_H
#define PACE_SIM_LINK_H
#include <stdint.h>
#include <stdbool.h>
#include "pace/state.h"
#ifndef __cplusplus
#include <stdatomic.h>
#include "pace/seqlock.h"
#endif
#ifdef __cplusplus
extern "C" {
#endif

#define PACE_SIMLINK_MAGIC   0x53494D4Cu  /* 'SIML' */
#define PACE_SIMLINK_VERSION 1u

typedef struct {
    uint64_t tick;              /* 제어기 틱 번호 */
    uint64_t t_cmd_ns;          /* 명령 기록 시각 */
    uint16_t dof;
    uint16_t mode;              /* pace_mode_t (시각화용) */
    uint32_t stop_level;        /* 0 정상, pace_stop_level_t */
    float q_cmd[PACE_MAX_DOF];
    float qd_cmd[PACE_MAX_DOF];
} pace_sim_cmd_t;

typedef struct {
    uint64_t tick;              /* 이 상태를 만든 명령의 틱 */
    uint64_t t_state_ns;        /* 상태 기록 시각 */
    uint64_t sim_time_ns;       /* 시뮬 내부 시각 */
    uint32_t step_ns;           /* 이번 스텝 연산 시간 */
    uint32_t late;              /* 누적: 스텝 중 다음 명령이 이미 도착한 횟수 (시뮬 지각) */
    pace_robot_state_t st;
    pace_hal_limits_t limits;   /* 모델에서 읽은 로봇별 한계값 (HAL 공통 데이터 구조) */
} pace_sim_state_t;

#ifdef __cplusplus
typedef struct pace_sim_link pace_sim_link_t;   /* C++ 에서는 불투명 (C11 atomics 를 쓰므로 함수 API 만 노출) */
#else
typedef struct pace_sim_link {
    uint32_t magic, version;
    uint64_t created_ns;
    uint8_t  _pad0[48];
    _Alignas(PACE_CACHELINE) atomic_uint_fast32_t futex_tick;   /* 시뮬이 기다리는 워드 */
    uint8_t  _pad1[PACE_CACHELINE - 4];
    _Alignas(PACE_CACHELINE) pace_seqlock_t cmd_lock;  pace_sim_cmd_t   cmd;    /* seqlock 데이터는 lock 바로 뒤 */
    uint8_t  _pad2[PACE_CACHELINE - (sizeof(pace_sim_cmd_t) % PACE_CACHELINE)];
    _Alignas(PACE_CACHELINE) pace_seqlock_t state_lock; pace_sim_state_t state;
} pace_sim_link_t;

PACE_STATIC_ASSERT(offsetof(pace_sim_link_t, cmd) == offsetof(pace_sim_link_t, cmd_lock) + sizeof(pace_seqlock_t), "cmd must follow cmd_lock");
PACE_STATIC_ASSERT(offsetof(pace_sim_link_t, state) == offsetof(pace_sim_link_t, state_lock) + sizeof(pace_seqlock_t), "state must follow state_lock");
#endif

/* 생성/열기 (shm_open). 0 성공 */
int  pace_sim_link_create(const char *name, pace_sim_link_t **out);
int  pace_sim_link_open(const char *name, pace_sim_link_t **out);
void pace_sim_link_close(pace_sim_link_t *l);

/* 제어기 측 */
void pace_sim_link_send_cmd(pace_sim_link_t *l, const pace_sim_cmd_t *c);        /* 기록 + futex wake */
bool pace_sim_link_read_state(pace_sim_link_t *l, pace_sim_state_t *s);
/* 시뮬 측: 새 틱까지 대기 (timeout_ns 후 false), 그 뒤 cmd 읽기 */
bool pace_sim_link_wait_cmd(pace_sim_link_t *l, uint32_t last_tick, uint64_t timeout_ns, pace_sim_cmd_t *c);
void pace_sim_link_write_state(pace_sim_link_t *l, const pace_sim_state_t *s);

#ifdef __cplusplus
}
#endif
#endif
