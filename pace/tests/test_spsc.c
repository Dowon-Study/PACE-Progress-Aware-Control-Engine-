#undef NDEBUG   /* 테스트는 Release 빌드에서도 assert 를 살린다 (초기화 호출이 assert 안에 있음) */
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include "pace/spsc.h"

#define N 2000000ull
typedef struct { uint64_t v; uint64_t pad[7]; } item_t;   /* 64바이트 원소 */

static pace_spsc_t *q;
static void *producer(void *a) { (void)a; for (uint64_t i = 0; i < N; ++i) { item_t it = { .v = i }; while (!pace_spsc_push(q, &it)) ; } return NULL; }
static void *consumer(void *a) { (void)a; item_t it; for (uint64_t i = 0; i < N; ++i) { while (!pace_spsc_pop(q, &it)) ; if (it.v != i) { fprintf(stderr, "ORDER BROKEN at %llu got %llu\n", (unsigned long long)i, (unsigned long long)it.v); exit(2); } } return NULL; }

int main(void)
{
    /* 1) 단일 스레드 의미론: 비움/가득참/랩어라운드/최신만 */
    uint32_t cap = 8;
    q = aligned_alloc(64, pace_spsc_bytes(cap, sizeof(item_t)));
    assert(pace_spsc_init(q, cap, sizeof(item_t)));
    assert(!pace_spsc_init(q, 6, sizeof(item_t)));          /* 2의 거듭제곱 아님 */
    assert(pace_spsc_init(q, cap, sizeof(item_t)));
    item_t it, out;
    assert(!pace_spsc_pop(q, &out));
    for (uint64_t i = 0; i < cap; ++i) { it.v = i; assert(pace_spsc_push(q, &it)); }
    it.v = 99; assert(!pace_spsc_push(q, &it)); assert(q->drops == 1);
    assert(pace_spsc_count(q) == cap);
    for (uint64_t i = 0; i < cap; ++i) { assert(pace_spsc_pop(q, &out)); assert(out.v == i); }
    assert(!pace_spsc_pop(q, &out));
    for (uint64_t r = 0; r < 1000; ++r) { it.v = r; assert(pace_spsc_push(q, &it)); assert(pace_spsc_pop(q, &out)); assert(out.v == r); } /* 랩어라운드 */
    for (uint64_t i = 0; i < 5; ++i) { it.v = 100 + i; assert(pace_spsc_push(q, &it)); }
    uint32_t skipped = 0; assert(pace_spsc_pop_latest(q, &out, &skipped)); assert(out.v == 104 && skipped == 4); assert(pace_spsc_count(q) == 0);
    free(q);

    /* 2) 두 스레드, 2M 원소, 순서·손실 없음 */
    cap = 64;
    q = aligned_alloc(64, pace_spsc_bytes(cap, sizeof(item_t)));
    assert(pace_spsc_init(q, cap, sizeof(item_t)));
    pthread_t p, c;
    pthread_create(&p, NULL, producer, NULL); pthread_create(&c, NULL, consumer, NULL);
    pthread_join(p, NULL); pthread_join(c, NULL);
    assert(pace_spsc_count(q) == 0);
    printf("spsc OK (2 threads, %llu items, drops=%llu)\n", N, (unsigned long long)q->drops);
    free(q);
    return 0;
}
