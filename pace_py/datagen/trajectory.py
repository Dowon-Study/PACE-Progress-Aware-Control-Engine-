"""용접 궤적 GT: 용접선을 일정 속도로 따라가는 툴 포즈 열과 그 역기구학 해.

툴 프레임 규약 (ur5e_torch.xml 의 'tool' 사이트): z = 토치 축(팁 방향). 월드에서 토치는 아래(-z)를 향하되
진행 방향으로 travel_angle 만큼 기울인다(push angle). x 는 진행 접선 방향 → 근접 카메라가 용접선 앞쪽을 본다.
"""
from __future__ import annotations
import numpy as np
import mujoco

STANDOFF = 0.002       # 팁-용접선 간격 (m)


def tool_rotation(tangent: np.ndarray, travel_angle: float) -> np.ndarray:
    """월드 접선(단위, 거의 수평)과 진행각으로 툴 회전행렬 [x y z] 열벡터."""
    t = tangent.copy(); t[2] = 0.0; t /= np.linalg.norm(t) + 1e-12
    down = np.array([0.0, 0.0, -1.0])
    # 진행 방향으로 기울인 토치 축: down 을 접선 방향으로 travel_angle 회전
    z = np.cos(travel_angle) * down + np.sin(travel_angle) * t
    z /= np.linalg.norm(z)
    x = t - np.dot(t, z) * z; x /= np.linalg.norm(x) + 1e-12
    y = np.cross(z, x)
    return np.stack([x, y, z], axis=1)


def rotmat_to_quat(R: np.ndarray) -> np.ndarray:
    q = np.zeros(4); mujoco.mju_mat2Quat(q, R.reshape(9)); return q


class SeamIK:
    """감쇠 최소제곱 IK, 이전 해에서 웜스타트. 관절 한계 안, 각도 래핑."""

    def __init__(self, model: mujoco.MjModel, site_name: str = "tool"):
        self.m = model; self.d = mujoco.MjData(model)
        self.sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, site_name)
        self.jacp = np.zeros((3, model.nv)); self.jacr = np.zeros((3, model.nv))

    def solve(self, pos: np.ndarray, R: np.ndarray, q_init: np.ndarray, iters: int = 60, tol_p: float = 2e-5, tol_r: float = 2e-4):
        d, m = self.d, self.m
        d.qpos[:] = q_init
        er = np.zeros(3); q4 = np.zeros(4)
        for _ in range(iters):
            mujoco.mj_kinematics(m, d); mujoco.mj_comPos(m, d)
            ep = pos - d.site_xpos[self.sid]
            Rc = d.site_xmat[self.sid].reshape(3, 3)
            mujoco.mju_mat2Quat(q4, (R @ Rc.T).reshape(9)); mujoco.mju_quat2Vel(er, q4, 1.0)
            if np.linalg.norm(ep) < tol_p and np.linalg.norm(er) < tol_r: break
            mujoco.mj_jacSite(m, d, self.jacp, self.jacr, self.sid)
            J = np.vstack([self.jacp, 0.3 * self.jacr]); e = np.concatenate([ep, 0.3 * er])
            dq = J.T @ np.linalg.solve(J @ J.T + 1e-6 * np.eye(6), e)
            d.qpos[:] = np.clip(d.qpos + np.clip(dq, -0.2, 0.2), m.jnt_range[:, 0] + 0.05, m.jnt_range[:, 1] - 0.05)
        mujoco.mj_kinematics(m, d); mujoco.mj_comPos(m, d)
        return d.qpos.copy(), float(np.linalg.norm(pos - d.site_xpos[self.sid])), float(np.linalg.norm(er))


def weld_trajectory(model, seam_pts: np.ndarray, seam_s: np.ndarray, seam_tan: np.ndarray, q_home: np.ndarray,
                    speed: float = 0.010, travel_angle: float = np.deg2rad(10), dt: float = 0.001, ik_rate: float = 100.0,
                    lead_in: float = 1.0, standoff: float = STANDOFF):
    """일정 속도 speed(m/s)로 용접선을 따라가는 GT 궤적을 dt 간격으로.
    lead_in: 시작점 위에서 토치 정렬 후 대기하는 시간(s).
    반환 dict: t, s, tool_pos[N,3], tool_quat[N,4], q[N,6], qd[N,6], ik_pos_err[N], seam_idx[N]"""
    L = seam_s[-1]; T = L / speed
    n_ik = int(np.ceil(T * ik_rate)) + 1
    t_ik = np.linspace(0, T, n_ik); s_ik = np.minimum(t_ik * speed, L)
    pos_ik = np.stack([np.interp(s_ik, seam_s, seam_pts[:, k]) for k in range(3)], axis=1); pos_ik[:, 2] += standoff
    tan_ik = np.stack([np.interp(s_ik, seam_s, seam_tan[:, k]) for k in range(3)], axis=1)
    ik = SeamIK(model)
    q_ik = np.zeros((n_ik, model.nv)); err = np.zeros(n_ik); q_prev = q_home.copy()
    # 시작점: 홈에서 출발, 실패하면 홈 주변 랜덤 시드로 다중 시작
    R0 = tool_rotation(tan_ik[0], travel_angle)
    rng = np.random.default_rng(0); best = None
    for k in range(40):
        seed = q_home if k == 0 else q_home + rng.normal(0, 0.3, size=q_home.shape)
        q0, e, er0 = ik.solve(pos_ik[0], R0, seed, iters=300)
        if best is None or e + 0.1 * er0 < best[0]: best = (e + 0.1 * er0, q0, e)
        if e < 1e-4 and er0 < 1e-3: break
    q_prev = best[1]
    if best[2] > 1e-3:
        return {"ik_pos_err_max": best[2], "length": float(L), "fail": "start"}
    for i in range(n_ik):
        R = tool_rotation(tan_ik[i], travel_angle)
        q_prev, err[i], _ = ik.solve(pos_ik[i], R, q_prev)
        q_ik[i] = q_prev
    # 연속성: IK 샘플(10ms) 사이 관절 점프가 0.05rad 를 넘으면 해가 갈라진 것
    dq_max = float(np.abs(np.diff(q_ik, axis=0)).max()) if n_ik > 1 else 0.0
    if dq_max > 0.05:
        return {"ik_pos_err_max": float(err.max()), "length": float(L), "fail": f"joint jump {dq_max:.3f} rad"}
    # 1kHz 로 보간 (관절은 3차 스플라인 대신 선형+스무딩: IK 100Hz 가 충분히 조밀)
    t = np.arange(0, T + lead_in, dt); n = len(t)
    t_move = np.clip(t - lead_in, 0, T)
    q = np.stack([np.interp(t_move, t_ik, q_ik[:, j]) for j in range(model.nv)], axis=1)
    qd = np.gradient(q, dt, axis=0)
    s = t_move * speed
    tool_pos = np.stack([np.interp(s, seam_s, seam_pts[:, k]) for k in range(3)], axis=1); tool_pos[:, 2] += standoff
    tan = np.stack([np.interp(s, seam_s, seam_tan[:, k]) for k in range(3)], axis=1)
    tool_quat = np.array([rotmat_to_quat(tool_rotation(tan[i], travel_angle)) for i in range(0, n)])
    return {"t": t, "s": s, "tool_pos": tool_pos, "tool_quat": tool_quat, "q": q, "qd": qd,
            "ik_pos_err_max": float(err.max()), "dq_max": dq_max, "speed": speed, "travel_angle": float(travel_angle), "lead_in": lead_in, "length": float(L)}
