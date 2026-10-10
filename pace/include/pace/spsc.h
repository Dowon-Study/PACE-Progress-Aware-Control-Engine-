/*
 * 단일 생산자 / 단일 소비자 락프리 링버퍼 (공유메모리용, 포인터 없음)
 *  - 헤더 바로 뒤에 버퍼가 이어진다: [pace_spsc_t][elem_size * capacity]
 *  - head(생산자 전용)와 tail(소비자 전용)을 서로 다른 캐시라인에 두어 허위 공유를 막는다
 *  - capacity 는 2의 거듭제곱. 원소는 memcpy 로 복사(값 전달) → 소비자는 생산자의 이후 덮어쓰기에 영향받지 않음
 *  - 실시간 루프 쪽(소비자 또는 생산자)은 대기하지 않는다: 비어 있으면 false, 가득 차면 false
 */
#ifndef PACE_SPSC_H
#define PACE_SPSC_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <stdatomic.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PACE_CACHELINE 64

typedef struct {
    _Alignas(PACE_CACHELINE) atomic_uint_fast64_t head;   /* 다음에 쓸 인덱스 (생산자만 수정) */
    uint8_t _pad0[PACE_CACHELINE - sizeof(atomic_uint_fast64_t)];
    _Alignas(PACE_CACHELINE) atomic_uint_fast64_t tail;   /* 다음에 읽을 인덱스 (소비자만 수정) */
    uint8_t _pad1[PACE_CACHELINE - sizeof(atomic_uint_fast64_t)];
    _Alignas(PACE_CACHELINE) uint32_t capacity;
    uint32_t elem_size;
    uint64_t mask;
    uint64_t drops;                                       /* 가득 차서 버린 횟수 (생산자가 증가, 진단용) */
    uint8_t _pad2[PACE_CACHELINE - 24];
} pace_spsc_t;

_Static_assert(sizeof(pace_spsc_t) == 3 * PACE_CACHELINE, "pace_spsc_t layout");

static inline size_t pace_spsc_bytes(uint32_t capacity, uint32_t elem_size)
{
    return sizeof(pace_spsc_t) + (size_t)capacity * elem_size;
}

static inline uint8_t *pace_spsc_buf(pace_spsc_t *q) { return (uint8_t *)q + sizeof(pace_spsc_t); }

static inline bool pace_spsc_init(pace_spsc_t *q, uint32_t capacity, uint32_t elem_size)
{
    if (capacity == 0 || (capacity & (capacity - 1)) != 0 || elem_size == 0) return false;
    atomic_store_explicit(&q->head, 0, memory_order_relaxed);
    atomic_store_explicit(&q->tail, 0, memory_order_relaxed);
    q->capacity = capacity; q->elem_size = elem_size; q->mask = capacity - 1; q->drops = 0;
    atomic_thread_fence(memory_order_seq_cst);
    return true;
}

/* 생산자: 복사해서 넣는다. 가득 차면 false (버림, drops++). */
static inline bool pace_spsc_push(pace_spsc_t *q, const void *elem)
{
    uint64_t head = atomic_load_explicit(&q->head, memory_order_relaxed);
    uint64_t tail = atomic_load_explicit(&q->tail, memory_order_acquire);
    if (head - tail >= q->capacity) { q->drops++; return false; }
    memcpy(pace_spsc_buf(q) + (size_t)(head & q->mask) * q->elem_size, elem, q->elem_size);
    atomic_store_explicit(&q->head, head + 1, memory_order_release);
    return true;
}

/* 소비자: 복사해서 꺼낸다. 비어 있으면 false. */
static inline bool pace_spsc_pop(pace_spsc_t *q, void *out)
{
    uint64_t tail = atomic_load_explicit(&q->tail, memory_order_relaxed);
    uint64_t head = atomic_load_explicit(&q->head, memory_order_acquire);
    if (head == tail) return false;
    memcpy(out, pace_spsc_buf(q) + (size_t)(tail & q->mask) * q->elem_size, q->elem_size);
    atomic_store_explicit(&q->tail, tail + 1, memory_order_release);
    return true;
}

/* 소비자: 가장 최근 것만 남기고 오래된 것은 버린다 ("최신 입력만 처리" 큐 깊이 1 정책). 꺼낸 게 있으면 true. */
static inline bool pace_spsc_pop_latest(pace_spsc_t *q, void *out, uint32_t *skipped)
{
    uint64_t tail = atomic_load_explicit(&q->tail, memory_order_relaxed);
    uint64_t head = atomic_load_explicit(&q->head, memory_order_acquire);
    if (head == tail) { if (skipped) *skipped = 0; return false; }
    uint64_t last = head - 1;
    memcpy(out, pace_spsc_buf(q) + (size_t)(last & q->mask) * q->elem_size, q->elem_size);
    if (skipped) *skipped = (uint32_t)(last - tail);
    atomic_store_explicit(&q->tail, head, memory_order_release);
    return true;
}

static inline uint64_t pace_spsc_count(const pace_spsc_t *q)
{
    uint64_t head = atomic_load_explicit(&q->head, memory_order_acquire);
    uint64_t tail = atomic_load_explicit(&q->tail, memory_order_acquire);
    return head - tail;
}

#ifdef __cplusplus
}
#endif
#endif /* PACE_SPSC_H */
