#undef NDEBUG
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "pace/kin.h"
static double now_us(void) { struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); return ts.tv_sec * 1e6 + ts.tv_nsec / 1e3; }
int main(int argc, char **argv)
{
    const char *xml = argc > 1 ? argv[1] : "../models/ur5e/weld_ur5e.xml"; char err[256];
    pace_kin_t *k = pace_kin_create(xml, "tool", err, sizeof err); if (!k) { fprintf(stderr, "%s\n", err); return 1; }
    assert(pace_kin_dof(k) == 6);
    float q0[6] = { 2.5907f, -1.5383f, 1.6162f, -1.6484f, -1.5711f, -2.1217f };   /* weld_home */
    float pos[3], quat[4], R[9]; pace_kin_fk(k, q0, pos, quat, R);
    printf("fk weld_home: pos=(%.4f %.4f %.4f) z-axis=(%.2f %.2f %.2f)\n", pos[0], pos[1], pos[2], R[2], R[5], R[8]);
    assert(fabsf(pos[0] - 0.5f) < 2e-3 && fabsf(pos[1] + 0.15f) < 2e-3 && fabsf(pos[2] - 0.3122f) < 2e-3);
    /* IK: 목표를 2mm 옆, 1mm 위로 → 1~3 반복으로 수렴, 시간 측정 */
    float tgt[3] = { pos[0] + 0.002f, pos[1] + 0.001f, pos[2] + 0.001f }, q1[6], ep, er;
    double t0 = now_us(); pace_kin_ik(k, q0, tgt, R, 3, 1e-6f, q1, &ep, &er); double dt = now_us() - t0;
    printf("ik 3 iters: pos_err=%.3f mm rot_err=%.5f, %.1f us\n", ep * 1e3, er, dt);
    assert(ep < 2e-5 && er < 1e-3);
    /* 1000회 WCET */
    double worst = 0; for (int i = 0; i < 1000; ++i) { float t2[3] = { tgt[0] + 1e-5f * i, tgt[1], tgt[2] }; double a = now_us(); pace_kin_ik(k, q1, t2, R, 2, 1e-6f, q1, &ep, &er); double d = now_us() - a; if (d > worst) worst = d; }
    printf("ik 2 iters × 1000: worst %.1f us, final pos_err=%.3f mm\n", worst, ep * 1e3);
    /* 접선 회전 규약: 접선 +x, 진행각 0 → z = -ẑ, x = +x */
    float tan[3] = { 1, 0, 0 }, R2[9]; pace_kin_tool_rotation(tan, 0.0f, R2);
    assert(fabsf(R2[0] - 1) < 1e-6 && fabsf(R2[8] + 1) < 1e-6 && fabsf(R2[4] + 1) < 1e-6);
    pace_kin_destroy(k); printf("kin OK\n"); return 0;
}
