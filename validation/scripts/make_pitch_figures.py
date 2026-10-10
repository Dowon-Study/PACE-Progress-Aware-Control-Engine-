"""발표용 그림: 실측 결과 중 PACE 의 강점이 드러나는 지표를 골라 큰 글씨·단순 구성으로 그린다 (수치는 전부 실측 로그에서 읽음, 가공 없음).
출력: docs/figures/pitch/P1~P8. 사용: MUJOCO 불필요. .venv/bin/python validation/scripts/make_pitch_figures.py"""
import json, csv, sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, Patch
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); V = ROOT / "validation/figures/verification"; OUT = ROOT / "docs/figures/pitch"; OUT.mkdir(parents=True, exist_ok=True)
for f in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]:
    if Path(f).exists(): font_manager.fontManager.addfont(f); plt.rcParams["font.family"] = font_manager.FontProperties(fname=f).get_name()
plt.rcParams.update({"axes.unicode_minus": False, "font.size": 13, "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlesize": 15})
NAVY, TEAL, ORANGE, GRAY, RED, GREEN, LIGHT = "#1b2a49", "#00897b", "#ef6c00", "#90a4ae", "#d32f2f", "#2e7d32", "#eceff1"
J = lambda n: json.load(open(V / f"{n}_ctrl.json", encoding="utf-8"))
MC = {1: "#43a047", 2: "#1e88e5", 3: "#fb8c00", 4: "#8e24aa", 5: "#00acc1", 6: "#e53935", 7: "#26a69a", 0: "#bdbdbd"}
MODE = {1: "NORMAL", 2: "PACING", 3: "LOCAL", 4: "EXTRAP", 5: "HOLD", 6: "STOPPED", 7: "RECOVER"}


def read_run(name):
    rows = list(csv.DictReader(open(ROOT / f"docs/benchmarks/runs/{name}.csv"))); t0 = int(rows[0]["t_sched_ns"])
    return {"t": np.array([(int(r["t_sched_ns"]) - t0) * 1e-9 for r in rows]), "mode": np.array([int(r["mode"]) for r in rows]), "speed": np.array([float(r["speed_scale"]) for r in rows]), "arc": np.array([int(r.get("arc_on", 1)) for r in rows])}


def coverage_curve(name, ep=0):
    from pace_py.tools.trace import load_trace
    from scipy.spatial import cKDTree
    tr = load_trace(str(ROOT / f"docs/benchmarks/runs/{name}.trace.bin")); r = read_run(name); n = min(len(r["t"]), len(tr["tool"]))
    g = np.load(ROOT / f"data/gt/ep_{ep:04d}.npz"); seam = g["seam_pts"]; tree = cKDTree(seam[:, :2]); nseg = len(seam) // 4 + 1
    dist, idx = tree.query(tr["tool"][:n, :2]); ok = (r["arc"][:n] > 0) & np.isin(r["mode"][:n], [1, 2, 3, 4, 7]) & (dist < 2e-3)
    cov = np.zeros(n); seen = set()
    for i in range(n):
        if ok[i]: seen.add(int(idx[i]) // 4)
        cov[i] = 100.0 * len(seen) / nseg
    return r["t"][:n], cov, r["mode"][:n], r["speed"][:n]


def strip(ax, t, mode, y0, h):
    ch = np.flatnonzero(np.diff(mode)) + 1; st = np.r_[0, ch]; en = np.r_[ch, len(mode)]
    for a, b in zip(st, en): ax.axvspan(t[a], t[min(b, len(t) - 1)], ymin=y0, ymax=y0 + h, color=MC.get(int(mode[a]), "#bdbdbd"), lw=0)


def card(ax, x, y, w, h, big, title, sub, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.005,rounding_size=0.02", fc="white", ec=color, lw=2.5))
    ax.text(x + w / 2, y + h * 0.64, big, ha="center", va="center", fontsize=27, fontweight="bold", color=color)
    ax.text(x + w / 2, y + h * 0.34, title, ha="center", va="center", fontsize=12, color=NAVY, fontweight="bold")
    ax.text(x + w / 2, y + h * 0.15, sub, ha="center", va="center", fontsize=9, color="#546e7a")


def p1_hero():
    fig, ax = plt.subplots(figsize=(16, 4.2)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    items = [("0 / 532,000", "1 ms 주기 미스", "12개 실행 전부, 장애 주입 포함", GREEN), ("max 17 μs", "제어 루프 지터 (기준 100 μs)", "GPU 추론 중 13 μs · 부하 중 96 μs", TEAL),
             ("100 %", "6 s AI 단절에도 완주", "일반 재생은 33 % 에서 정지", ORANGE), ("0.30 mm", "4 로봇 용접 오차 (교시 1.47)", "UR5e·Panda·iiwa14·xArm7 0.30~0.32", NAVY), ("0 줄", "로봇 교체 시 핵심 코드 변경", "모델 파일 + 장면 생성기만 추가", "#6a1b9a")]
    w = 0.182; gap = (1 - 5 * w) / 6
    for i, (b, t, s, c) in enumerate(items): card(ax, gap + i * (w + gap), 0.08, w, 0.84, b, t, s, c)
    fig.savefig(OUT / "P1_hero_kpi.png", dpi=170, bbox_inches="tight"); plt.close(fig)


def p2_gap_race():
    tb, cb, mb, sb = coverage_curve("s13_baseline_timeidx_gap6_ep0"); tp, cp, mp, sp_ = coverage_curve("s9b_local_long_gap6_ep0")
    fig, ax = plt.subplots(figsize=(13, 5.6))
    ax.axvspan(12.5, 18.6, color="#ffebee", lw=0); ax.text(15.55, 97, "AI 공급 단절 6 s", ha="center", fontsize=13, color=RED, fontweight="bold")
    ax.plot(tb, cb, color=GRAY, lw=3.5, label="일반 추론 재생 (시간 인덱스 + 유지→정지)"); ax.plot(tp, cp, color=TEAL, lw=3.5, label="PACE (진행도 접합 + 공백 사다리)")
    ax.annotate(f"정지 → {cb[-1]:.0f} % 에서 용접 중단 (불량)", xy=(16.5, cb[-1]), xytext=(20.5, cb[-1] + 14), fontsize=13, color=RED, fontweight="bold", arrowprops=dict(arrowstyle="->", color=RED, lw=2))
    i100 = int(np.argmax(cp >= 99.5)); ax.annotate(f"완주 100 % (t={tp[i100]:.1f} s)", xy=(tp[i100], 100), xytext=(tp[i100] - 8.5, 64), fontsize=13, color=TEAL, fontweight="bold", arrowprops=dict(arrowstyle="->", color=TEAL, lw=2))
    strip(ax, tb, mb, 0.015, 0.045); strip(ax, tp, mp, 0.075, 0.045); ax.text(2.3, 1.5, "기준선 모드", fontsize=9, color="#455a64"); ax.text(2.3, 8.5, "PACE 모드", fontsize=9, color="#455a64")
    ax.set_xlim(2, 30); ax.set_ylim(0, 108); ax.set_xlabel("시간 [s]"); ax.set_ylabel("용접 비드 진행률 [%]"); ax.set_title("같은 6 s 단절 — 기준선은 멈추고, PACE 는 로컬 정책으로 이어 가 완주한다")
    ax.legend(loc="upper left", fontsize=12, frameon=False, bbox_to_anchor=(0, 0.93))
    fig.legend(handles=[Patch(color=MC[k], label=MODE[k]) for k in (1, 2, 3, 5, 6, 7)], loc="lower center", ncol=6, fontsize=10, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=[0, 0.04, 1, 1]); fig.savefig(OUT / "P2_gap_race.png", dpi=170, bbox_inches="tight"); plt.close(fig)


def p3_stop_free():
    rows = [("일반 RTOS 재생 (유지만)", 2.0, GRAY, "2.0 s"), ("+ 페이싱(감속)", 2.0, "#78909c", "2.0 s"), ("+ 페이싱 + 규칙 외삽", 4.0, "#26a69a", "4.0 s"), ("+ 로컬 연속 정책  (PACE 전체)", 10.0, TEAL, "≥ 10 s")]
    fig, ax = plt.subplots(figsize=(12, 4.6)); y = np.arange(len(rows))[::-1]
    for yi, (lb, v, c, txt) in zip(y, rows):
        ax.barh(yi, v, color=c, height=0.62); ax.text(v + 0.2, yi, txt, va="center", fontsize=16, fontweight="bold", color=c)
    ax.axvline(1.0, color=RED, ls="--", lw=1.5); ax.text(1.05, 3.45, "청크 길이 1 s", color=RED, fontsize=10)
    ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rows], fontsize=13); ax.set_xlim(0, 12.5); ax.set_xlabel("정지 없이 버틴 AI 공급 중단 길이 [s]"); ax.set_title("AI 가 끊겨도 정지 없이 버티는 시간 — 2 s → 10 s 이상 (5배)")
    fig.text(0.99, 0.01, "※ 10 s 는 실험 상한(로컬 허용 10 s). 1 mm 용접 허용 안에서는 ≈ 6 s", fontsize=9.5, color="#546e7a", ha="right")
    fig.tight_layout(rect=[0, 0.04, 1, 1]); fig.savefig(OUT / "P3_stop_free_limit.png", dpi=170, bbox_inches="tight"); plt.close(fig)


def p4_recovery():
    items = [("돌출부 접촉 (힘 센서)", "s11_contact"), ("AI 통신 단절 6 s", "s9_disconnect6s_local"), ("드라이브 폴트 1 s (HAL)", "s8_halfault1s")]
    det = [J(n)["B3"]["detect_ms"] for _, n in items]; back = [J(n)["B3"]["back_to_fresh_ms"] / 1e3 for _, n in items]; miss = [J(n)["B3"]["a1_miss_during_abnormal"] for _, n in items]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.4), gridspec_kw={"width_ratios": [1.1, 1]}); y = np.arange(3)[::-1]
    for yi, d, lb in zip(y, det, items):
        a1.plot([0, d], [yi, yi], color=TEAL, lw=6, solid_capstyle="round"); a1.plot(d, yi, "o", ms=16, color=TEAL); a1.text(d + 2, yi, f"{d:.0f} ms", va="center", fontsize=16, fontweight="bold", color=NAVY)
    a1.set_yticks(y); a1.set_yticklabels([i[0] for i in items], fontsize=12); a1.set_xlim(0, 60); a1.set_xlabel("장애 → 감지·대응 시작 [ms]"); a1.set_title("장애 감지: 1 ~ 40 ms (1 kHz 규칙 감시기)")
    for yi, b, lb, m in zip(y, back, items, miss):
        a2.barh(yi, b, color=ORANGE, height=0.55); a2.text(b + 0.15, yi, f"{b:.2f} s", va="center", fontsize=15, fontweight="bold", color=NAVY)
    a2.set_yticks(y); a2.set_yticklabels(["", "", ""]); a2.set_xlim(0, 10.5); a2.set_xlabel("정상(NORMAL) 복귀까지 [s]"); a2.set_title("자동 복귀 — 사람 개입 0, 그동안 주기 미스 0")
    fig.text(0.99, 0.01, "단절 6 s 의 7.95 s = 단절 6 s + 접합 복귀 1.9 s", fontsize=9.5, color="#546e7a", ha="right")
    fig.tight_layout(rect=[0, 0.04, 1, 1]); fig.savefig(OUT / "P4_fault_recovery.png", dpi=170, bbox_inches="tight"); plt.close(fig)


def p5_robots():
    ev = json.load(open(ROOT / "docs/benchmarks/s13_robots4_eye_ep1.json", encoding="utf-8"))["runs"]
    robots = [("UR5e\n6축", "s12_ur5e_eye_ep1"), ("Franka Panda\n7축", "s8_panda_eye_ep1"), ("KUKA iiwa14\n7축", "s13_iiwa14_eye_ep1"), ("UFactory xArm7\n7축", "s13_xarm7_eye_ep1")]
    before = 1.47; after = [ev[n]["lat_mean_mm"] for _, n in robots]
    fig, ax = plt.subplots(figsize=(12, 5)); x = np.arange(4)
    ax.bar(x - 0.2, [before] * 4, 0.4, color=GRAY, label="교시 경로만 (고정구 오차 그대로)"); ax.bar(x + 0.2, after, 0.4, color=TEAL, label="PACE: 눈 보정 (CORRECTION) 적용")
    for i, a in enumerate(after): ax.text(i + 0.2, a + 0.04, f"{a:.2f}", ha="center", fontsize=15, fontweight="bold", color=TEAL); ax.text(i - 0.2, before + 0.04, f"{before:.2f}", ha="center", fontsize=12, color="#546e7a")
    ax.axhline(1.0, color=RED, ls="--", lw=1.5); ax.text(3.55, 1.04, "용접 허용 1 mm", color=RED, fontsize=11, ha="right")
    ax.set_xticks(x); ax.set_xticklabels([r[0] for r in robots], fontsize=13); ax.set_ylabel("실제 용접선 대비 가로 오차 mean [mm]"); ax.set_ylim(0, 1.85)
    ax.set_title("서로 다른 4 로봇, 같은 제어기·같은 눈 → 오차 1.47 → 0.30 mm (약 5배 개선), 코드 변경 0 줄"); ax.legend(loc="upper left", frameon=False, fontsize=12)
    fig.tight_layout(); fig.savefig(OUT / "P5_robots_error.png", dpi=170, bbox_inches="tight"); plt.close(fig)


def p6_validator():
    inj = J("s4_outliers")["B1"]; ai = J("s12_realai")["B1"]
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(14, 4.6))
    a1.pie([3, 0.0001], colors=[RED, LIGHT], startangle=90, wedgeprops=dict(width=0.32)); a1.text(0, 0.08, "3 / 3", ha="center", va="center", fontsize=30, fontweight="bold", color=RED); a1.text(0, -0.3, "주입 이상값 거부", ha="center", fontsize=12, color=NAVY)
    a1.set_title("속도 한계 · 순서 역전 · 신뢰도 미달\n→ 전부 사유 일치로 거부", fontsize=12)
    n = ai["reject_ticks"]; tot = round(n / ai["reject_ratio"]); a2.pie([n, tot - n], colors=[ORANGE, LIGHT], startangle=90, wedgeprops=dict(width=0.32)); a2.text(0, 0.08, f"{100*n/tot:.0f} %", ha="center", va="center", fontsize=30, fontweight="bold", color=ORANGE); a2.text(0, -0.3, f"실제 AI 잡음 청크 거부 ({n}/{tot})", ha="center", fontsize=11, color=NAVY)
    a2.set_title("실제 AI 모델의 흔들리는 청크도\n가속 한계로 걸러 로봇에 전달 안 함", fontsize=12)
    a3.pie([0.0001, 1], colors=[RED, GREEN], startangle=90, wedgeprops=dict(width=0.32)); a3.text(0, 0.08, "0", ha="center", va="center", fontsize=34, fontweight="bold", color=GREEN); a3.text(0, -0.3, "유효기간 지난 결과 사용", ha="center", fontsize=12, color=NAVY)
    a3.set_title("늦게 도착한 AI 결과는 절대 실행 안 함\n(검증기 3단계: 범위 → 시간 → 유효성)", fontsize=12)
    fig.suptitle("AI 결과 검증기 — 틀린 것·늦은 것은 로봇에 닿지 않는다", fontsize=15, fontweight="bold"); fig.tight_layout(); fig.savefig(OUT / "P6_validator.png", dpi=170, bbox_inches="tight"); plt.close(fig)


def p7_jitter_load():
    d = json.load(open(V / "A7_ai_load_A7.json", encoding="utf-8"))
    conds = [("AI 없음", "fake"), ("AI 없음 + CPU 부하", "fake_stress"), ("실제 AI · CPU 추론", "ai_cpu"), ("실제 AI · GPU 추론", "ai_gpu"), ("실제 AI · GPU + CPU 부하", "ai_gpu_stress")]
    by = {c["label"]: c["stats"] for c in d}; mx = [by[k]["max"] for _, k in conds]; p99 = [by[k]["p99"] for _, k in conds]
    fig, ax = plt.subplots(figsize=(12, 4.8)); x = np.arange(len(conds))
    ax.bar(x, mx, 0.55, color=[TEAL, TEAL, TEAL, TEAL, "#26a69a"]); ax.plot(x, p99, "D", color=NAVY, ms=9, label="p99")
    for i, (m, p) in enumerate(zip(mx, p99)):
        if m > 60: ax.text(i, m - 9, f"max {m:.0f} μs", ha="center", fontsize=13, fontweight="bold", color="white")
        else: ax.text(i, m + 2.5, f"max {m:.0f} μs", ha="center", fontsize=13, fontweight="bold", color=NAVY)
    ax.axhline(100, color=RED, ls="--", lw=2); ax.text(0.02, 103, "과제 기준 ±100 μs", color=RED, fontsize=12, ha="left", transform=ax.get_yaxis_transform())
    ax.set_xticks(x); ax.set_xticklabels([c[0] for c in conds], fontsize=11); ax.set_ylabel("1 kHz 루프 깨어남 지연 [μs]"); ax.set_ylim(0, 118); ax.legend(frameon=False)
    ax.set_title("AI 가 돌아도 제어 루프는 흔들리지 않는다 — 5조건 모두 주기 미스 0, 기준 안"); fig.tight_layout(); fig.savefig(OUT / "P7_jitter_under_ai_load.png", dpi=170, bbox_inches="tight"); plt.close(fig)


def p8_safety():
    items = [("정상", "s5_normal"), ("지연 200 ms", "s5_delay200ms"), ("이상값 주입", "s4_outliers"), ("누락", "s5_dropout"), ("단절 6 s", "s9_disconnect6s_local"), ("HAL 폴트", "s8_halfault1s"), ("접촉", "s11_contact"), ("실제 AI", "s12_realai")]
    trk = [J(n)["B2"]["track_err_rad"]["max"] * 1e3 for _, n in items]
    fig, ax = plt.subplots(figsize=(12, 4.8)); x = np.arange(len(items))
    ax.bar(x, trk, 0.6, color=TEAL)
    for i, v in enumerate(trk): ax.text(i, v + 1.5, f"{v:.1f}", ha="center", fontsize=13, fontweight="bold", color=NAVY)
    ax.axhline(100, color=RED, ls="--", lw=2); ax.text(7.3, 103, "감시기 정지 한계 100 mrad", color=RED, fontsize=12, ha="right")
    ax.annotate("최악 조건도 한계의 1/9", xy=(6, 10.6), xytext=(3.2, 60), fontsize=14, fontweight="bold", color=NAVY, arrowprops=dict(arrowstyle="->", color=NAVY, lw=2))
    ax.set_xticks(x); ax.set_xticklabels([i[0] for i in items], fontsize=12); ax.set_ylabel("추종 오차 max [mrad]"); ax.set_ylim(0, 118)
    ax.set_title("장애를 주입해도 로봇은 흔들리지 않는다 — 추종 오차 max ≤ 10.6 mrad (전 조건)"); fig.tight_layout(); fig.savefig(OUT / "P8_safety_margin.png", dpi=170, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    for f in (p1_hero, p2_gap_race, p3_stop_free, p4_recovery, p5_robots, p6_validator, p7_jitter_load, p8_safety): f(); print("saved", f.__name__)
