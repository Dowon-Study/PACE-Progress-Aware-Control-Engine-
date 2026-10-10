#undef NDEBUG   /* 테스트는 Release 빌드에서도 assert 를 살린다 (초기화 호출이 assert 안에 있음) */
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include "pace/seqlock.h"

typedef struct { uint64_t a[64]; } blob_t;   /* 512바이트, 모든 필드가 같은 값이어야 일관 */
static pace_seqlock_t *s; static atomic_int stop;
static void *writer(void *x) { (void)x; blob_t b; for (uint64_t v = 1; !atomic_load(&stop); ++v) { for (int i = 0; i < 64; ++i) b.a[i] = v; pace_seqlock_write(s, &b); } return NULL; }
static void *reader(void *x) { long ok = 0, torn = 0, fail = 0; blob_t b; for (long i = 0; i < 2000000; ++i) { if (!pace_seqlock_read(s, &b, 1000, NULL)) { fail++; continue; } for (int k = 1; k < 64; ++k) if (b.a[k] != b.a[0]) { torn++; break; } ok++; } long *r = x; r[0] = ok; r[1] = torn; r[2] = fail; return NULL; }

int main(void)
{
    s = aligned_alloc(64, pace_seqlock_bytes(sizeof(blob_t)));
    pace_seqlock_init(s, sizeof(blob_t));
    blob_t b; assert(!pace_seqlock_read(s, &b, 10, NULL));        /* 아직 안 씀 */
    for (int i = 0; i < 64; ++i) b.a[i] = 7; pace_seqlock_write(s, &b);
    blob_t o; uint64_t seq; assert(pace_seqlock_read(s, &o, 10, &seq)); assert(o.a[63] == 7 && seq == 2);
    pthread_t w, r[3]; long res[3][3];
    pthread_create(&w, NULL, writer, NULL);
    for (int i = 0; i < 3; ++i) pthread_create(&r[i], NULL, reader, res[i]);
    for (int i = 0; i < 3; ++i) pthread_join(r[i], NULL);
    atomic_store(&stop, 1); pthread_join(w, NULL);
    long torn = res[0][1] + res[1][1] + res[2][1];
    printf("seqlock: readers ok=%ld torn=%ld fail=%ld writes=%llu\n", res[0][0] + res[1][0] + res[2][0], torn, res[0][2] + res[1][2] + res[2][2], (unsigned long long)s->writes);
    assert(torn == 0);
    free(s); return 0;
}
