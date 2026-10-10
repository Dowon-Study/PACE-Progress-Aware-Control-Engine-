#define _GNU_SOURCE
#include "pace/sim_link.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/futex.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static long futex(volatile void *addr, int op, uint32_t val, const struct timespec *to)
{ return syscall(SYS_futex, addr, op, val, to, NULL, 0); }

static uint64_t now_ns(void) { struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); return (uint64_t)ts.tv_sec * 1000000000ull + ts.tv_nsec; }

int pace_sim_link_create(const char *name, pace_sim_link_t **out)
{
    shm_unlink(name);
    int fd = shm_open(name, O_CREAT | O_EXCL | O_RDWR, 0660);
    if (fd < 0) return -errno;
    if (ftruncate(fd, sizeof(pace_sim_link_t)) != 0) { int e = errno; close(fd); return -e; }
    void *p = mmap(NULL, sizeof(pace_sim_link_t), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_POPULATE, fd, 0);
    close(fd);
    if (p == MAP_FAILED) return -errno;
    memset(p, 0, sizeof(pace_sim_link_t)); mlock(p, sizeof(pace_sim_link_t));
    pace_sim_link_t *l = p;
    l->magic = PACE_SIMLINK_MAGIC; l->version = PACE_SIMLINK_VERSION; l->created_ns = now_ns();
    atomic_store(&l->futex_tick, 0);
    pace_seqlock_init(&l->cmd_lock, sizeof(pace_sim_cmd_t));
    pace_seqlock_init(&l->state_lock, sizeof(pace_sim_state_t));
    *out = l; return 0;
}

int pace_sim_link_open(const char *name, pace_sim_link_t **out)
{
    int fd = shm_open(name, O_RDWR, 0);
    if (fd < 0) return -errno;
    struct stat st; if (fstat(fd, &st) != 0 || (size_t)st.st_size != sizeof(pace_sim_link_t)) { close(fd); return -EINVAL; }
    void *p = mmap(NULL, sizeof(pace_sim_link_t), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_POPULATE, fd, 0);
    close(fd);
    if (p == MAP_FAILED) return -errno;
    pace_sim_link_t *l = p;
    if (l->magic != PACE_SIMLINK_MAGIC || l->version != PACE_SIMLINK_VERSION) { munmap(p, sizeof *l); return -EPROTO; }
    mlock(p, sizeof(pace_sim_link_t));
    *out = l; return 0;
}

void pace_sim_link_close(pace_sim_link_t *l) { if (l) munmap(l, sizeof *l); }

void pace_sim_link_send_cmd(pace_sim_link_t *l, const pace_sim_cmd_t *c)
{
    pace_seqlock_write(&l->cmd_lock, c);
    atomic_store_explicit(&l->futex_tick, (uint32_t)c->tick, memory_order_release);
    futex(&l->futex_tick, FUTEX_WAKE, 1, NULL);
}

bool pace_sim_link_read_state(pace_sim_link_t *l, pace_sim_state_t *s)
{ return pace_seqlock_read(&l->state_lock, s, 16, NULL); }

bool pace_sim_link_wait_cmd(pace_sim_link_t *l, uint32_t last_tick, uint64_t timeout_ns, pace_sim_cmd_t *c)
{
    struct timespec to = { .tv_sec = (time_t)(timeout_ns / 1000000000ull), .tv_nsec = (long)(timeout_ns % 1000000000ull) };
    for (;;) {
        uint32_t cur = atomic_load_explicit(&l->futex_tick, memory_order_acquire);
        if (cur != last_tick) break;
        long r = futex(&l->futex_tick, FUTEX_WAIT, cur, &to);
        if (r != 0 && errno == ETIMEDOUT) return false;
    }
    return pace_seqlock_read(&l->cmd_lock, c, 64, NULL);
}

void pace_sim_link_write_state(pace_sim_link_t *l, const pace_sim_state_t *s)
{ pace_seqlock_write(&l->state_lock, s); }
