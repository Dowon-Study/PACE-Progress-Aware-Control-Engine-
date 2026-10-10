#define _GNU_SOURCE
#include "pace/shm.h"
#include <errno.h>
#include <stdio.h>
#include <fcntl.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static size_t align_up(size_t x, size_t a) { return (x + a - 1) & ~(a - 1); }

static uint64_t now_ns(void)
{
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

/* 레이아웃 계산: 모든 영역은 4096 정렬 (페이지 단위 사전 터치가 쉬움) */
static void layout(pace_shm_header_t *h)
{
    size_t off = sizeof(pace_shm_header_t);
    off = align_up(off, 4096);
    for (unsigned i = 0; i < PACE_SHM_NQUEUES; ++i) {
        h->off_queue[i] = off;
        off = align_up(off + pace_spsc_bytes(PACE_SHM_QUEUE_CAP, sizeof(pace_msg_t)), 4096);
    }
    h->off_state = off;    off = align_up(off + pace_seqlock_bytes(sizeof(pace_robot_state_t)), 4096);
    h->off_contract = off; off = align_up(off + pace_seqlock_bytes(sizeof(pace_contract_t)), 4096);
    h->off_limits = off;   off = align_up(off + pace_seqlock_bytes(sizeof(pace_hal_limits_t)), 4096);
    h->off_metrics = off;  off = align_up(off + pace_spsc_bytes(PACE_SHM_METRICS_CAP, sizeof(pace_tick_record_t)), 4096);
    h->off_frame = off;    off = align_up(off + pace_seqlock_bytes(sizeof(pace_frame_t)), 4096);
    h->total_bytes = off;
    h->queue_cap = PACE_SHM_QUEUE_CAP; h->metrics_cap = PACE_SHM_METRICS_CAP;
    h->msg_size = sizeof(pace_msg_t); h->record_size = sizeof(pace_tick_record_t);
}

size_t pace_shm_total_bytes(void)
{
    pace_shm_header_t h; memset(&h, 0, sizeof h); layout(&h); return h.total_bytes;
}

static void bind(pace_shm_t *out)
{
    uint8_t *b = (uint8_t *)out->base;
    out->hdr = (pace_shm_header_t *)b;
    for (unsigned i = 0; i < PACE_SHM_NQUEUES; ++i) out->queue[i] = (pace_spsc_t *)(b + out->hdr->off_queue[i]);
    out->state    = (pace_seqlock_t *)(b + out->hdr->off_state);
    out->contract = (pace_seqlock_t *)(b + out->hdr->off_contract);
    out->limits   = (pace_seqlock_t *)(b + out->hdr->off_limits);
    out->metrics  = (pace_spsc_t *)(b + out->hdr->off_metrics);
    out->frame    = (pace_seqlock_t *)(b + out->hdr->off_frame);
}

int pace_shm_create(const char *name, pace_shm_t *out)
{
    memset(out, 0, sizeof *out);
    snprintf(out->name, sizeof out->name, "%s", name);
    pace_shm_header_t tmp; memset(&tmp, 0, sizeof tmp); layout(&tmp);

    shm_unlink(name);
    int fd = shm_open(name, O_CREAT | O_EXCL | O_RDWR, 0660);
    if (fd < 0) return -errno;
    if (ftruncate(fd, (off_t)tmp.total_bytes) != 0) { int e = errno; close(fd); return -e; }
    void *base = mmap(NULL, tmp.total_bytes, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_POPULATE, fd, 0);
    if (base == MAP_FAILED) { int e = errno; close(fd); return -e; }
    /* 사전 터치 (페이지 폴트를 지금 다 낸다) + mlock (실패해도 치명적이진 않음: 권한 없을 수 있음) */
    memset(base, 0, tmp.total_bytes);
    mlock(base, tmp.total_bytes);

    out->fd = fd; out->base = base; out->size = tmp.total_bytes;
    pace_shm_header_t *h = (pace_shm_header_t *)base;
    *h = tmp;
    h->magic = PACE_SHM_MAGIC; h->version = PACE_SHM_VERSION; h->created_ns = now_ns();
    bind(out);
    for (unsigned i = 0; i < PACE_SHM_NQUEUES; ++i) pace_spsc_init(out->queue[i], PACE_SHM_QUEUE_CAP, sizeof(pace_msg_t));
    pace_seqlock_init(out->state, sizeof(pace_robot_state_t));
    pace_seqlock_init(out->contract, sizeof(pace_contract_t));
    pace_seqlock_init(out->limits, sizeof(pace_hal_limits_t));
    pace_spsc_init(out->metrics, PACE_SHM_METRICS_CAP, sizeof(pace_tick_record_t));
    pace_seqlock_init(out->frame, sizeof(pace_frame_t));
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    return 0;
}

int pace_shm_open(const char *name, pace_shm_t *out)
{
    memset(out, 0, sizeof *out);
    snprintf(out->name, sizeof out->name, "%s", name);
    int fd = shm_open(name, O_RDWR, 0);
    if (fd < 0) return -errno;
    struct stat st; if (fstat(fd, &st) != 0) { int e = errno; close(fd); return -e; }
    if ((size_t)st.st_size < sizeof(pace_shm_header_t)) { close(fd); return -EINVAL; }
    void *base = mmap(NULL, (size_t)st.st_size, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_POPULATE, fd, 0);
    if (base == MAP_FAILED) { int e = errno; close(fd); return -e; }
    pace_shm_header_t *h = (pace_shm_header_t *)base;
    if (h->magic != PACE_SHM_MAGIC || h->version != PACE_SHM_VERSION || h->total_bytes != (uint64_t)st.st_size
        || h->msg_size != sizeof(pace_msg_t) || h->record_size != sizeof(pace_tick_record_t)) {
        munmap(base, (size_t)st.st_size); close(fd); return -EPROTO;
    }
    mlock(base, (size_t)st.st_size);
    out->fd = fd; out->base = base; out->size = (size_t)st.st_size;
    bind(out);
    return 0;
}

void pace_shm_close(pace_shm_t *h)
{
    if (h->base) munmap(h->base, h->size);
    if (h->fd >= 0) close(h->fd);
    memset(h, 0, sizeof *h); h->fd = -1;
}

int pace_shm_unlink(const char *name) { return shm_unlink(name) == 0 ? 0 : -errno; }
