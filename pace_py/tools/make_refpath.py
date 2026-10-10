"""GT 에피소드에서 기준(교시) 경로 파일 생성: nominal 모드면 교시 경로(고정구 오차 포함), 아니면 실제 용접선.
형식: u32 'RPTH', u32 n, f32 sdot, f32 standoff, f32 travel_angle, f32 pad, n×[s,x,y,z,tx,ty,tz] f32
사용: python -m pace_py.tools.make_refpath --episode 1 [--real]  → data/refpath/ep_0001_{teach|real}.bin"""
import argparse, json, struct, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--episode", type=int, required=True); ap.add_argument("--real", action="store_true"); ap.add_argument("--step", type=float, default=0.002)
    a = ap.parse_args()
    ep = np.load(f"data/gt/ep_{a.episode:04d}.npz"); meta = json.load(open(f"data/gt/ep_{a.episode:04d}.json"))
    pts = (ep["seam_pts"] if a.real else ep["nominal_seam_pts"]).astype(np.float64); s = ep["seam_s"].astype(np.float64)
    tan = np.gradient(pts, s, axis=0); tan /= np.linalg.norm(tan, axis=1, keepdims=True) + 1e-12
    idx = np.arange(0, len(s), max(1, int(round(a.step / 0.001))));
    if idx[-1] != len(s) - 1: idx = np.append(idx, len(s) - 1)
    kind = "real" if a.real else "teach"; out = Path("data/refpath") / f"ep_{a.episode:04d}_{kind}.bin"; out.parent.mkdir(exist_ok=True, parents=True)
    with out.open("wb") as f:
        f.write(struct.pack("<II4f", 0x48545052, len(idx), meta["speed_mps"], 0.002, np.deg2rad(meta["travel_angle_deg"]), 0.0))
        for i in idx: f.write(struct.pack("<7f", s[i], *pts[i], *tan[i]))
    off = np.linalg.norm(ep["nominal_seam_pts"][:, :2] - ep["seam_pts"][:, :2], axis=1)
    print(f"saved {out}: n={len(idx)} length={s[-1]:.3f}m sdot={meta['speed_mps']*1e3:.1f}mm/s mode={meta['mode']} 교시-실제 오프셋 mean={off.mean()*1e3:.1f} max={off.max()*1e3:.1f} mm")

if __name__ == "__main__":
    main()
