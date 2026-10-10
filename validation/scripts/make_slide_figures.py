"""슬라이드용 보조 그림: AI 추론 지연 분해(A3~A6) + AI 부하 비교(A7). 논문 스타일과 같은 설정."""
import json, sys
from pathlib import Path
import numpy as np, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib import font_manager
ROOT = Path(__file__).resolve().parents[2]; V = ROOT / "validation/figures/verification"; OUT = ROOT / "docs/slides/assets"; OUT.mkdir(parents=True, exist_ok=True)
font_manager.fontManager.addfont("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"); plt.rcParams["font.family"] = "Noto Sans CJK KR"
plt.rcParams.update({"font.size": 11, "axes.titlesize": 12, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.3, "legend.frameon": False, "axes.unicode_minus": False})
ai = json.load(open(V / "s12_realai_ai.json")); dec = ai["A6_decomposition_ms"]
fig, ax = plt.subplots(figsize=(7.2, 2.6))
parts = [("캡처→추론 시작", dec["capture→infer_start_ms"], "#c6dbef"), ("AI 추론 (GPU)", dec["infer_ms"], "#3182bd"), ("발행", dec["infer_end→publish_ms"], "#9ecae1"), ("제어 반영", dec["publish→first_apply_ms"], "#08519c")]
left = 0
for lb, v, c in parts:
    ax.barh(0, v, left=left, color=c, height=0.5, label=f"{lb} {v:.1f} ms"); left += v
ax.text(left + 0.2, 0, f"합계 {left:.1f} ms (avg)   p99 {ai['A6_e2e_us']['p99']/1e3:.1f} ms   max {ai['A6_e2e_us']['max']/1e3:.1f} ms", va="center", fontsize=10)
ax.set_xlim(0, 24); ax.set_yticks([]); ax.set_xlabel("캡처 시각 기준 경과 [ms]"); ax.legend(loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.35), fontsize=9)
ax.text(0, -0.42, f"추론 주기 avg {ai['A4_period_ms']['avg']:.1f} ms (설정 100)  ·  추론시간 avg {ai['A3_infer_ms']['avg']:.1f} / max {ai['A3_infer_ms']['max']:.1f} ms", fontsize=9, color="#444")
ax.set_ylim(-0.6, 0.5); fig.tight_layout(); fig.savefig(OUT / "e2e_decomp.png", dpi=220, bbox_inches="tight"); print("saved e2e")
d = json.load(open(V / "A7_ai_load_A7.json")); by = {c["label"]: c for c in d}
conds = [("AI 없음", "fake"), ("AI 없음\n+ CPU 부하", "fake_stress"), ("AI · CPU 추론", "ai_cpu"), ("AI · GPU 추론", "ai_gpu"), ("AI · GPU 추론\n+ CPU 부하", "ai_gpu_stress")]
fig, ax = plt.subplots(figsize=(7.2, 3.0)); x = np.arange(5)
ax.bar(x - 0.2, [by[k]["stats"]["p99"] for _, k in conds], 0.4, color="#9ecae1", label="p99"); ax.bar(x + 0.2, [by[k]["stats"]["max"] for _, k in conds], 0.4, color="#3182bd", label="max")
for i, (_, k) in enumerate(conds): ax.text(i + 0.2, by[k]["stats"]["max"] + 2, f"{by[k]['stats']['max']:.0f}", ha="center", fontsize=9); ax.text(i, -14, f"미스 {by[k]['a1']['miss']}", ha="center", fontsize=8.5, color="#2e7d32")
ax.axhline(100, color="#d62728", ls=":", lw=1); ax.text(4.4, 102, "기준 100 μs", ha="right", color="#d62728", fontsize=9)
ax.set_xticks(x); ax.set_xticklabels([c[0] for c in conds], fontsize=9); ax.set_ylabel("깨어남 지연 [μs]"); ax.set_ylim(-20, 115); ax.legend(loc="upper left"); ax.set_title("AI 연산 부하 유무에 따른 1 kHz 제어 루프 (각 20,000 틱)")
fig.tight_layout(); fig.savefig(OUT / "ai_load.png", dpi=220, bbox_inches="tight"); print("saved load")

# 절제 실험 (9c~9f): 로컬 블록만 교체 — 수치 출처 docs/benchmarks/README.md 9c 절
fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.0), gridspec_kw={"width_ratios": [1, 1.15]})
blocks = ["없음\n(유지→정지)", "등속\n외삽", "회귀\nMLP", "flow\nmatching"]; T = [2, 4, 10, 10]; T1 = [2, 4, 10, 6]; cols = ["#bdbdbd", "#9ecae1", "#3182bd", "#fdae6b"]
x = np.arange(4); axs[0].bar(x - 0.2, T, 0.4, color=cols, label="정지 0회"); axs[0].bar(x + 0.2, T1, 0.4, color=cols, alpha=0.45, label="1 mm 안 유지")
for i, (a, b) in enumerate(zip(T, T1)): axs[0].text(i - 0.2, a + 0.2, f"{'≥' if a == 10 else ''}{a}", ha="center", fontsize=9); axs[0].text(i + 0.2, b + 0.2, f"{'≥' if b == 10 else ('≈' if b == 6 else '')}{b}", ha="center", fontsize=9)
axs[0].set_xticks(x); axs[0].set_xticklabels(blocks, fontsize=9); axs[0].set_ylabel("버틴 중단 길이 T [s]"); axs[0].set_ylim(0, 12); axs[0].legend(loc="upper left", fontsize=8.5); axs[0].set_title("(a) 보조 궤적 생성기별 버티는 시간", fontsize=10.5)
cases = ["기본", "+ 점프 비례\n블렌딩", "+ 복귀 증강"]; fm = [17.2, 2.3, 12.6]; mlp = [0.59, 0.53, 0.62]; x2 = np.arange(3)
axs[1].bar(x2 - 0.2, mlp, 0.4, color="#3182bd", label="회귀 MLP"); axs[1].bar(x2 + 0.2, fm, 0.4, color="#fdae6b", label="flow matching")
for i, (m, f) in enumerate(zip(mlp, fm)): axs[1].text(i - 0.2, m * 1.25, f"{m:.2f}", ha="center", fontsize=9); axs[1].text(i + 0.2, f * 1.25, f"{f:.1f}", ha="center", fontsize=9)
axs[1].set_yscale("log"); axs[1].set_ylim(0.2, 60); axs[1].axhline(1.0, color="#d62728", ls=":", lw=1); axs[1].text(2.4, 1.1, "허용 1 mm", ha="right", fontsize=8.5, color="#d62728")
axs[1].set_xticks(x2); axs[1].set_xticklabels(cases, fontsize=9); axs[1].set_ylabel("10 s 중단 가로 오차 max [mm]"); axs[1].legend(loc="upper right", fontsize=8.5); axs[1].set_title("(b) 10 s 중단, 복귀 접합까지 포함", fontsize=10.5)
fig.tight_layout(w_pad=1.5); fig.savefig(OUT / "ablation.png", dpi=220, bbox_inches="tight"); print("saved ablation")

# 5단계: 반영 정책 비교 (진행도 접합 vs 시간 인덱스 vs 즉시) — 수치 출처 docs/benchmarks/README.md 5단계
fig, axs = plt.subplots(1, 3, figsize=(9.0, 2.9)); pol = ["시간 인덱스\n(기준선)", "즉시 반영", "진행도 접합\n(PACE)"]; cols = ["#bdbdbd", "#9ecae1", "#3182bd"]; x = np.arange(3)
def bars(ax, vals, ylab, title, fmt="{:.2f}", hline=None, htxt=None, ylim=None):
    ax.bar(x, vals, 0.6, color=cols)
    for i, v in enumerate(vals): ax.text(i, v * 1.03 if not ylim else v + ylim * 0.02, fmt.format(v), ha="center", fontsize=9.5)
    ax.set_xticks(x); ax.set_xticklabels(pol, fontsize=9); ax.set_ylabel(ylab); ax.set_title(title, fontsize=10.5)
    if hline is not None: ax.axhline(hline, color="#d62728", ls=":", lw=1); ax.text(2.4, hline * 1.04, htxt, ha="right", fontsize=8.5, color="#d62728")
    if ylim: ax.set_ylim(0, ylim)
bars(axs[0], [5.16, 0.29, 0.26], "가로 오차 max [mm]", "(a) 공급 중단 2.5 s 뒤 복귀", hline=1.0, htxt="허용 1 mm", ylim=6.2)
bars(axs[1], [2.40, 0.87, 1.07], "복귀 직후 툴 속도 / GT", "(b) 복귀 시 '따라잡기' 가속", hline=1.0, htxt="정상 1.0×", ylim=2.9)
bars(axs[2], [1.00, 0.52, 0.53], "실행된 속도 배율", "(c) 운영자 속도 지령 0.5×", hline=0.5, htxt="지령 0.5×", ylim=1.25)
axs[2].text(0, 1.06, "지령 무시", ha="center", fontsize=8.5, color="#d62728")
fig.tight_layout(w_pad=1.2); fig.savefig(OUT / "policy_compare.png", dpi=220, bbox_inches="tight"); print("saved policy")
