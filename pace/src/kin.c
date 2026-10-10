#include "pace/kin.h"
#include <mujoco/mujoco.h>
#include <stdio.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

struct pace_kin { mjModel *m; mjData *d; int site; int dof; double *jacp, *jacr; };

pace_kin_t *pace_kin_create(const char *model_xml, const char *tool_site, char *err, int errlen)
{
    pace_kin_t *k = calloc(1, sizeof *k);
    k->m = mj_loadXML(model_xml, NULL, err, errlen);
    if (!k->m) { free(k); return NULL; }
    k->d = mj_makeData(k->m);
    k->site = mj_name2id(k->m, mjOBJ_SITE, tool_site);
    if (k->site < 0) { snprintf(err, errlen, "site '%s' not found", tool_site); mj_deleteData(k->d); mj_deleteModel(k->m); free(k); return NULL; }
    k->dof = k->m->nv < PACE_KIN_MAXDOF ? k->m->nv : PACE_KIN_MAXDOF;
    k->jacp = calloc(3 * k->m->nv, sizeof(double)); k->jacr = calloc(3 * k->m->nv, sizeof(double));
    /* 사전 터치: 첫 호출의 페이지 폴트를 지금 낸다 */
    mj_kinematics(k->m, k->d); mj_comPos(k->m, k->d); mj_jacSite(k->m, k->d, k->jacp, k->jacr, k->site);
    return k;
}
void pace_kin_destroy(pace_kin_t *k) { if (!k) return; free(k->jacp); free(k->jacr); mj_deleteData(k->d); mj_deleteModel(k->m); free(k); }
int pace_kin_dof(const pace_kin_t *k) { return k->dof; }

void pace_kin_fk(pace_kin_t *k, const float *q, float pos[3], float quat[4], float rot9[9])
{
    for (int j = 0; j < k->dof; ++j) k->d->qpos[j] = q[j];
    mj_kinematics(k->m, k->d);
    for (int i = 0; i < 3; ++i) pos[i] = (float)k->d->site_xpos[3 * k->site + i];
    for (int i = 0; i < 9; ++i) rot9[i] = (float)k->d->site_xmat[9 * k->site + i];
    if (quat) { mjtNum qd[4]; mju_mat2Quat(qd, k->d->site_xmat + 9 * k->site); for (int i = 0; i < 4; ++i) quat[i] = (float)qd[i]; }
}

void pace_kin_ik(pace_kin_t *k, const float *q_in, const float pos[3], const float rot9[9], int iters, float damping,
                 float *q_out, float *err_pos, float *err_rot)
{
    mjModel *m = k->m; mjData *d = k->d; int n = k->dof;
    for (int j = 0; j < n; ++j) d->qpos[j] = q_in[j];
    mjtNum Rt[9]; for (int i = 0; i < 9; ++i) Rt[i] = rot9[i];
    double ep_n = 0, er_n = 0;
    for (int it = 0; it < iters; ++it) {
        mj_kinematics(m, d); mj_comPos(m, d);
        mjtNum ep[3], er[3], Rc_T[9], Rerr[9], qerr[4];
        for (int i = 0; i < 3; ++i) ep[i] = pos[i] - d->site_xpos[3 * k->site + i];
        mju_transpose(Rc_T, d->site_xmat + 9 * k->site, 3, 3); mju_mulMatMat(Rerr, Rt, Rc_T, 3, 3, 3);
        mju_mat2Quat(qerr, Rerr); mju_quat2Vel(er, qerr, 1.0);
        ep_n = mju_norm3(ep); er_n = mju_norm3(er);
        if (ep_n < 1e-5 && er_n < 1e-4) break;
        mj_jacSite(m, d, k->jacp, k->jacr, k->site);
        /* J (6×n): [jacp; 0.3·jacr],  e (6): [ep; 0.3·er].  dq = Jᵀ (J Jᵀ + λI)⁻¹ e  — 6×6 을 가우스 소거로 */
        double J[6][PACE_KIN_MAXDOF], e[6], A[6][6], b[6];
        for (int j = 0; j < n; ++j) { for (int r = 0; r < 3; ++r) { J[r][j] = k->jacp[r * m->nv + j]; J[3 + r][j] = 0.3 * k->jacr[r * m->nv + j]; } }
        for (int r = 0; r < 3; ++r) { e[r] = ep[r]; e[3 + r] = 0.3 * er[r]; }
        for (int r = 0; r < 6; ++r) { for (int c = 0; c < 6; ++c) { double s = 0; for (int j = 0; j < n; ++j) s += J[r][j] * J[c][j]; A[r][c] = s + (r == c ? damping : 0.0); } b[r] = e[r]; }
        for (int c = 0; c < 6; ++c) {                                           /* 부분 피벗 가우스 소거 */
            int p = c; for (int r = c + 1; r < 6; ++r) if (fabs(A[r][c]) > fabs(A[p][c])) p = r;
            if (p != c) { for (int cc = 0; cc < 6; ++cc) { double t = A[c][cc]; A[c][cc] = A[p][cc]; A[p][cc] = t; } double t = b[c]; b[c] = b[p]; b[p] = t; }
            if (fabs(A[c][c]) < 1e-12) continue;
            for (int r = c + 1; r < 6; ++r) { double f = A[r][c] / A[c][c]; for (int cc = c; cc < 6; ++cc) A[r][cc] -= f * A[c][cc]; b[r] -= f * b[c]; }
        }
        double y[6]; for (int r = 5; r >= 0; --r) { double s = b[r]; for (int cc = r + 1; cc < 6; ++cc) s -= A[r][cc] * y[cc]; y[r] = fabs(A[r][r]) < 1e-12 ? 0 : s / A[r][r]; }
        for (int j = 0; j < n; ++j) {
            double dq = 0; for (int r = 0; r < 6; ++r) dq += J[r][j] * y[r];
            if (dq > 0.1) dq = 0.1; if (dq < -0.1) dq = -0.1;
            double qn = d->qpos[j] + dq; int jid = m->dof_jntid[j];
            if (m->jnt_limited[jid]) { double lo = m->jnt_range[2 * jid] + 0.02, hi = m->jnt_range[2 * jid + 1] - 0.02; if (qn < lo) qn = lo; if (qn > hi) qn = hi; }
            d->qpos[j] = qn;
        }
    }
    for (int j = 0; j < n; ++j) q_out[j] = (float)d->qpos[j];
    if (err_pos) *err_pos = (float)ep_n; if (err_rot) *err_rot = (float)er_n;
}

void pace_kin_tool_rotation(const float tangent[3], float travel_angle, float rot9[9])
{
    double t[3] = { tangent[0], tangent[1], 0.0 }; double tn = sqrt(t[0] * t[0] + t[1] * t[1]) + 1e-12; t[0] /= tn; t[1] /= tn;
    double down[3] = { 0, 0, -1 };
    double z[3] = { cos(travel_angle) * down[0] + sin(travel_angle) * t[0], cos(travel_angle) * down[1] + sin(travel_angle) * t[1], cos(travel_angle) * down[2] + sin(travel_angle) * t[2] };
    double zn = sqrt(z[0] * z[0] + z[1] * z[1] + z[2] * z[2]); for (int i = 0; i < 3; ++i) z[i] /= zn;
    double dot = t[0] * z[0] + t[1] * z[1] + t[2] * z[2]; double x[3] = { t[0] - dot * z[0], t[1] - dot * z[1], t[2] - dot * z[2] };
    double xn = sqrt(x[0] * x[0] + x[1] * x[1] + x[2] * x[2]) + 1e-12; for (int i = 0; i < 3; ++i) x[i] /= xn;
    double y[3] = { z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0] };
    /* 열벡터 [x y z] → 행 우선 3×3 */
    rot9[0] = (float)x[0]; rot9[1] = (float)y[0]; rot9[2] = (float)z[0];
    rot9[3] = (float)x[1]; rot9[4] = (float)y[1]; rot9[5] = (float)z[1];
    rot9[6] = (float)x[2]; rot9[7] = (float)y[2]; rot9[8] = (float)z[2];
}
