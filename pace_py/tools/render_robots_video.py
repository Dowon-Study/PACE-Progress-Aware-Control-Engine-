"""4 로봇 4분할 영상: 같은 교시 경로·같은 눈·같은 제어기로 각 로봇이 용접을 완주하는 모습을 2×2 로 붙인다.
각 칸: 모드, 속도 배율, 실제 용접선 대비 가로 오차, 비드 진행률(아크 ON 동안 지나간 용접선 비율).
사용: MUJOCO_GL=egl .venv/bin/python -m pace_py.tools.render_robots_video --episode 1 --out docs/figures/robots4_ep1.mp4"""
import argparse, csv, sys
from pathlib import Path
import numpy as np, cv2, mujoco
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.trace import load_trace   # noqa: E402
from pace_py.tools.render_compare_video import put_kr, MODE, COLOR   # noqa: E402
from scipy.spatial import cKDTree
ROBOTS = [("UR5e 6축", "s12_ur5e_eye_ep1", "pace/models/ur5e/_gen_ep{ep:04d}.xml"), ("Franka Panda 7축", "s8_panda_eye_ep1", "pace/models/panda/_gen_ep{ep:04d}_panda.xml"),
          ("KUKA iiwa14 7축", "s13_iiwa14_eye_ep1", "pace/models/iiwa14/_gen_ep{ep:04d}_iiwa14.xml"), ("UFactory xArm7 7축", "s13_xarm7_eye_ep1", "pace/models/xarm7/_gen_ep{ep:04d}_xarm7.xml")]


def load_run(name):
    tr = load_trace(f"docs/benchmarks/runs/{name}.trace.bin"); t = (tr["t_ns"] - tr["t_ns"][0]) * 1e-9
    rows = list(csv.DictReader(open(f"docs/benchmarks/runs/{name}.csv"))); n = min(len(rows), len(t))
    return {"t": t[:n], "q": tr["q_meas"][:n], "tool": tr["tool"][:n, :3], "mode": np.array([int(r["mode"]) for r in rows[:n]]),
            "speed": np.array([float(r["speed_scale"]) for r in rows[:n]]), "arc": np.array([int(r.get("arc_on", 1)) for r in rows[:n]])}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--episode", type=int, default=1); ap.add_argument("--out", required=True); ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--t0", type=float, default=2.5); ap.add_argument("--t1", type=float, default=24.0); ap.add_argument("--snap", type=float, default=None); a = ap.parse_args()
    W, H, S = 640, 480, 70; g = np.load(f"data/gt/ep_{a.episode:04d}.npz"); seam = g["seam_pts"]; tree = cKDTree(seam[:, :2]); nseg = len(seam) // 4 + 1
    panels = []
    for label, run, scene in ROBOTS:
        m = mujoco.MjModel.from_xml_path(scene.format(ep=a.episode)); d = mujoco.MjData(m); r = mujoco.Renderer(m, H, W); mujoco.mj_forward(m, d)
        cid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_CAMERA, "cam_scene"); f = (H / 2) / np.tan(np.radians(m.cam_fovy[cid]) / 2); cp = d.cam_xpos[cid].copy(); cR = d.cam_xmat[cid].reshape(3, 3).copy()
        def proj(p, cR=cR, cp=cp, f=f):
            v = cR.T @ (p - cp)
            return None if v[2] >= -1e-3 else (int(W / 2 + f * v[0] / -v[2]), int(H / 2 - f * v[1] / -v[2]))
        panels.append({"label": label, "m": m, "d": d, "r": r, "proj": proj, "run": load_run(run), "beads": [], "cov": set(), "seam_px": [q for q in (proj(p) for p in seam[::4]) if q is not None]})
    t1 = min(a.t1, min(p["run"]["t"][-1] for p in panels)); times = np.arange(a.t0, t1, 1.0 / a.fps)
    out = cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"mp4v"), a.fps, (2 * W, 2 * (H + S)))
    for tt in times:
        imgs = []
        for p in panels:
            run = p["run"]; i = min(len(run["t"]) - 1, int(np.searchsorted(run["t"], tt))); m, d = p["m"], p["d"]; nq = run["q"].shape[1]
            d.qpos[:nq] = run["q"][i][:nq]; mujoco.mj_forward(m, d); p["r"].update_scene(d, camera="cam_scene"); img = p["r"].render().copy()
            mode = int(run["mode"][i]); dist, idx = tree.query(run["tool"][i][:2]); lat = float(dist) * 1e3
            if run["arc"][i] and mode in (1, 2, 3, 4, 7): p["beads"].append(run["tool"][i].copy()); (lat < 2.0) and p["cov"].add(int(idx) // 4)
            sp = p["seam_px"]
            for j in range(1, len(sp)): cv2.line(img, sp[j - 1], sp[j], (90, 90, 90), 1)
            for b in p["beads"][::2]:
                q = p["proj"](b)
                if q is not None and 0 <= q[0] < W and 0 <= q[1] < H: cv2.circle(img, q, 3, (255, 120, 40), -1)
            cov = 100.0 * len(p["cov"]) / nseg; img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            if cov >= 99.0: img = put_kr(img, "완주 ✓", (W - 150, 16), 0.9, (60, 220, 60))
            strip = np.zeros((S, W, 3), np.uint8) + 25; cv2.rectangle(strip, (10, 8), (30, 28), COLOR.get(mode, (120, 120, 120)), -1)
            strip = put_kr(strip, p["label"], (40, 2), 0.55, (255, 255, 255))
            strip = put_kr(strip, f"t={tt:5.1f}s  {MODE.get(mode, mode):4s}  속도 {run['speed'][i]:.2f}x  용접선 오차 {lat:4.2f} mm  진행 {cov:5.1f} %", (40, 36), 0.5, (200, 200, 200))
            imgs.append(np.vstack([img, strip]))
        frame = np.vstack([np.hstack(imgs[:2]), np.hstack(imgs[2:])]); out.write(frame)
        if a.snap is not None and abs(tt - a.snap) < 0.5 / a.fps: cv2.imwrite(str(Path(a.out).with_suffix("")) + f"_t{a.snap:.0f}s.png", frame)
    out.release(); print("saved", a.out, f"{len(times)} frames @ {a.fps} fps")


if __name__ == "__main__":
    main()
