/*
 * 단일 작성자 / 다중 독자 스냅샷 버퍼 (seqlock). 공유메모리용.
 *  - 레이아웃: [pace_seqlock_t][data_size]
 *  - 작성자(실시간 루프 또는 시뮬 렌더 스레드)는 절대 기다리지 않는다
 *  - 독자는 일관된 스냅샷을 얻을 때까지 재시도 (독자는 비실시간 쪽이거나, 데이터가 작아 재시도가 μs 단위)
 */
#ifndef PACE_SEQLOCK_H
#define PACE_SEQLOCK_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <stdatomic.h>
#include "pace/spsc.h"   /* PACE_CACHELINE */

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    _Alignas(PACE_CACHELINE) atomic_uint_fast64_t seq;   /* 홀수 = 쓰는 중 */
    uint32_t data_size;
    uint32_t _pad0;
    uint64_t writes;
    uint8_t _pad1[PACE_CACHELINE - sizeof(atomic_uint_fast64_t) - 16];
} pace_seqlock_t;

_Static_assert(sizeof(pace_seqlock_t) == PACE_CACHELINE, "pace_seqlock_t layout");

static inline size_t pace_seqlock_bytes(uint32_t data_size) { return sizeof(pace_seqlock_t) + data_size; }
static inline uint8_t *pace_seqlock_data(pace_seqlock_t *s) { return (uint8_t *)s + sizeof(pace_seqlock_t); }

static inline void pace_seqlock_init(pace_seqlock_t *s, uint32_t data_size)
{
    atomic_store_explicit(&s->seq, 0, memory_order_relaxed);
    s->data_size = data_size; s->writes = 0;
    atomic_thread_fence(memory_order_seq_cst);
}

static inline void pace_seqlock_write(pace_seqlock_t *s, const void *data)
{
    uint64_t v = atomic_load_explicit(&s->seq, memory_order_relaxed);
    atomic_store_explicit(&s->seq, v + 1, memory_order_relaxed);   /* 홀수: 쓰기 시작 */
    atomic_thread_fence(memory_order_release);
    memcpy(pace_seqlock_data(s), data, s->data_size);
    s->writes++;
    atomic_store_explicit(&s->seq, v + 2, memory_order_release);   /* 짝수: 완료 */
}

/* 일관된 스냅샷을 out 에 복사. 작성자가 한 번도 안 썼으면 false. max_retry 초과 시 false. */
static inline bool pace_seqlock_read(pace_seqlock_t *s, void *out, uint32_t max_retry, uint64_t *seq_out)
{
    for (uint32_t i = 0; i <= max_retry; ++i) {
        uint64_t s1 = atomic_load_explicit(&s->seq, memory_order_acquire);
        if (s1 == 0) return false;
        if (s1 & 1) continue;
        memcpy(out, pace_seqlock_data(s), s->data_size);
        atomic_thread_fence(memory_order_acquire);
        uint64_t s2 = atomic_load_explicit(&s->seq, memory_order_relaxed);
        if (s1 == s2) { if (seq_out) *seq_out = s1; return true; }
    }
    return false;
}

#ifdef __cplusplus
}
#endif
#endif /* PACE_SEQLOCK_H */
