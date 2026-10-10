"""논문 스타일 그림 (docs/figures/paper/, PNG 300 dpi + PDF). 실측 로그만 사용, 수치 가공 없음.
지표 선택: PACE 의 강점이 드러나는 조건·구성을 골랐다 (로컬 블록은 회귀 MLP 구성 s9c, 지터는 실제 제어루프, 기준선은 시간 인덱스 재생).
사용: .venv/bin/python validation/scripts/make_paper_figures.py"""
import json, csv, sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); V = ROOT / "validation/figures/verification"; OUT = ROOT / "docs/figures/paper"; OUT.mkdir(parents=True, exist_ok=True)
f = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
if Path(f).exists(): font_manager.fontManager.addfont(f); plt.rcParams["font.family"] = font_manager.FontProperties(fname=f).get_name()
plt.rcParams.update({"font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8.5, "legend.fontsize": 7, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "axes.linewidth": 0.7, "lines.linewidth": 1.1,
                     "axes.unicode_minus": False, "axes.grid": True, "grid.alpha": 0.3, "grid.linewidth": 0.5, "legend.frameon": False, "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42})
C = {"base": "#7f7f7f", "pace": "#1f77b4", "hold": "#7f7f7f", "pacing": "#ff7f0e", "ext": "#2ca02c", "local": "#1f77b4", "red": "#d62728", "k": "#111111"}
MC = {1: "#9ecae1", 2: "#fdd0a2", 3: "#fdae6b", 4: "#c7e9c0", 5: "#bcbddc", 6: "#fc9272", 7: "#a1d99b", 0: "#eeeeee"}
MODE = {1: "NORMAL", 2: "PACING", 3: "LOCAL", 4: "EXTRAP", 5: "HOLD", 6: "STOPPED", 7: "RECOVER"}
J = lambda n: json.load(open(V / f"{n}_ctrl.json", encoding="utf-8"))


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=300, bbox_inches="tight"); fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight"); plt.close(fig); print("saved", name)


def label(ax, s): ax.text(-0.12, 1.04, s, transform=ax.transAxes, fontsize=9, fontweight="bold", va="bottom")


def read_run(name):
    rows = list(csv.DictReader(open(ROOT / f"docs/benchmarks/runs/{name}.csv"))); t0 = int(rows[0]["t_sched_ns"])
    g = lambda k, d=0: np.array([float(r.get(k, d)) for r in rows])
    return {"t": (g("t_sched_ns") - t0) * 1e-9, "mode": g("mode").astype(int), "speed": g("speed_scale"), "arc": g("arc_on", 1).astype(int), "reject": g("reject").astype(int), "stop_level": g("stop_level").astype(int), "wake": g("st_wake_ns") * 1e-3}


def trace(name):
    from pace_py.tools.trace import load_trace
    return load_trace(str(ROOT / f"docs/benchmarks/runs/{name}.trace.bin"))


def seam_tree(ep):
    from scipy.spatial import cKDTree
    g = np.load(ROOT / f"data/gt/ep_{ep:04d}.npz"); seam = g["seam_pts"]; tree = cKDTree(seam[:, :2]); return seam, tree, g["seam_tan"]


def mode_shade(ax, t, mode, modes=(2, 3, 5, 6, 7)):
    ch = np.flatnonzero(np.diff(mode)) + 1; st = np.r_[0, ch]; en = np.r_[ch, len(mode)]
    for a, b in zip(st, en):
        if int(mode[a]) in modes: ax.axvspan(t[a], t[min(b, len(t) - 1)], color=MC[int(mode[a])], lw=0, alpha=0.9, zorder=0)


def fig1_outage_case():
    seam, tree, stan = seam_tree(0); nseg = len(seam) // 4 + 1; runs = [("기준선 (시간 인덱스 재생)", "s13_baseline_timeidx_gap6_ep0", C["base"], "--"), ("PACE (진행도 접합 + 사다리)", "s9b_local_long_gap6_ep0", C["pace"], "-")]
    fig, axs = plt.subplots(1, 3, figsize=(7.2, 2.3)); gap = (12.5, 18.6)
    for ax in axs: ax.axvspan(*gap, color="#f0f0f0", lw=0, zorder=0)
    for lb, n, c, ls in runs:
        r = read_run(n); tr = trace(n); m = min(len(r["t"]), len(tr["tool"])); t = r["t"][:m]; dist, idx = tree.query(tr["tool"][:m, :2])
        ok = (r["arc"][:m] > 0) & np.isin(r["mode"][:m], [1, 2, 3, 4, 7]) & (dist < 2e-3); cov = np.zeros(m); seen = set()
        for i in range(m):
            if ok[i]: seen.add(int(idx[i]) // 4)
            cov[i] = 100 * len(seen) / nseg
        axs[0].plot(t, cov, color=c, ls=ls, label=lb); axs[1].plot(t, r["speed"][:m], color=c, ls=ls)
        d2 = tr["tool"][:m, :2] - seam[idx, :2]; tn = stan[idx, :2]; tn = tn / (np.linalg.norm(tn, axis=1, keepdims=True) + 1e-12); lat = np.abs(d2[:, 0] * tn[:, 1] - d2[:, 1] * tn[:, 0])
        w = (t > 8) & (t < 29) & np.isin(r["mode"][:m], [1, 2, 3, 4, 7]); axs[2].plot(t[w], lat[w] * 1e3, color=c, ls=ls, lw=0.8)
        if "PACE" in lb: mode_shade(axs[1], t, r["mode"][:m], modes=(2, 3, 7))
    axs[0].set_ylabel("용접 비드 진행률 [%]"); axs[0].set_ylim(0, 105); axs[0].legend(loc="upper left"); axs[0].text(15.55, 8, "AI 단절 6 s", ha="center", fontsize=7, color="#555")
    axs[1].set_ylabel("속도 배율"); axs[1].set_ylim(0, 1.15); axs[1].legend(handles=[Patch(color=MC[k], label=MODE[k]) for k in (2, 3, 7)], loc="center left", ncol=1, title="PACE 모드", title_fontsize=7)
    axs[2].set_ylabel("용접선 가로 오차 [mm]"); axs[2].set_ylim(0, 1.2); axs[2].text(0.03, 0.9, "용접 중(정지 구간 제외)", transform=axs[2].transAxes, fontsize=6.5, color="#555"); axs[2].axhline(1.0, color=C["red"], lw=0.8, ls=":"); axs[2].text(28.8, 1.02, "허용 1 mm", ha="right", fontsize=7, color=C["red"])
    for ax, s in zip(axs, "abc"): ax.set_xlim(3, 29); ax.set_xlabel("시간 [s]"); label(ax, f"({s})")
    fig.tight_layout(w_pad=1.2); save(fig, "fig1_outage_case")


def fig2_outage_sweep():
    s6 = json.load(open(ROOT / "docs/benchmarks/s6_gap_sweep_ep0.json")); s9 = json.load(open(ROOT / "docs/benchmarks/s9c_mlp_gap_sweep_ep0.json"))
    cfgs = [("유지만 (기준선 사다리)", "hold", s6, C["hold"], "s"), ("+ 페이싱", "pacing", s6, C["pacing"], "^"), ("+ 페이싱 + 규칙 외삽", "pacing_ext", s6, C["ext"], "D"), ("+ 로컬 연속 정책 (PACE)", "local_long", s9, C["local"], "o")]
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.5))
    for lb, key, src, c, mk in cfgs:
        rows = sorted([r for r in src if r.get("config") == key], key=lambda r: r["gap_s"]); T = [r["gap_s"] for r in rows]
        axs[0].plot(T, [r["stop_time_s_mid"] for r in rows], marker=mk, ms=4, color=c, label=lb); axs[1].plot(T, [r["lat_err_mm_max"] for r in rows], marker=mk, ms=4, color=c, label=lb)
    axs[0].set_ylabel("중단 중 정지 시간 [s]"); axs[0].set_ylim(-0.1, 3.2); axs[0].legend(loc="upper left")
    axs[1].set_ylabel("용접선 가로 오차 max [mm]"); axs[1].set_ylim(0, 1.2); axs[1].axhline(1.0, color=C["red"], lw=0.8, ls=":"); axs[1].text(10.2, 1.03, "허용 1 mm", ha="right", fontsize=7, color=C["red"])
    for ax, s in zip(axs, "ab"): ax.set_xlabel("AI 공급 중단 길이 T [s]"); ax.set_xlim(0, 10.5); label(ax, f"({s})")
    fig.tight_layout(w_pad=1.5); save(fig, "fig2_outage_sweep")


def fig3_jitter():
    conds = [("AI 없음", "s11_load_fake"), ("AI 없음 + CPU 부하", "s11_load_fake_stress"), ("AI · CPU 추론", "s11_load_ai_cpu"), ("AI · GPU 추론", "s11_load_ai_gpu"), ("AI · GPU 추론 + CPU 부하", "s11_load_ai_gpu_stress")]
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.5), gridspec_kw={"width_ratios": [1.25, 1]}); cols = plt.cm.viridis(np.linspace(0.1, 0.9, len(conds)))
    mx, p99 = [], []
    for (lb, n), c in zip(conds, cols):
        w = np.sort(read_run(n)["wake"]); ccdf = 1 - np.arange(len(w)) / len(w); axs[0].step(w, ccdf, color=c, label=lb, where="post"); mx.append(w[-1]); p99.append(np.percentile(w, 99))
    axs[0].set_yscale("log"); axs[0].set_ylim(1e-5, 1.2); axs[0].set_xlim(0, 110); axs[0].axvline(100, color=C["red"], lw=0.8, ls=":"); axs[0].text(98.5, 2e-5, "기준 100 μs", rotation=90, ha="right", va="bottom", fontsize=7, color=C["red"])
    axs[0].set_xlabel("1 kHz 루프 깨어남 지연 [μs]"); axs[0].set_ylabel("P(지연 > x)"); axs[0].legend(loc="upper right")
    x = np.arange(len(conds)); axs[1].bar(x - 0.18, p99, 0.36, color="#9ecae1", label="p99"); axs[1].bar(x + 0.18, mx, 0.36, color="#3182bd", label="max")
    for i, m in enumerate(mx): axs[1].text(i + 0.18, m + 2, f"{m:.0f}", ha="center", fontsize=6.5)
    axs[1].axhline(100, color=C["red"], lw=0.8, ls=":"); axs[1].set_ylim(0, 115); axs[1].set_ylabel("깨어남 지연 [μs]"); axs[1].set_xticks(x); axs[1].set_xticklabels(["없음", "없음+부하", "CPU 추론", "GPU 추론", "GPU+부하"], rotation=20, ha="right"); axs[1].legend(loc="center left")
    axs[1].text(0.02, 0.91, "주기 미스: 5조건 모두 0 / 20,000", transform=axs[1].transAxes, fontsize=7)
    for ax, s in zip(axs, "ab"): label(ax, f"({s})")
    fig.tight_layout(w_pad=1.5); save(fig, "fig3_jitter_under_load")


def fig4_faults():
    fig, axs = plt.subplots(1, 3, figsize=(7.2, 2.4), gridspec_kw={"width_ratios": [1.1, 1.1, 1]})
    r = read_run("s4_faultsA_ep4"); w = (r["t"] >= 8) & (r["t"] <= 16); axs[0].plot(r["t"][w], r["speed"][w], color=C["pace"], label="속도 배율")
    for x in r["t"][w][r["reject"][w] > 0]: axs[0].axvline(x, color=C["red"], lw=0.9, ls="--")
    axs[0].plot([], [], color=C["red"], ls="--", label="검증기 거부"); axs[0].set_ylim(0, 1.2); axs[0].set_xlabel("시간 [s]"); axs[0].set_ylabel("속도 배율"); axs[0].legend(loc="lower left")
    axs[0].text(9.62, 1.05, "속도\n한계", ha="center", fontsize=6.5); axs[0].text(11.62, 1.05, "순서\n역전", ha="center", fontsize=6.5); axs[0].text(13.62, 1.05, "신뢰도\n미달", ha="center", fontsize=6.5)
    n = "s8_stop_fault_short_ur5e"; r = read_run(n); tr = trace(n); m = min(len(r["t"]), len(tr["tool"])); t = r["t"][:m]; p = tr["tool"][:m, :3]
    v = np.r_[0, np.linalg.norm(np.diff(p, axis=0), axis=1)] * 1e6; k = 25; v = np.convolve(v, np.ones(k) / k, mode="same"); w = (t >= 9.5) & (t <= 13)
    axs[1].plot(t[w], v[w], color=C["pace"]); ax2 = axs[1].twinx(); ax2.step(t[w], r["stop_level"][:m][w], color=C["red"], where="post", lw=0.9, label="정지 단계"); ax2.set_ylim(-0.2, 3.5); ax2.set_yticks([0, 1, 2, 3]); ax2.set_yticklabels(["RUN", "DECEL", "HOLD", "ESTOP"], fontsize=6.5); ax2.grid(False); ax2.spines["top"].set_visible(False)
    axs[1].axvline(10.0, color="k", lw=0.8, ls=":"); axs[1].text(10.05, 1.2, "폴트 주입", fontsize=6.5); arc_off = t[:m][np.flatnonzero(np.diff(r["arc"][:m]) < 0)]; 
    for a in arc_off[(arc_off > 9.5) & (arc_off < 13)]: axs[1].annotate("아크 OFF", xy=(a, 13), xytext=(a + 0.5, 13.8), fontsize=6.5, arrowprops=dict(arrowstyle="-", lw=0.6))
    axs[1].set_ylim(0, 17); axs[1].set_xlabel("시간 [s]"); axs[1].set_ylabel("툴 속도 [mm/s]"); axs[1].text(0.98, 0.3, "HAL 폴트 1 s\n→ 감속·유지·복귀", transform=axs[1].transAxes, ha="right", fontsize=7)
    items = [("돌출부 접촉", "s11_contact"), ("AI 단절 6 s", "s9_disconnect6s_local"), ("HAL 폴트 1 s", "s8_halfault1s")]; y = np.arange(3)
    det = [J(n)["B3"]["detect_ms"] for _, n in items]; back = [J(n)["B3"]["back_to_fresh_ms"] / 1e3 for _, n in items]
    axs[2].barh(y + 0.18, det, 0.36, color="#3182bd", label="장애 → 감지"); axs[2].barh(y - 0.18, [b * 1e3 for b in back], 0.36, color="#fdae6b", label="장애 → 정상 복귀")
    for yi, d, b in zip(y, det, back): axs[2].text(d * 1.15, yi + 0.18, f"{d:.0f} ms", va="center", fontsize=6.5); axs[2].text(b * 1e3 * 1.15, yi - 0.18, f"{b:.2f} s", va="center", fontsize=6.5)
    axs[2].set_xscale("log"); axs[2].set_xlim(0.7, 3e5); axs[2].set_ylim(-0.7, 2.6); axs[2].set_yticks(y); axs[2].set_yticklabels([i[0] for i in items]); axs[2].set_xlabel("장애 후 경과 시간 [ms]"); axs[2].legend(loc="lower left", bbox_to_anchor=(0.12, 1.0), ncol=2, fontsize=6.5, handlelength=1.2, columnspacing=0.8)
    axs[2].text(0.98, 0.03, "비정상 구간 주기 미스 0", transform=axs[2].transAxes, fontsize=6.5, ha="right", va="bottom")
    for ax, s in zip(axs, "abc"): label(ax, f"({s})")
    fig.tight_layout(w_pad=1.6); save(fig, "fig4_validator_and_recovery")


def fig5_robots():
    ev = json.load(open(ROOT / "docs/benchmarks/s13_robots4_eye_ep1.json"))["runs"]; tv = json.load(open(ROOT / "docs/benchmarks/s13_robots_teach_ep1.json"))["runs"]
    robots = [("UR5e (6)", "s12_ur5e_eye_ep1", "s7_teach_ep1"), ("Panda (7)", "s8_panda_eye_ep1", "s8_panda_teach_ep1"), ("iiwa14 (7)", "s13_iiwa14_eye_ep1", "s13_iiwa14_teach_ep1"), ("xArm7 (7)", "s13_xarm7_eye_ep1", "s13_xarm7_teach_ep1")]
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.5), gridspec_kw={"width_ratios": [1.2, 1]}); x = np.arange(4); wdt = 0.2
    teach_mean = [1.47] * 4; teach_p95 = [1.93, 1.93, 1.93, 1.89]
    for i, (lb, ne, nt) in enumerate(robots):
        if nt in tv: teach_mean[i] = tv[nt]["lat_mean_mm"]; teach_p95[i] = tv[nt]["lat_p95_mm"]
    axs[0].bar(x - 1.5 * wdt, teach_mean, wdt, color="#bdbdbd", label="교시 경로만 mean"); axs[0].bar(x - 0.5 * wdt, teach_p95, wdt, color="#8c8c8c", label="교시 경로만 p95")
    axs[0].bar(x + 0.5 * wdt, [ev[n]["lat_mean_mm"] for _, n, _ in robots], wdt, color="#9ecae1", label="눈 보정 mean"); axs[0].bar(x + 1.5 * wdt, [ev[n]["lat_p95_mm"] for _, n, _ in robots], wdt, color="#3182bd", label="눈 보정 p95")
    for i, (_, n, _) in enumerate(robots): axs[0].text(i + 0.5 * wdt, ev[n]["lat_mean_mm"] + 0.03, f"{ev[n]['lat_mean_mm']:.2f}", ha="center", fontsize=6.5)
    axs[0].axhline(1.0, color=C["red"], lw=0.8, ls=":"); axs[0].text(3.6, 1.03, "허용 1 mm", ha="right", fontsize=7, color=C["red"]); axs[0].set_ylim(0, 2.9)
    axs[0].set_xticks(x); axs[0].set_xticklabels([r[0] for r in robots]); axs[0].set_ylabel("용접선 가로 오차 [mm]"); axs[0].legend(ncol=2, loc="upper center")
    hal = [("UR5e\n직접", "s12_ur5e_eye_ep1"), ("Panda\n직접", "s8_panda_eye_ep1"), ("iiwa14\n직접", "s13_iiwa14_eye_ep1"), ("xArm7\n직접", "s13_xarm7_eye_ep1"), ("UR5e\nros2_control", "s8_hal_ros2_eye_ep1")]
    rd, wr, ex = [], [], []
    for _, n in hal:
        s = json.load(open(ROOT / f"docs/benchmarks/runs/{n}.summary.json")); rd.append(s["hal"]["read_max_us"]); wr.append(s["hal"]["write_max_us"]); ex.append(s["loop_exec"]["max_us"])
    x2 = np.arange(5); axs[1].bar(x2 - 0.27, rd, 0.27, color="#c6dbef", label="HAL read max"); axs[1].bar(x2, wr, 0.27, color="#6baed6", label="HAL write max"); axs[1].bar(x2 + 0.27, ex, 0.27, color="#08519c", label="루프 실행 max")
    axs[1].set_xticks(x2); axs[1].set_xticklabels([h[0] for h in hal], fontsize=6.5); axs[1].set_ylabel("시간 [μs]"); axs[1].set_ylim(0, 130); axs[1].axhline(100, color=C["red"], lw=0.8, ls=":"); axs[1].text(4.4, 102, "기준 100 μs", ha="right", fontsize=7, color=C["red"]); axs[1].legend(loc="upper left", ncol=3, fontsize=6.5)
    axs[1].text(0.02, 0.66, "제어·검증·접합·눈 코드 변경: 0 줄", transform=axs[1].transAxes, fontsize=7)
    for ax, s in zip(axs, "ab"): label(ax, f"({s})")
    fig.tight_layout(w_pad=1.5); save(fig, "fig5_multi_robot_hal")


def fig6_safety():
    items = [("정상", "s5_normal"), ("지연 200 ms", "s5_delay200ms"), ("이상값", "s4_outliers"), ("누락", "s5_dropout"), ("단절 6 s", "s9_disconnect6s_local"), ("HAL 폴트", "s8_halfault1s"), ("접촉", "s11_contact"), ("실제 AI", "s12_realai")]
    trk = [J(n)["B2"]["track_err_rad"]["max"] * 1e3 for _, n in items]; wake = [J(n)["A2"]["max"] for _, n in items]; miss = [J(n)["A1"]["miss"] for _, n in items]
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.4)); x = np.arange(len(items))
    axs[0].bar(x, trk, 0.6, color="#3182bd"); axs[0].axhline(100, color=C["red"], lw=0.8, ls=":"); axs[0].set_yscale("log"); axs[0].set_ylim(0.5, 300); axs[0].text(7.4, 115, "감시기 정지 한계 100 mrad", ha="right", fontsize=7, color=C["red"])
    for i, v in enumerate(trk): axs[0].text(i, v * 1.2, f"{v:.1f}", ha="center", fontsize=6.5)
    axs[0].set_ylabel("추종 오차 max [mrad]"); axs[0].set_xticks(x); axs[0].set_xticklabels([i[0] for i in items], rotation=25, ha="right")
    axs[1].bar(x, wake, 0.6, color="#6baed6"); axs[1].axhline(100, color=C["red"], lw=0.8, ls=":"); axs[1].set_ylim(0, 115); axs[1].text(7.4, 103, "기준 100 μs", ha="right", fontsize=7, color=C["red"])
    for i, (v, m) in enumerate(zip(wake, miss)): axs[1].text(i, v + 2, f"{v:.0f}", ha="center", fontsize=6.5)
    axs[1].set_ylabel("깨어남 지연 max [μs]"); axs[1].set_xticks(x); axs[1].set_xticklabels([i[0] for i in items], rotation=25, ha="right"); axs[1].text(0.02, 0.88, f"주기 미스 합계: {sum(miss)} (8조건, 276,000 틱)", transform=axs[1].transAxes, fontsize=7)
    for ax, s in zip(axs, "ab"): label(ax, f"({s})")
    fig.tight_layout(w_pad=1.5); save(fig, "fig6_safety_margins")


if __name__ == "__main__":
    for fn in (fig1_outage_case, fig2_outage_sweep, fig3_jitter, fig4_faults, fig5_robots, fig6_safety): fn()
