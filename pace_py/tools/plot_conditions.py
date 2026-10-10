"""조건별 시스템 동작 통합 시각화 (과제 평가 항목): 정상 / 지연 / 통신 단절 — 모드 사다리, 속도 배율·감시기 판정, 실제 용접선 대비 가로 오차.
사용: python -m pace_py.tools.plot_conditions --episode 0 --normal s5_progress_d0_ep0 --delay s5_progress_d200_ep0 --dropout s9b_local_long_gap6_ep0 --out docs/figures/s11_conditions_ep0.png"""
import argparse, csv, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.trace import load_trace   # noqa: E402
import matplotlib; matplotlib.use("Agg")
from matplotlib import font_manager as fm
_c = [f for f in fm.findSystemFonts() if "NotoSansCJK" in f]
if _c: fm.fontManager.addfont(_c[0]); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c[0]).get_name()
import matplotlib.pyplot as plt
MODE = ["INIT", "NORMAL", "PACING", "LOCAL", "EXTRAP", "HOLD", "STOPPED", "RECOVER"]

ap = argparse.ArgumentParser(); ap.add_argument("--episode", type=int, default=0); ap.add_argument("--normal", required=True); ap.add_argument("--delay", required=True); ap.add_argument("--dropout", required=True); ap.add_argument("--labels", nargs=3, default=["정상 (지연 0)", "지연 200±50 ms", "통신 단절 6 s (+로컬 정책)"]); ap.add_argument("--out", required=True)
a = ap.parse_args(); seam = np.load(f"data/gt/ep_{a.episode:04d}.npz")["seam_pts"][:, :2]
from scipy.spatial import cKDTree; tree = cKDTree(seam)
fig, ax = plt.subplots(3, 3, figsize=(16, 8), sharex="col")
for k, (run, lb) in enumerate(zip([a.normal, a.delay, a.dropout], a.labels)):
    rows = list(csv.DictReader(open(f"docs/benchmarks/runs/{run}.csv"))); t0 = int(rows[0]["t_sched_ns"]); t = np.array([(int(r["t_sched_ns"]) - t0) * 1e-9 for r in rows])
    mode = np.array([int(r["mode"]) for r in rows]); sp = np.array([float(r["speed_scale"]) for r in rows]); mon = np.array([int(r["monitor"]) for r in rows])
    tr = load_trace(f"docs/benchmarks/runs/{run}.trace.bin"); tt = (tr["t_ns"] - tr["t_ns"][0]) * 1e-9; p = tr["tool"][:, :3]; moving = np.r_[np.linalg.norm(np.diff(p, axis=0), axis=1) > 2e-6, False]
    d, _ = tree.query(p[:, :2]); on = (p[:, 2] < 0.33) & moving & (tt > 4.0)
    ax[0, k].step(t, mode, where="post", lw=1.2, color="C2"); ax[0, k].set_yticks(range(8)); ax[0, k].set_yticklabels(MODE, fontsize=7); ax[0, k].set_title(lb, fontsize=10); ax[0, k].grid(alpha=.3)
    ax[1, k].plot(t, sp, color="C1", label="속도 배율"); ax[1, k].step(t, mon / 2, where="post", color="k", lw=0.8, alpha=.6, label="감시기 (0 OK, .5 SLOW, 1 STOP)"); ax[1, k].set_ylim(-0.05, 1.1); ax[1, k].grid(alpha=.3)
    if k == 0: ax[1, k].legend(fontsize=7)
    ax[2, k].plot(tt[on], d[on] * 1e3, color="C0", lw=0.8); ax[2, k].set_ylim(0, 3); ax[2, k].grid(alpha=.3); ax[2, k].set_xlabel("t [s]")
    ax[2, k].text(0.02, 0.9, f"용접 중 가로 오차 mean {np.mean(d[on])*1e3:.2f} / max {np.max(d[on])*1e3:.2f} mm" if on.any() else "", transform=ax[2, k].transAxes, fontsize=8)
ax[0, 0].set_ylabel("모드 사다리"); ax[1, 0].set_ylabel("속도 배율 / 판정"); ax[2, 0].set_ylabel("가로 오차 [mm] (최근접, 바닥 ≈0.5)")
fig.suptitle(f"조건별 시스템 동작 (ep{a.episode}, 진행도 접합 정책): 정상 · 지연 · 통신 단절", fontsize=11); fig.tight_layout(); fig.savefig(a.out, dpi=100); print("saved", a.out)
