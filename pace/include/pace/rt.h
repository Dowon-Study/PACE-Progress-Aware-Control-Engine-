/* 실시간 스레드 설정과 시간 유틸 (docs/IDEA_FIXED.md 5절·8절) */
#ifndef PACE_RT_H
#define PACE_RT_H
#include <stdint.h>
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int cpu;                 /* -1: 고정 안 함 */
    int priority;            /* SCHED_FIFO 우선순위, 0: 일반 스케줄링 */
    bool lock_memory;        /* mlockall + 스택 사전 터치 */
    bool dma_latency;        /* /dev/cpu_dma_latency 에 0 기록 (C-state 진입 차단) */
    bool ftz_daz;            /* 비정규수 연산 차단 (MXCSR FTZ/DAZ) */
} pace_rt_config_t;

/* 적용 결과 보고 (각 항목 0 성공 / 음수 errno). 전부 적용되지 않아도 계속 실행 가능 (경고로 처리). */
typedef struct { int affinity, sched, mlock, dma, ftz; int dma_fd; } pace_rt_result_t;

pace_rt_result_t pace_rt_setup(const pace_rt_config_t *cfg);
void pace_rt_teardown(pace_rt_result_t *r);

uint64_t pace_now_ns(void);                       /* CLOCK_MONOTONIC */
void     pace_sleep_until_ns(uint64_t t_abs_ns);  /* clock_nanosleep TIMER_ABSTIME, EINTR 재시도 */

#ifdef __cplusplus
}
#endif
#endif
