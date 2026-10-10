"""시연용: trace 의 로봇 자세로 cam_tool 영상을 다시 그리고 검출된 용접선/꼭대기/ROI 를 겹쳐 그린 타일 그림.
사용: python -m pace_py.eye.eye_frames_fig --episode 1 --run s7_eye_ep1 --times 4 8 12 16 20 --out docs/figures/s7_eye_frames_ep1.png"""
import argparse, sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.trace import load_trace                       # noqa: E402
from pace_py.eye.seam_eye import Eye, detect_seam, W, H           # noqa: E402


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--episode", type=int, required=True); ap.add_argument("--run", required=True)
    ap.add_argument("--times", type=float, nargs="+", default=[4, 8, 12, 16, 20]); ap.add_argument("--out", required=True); ap.add_argument("--scale", type=int, default=3)
    a = ap.parse_args()
    tr = load_trace(f"docs/benchmarks/runs/{a.run}.trace.bin"); t = (tr["t_ns"] - tr["t_ns"][0]) * 1e-9
    eye = Eye(f"pace/models/ur5e/_gen_ep{a.episode:04d}.xml", "pace_py/eye/calib.json", f"data/refpath/ep_{a.episode:04d}_teach.bin")
    tx, ty = eye.tip; k = a.scale; tiles = []
    for tt in a.times:
        i = int(np.searchsorted(t, tt)); img = eye.render(tr["q_meas"][i]); u, ang, inl, ok = detect_seam(img, eye.mask, eye.tip)
        big = cv2.resize(img, (W * k, H * k), interpolation=cv2.INTER_NEAREST)
        cv2.rectangle(big, (int((tx - 60) * k), int((ty - 30) * k)), (int((tx + 60) * k), int((ty + 20) * k)), (255, 255, 0), 1)       # ROI
        cv2.drawMarker(big, (int(tx * k), int(ty * k)), (255, 0, 0), cv2.MARKER_CROSS, 10 * k // 3, 1)                             # 토치 꼭대기
        if ok:
            vx, vy = np.cos(ang), np.sin(ang); py = ty + u; x0, x1 = tx - 30, tx + 30          # 접선은 적합 창(±30px) 안에서만
            cv2.line(big, (int(x0 * k), int((py + (x0 - tx) * vy / vx) * k)), (int(x1 * k), int((py + (x1 - tx) * vy / vx) * k)), (0, 255, 0), 1)
            cv2.line(big, (int(tx * k), int(ty * k)), (int(tx * k), int(py * k)), (255, 0, 255), 2)                                 # 가로 오프셋
        lat = eye.calib["sign"] * (eye.calib["a_m_per_px"] * u + eye.calib["b_m"]) if ok else float("nan")
        cv2.rectangle(big, (0, 0), (W * k, 20), (30, 30, 30), -1)
        cv2.putText(big, f"t={tt:.0f}s  u={u:+.1f}px  lat={lat*1e3:+.2f}mm  inl={inl:.2f}" if ok else f"t={tt:.0f}s  no seam", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(big)
    rows = [np.hstack(tiles[j:j + 3]) for j in range(0, len(tiles), 3)]; wmax = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, wmax - r.shape[1]), (0, 0))) for r in rows]; grid = np.vstack(rows)
    cv2.imwrite(a.out, cv2.cvtColor(grid, cv2.COLOR_RGB2BGR)); print("wrote", a.out)


if __name__ == "__main__":
    main()
