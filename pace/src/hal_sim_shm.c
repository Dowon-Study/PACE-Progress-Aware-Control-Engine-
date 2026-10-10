/* HAL 백엔드: 공유메모리 락스텝 시뮬레이터 (pace_sim 프로세스) */
#include "pace/hal.h"
#include "pace/sim_link.h"
#include "pace/rt.h"
#include <stdlib.h>
#include <string.h>

typedef struct {
    pace_sim_link_t *link;
    pace_hal_limits_t limits;
    uint64_t last_tick_sent;
    uint64_t last_tick_seen;
    uint64_t lag_ticks;
    pace_sim_state_t ss;
} ctx_t;

static int sim_init(pace_hal_t *h, const char *arg)
{
    ctx_t *c = h->ctx;
    int r = pace_sim_link_open(arg ? arg : "/pace_sim", &c->link);
    if (r) return r;
    /* 한계값은 시뮬이 state 에 dof 를 알려주기 전까지 보수적 기본값. 모델별 값은 설정 파일(8단계)에서. */
    memset(&c->limits, 0, sizeof c->limits);
    c->limits.dof = PACE_MAX_DOF; c->limits.accepts_position = 1; c->limits.accepts_velocity = 1;
    c->limits.native_period_ns = 1000000; c->limits.read_wcet_ns = 20000; c->limits.write_wcet_ns = 20000;
    for (int i = 0; i < (int)PACE_MAX_DOF; ++i) { c->limits.q_min[i] = -6.3f; c->limits.q_max[i] = 6.3f; c->limits.qd_max[i] = 3.15f; c->limits.qdd_max[i] = 20.0f; c->limits.jerk_max[i] = 500.0f; c->limits.tau_max[i] = 150.0f; }
    for (int i = 0; i < 3; ++i) { c->limits.workspace_min[i] = -2.0f; c->limits.workspace_max[i] = 2.0f; }
    return 0;
}
static void sim_shutdown(pace_hal_t *h) { ctx_t *c = h->ctx; pace_sim_link_close(c->link); c->link = NULL; }

static int sim_read(pace_hal_t *h, pace_robot_state_t *st)
{
    ctx_t *c = h->ctx;
    if (!pace_sim_link_read_state(c->link, &c->ss)) { st->hal_fault = 1; return 1; }   /* 시뮬이 아직 아무것도 안 씀 */
    *st = c->ss.st;
    if (c->ss.limits.dof) c->limits = c->ss.limits;   /* 시뮬이 보고한 로봇별 한계값 채택 */
    c->last_tick_seen = c->ss.tick;
    c->lag_ticks = c->last_tick_sent > c->ss.tick ? c->last_tick_sent - c->ss.tick : 0;
    return 0;
}
static int sim_write(pace_hal_t *h, uint64_t tick, uint16_t mode, const float *q, const float *qd, uint16_t dof)
{
    ctx_t *c = h->ctx;
    pace_sim_cmd_t cmd; memset(&cmd, 0, sizeof cmd);
    cmd.tick = tick; cmd.t_cmd_ns = pace_now_ns(); cmd.dof = dof; cmd.mode = mode; cmd.stop_level = 0;
    memcpy(cmd.q_cmd, q, dof * sizeof(float)); if (qd) memcpy(cmd.qd_cmd, qd, dof * sizeof(float));
    pace_sim_link_send_cmd(c->link, &cmd);
    c->last_tick_sent = tick;
    return 0;
}
static int sim_stop(pace_hal_t *h, uint64_t tick, pace_stop_level_t level)
{
    ctx_t *c = h->ctx;
    pace_sim_cmd_t cmd; memset(&cmd, 0, sizeof cmd);
    cmd.tick = tick; cmd.t_cmd_ns = pace_now_ns(); cmd.dof = c->ss.st.dof; cmd.stop_level = level;
    memcpy(cmd.q_cmd, c->ss.st.q, sizeof cmd.q_cmd);   /* 현재 위치 유지 */
    pace_sim_link_send_cmd(c->link, &cmd);
    c->last_tick_sent = tick;
    return 0;
}
static const pace_hal_limits_t *sim_limits(pace_hal_t *h) { return &((ctx_t *)h->ctx)->limits; }
static uint64_t sim_lag(pace_hal_t *h) { return ((ctx_t *)h->ctx)->lag_ticks; }

pace_hal_t *pace_hal_sim_shm_create(void)
{
    pace_hal_t *h = calloc(1, sizeof *h); ctx_t *c = calloc(1, sizeof *c);
    h->name = "sim_shm"; h->ctx = c;
    h->init = sim_init; h->shutdown = sim_shutdown; h->read = sim_read; h->write = sim_write; h->stop = sim_stop;
    h->limits = sim_limits; h->backend_lag_ticks = sim_lag;
    return h;
}
