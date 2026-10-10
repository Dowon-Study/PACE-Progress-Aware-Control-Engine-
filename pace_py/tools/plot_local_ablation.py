"""로컬 블록 절제 실험 그림/표: 없음(유지) / 규칙 외삽 / 회귀 MLP / flow matching — 중단 구간 내 정지 시간, LOCAL 재생, 가로 오차 최대.
사용: python -m pace_py.tools.plot_local_ablation --out docs/figures/s9c_local_ablation_ep0.png"""
import argparse, json
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
from matplotlib import font_manager as fm
_c = [f for f in fm.findSystemFonts() if "NotoSansCJK" in f]
if _c: fm.fontManager.addfont(_c[0]); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c[0]).get_name()
import matplotlib.pyplot as plt

ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--md", default=None); a = ap.parse_args()
SRC = [("없음 (유지 → 정지)", "docs/benchmarks/s6_gap_sweep_ep0_post.json", "hold"), ("규칙 외삽 (페이싱+외삽)", "docs/benchmarks/s9_gap_sweep_ep0_post.json", "pacing_ext"),
       ("회귀 MLP (10s 상한)", "docs/benchmarks/s9c_mlp_gap_sweep_ep0_post.json", "local_long"), ("flow matching (10s 상한)", "docs/benchmarks/s9c_fm_gap_sweep_ep0_post.json", "local_long")]
fig, ax = plt.subplots(1, 3, figsize=(15, 4.2)); rows_md = ["| 로컬 블록 | T [s] | 정지 [s] | LOCAL [s] | 가로 오차 max [mm] |", "|---|---|---|---|---|"]
for lb, f, cfg in SRC:
    if not Path(f).exists(): continue
    rs = sorted([r for r in json.load(open(f)) if r["config"] == cfg and r.get("gap_onset_s") is not None and r["gap_s"] >= 2.0], key=lambda r: r["gap_s"]); x = [r["gap_s"] for r in rs]
    ax[0].plot(x, [r["stop_ticks_gap"] / 1000 for r in rs], "o-", label=lb); ax[1].plot(x, [r["local_ticks_gap"] / 1000 for r in rs], "o-", label=lb); ax[2].plot(x, [r["lat_mm_max_gap"] for r in rs], "o-", label=lb)
    for r in rs: rows_md.append(f"| {lb} | {r['gap_s']:g} | {r['stop_ticks_gap']/1000:.2f} | {r['local_ticks_gap']/1000:.2f} | {r['lat_mm_max_gap']:.2f} |")
ax[2].axhline(1.0, color="k", lw=0.6, ls="--"); ax[2].text(2.1, 1.05, "용접 허용 1 mm", fontsize=8); ax[2].set_yscale("log")
for k, t in enumerate(["중단 구간 내 정지 시간 [s]", "로컬 청크 재생 시간 [s]", "중단 구간 가로 오차 최대 [mm] (log)"]):
    ax[k].set_title(t); ax[k].set_xlabel("공급 중단 길이 T [s]"); ax[k].grid(alpha=.3); ax[k].legend(fontsize=8)
fig.suptitle("로컬 블록 절제 실험 (ep0, 같은 사다리): 없음 / 규칙 외삽 / 회귀 MLP / flow matching", fontsize=11); fig.tight_layout(); fig.savefig(a.out, dpi=100); print("saved", a.out)
if a.md: Path(a.md).write_text("\n".join(rows_md)); print("\n".join(rows_md))
