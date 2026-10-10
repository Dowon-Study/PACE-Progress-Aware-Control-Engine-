"""공정 상태 추론기 시연 그림: 속도 배율 vs 아크 출력(PARAM), 입열 지수(아크/속도) 제어 유무 비교.
사용: python -m pace_py.tools.plot_process --run s11_process_gap --out docs/figures/s11_process_gap_ep0.png"""
import argparse, csv, json
import numpy as np
import matplotlib; matplotlib.use("Agg")
from matplotlib import font_manager as fm
_c = [f for f in fm.findSystemFonts() if "NotoSansCJK" in f]
if _c: fm.fontManager.addfont(_c[0]); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c[0]).get_name()
import matplotlib.pyplot as plt

ap = argparse.ArgumentParser(); ap.add_argument("--run", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
rows = list(csv.DictReader(open(f"docs/benchmarks/runs/{a.run}.csv"))); t0 = int(rows[0]["t_sched_ns"]); t = np.array([(int(r["t_sched_ns"]) - t0) * 1e-9 for r in rows])
sp = np.array([float(r["speed_scale"]) for r in rows]); ap_ = np.array([int(r["arc_power_pct"]) for r in rows]); arc = np.array([int(r["arc_on"]) for r in rows])
on = arc == 1; H = np.where(on, ap_ / 100.0 / np.maximum(sp, 0.05), np.nan); H0 = np.where(on, 1 / np.maximum(sp, 0.05), np.nan)
fig, ax = plt.subplots(2, 1, figsize=(9, 4.6), sharex=True)
ax[0].plot(t, sp, label="속도 배율"); ax[0].plot(t, ap_ / 100, label="아크 출력 (공정 상태 추론기 PARAM)"); ax[0].step(t, arc * 0.05, where="post", lw=0.8, color="k", label="아크 ON"); ax[0].legend(fontsize=7); ax[0].grid(alpha=.3); ax[0].set_ylim(-0.05, 1.1)
ax[1].plot(t, H, color="C3", label="입열 지수 = 아크/속도 (제어)"); ax[1].plot(t, H0, color="C7", ls="--", label="아크 제어 없을 때"); ax[1].set_ylim(0, 6); ax[1].legend(fontsize=7); ax[1].grid(alpha=.3); ax[1].set_xlabel("t [s]")
fig.suptitle("공정 상태 추론(규칙) 기반 파라미터 변경: 페이싱으로 느려지면 아크 출력을 낮춰 입열 유지", fontsize=10); fig.tight_layout(); fig.savefig(a.out, dpi=110)
w = on & (sp < 0.95); print(json.dumps({"slow_window_ticks": int(w.sum()), "speed_min": float(sp[on].min()), "arc_power_min_pct": int(ap_[on].min()), "heat_index_mean_controlled": float(np.nanmean(H[w])) if w.any() else None, "heat_index_max_controlled": float(np.nanmax(H[w])) if w.any() else None, "heat_index_max_uncontrolled": float(np.nanmax(H0[w])) if w.any() else None})); print("saved", a.out)
