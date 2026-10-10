"""성공 vs 실패 나란히 시뮬레이션 영상: 두 실행의 trace(q_meas 1kHz)로 같은 장면을 렌더해 좌우로 붙인다.
각 칸에 상태 띠(모드), 속도 배율, 실제 용접선 대비 가로 오차, 아크 ON 동안 지나간 용접 비드(초록 점) 를 그린다.
사용: python -m pace_py.tools.render_compare_video --episode 0 --left s13_baseline_timeidx_gap6_ep0 --right s9b_local_long_gap6_ep0 \\
        --left-label "기준: 시간 인덱스 재생 + 유지→정지" --right-label "PACE: 진행도 접합 + 사다리(+로컬 정책)" --out docs/figures/compare_gap6.mp4"""
import argparse, csv, sys
from pathlib import Path
import numpy as np, cv2, mujoco
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.trace import load_trace   # noqa: E402
from scipy.spatial import cKDTree
MODE = {0: "초기", 1: "정상", 2: "감속", 3: "보조궤적", 4: "외삽", 5: "유지", 6: "정지", 7: "복귀"}
COLOR = {1: (60, 180, 60), 2: (40, 160, 230), 3: (230, 160, 30), 4: (160, 90, 220), 5: (0, 200, 230), 6: (30, 30, 220), 7: (30, 200, 180), 0: (120, 120, 120)}
FONT = cv2.FONT_HERSHEY_SIMPLEX


def put_kr(img, text, org, size=0.6, color=(255, 255, 255), thick=1):
    """한글은 PIL 로 (OpenCV 기본 폰트는 한글 미지원)"""
    from PIL import Image, ImageDraw, ImageFont
    pil = Image.fromarray(img); dr = ImageDraw.Draw(pil)
    try: font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", int(size * 36))
    except Exception: font = ImageFont.load_default()
    dr.text(org, text, font=font, fill=color); return np.array(pil)


def load_run(name, ep):
    tr = load_trace(f"docs/benchmarks/runs/{name}.trace.bin"); t = (tr["t_ns"] - tr["t_ns"][0]) * 1e-9
    rows = list(csv.DictReader(open(f"docs/benchmarks/runs/{name}.csv"))); n = min(len(rows), len(t))
    mode = np.array([int(r["mode"]) for r in rows[:n]]); sp = np.array([float(r["speed_scale"]) for r in rows[:n]]); arc = np.array([int(r.get("arc_on", 1)) for r in rows[:n]])
    return {"t": t[:n], "q": tr["q_meas"][:n], "tool": tr["tool"][:n, :3], "mode": mode, "speed": sp, "arc": arc}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--episode", type=int, required=True); ap.add_argument("--left", required=True); ap.add_argument("--right", required=True)
    ap.add_argument("--left-label", default="baseline"); ap.add_argument("--right-label", default="PACE"); ap.add_argument("--out", required=True); ap.add_argument("--fps", type=int, default=20); ap.add_argument("--t0", type=float, default=0); ap.add_argument("--t1", type=float, default=None); ap.add_argument("--scene", default=None); ap.add_argument("--gap", type=float, nargs=2, default=None, help="AI 공급 단절 구간 [s] (배너 표시용)"); ap.add_argument("--snap", type=float, default=None, help="이 시각의 프레임을 PNG 로도 저장")
    a = ap.parse_args(); scene = a.scene or f"pace/models/ur5e/_gen_ep{a.episode:04d}.xml"
    m = mujoco.MjModel.from_xml_path(scene); d = mujoco.MjData(m); W, H = 640, 480; r = mujoco.Renderer(m, H, W)
    g = np.load(f"data/gt/ep_{a.episode:04d}.npz"); seam = g["seam_pts"]; tree = cKDTree(seam[:, :2])
    runs = [load_run(a.left, a.episode), load_run(a.right, a.episode)]; labels = [a.left_label, a.right_label]
    t1 = a.t1 or min(x["t"][-1] for x in runs); times = np.arange(a.t0, t1, 1.0 / a.fps)
    cam = mujoco.MjvCamera(); cam.type = mujoco.mjtCamera.mjCAMERA_FIXED; cam.fixedcamid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_CAMERA, "cam_scene")
    out = cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"mp4v"), a.fps, (2 * W, H + 90)); beads = [[], []]; stopped_s = [0.0, 0.0]; covered = [set(), set()]
    cid = cam.fixedcamid; fovy = m.cam_fovy[cid]; f = (H / 2) / np.tan(np.radians(fovy) / 2); mujoco.mj_forward(m, d); cp = d.cam_xpos[cid].copy(); cR = d.cam_xmat[cid].reshape(3, 3).copy()
    def proj(p):
        v = cR.T @ (p - cp)                      # 카메라 좌표계 (MuJoCo 카메라는 -z 를 본다)
        if v[2] >= -1e-3: return None
        return int(W / 2 + f * v[0] / -v[2]), int(H / 2 - f * v[1] / -v[2])
    seam_px = [q for q in (proj(p) for p in seam[::4]) if q is not None]
    for tt in times:
        panels = []
        for k, run in enumerate(runs):
            i = min(len(run["t"]) - 1, int(np.searchsorted(run["t"], tt))); d.qpos[:m.nq] = run["q"][i][:m.nq]; mujoco.mj_forward(m, d)
            if run["arc"][i] and run["mode"][i] in (1, 2, 3, 4, 7): beads[k].append(run["tool"][i].copy())
            # 비드: 지나간 툴 위치를 작은 구로 (렌더 scene 에 직접 그리기 어려워 영상 위에 투영 점으로 표시)
            r.update_scene(d, camera="cam_scene"); img = r.render().copy()
            for j in range(1, len(seam_px)): cv2.line(img, seam_px[j - 1], seam_px[j], (90, 90, 90), 1)      # 목표 용접선 (회색)
            for p in beads[k][::2]:
                q = proj(p)
                if q is not None and 0 <= q[0] < W and 0 <= q[1] < H: cv2.circle(img, q, 3, (255, 120, 40), -1)   # 비드 (주황)
            dist, idx = tree.query(run["tool"][i][:2]); lat = float(dist) * 1e3; mode = int(run["mode"][i])
            if run["arc"][i] and mode in (1, 2, 3, 4, 7) and lat < 2.0: covered[k].add(int(idx) // 4)
            cov = 100.0 * len(covered[k]) / (len(seam) // 4 + 1)
            if mode == 6 and tt > 3: stopped_s[k] += 1.0 / a.fps
            strip = np.zeros((90, W, 3), np.uint8) + 25
            cv2.rectangle(strip, (0, 0), (W, 90), (25, 25, 25), -1); cv2.rectangle(strip, (10, 10), (30, 30), COLOR.get(mode, (120, 120, 120)), -1)
            strip = put_kr(strip, f"{labels[k]}", (40, 4), 0.55, (255, 255, 255))
            strip = put_kr(strip, f"t={tt:5.1f}s  {MODE.get(mode, mode):4s}  속도 {run['speed'][i]:.2f}x  오차 {lat:4.2f} mm  진행 {cov:5.1f} %  정지 {stopped_s[k]:.1f}s", (40, 44), 0.5, (200, 200, 200))
            if a.gap and a.gap[0] <= tt < a.gap[1]: img = put_kr(img, f"AI 공급 단절 {a.gap[0]:.0f}–{a.gap[1]:.0f} s", (W // 2 - 120, H - 50), 0.7, (255, 80, 80))
            if tt > 3 and not run["arc"][i] and mode != 6: img = put_kr(img, "아크 OFF", (W - 130, 20), 0.7, (255, 80, 80))
            if mode == 6 and tt > 3: img = put_kr(img, "정지 — 용접 불량", (W // 2 - 150, 20), 0.9, (40, 40, 255))
            if mode == 3: img = put_kr(img, "보조 궤적으로 이어 가는 중", (W // 2 - 190, 20), 0.7, (255, 200, 60))
            if mode == 2: img = put_kr(img, "감속: AI 응답 지연 조짐", (W // 2 - 150, 20), 0.7, (255, 200, 60))
            panels.append(np.vstack([cv2.cvtColor(img, cv2.COLOR_RGB2BGR), strip]))
        frame = np.hstack(panels); out.write(frame)
        if a.snap is not None and abs(tt - a.snap) < 0.5 / a.fps: cv2.imwrite(str(Path(a.out).with_suffix("")) + f"_t{a.snap:.0f}s.png", frame)
    out.release(); print("saved", a.out, f"{len(times)} frames @ {a.fps} fps")


if __name__ == "__main__":
    main()
