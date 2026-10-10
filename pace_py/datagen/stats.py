"""data/gt/index.json 요약: 형상·모드별 개수, 길이·속도·프레임 분포, 보정 라벨 분포, 추종 오차."""
import json, sys
from collections import Counter
from pathlib import Path
import numpy as np

root = Path(sys.argv[1] if len(sys.argv) > 1 else "data/gt")
idx = json.load((root / "index.json").open())
fam = Counter(m["spec"]["family"] for m in idx); mode = Counter(m["mode"] for m in idx)
L = np.array([m["length_m"] for m in idx]); v = np.array([m["speed_mps"] for m in idx]) * 1e3; F = np.array([m["frames"] for m in idx]); T = np.array([m["duration_s"] for m in idx])
te = np.array([m["track_err_max_mm"] for m in idx]); corr = np.array([m["correction_lat_abs_max_mm"] for m in idx if m["mode"] == "nominal"])
size = sum(f.stat().st_size for f in root.glob("ep_*.npz")) / 2**30
print(f"episodes: {len(idx)}  modes: {dict(mode)}  families: {dict(sorted(fam.items()))}")
print(f"length m: mean {L.mean():.3f} min {L.min():.3f} max {L.max():.3f}  total {L.sum():.1f} m")
print(f"speed mm/s: {v.min():.1f}~{v.max():.1f}   duration s: mean {T.mean():.1f} total {T.sum()/60:.1f} min   frames total {F.sum()} (scene+tool 각각)")
print(f"track err max mm: mean {te.mean():.3f} max {te.max():.3f}")
if len(corr): print(f"nominal correction |lat| max mm: mean {corr.mean():.1f} min {corr.min():.1f} max {corr.max():.1f}")
print(f"disk: {size:.2f} GiB")
