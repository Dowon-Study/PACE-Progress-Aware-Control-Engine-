#define _GNU_SOURCE
#include "pace/rt.h"
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <pthread.h>
#if defined(__x86_64__)
#include <xmmintrin.h>
#include <pmmintrin.h>
#endif

#define PACE_STACK_PREFAULT (1u << 20)   /* 1 MB */

uint64_t pace_now_ns(void)
{
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

void pace_sleep_until_ns(uint64_t t)
{
    struct timespec ts = { .tv_sec = (time_t)(t / 1000000000ull), .tv_nsec = (long)(t % 1000000000ull) };
    while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL) == EINTR) ;
}

static void prefault_stack(void)
{
    volatile unsigned char buf[PACE_STACK_PREFAULT];
    for (size_t i = 0; i < sizeof buf; i += 4096) buf[i] = 0;
    (void)buf[0];
}

pace_rt_result_t pace_rt_setup(const pace_rt_config_t *cfg)
{
    pace_rt_result_t r = { 0, 0, 0, 0, 0, -1 };
    if (cfg->cpu >= 0) {
        cpu_set_t set; CPU_ZERO(&set); CPU_SET(cfg->cpu, &set);
        r.affinity = pthread_setaffinity_np(pthread_self(), sizeof set, &set) == 0 ? 0 : -errno;
    }
    if (cfg->lock_memory) {
        r.mlock = mlockall(MCL_CURRENT | MCL_FUTURE) == 0 ? 0 : -errno;
        prefault_stack();
    }
    if (cfg->priority > 0) {
        struct sched_param sp; memset(&sp, 0, sizeof sp); sp.sched_priority = cfg->priority;
        r.sched = pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp) == 0 ? 0 : -errno;
    }
    if (cfg->dma_latency) {
        int fd = open("/dev/cpu_dma_latency", O_WRONLY);
        if (fd < 0) r.dma = -errno;
        else { int32_t zero = 0; if (write(fd, &zero, sizeof zero) != (ssize_t)sizeof zero) { r.dma = -errno; close(fd); } else { r.dma = 0; r.dma_fd = fd; } }
    }
    if (cfg->ftz_daz) {
#if defined(__x86_64__)
        _MM_SET_FLUSH_ZERO_MODE(_MM_FLUSH_ZERO_ON);
        _MM_SET_DENORMALS_ZERO_MODE(_MM_DENORMALS_ZERO_ON);
        r.ftz = 0;
#else
        r.ftz = -ENOTSUP;
#endif
    }
    return r;
}

void pace_rt_teardown(pace_rt_result_t *r)
{
    if (r->dma_fd >= 0) { close(r->dma_fd); r->dma_fd = -1; }
}
