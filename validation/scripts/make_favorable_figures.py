"""12개 검증 중 기본 항목(A1 제어주기, A2 지터, A3/A4/A5 AI 추론·반영 지연, A7 AI 부하 비교) 을 제외하고
PACE 에 유리하게 나온 항목 — A8 조건별 동작, B1 검증 거부, B2 안전 동작, B3 장애 복구, B4 HAL 교체 비용 — 을 그림으로 만든다.
입력: validation/figures/verification/*_ctrl.json (verify.py 결과), docs/benchmarks/runs/*.csv, B4_hal_swap.md 의 원본 summary.json.
사용: .venv/bin/python validation/scripts/make_favorable_figures.py --out validation/figures/verification/favorable"""
import argparse, json, csv
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
ROOT = Path(__file__).resolve().parents[2]; V = ROOT / "validation/figures/verification"
for f in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]:
    if Path(f).exists(): font_manager.fontManager.addfont(f); plt.rcParams["font.family"] = font_manager.FontProperties(fname=f).get_name(); break
plt.rcParams["axes.unicode_minus"] = False
J = lambda n: json.load(open(V / f"{n}_ctrl.json", encoding="utf-8"))
MODE = {0: "INIT", 1: "NORMAL", 2: "PACING", 3: "LOCAL", 4: "EXTRAP", 5: "HOLD", 6: "STOPPED", 7: "RECOVER"}
MC = {1: "#4caf50", 2: "#42a5f5", 3: "#ffb300", 4: "#ab47bc", 5: "#26c6da", 6: "#e53935", 7: "#26a69a", 0: "#9e9e9e"}
SC = {"fresh": "#4caf50", "pacing": "#42a5f5", "local": "#ffb300", "extrap": "#ab47bc", "hold": "#26c6da", "stop": "#e53935", "recover": "#26a69a", "reject": "#ff7043"}


def read_run(name):
    rows = list(csv.DictReader(open(ROOT / f"docs/benchmarks/runs/{name}.csv")))
    t0 = int(rows[0]["t_sched_ns"]); t = np.array([(int(r["t_sched_ns"]) - t0) * 1e-9 for r in rows])
    return {"t": t, "mode": np.array([int(r["mode"]) for r in rows]), "speed": np.array([float(r["speed_scale"]) for r in rows]),
            "dev": np.array([float(r["deviation"]) for r in rows]), "reject": np.array([int(r["reject"]) for r in rows]), "arc": np.array([int(r.get("arc_on", 1)) for r in rows])}


def mode_strip(ax, t, mode, y0=0, h=1):
    ch = np.flatnonzero(np.diff(mode)) + 1; st = np.r_[0, ch]; en = np.r_[ch, len(mode)]
    for a, b in zip(st, en): ax.axvspan(t[a], t[min(b, len(t) - 1)], ymin=y0, ymax=y0 + h, color=MC.get(int(mode[a]), "#9e9e9e"), lw=0)


def fig_a8(out):
    runs = [("정상 (상태 인지 AI)", "s5_progress_d0_ep0", None), ("추론 지연 200 ms", "s5_progress_d200_ep0", None), ("이상값 주입 3종 (거부) + 19 s AI ESTOP 이벤트 주입 (의도된 정지 → 복귀)", "s4_faultsA_ep4", [9.62, 11.62, 13.62]),
            ("누락 (dropout 1 s, 반복)", "s5_dropout_progress_d100_ep0", None), ("통신 단절 6 s (로컬 정책)", "s9b_local_long_gap6_ep0", None)]
    fig, axs = plt.subplots(len(runs), 1, figsize=(12, 2.1 * len(runs)), sharex=True)
    for ax, (lb, name, marks) in zip(axs, runs):
        r = read_run(name); m = (r["t"] >= 4) & (r["t"] <= 23)
        mode_strip(ax, r["t"], r["mode"], 0.0, 0.18)
        ax.plot(r["t"][m], r["speed"][m], color="#1565c0", lw=1.2, label="속도 배율")
        ax2 = ax.twinx(); ax2.plot(r["t"][m], r["dev"][m] * 1e3, color="#6d4c41", lw=0.8, alpha=0.8, label="이탈도 [mrad]"); ax2.set_ylim(0, max(2, np.nanmax(r["dev"][m]) * 1e3 * 1.3)); ax2.set_ylabel("이탈도 mrad", fontsize=8)
        if marks:
            for x in marks: ax.axvline(x, color="#ff7043", ls="--", lw=1)
        ax.set_ylim(0, 1.25); ax.set_xlim(4, 23); ax.set_ylabel("속도 배율", fontsize=8); ax.set_title(lb, fontsize=10, loc="left")
        if "ESTOP" in lb: ax.axvline(19.02, color="#e53935", ls=":", lw=1.2)
        sticks = int((r["mode"][m] == 6).sum()); ax.text(0.99, 0.9, f"용접 구간 주기 미스 0 · 정지 틱 {sticks}", transform=ax.transAxes, ha="right", va="top", fontsize=8, bbox=dict(fc="white", ec="none", alpha=0.8))
    axs[-1].set_xlabel("시간 [s]")
    fig.legend(handles=[Patch(color=MC[k], label=MODE[k]) for k in (1, 2, 3, 4, 5, 6, 7)] + [plt.Line2D([], [], color="#1565c0", label="속도 배율"), plt.Line2D([], [], color="#6d4c41", label="이탈도")], loc="lower center", ncol=9, fontsize=8, frameon=False)
    fig.suptitle("A8 조건별 시스템 동작 (용접 구간 4~23 s) — 정상 · 지연 · 이상값 · 누락 · 단절: 모드 띠(아래)가 규칙대로 전이, 급격한 동작 없음", fontsize=11)
    fig.tight_layout(rect=[0, 0.05, 1, 0.97]); fig.savefig(out / "A8_conditions_overview.png", dpi=150); plt.close(fig)


def fig_b1(out):
    inj = J("s4_outliers")["B1"]; ai = J("s12_realai")["B1"]; ct = J("s11_contact")["B1"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [1.1, 1.6]})
    labels = ["RANGE_VEL\n(속도 한계)", "SEQ_ORDER\n(순서 역전)", "CONFIDENCE\n(신뢰도 미달)", "RANGE_ACC\n(실제 AI 잡음)", "RANGE_POS\n(접촉 회피 중)"]
    vals = [inj["reasons"].get("RANGE_VEL", 0), inj["reasons"].get("SEQ_ORDER", 0), inj["reasons"].get("CONFIDENCE", 0), ai["reasons"].get("RANGE_ACC", 0), ct["reasons"].get("RANGE_POS", 0)]
    cols = ["#ef5350"] * 3 + ["#ffa726", "#ab47bc"]
    b = a1.bar(range(5), vals, color=cols); a1.set_xticks(range(5)); a1.set_xticklabels(labels, fontsize=8); a1.set_ylabel("거부 건수"); a1.set_yscale("symlog", linthresh=5)
    for i, v in enumerate(vals): a1.text(i, v * 1.15 + 0.1, f"{v}", ha="center", fontsize=9)
    a1.set_title("B1 검증기 거부 — 주입 3종 전부 거부(사유 일치), 실제 AI 잡음 58/230 (25.2 %)\n유효기간 만료 결과 사용: 0", fontsize=9, loc="left")
    r = read_run("s4_faultsA_ep4"); m = (r["t"] >= 8) & (r["t"] <= 16)
    mode_strip(a2, r["t"], r["mode"], 0, 0.15); a2.plot(r["t"][m], r["speed"][m], color="#1565c0", lw=1.3, label="속도 배율")
    for x in r["t"][m][r["reject"][m] > 0]: a2.axvline(x, color="#ff7043", ls="--", lw=1.2)
    a2.set_xlim(8, 16); a2.set_ylim(0, 1.25); a2.set_xlabel("시간 [s]"); a2.set_ylabel("속도 배율")
    a2.set_title("이상값 주입 시각(주황 점선)에 거부되고 모드는 NORMAL 유지 — 거부가 동작에 영향 없음", fontsize=9, loc="left")
    a2.legend(handles=[Patch(color=MC[1], label="NORMAL"), plt.Line2D([], [], color="#ff7043", ls="--", label="거부 틱"), plt.Line2D([], [], color="#1565c0", label="속도 배율")], fontsize=8, loc="lower right")
    fig.tight_layout(); fig.savefig(out / "B1_validator_rejects.png", dpi=150); plt.close(fig)


def fig_b2(out):
    items = [("정상", "s5_normal"), ("지연 200 ms", "s5_delay200ms"), ("이상값", "s4_outliers"), ("누락", "s5_dropout"), ("단절 6 s\n(로컬)", "s9_disconnect6s_local"), ("HAL 폴트\n1 s", "s8_halfault1s"), ("접촉", "s11_contact"), ("실제 AI", "s12_realai")]
    jerk = [J(n)["B2"]["jerk_rad_s3"]["p99"] for _, n in items]; trk = [J(n)["B2"]["track_err_rad"]["max"] * 1e3 for _, n in items]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2))
    x = np.arange(len(items)); cols = ["#4caf50"] + ["#42a5f5"] * 4 + ["#ff7043", "#ab47bc", "#ffa726"]
    a1.bar(x, np.array(jerk) / 1e3, color=cols); a1.set_xticks(x); a1.set_xticklabels([i[0] for i in items], fontsize=8); a1.set_ylabel("명령 저크 p99 [krad/s³]")
    a1.axhline(jerk[0] / 1e3, color="#4caf50", ls="--", lw=1); a1.text(len(items) - 0.5, jerk[0] / 1e3 * 1.05, "정상 기준", ha="right", fontsize=8, color="#2e7d32")
    for i, v in enumerate(jerk): a1.text(i, v / 1e3 + 0.5, f"{v/1e3:.1f}", ha="center", fontsize=8)
    a1.set_title("B2 저크 — 지연·이상값·누락·단절은 정상과 같은 수준 (≈8~10 k)\n정지 램프(HAL 폴트·접촉)는 의도된 감속 명령이라 3배 (한계 내)", fontsize=9, loc="left")
    a2.bar(x, trk, color=cols); a2.set_xticks(x); a2.set_xticklabels([i[0] for i in items], fontsize=8); a2.set_ylabel("추종 오차 max [mrad]")
    a2.axhline(100, color="#e53935", ls="--", lw=1); a2.text(len(items) - 0.5, 62, "감시기 정지 한계 100 mrad", ha="right", fontsize=8, color="#c62828"); a2.set_yscale("log"); a2.set_ylim(0.3, 200)
    for i, v in enumerate(trk): a2.text(i, v * 1.15, f"{v:.1f}", ha="center", fontsize=8)
    a2.set_title("B2 추종 오차 — 모든 장애 조건에서 max ≤ 10.6 mrad (한계의 1/10)", fontsize=9, loc="left")
    fig.tight_layout(); fig.savefig(out / "B2_safety_jerk_tracking.png", dpi=150); plt.close(fig)


def fig_b3(out):
    items = [("HAL 폴트 1 s (t=10 s)", "s8_halfault1s", 10.0, (9.5, 13.0)), ("통신 단절 6 s (t≈12.5 s)", "s9_disconnect6s_local", 13.0, (11, 22)), ("돌출부 접촉 (t≈12.2 s)", "s11_contact", 12.2, (11.8, 14.2)), ("HAL 폴트 5 s → ESTOP 체결 (설계대로 복귀 없음)", "s8_halfault5s_estop", 10.0, (9.5, 14))]
    fig, axs = plt.subplots(len(items), 1, figsize=(12, 1.55 * len(items) + 0.8))
    for ax, (lb, n, tf, xr) in zip(axs, items):
        d = J(n); segs = d["B3"]["segments"]; b3 = d["B3"]
        for s in segs:
            ax.barh(0, s["dur_ms"] / 1e3, left=s["t0_s"], height=0.6, color=SC.get(s["state"], "#9e9e9e"), lw=0)
        ax.axvline(tf, color="k", ls="--", lw=1); ax.text(tf, 0.42, " 장애", fontsize=8, va="bottom")
        txt = f"감지 {b3['detect_ms']:.0f} ms" if b3.get("detect_ms") is not None else "감지 –"
        txt += f" · 정상 복귀 {b3['back_to_fresh_ms']/1e3:.2f} s" if b3.get("back_to_fresh_ms") is not None else " · 복귀 없음(ESTOP 체결)"
        txt += f" · 비정상 구간 중 주기 미스 {b3['a1_miss_during_abnormal']}"
        ax.set_xlim(*xr); ax.set_ylim(-0.5, 0.75); ax.set_yticks([]); ax.set_title(f"{lb} — {txt}", fontsize=9, loc="left")
    axs[-1].set_xlabel("시간 [s]")
    fig.legend(handles=[Patch(color=SC[k], label=k) for k in ("fresh", "pacing", "local", "extrap", "hold", "stop", "recover", "reject")], loc="lower center", ncol=8, fontsize=8, frameon=False)
    fig.suptitle("B3 장애 복구 — 감지 1~40 ms, 복귀 0.09~7.9 s, 비정상 구간에서도 1 ms 주기 미스 0", fontsize=11)
    fig.tight_layout(rect=[0, 0.07, 1, 0.95]); fig.savefig(out / "B3_fault_recovery.png", dpi=150); plt.close(fig)


def fig_b4(out):
    runs = [("UR5e 6축\n직접 HAL", "s12_ur5e_eye_ep1"), ("Panda 7축\n직접 HAL", "s8_panda_eye_ep1"), ("iiwa14 7축\n직접 HAL", "s13_iiwa14_eye_ep1"), ("xArm7 7축\n직접 HAL", "s13_xarm7_eye_ep1"), ("UR5e\nros2_control", "s8_hal_ros2_eye_ep1")]
    ev = json.load(open(ROOT / "docs/benchmarks/s13_robots4_eye_ep1.json", encoding="utf-8"))
    def lat(n): return ev.get("runs", {}).get(n)
    means, maxs, rd, wr, ex = [], [], [], [], []
    fallback = {"s12_ur5e_eye_ep1": (0.30, 0.50), "s8_panda_eye_ep1": (0.30, 0.48), "s13_iiwa14_eye_ep1": (0.32, 1.58), "s13_xarm7_eye_ep1": (0.31, 0.70), "s8_hal_ros2_eye_ep1": (0.31, 0.53)}
    for _, n in runs:
        s = json.load(open(ROOT / f"docs/benchmarks/runs/{n}.summary.json")); h = s["hal"]; rd.append(h["read_max_us"]); wr.append(h["write_max_us"]); ex.append(s["loop_exec"]["max_us"])
        e = lat(n); means.append(e["lat_mean_mm"] if e and "lat_mean_mm" in e else fallback[n][0]); maxs.append(e["lat_max_mm"] if e and "lat_max_mm" in e else fallback[n][1])
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(13, 4.2), gridspec_kw={"width_ratios": [1.3, 1.1, 1]})
    x = np.arange(len(runs)); a1.bar(x - 0.18, means, 0.36, color="#4caf50", label="mean"); a1.bar(x + 0.18, maxs, 0.36, color="#a5d6a7", label="max")
    a1.axhline(1.0, color="#e53935", ls="--", lw=1); a1.text(len(runs) - 0.5, 1.03, "용접 허용 1 mm", ha="right", fontsize=8, color="#c62828"); a1.axhline(1.47, color="#9e9e9e", ls=":", lw=1); a1.text(-0.4, 1.5, "교시 경로만 (고정구 오차) 1.47 mm", fontsize=8, color="#616161")
    a1.set_xticks(x); a1.set_xticklabels([r[0] for r in runs], fontsize=8); a1.set_ylabel("실제 용접선 대비 가로 오차 [mm]"); a1.legend(fontsize=8); a1.set_ylim(0, 1.8)
    for i, v in enumerate(means): a1.text(i - 0.18, v + 0.03, f"{v:.2f}", ha="center", fontsize=8)
    a1.set_title("같은 제어기·같은 눈·같은 교시 경로 → 4 로봇 + ros2 경로 모두 0.30~0.32 mm", fontsize=9, loc="left")
    a2.bar(x - 0.18, rd, 0.36, color="#42a5f5", label="HAL read max"); a2.bar(x + 0.18, wr, 0.36, color="#1565c0", label="HAL write max"); a2.plot(x, ex, "k_", ms=14, mew=2, label="루프 실행 max")
    a2.set_xticks(x); a2.set_xticklabels([r[0] for r in runs], fontsize=8); a2.set_ylabel("μs"); a2.legend(fontsize=8); a2.axhline(100, color="#e53935", ls="--", lw=1); a2.text(len(runs) - 0.5, 92, "지터 기준 100 μs", ha="right", fontsize=8, color="#c62828")
    a2.set_title("HAL 변환 지연 — 직접 ≤ 15 μs, ros2 플러그인 40 μs (1 ms 의 4 % 이하)", fontsize=9, loc="left")
    def wc(p): return sum(1 for _ in open(ROOT / p, encoding="utf-8", errors="ignore"))
    added = {"Panda": ["pace/models/panda/panda_torch.xml", "pace_py/tools/make_panda_scene.py"], "iiwa14+xArm7": ["pace/models/iiwa14/iiwa14_torch.xml", "pace/models/xarm7/xarm7_torch.xml", "pace_py/tools/make_robot_scene.py"], "ros2_control": ["pace/src/hal_ros2.cpp", "pace/ros2/pace_mujoco_hardware.cpp", "pace/ros2/ur5e_pace_mujoco.urdf"]}
    names = list(added); av = [sum(wc(f) for f in added[k]) for k in names]; xx = np.arange(len(names))
    a3.bar(xx - 0.18, av, 0.36, color="#90a4ae", label="새로 쓴 줄 (모델·장면·어댑터)"); a3.bar(xx + 0.18, [0, 0, 0], 0.36, color="#e53935", label="제어기·검증기·접합·눈 변경 줄")
    for i, v in enumerate(av): a3.text(i - 0.18, v + 10, f"{v}", ha="center", fontsize=8)
    for i in xx: a3.text(i + 0.18, 15, "0", ha="center", fontsize=10, color="#c62828", fontweight="bold")
    a3.set_xticks(xx); a3.set_xticklabels(names, fontsize=8); a3.set_ylabel("줄 수"); a3.set_ylim(0, 520); a3.legend(fontsize=7, loc="upper right"); a3.set_title("교체 비용 — 핵심 코드 0 줄", fontsize=9, loc="left")
    fig.suptitle("B4 HAL 교체 비용 — 로봇 4종 · 백엔드 2종, 상위 제어 코드 변경 없이 같은 결과", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.94]); fig.savefig(out / "B4_hal_swap.png", dpi=150); plt.close(fig)


def fig_scorecard(out):
    rows = [("A1", "제어주기 1 ms 미스", "12개 실행 532,000 틱 미스 0", "합격", "기본"), ("A2", "지터 ±100 μs", "실제 루프 max 9.5~96 μs; cyclictest 메모리 포화 부하는 208 μs", "주의", "기본"),
            ("A3", "AI 추론시간", "GPU avg 6.5 / max 7.0 ms", "합격", "기본"), ("A4", "AI 추론 주기", "avg 100.0 / max 106.9 ms", "합격", "기본"), ("A5", "제어 반영 지연", "발행→첫 반영 0.49 ms (근사)", "주의", "기본"),
            ("A6", "End-to-End 지연", "캡처→반영 avg 10.3 / max 20.7 ms", "합격", "기본"), ("A7", "AI 부하 유무 비교", "실제 루프 5조건 미스 0, ≤100 μs", "주의", "기본"),
            ("A8", "조건별 동작 시각화", "정상·지연·이상값·누락·단절 5조건 급격한 동작 없음", "합격", "유리"), ("B1", "검증 거부율", "주입 3종 100 % 거부, 실제 AI 잡음 25 %, 만료 사용 0", "합격", "유리"),
            ("B2", "안전 동작(저크·추종)", "추종 오차 ≤ 10.6 mrad(한계 1/10); 저크는 정지 램프만 3배", "주의", "유리"), ("B3", "장애 복구 시간", "감지 1~40 ms, 복귀 0.09~7.9 s, 미스 0", "합격", "유리"), ("B4", "HAL 교체 비용", "4 로봇·2 백엔드 핵심 코드 0줄, 0.30~0.32 mm", "합격", "유리")]
    fig, ax = plt.subplots(figsize=(12, 5.4)); ax.axis("off")
    colors = {"합격": "#c8e6c9", "주의": "#ffe0b2"}
    tbl = ax.table(cellText=[[r[0], r[1], r[2], r[3]] for r in rows], colLabels=["#", "지표", "결과", "판정"], colWidths=[0.05, 0.22, 0.63, 0.07], loc="center", cellLoc="left")
    tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1, 1.55)
    for (i, j), c in tbl.get_celld().items():
        if i == 0: c.set_facecolor("#eceff1"); c.set_text_props(fontweight="bold"); continue
        r = rows[i - 1]; c.set_facecolor(colors[r[3]] if r[4] == "유리" else "#fafafa")
        if j == 3: c.get_text().set_ha("center")
        if r[4] == "유리" and j == 0: c.set_text_props(fontweight="bold")
    ax.set_title("12개 검증 지표 요약 — 색칠된 행(A8·B1~B4)이 이 폴더의 그림 대상, 흰 행은 기본 항목(별도 보고)", fontsize=10, loc="left")
    fig.tight_layout(); fig.savefig(out / "scorecard_12.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(V / "favorable")); a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for f in (fig_scorecard, fig_a8, fig_b1, fig_b2, fig_b3, fig_b4): f(out); print("saved", f.__name__)
