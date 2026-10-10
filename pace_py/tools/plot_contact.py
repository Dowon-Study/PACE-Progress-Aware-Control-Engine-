"""접촉력 시연 그림: 접촉력 / 속도 배율·감시기 판정 / 툴 높이(스탠드오프 상승) / 실제 용접선 대비 가로 오차.
사용: python -m pace_py.tools.plot_contact --run s11_contact_ep1 --episode 1 --out docs/figures/s11_contact_ep1.png"""
import argparse, csv, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.trace import load_trace                       # noqa: E402
from pace_py.tools.eval_refpath import evaluate, load_rpth        # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("--run", required=True); ap.add_argument("--episode", type=int, required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
rows = list(csv.DictReader(open(f"docs/benchmarks/runs/{a.run}.csv"))); t0 = int(rows[0]["t_sched_ns"]); t = np.array([(int(r["t_sched_ns"]) - t0) * 1e-9 for r in rows])
F = np.array([float(r["tool_force_N"]) for r in rows]); sp = np.array([float(r["speed_scale"]) for r in rows]); mon = np.array([int(r["monitor"]) for r in rows]); arc = np.array([int(r["arc_on"]) for r in rows])
_, poly, _ = load_rpth(f"data/refpath/ep_{a.episode:04d}_real.bin"); ev = evaluate(f"docs/benchmarks/runs/{a.run}.trace.bin", poly); tr = load_trace(f"docs/benchmarks/runs/{a.run}.trace.bin"); tt = (tr["t_ns"] - tr["t_ns"][0]) * 1e-9
import matplotlib; matplotlib.use("Agg")
from matplotlib import font_manager as fm
_c = [f for f in fm.findSystemFonts() if "NotoSansCJK" in f]
if _c: fm.fontManager.addfont(_c[0]); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c[0]).get_name()
import matplotlib.pyplot as plt
fig, ax = plt.subplots(4, 1, figsize=(10, 8), sharex=True)
ax[0].plot(t, F, color="C3"); ax[0].set_ylabel("tip contact force [N]"); ax[0].axhline(2, ls="--", lw=0.7, color="k"); ax[0].axhline(30, ls=":", lw=0.7, color="k"); ax[0].grid(alpha=.3)
ax[1].plot(t, sp, color="C1", label="speed scale"); ax[1].step(t, mon / 2.0, where="post", color="k", alpha=.6, lw=0.8, label="monitor (0 OK, .5 SLOW, 1 STOP)"); ax[1].step(t, arc * 0.9, where="post", color="C4", lw=0.8, label="arc on"); ax[1].set_ylim(-0.05, 1.1); ax[1].legend(fontsize=7); ax[1].grid(alpha=.3)
ax[2].plot(tt, (tr["tool"][:, 2] - 0.310) * 1e3, color="C0"); ax[2].set_ylabel("tool height above plate [mm]"); ax[2].grid(alpha=.3)
m = ev["weld_mask"]; ax[3].plot(ev["t"][m], ev["lat_mm"][m], color="C2"); ax[3].set_ylabel("lateral err vs real seam [mm]"); ax[3].set_xlabel("t [s]"); ax[3].grid(alpha=.3)
c = F > 2.0
if c.any():
    for k in range(4): ax[k].axvspan(t[c][0], t[c][-1], color="C3", alpha=.08)
fig.suptitle(f"접촉력 기반 조정 — {a.run}: 돌출부 접촉 → SLOW(0.5×) + 스탠드오프 상승 → 통과 후 복귀", fontsize=10); fig.tight_layout(); fig.savefig(a.out, dpi=110)
s = ev["summary"]; print(json.dumps({"contact_ticks": int(c.sum()), "F_max_N": float(F.max()), "slow_ticks": int((mon == 1).sum()), "stop_ticks": int((mon == 2).sum()), "lift_max_mm": float((tr["tool"][:, 2].max() - 0.312) * 1e3), "lat_mean_mm": s["lat_mean_mm"], "lat_max_mm": s["lat_max_mm"], "s_reached": s["s_reached_m"]}, indent=0)); print("saved", a.out)
