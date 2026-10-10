"""중단 구간 분해: 로컬 재생 중(첫 LOCAL ~ AI 복귀) vs AI 복귀 뒤 2s — 가로 오차 max, 손목 회전 드리프트, 툴 높이.
사용: python -m pace_py.tools.gap_split --episode 0 --runs s9f_fm_local_long_gap10_ep0 s9f_mlp_local_long_gap10_ep0"""
import argparse, csv, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.trace import load_trace   # noqa: E402
from scipy.spatial import cKDTree


def split(run, tree):
    tr = load_trace(f"docs/benchmarks/runs/{run}.trace.bin"); t = (tr["t_ns"] - tr["t_ns"][0]) * 1e-9; p = tr["tool"][:, :3]; q5 = tr["q_meas"][:, 5]
    rows = list(csv.DictReader(open(f"docs/benchmarks/runs/{run}.csv"))); mode = np.array([int(r["mode"]) for r in rows]); sup = np.array([int(r["supplier"]) for r in rows]); n = min(len(mode), len(t))
    d, _ = tree.query(p[:n, :2]); loc0 = np.nonzero((mode[:n] == 3) & (t[:n] > 10))[0]
    if not len(loc0): return None
    i0 = loc0[0]; after = np.nonzero(sup[i0:n] == 1)[0]; i1 = i0 + after[0] if len(after) else n - 1
    loc = slice(i0, i1); re = slice(i1, min(n, i1 + 2000))
    return {"run": run, "local_s": (i1 - i0) / 1000, "lat_max_local_mm": float(d[loc].max() * 1e3), "lat_end_local_mm": float(d[i1 - 1] * 1e3), "wrist_drift_mrad": float((q5[i1 - 1] - q5[i0]) * 1e3), "height_end_mm": float(p[i1 - 1, 2] * 1e3 - 310), "lat_max_reentry_mm": float(d[re].max() * 1e3)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--episode", type=int, default=0); ap.add_argument("--runs", nargs="+", required=True); ap.add_argument("--json", default=None); a = ap.parse_args()
    tree = cKDTree(np.load(f"data/gt/ep_{a.episode:04d}.npz")["seam_pts"][:, :2]); out = []
    for r in a.runs:
        s = split(r, tree)
        if s is None: print(f"{r}: no LOCAL window"); continue
        out.append(s); print(f"{r:32s} LOCAL {s['local_s']:.1f}s: 가로 max={s['lat_max_local_mm']:4.2f}mm 끝 {s['lat_end_local_mm']:4.2f}mm 손목5 {s['wrist_drift_mrad']:+6.1f}mrad 높이 끝 {s['height_end_mm']:3.1f}mm | AI 복귀 2s max={s['lat_max_reentry_mm']:5.2f}mm")
    if a.json: Path(a.json).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
