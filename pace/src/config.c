#include "pace/config.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void pace_config_defaults(pace_config_t *c)
{
    memset(c, 0, sizeof *c);
    c->val_limit_margin = 0.02f; c->val_dev_max = 0.08f; c->val_conf_min_ai = 0.2f; c->val_conf_min_local = 0.3f;
    c->val_t0_past_max_ns = 1500000000ull; c->val_t0_future_max_ns = 500000000ull; c->val_dt_min_ns = 1000000ull; c->val_dt_max_ns = 200000000ull;
    c->mon_limit_frac = 0.9f; c->mon_track_err_max = 0.10f; c->mon_lookahead_steps = 5; c->mon_lookahead_dt_ns = 10000000ull;
    c->mon_t_dead_ns = 1500000000ull; c->mon_buffer_low_ns = 200000000ull; c->mon_slow_scale = 0.5f; c->mon_hysteresis_ticks = 20; c->stop_estop_after_ns = 2000000000ull; c->local_enable = 0; c->local_max_ns = 3000000000ull; c->local_resplice_ns = 300000000ull; c->local_speed = 0.8f; c->advisor_stale_ns = 500000000ull; c->mon_force_slow = 2.0f; c->mon_force_stop = 30.0f; c->corr_force_lift = 0.012f; c->corr_force_hold_ns = 1000000000ull; c->splice_blend_rate = 0.2f;
    c->cmd_speed_ramp_per_s = 2.0f; c->cmd_qd_frac = 1.0f; c->cmd_qdd_frac = 1.0f;
    c->pace_enable = 1; c->pace_margin_target_ns = 200000000ull; c->pace_vmin = 0.2f; c->pace_jitter_k = 2.0f;
    c->ext_enable = 1; c->ext_max_ns = 400000000ull; c->ext_max_rad = 0.05f;
    c->corr_lat_max = 0.015f; c->corr_h_max = 0.010f; c->corr_ang_max = 0.3f; c->corr_jump_max = 0.003f; c->corr_stale_slow_ns = 500000000ull; c->corr_blend_ns = 100000000ull; c->ik_iters = 2;
}

#define KV_F(name) if (!strcmp(k, #name)) { c->name = (float)atof(v); continue; }
#define KV_U(name) if (!strcmp(k, #name)) { c->name = strtoull(v, NULL, 10); continue; }

int pace_config_load(pace_config_t *c, const char *path)
{
    FILE *f = fopen(path, "r"); if (!f) return -errno;
    char line[256]; int ln = 0;
    while (fgets(line, sizeof line, f)) {
        ln++; char *p = line; while (*p == ' ' || *p == '\t') p++;
        if (*p == '#' || *p == '\n' || *p == 0) continue;
        char *eq = strchr(p, '='); if (!eq) { fclose(f); return ln; }
        *eq = 0; char *k = p, *v = eq + 1; char *e = k + strlen(k); while (e > k && (e[-1] == ' ' || e[-1] == '\t')) *--e = 0;
        while (*v == ' ' || *v == '\t') v++;
        KV_F(val_limit_margin) KV_F(val_dev_max) KV_F(val_conf_min_ai) KV_F(val_conf_min_local)
        KV_U(val_t0_past_max_ns) KV_U(val_t0_future_max_ns) KV_U(val_dt_min_ns) KV_U(val_dt_max_ns)
        KV_F(mon_limit_frac) KV_F(mon_track_err_max) KV_U(mon_lookahead_steps) KV_U(mon_lookahead_dt_ns) KV_U(mon_t_dead_ns) KV_U(mon_buffer_low_ns)
        KV_F(mon_slow_scale) KV_U(mon_hysteresis_ticks) KV_U(stop_estop_after_ns) KV_U(local_enable) KV_U(local_max_ns) KV_U(local_resplice_ns) KV_F(local_speed) KV_U(advisor_stale_ns) KV_F(mon_force_slow) KV_F(mon_force_stop) KV_F(corr_force_lift) KV_U(corr_force_hold_ns) KV_F(splice_blend_rate) KV_F(cmd_speed_ramp_per_s) KV_F(cmd_qd_frac) KV_F(cmd_qdd_frac)
        KV_U(pace_enable) KV_U(pace_margin_target_ns) KV_F(pace_vmin) KV_F(pace_jitter_k) KV_U(ext_enable) KV_U(ext_max_ns) KV_F(ext_max_rad)
        KV_F(corr_lat_max) KV_F(corr_h_max) KV_F(corr_ang_max) KV_F(corr_jump_max) KV_U(corr_stale_slow_ns) KV_U(corr_blend_ns) KV_U(ik_iters)
        fclose(f); return ln;   /* 모르는 키 */
    }
    fclose(f); return 0;
}

void pace_config_print(const pace_config_t *c, void *file)
{
    FILE *f = file;
    fprintf(f, "[cfg] validator: margin=%.3f dev_max=%.3f conf_min(ai=%.2f local=%.2f) t0 past=%llums future=%llums\n", c->val_limit_margin, c->val_dev_max, c->val_conf_min_ai, c->val_conf_min_local, (unsigned long long)c->val_t0_past_max_ns / 1000000, (unsigned long long)c->val_t0_future_max_ns / 1000000);
    fprintf(f, "[cfg] pacing: enable=%u margin_target=%llums vmin=%.2f jitter_k=%.1f | extrap: enable=%u max=%llums max_rad=%.3f\n", c->pace_enable, (unsigned long long)c->pace_margin_target_ns / 1000000, c->pace_vmin, c->pace_jitter_k, c->ext_enable, (unsigned long long)c->ext_max_ns / 1000000, c->ext_max_rad);
    fprintf(f, "[cfg] monitor: limit_frac=%.2f track_err=%.3f lookahead=%ux%llums t_dead=%llums buffer_low=%llums slow=%.2f hyst=%u estop_after=%llums\n", c->mon_limit_frac, c->mon_track_err_max, c->mon_lookahead_steps, (unsigned long long)c->mon_lookahead_dt_ns / 1000000, (unsigned long long)c->mon_t_dead_ns / 1000000, (unsigned long long)c->mon_buffer_low_ns / 1000000, c->mon_slow_scale, c->mon_hysteresis_ticks, (unsigned long long)c->stop_estop_after_ns / 1000000);
}
