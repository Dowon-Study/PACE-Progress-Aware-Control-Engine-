"""9단계 그림: 공급 중단 길이 T 에 대한 (중단 구간 내) 정지 틱, LOCAL 틱, 가로 오차 최대 — 기준선(pacing+ext) vs local(3s) vs local_long(10s).
사용: python -m pace_py.tools.plot_gap_local --base docs/benchmarks/s9_gap_sweep_ep0_post.json --local docs/benchmarks/s9b_gap_sweep_ep0_post.json --out docs/figures/s9_gap_local_ep0.png"""
import argparse, json
import matplotlib; matplotlib.use("Agg")
from matplotlib import font_manager as fm
import matplotlib.pyplot as plt

ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True); ap.add_argument("--local", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
c = [f for f in fm.findSystemFonts() if "NotoSansCJK" in f]
if c: fm.fontManager.addfont(c[0]); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=c[0]).get_name()
rows = [r for r in json.load(open(a.base)) if r["config"] == "pacing_ext"] + json.load(open(a.local))
labels = {"pacing_ext": "페이싱+외삽 (6단계 기준선)", "local": "+ 로컬 연속 정책 (3s 상한)", "local_long": "+ 로컬 연속 정책 (10s 상한)"}
fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
for cfg in ["pacing_ext", "local", "local_long"]:
    rs = sorted([r for r in rows if r["config"] == cfg and r.get("gap_onset_s") is not None], key=lambda r: r["gap_s"]); x = [r["gap_s"] for r in rs]
    ax[0].plot(x, [r["stop_ticks_gap"] / 1000 for r in rs], "o-", label=labels[cfg]); ax[1].plot(x, [r["local_ticks_gap"] / 1000 for r in rs], "o-", label=labels[cfg]); ax[2].plot(x, [r["lat_mm_max_gap"] for r in rs], "o-", label=labels[cfg])
ax[2].axhline(1.0, color="k", lw=0.6, ls="--"); ax[2].text(2.1, 1.05, "용접 허용 1 mm", fontsize=8)
for k, t in enumerate(["중단 구간 내 정지 시간 [s]", "로컬 청크 재생 시간 [s]", "중단 구간 가로 오차 최대 [mm]"]):
    ax[k].set_title(t); ax[k].set_xlabel("공급 중단 길이 T [s]"); ax[k].grid(alpha=.3); ax[k].legend(fontsize=8)
fig.suptitle("9단계: 로컬 감독 계층(연속 정책) 유무에 따른 공급 중단 버티기 (ep0, progress, 지연 100±50ms)")
fig.tight_layout(); fig.savefig(a.out, dpi=100); print("saved", a.out)
