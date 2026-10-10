"""시나리오 ④ 타임라인: 상태 감시기 트리거 → 저크 제한 감속(DECEL) → 위치 유지(HOLD) → 비상 정지(ESTOP, 아크 OFF) → (트리거 해제 시) 복귀.
입력: metrics CSV(틱 레코드: mode, monitor, triggers, speed_scale, stop_level, arc_on) + trace(툴 속도).
사용: python -m pace_py.tools.plot_stop_ladder --run s8_stop_fault_ur5e --out docs/figures/s8_stop_fault_ur5e.png [--json ...]"""
import argparse, csv, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.trace import load_trace   # noqa: E402

RUNS = Path("docs/benchmarks/runs")
TRIG = {0: "JOINT_LIMIT", 1: "VEL_LIMIT", 2: "ACC_LIMIT", 3: "WORKSPACE", 4: "DEVIATION", 5: "TRACK_ERR", 6: "EXTRAP_CAP", 7: "HAL_FAULT", 8: "BLIND", 9: "EVENT", 10: "BUFFER_LOW", 11: "EYE_STALE", 12: "ESTOP_LATCH"}
MODE = {0: "INIT", 1: "NORMAL", 2: "PACING", 3: "LOCAL", 4: "EXTRAP", 5: "HOLD", 6: "STOPPED", 7: "RECOVER"}


def load_csv(path):
    rows = list(csv.DictReader(open(path)))
    g = lambda k, t=float: np.array([t(r[k]) for r in rows])
    t = (g("t_sched_ns") - g("t_sched_ns")[0]) * 1e-9
    return {"t": t, "mode": g("mode", int), "monitor": g("monitor", int), "triggers": g("triggers", int), "speed": g("speed_scale"), "stop_level": g("stop_level", int), "arc": g("arc_on", int)}


def first(mask, t):
    idx = np.nonzero(mask)[0]; return float(t[idx[0]]) if len(idx) else None


def analyze(c, tr):
    t = c["t"]; verdict_stop = c["monitor"] == 2
    t_trig = first(verdict_stop, t)
    out = {"t_trigger": t_trig}
    if t_trig is not None:
        i0 = int(np.searchsorted(t, t_trig)); trig_bits = int(c["triggers"][i0]); out["trigger_names"] = [n for b, n in TRIG.items() if trig_bits >> b & 1]
        out["t_arc_off"] = first((c["arc"] == 0) & (t >= t_trig - 0.001), t); out["arc_off_latency_ms"] = None if out["t_arc_off"] is None else (out["t_arc_off"] - t_trig) * 1e3
        out["t_decel_start"] = first(c["stop_level"] == 1, t); out["t_hold"] = first(c["stop_level"] == 2, t); out["t_estop"] = first(c["stop_level"] == 3, t)
        if out["t_hold"] is not None: out["decel_duration_ms"] = (out["t_hold"] - t_trig) * 1e3
        after = t > t_trig; resume = first(after & (c["monitor"] == 0) & (c["stop_level"] == 0), t); out["t_resume"] = resume
        out["estop_latched"] = bool(np.any(c["stop_level"] == 3))
    # 툴 속도 (trace) 와 저크
    tt = (tr["t_ns"] - tr["t_ns"][0]) * 1e-9; p = tr["tool"][:, :3].astype(np.float64); v = np.linalg.norm(np.gradient(p, tt, axis=0), axis=1)
    a = np.gradient(v, tt); j = np.gradient(a, tt)
    out["tool_speed_max_mps"] = float(np.nanmax(v)); 
    if t_trig is not None:
        w = (tt >= t_trig) & (tt <= t_trig + 1.5); out["decel_jerk_p99"] = float(np.nanpercentile(np.abs(j[w]), 99)) if w.any() else None; out["decel_peak_decel_mps2"] = float(np.nanmax(np.abs(a[w]))) if w.any() else None
    out["mode_ticks"] = {MODE.get(m, str(m)): int(np.sum(c["mode"] == m)) for m in np.unique(c["mode"])}
    out["stop_level_ticks"] = {int(k): int(np.sum(c["stop_level"] == k)) for k in np.unique(c["stop_level"])}
    return out, (tt, v)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--run", required=True); ap.add_argument("--out", default=None); ap.add_argument("--json", default=None); ap.add_argument("--title", default=None)
    a = ap.parse_args()
    c = load_csv(RUNS / f"{a.run}.csv"); tr = load_trace(RUNS / f"{a.run}.trace.bin"); res, (tt, v) = analyze(c, tr)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if a.json: Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    if a.out:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        t = c["t"]; fig, ax = plt.subplots(4, 1, figsize=(10, 7.5), sharex=True, gridspec_kw={"height_ratios": [2, 1.2, 1, 1]})
        ax[0].plot(tt, v * 1e3, lw=1, color="C0"); ax[0].set_ylabel("tool speed [mm/s]"); ax[0].grid(alpha=0.3)
        ax0b = ax[0].twinx(); ax0b.plot(t, c["speed"], lw=1, color="C1"); ax0b.set_ylabel("speed scale", color="C1"); ax0b.set_ylim(-0.05, 1.1)
        ax[1].step(t, c["mode"], where="post", lw=1.2, color="C2"); ax[1].set_yticks(list(MODE)); ax[1].set_yticklabels(list(MODE.values()), fontsize=7); ax[1].set_ylabel("mode"); ax[1].grid(alpha=0.3)
        ax[2].step(t, c["stop_level"], where="post", lw=1.2, color="C3"); ax[2].set_yticks([0, 1, 2, 3]); ax[2].set_yticklabels(["-", "DECEL", "HOLD", "ESTOP"], fontsize=8); ax[2].set_ylabel("HAL stop"); ax[2].grid(alpha=0.3)
        ax[3].step(t, c["arc"], where="post", lw=1.2, color="C4", label="arc on"); ax[3].step(t, c["monitor"] / 2.0, where="post", lw=1, color="k", alpha=0.6, label="monitor STOP"); ax[3].set_ylim(-0.1, 1.2); ax[3].set_ylabel("arc / verdict"); ax[3].legend(fontsize=7, loc="upper right"); ax[3].grid(alpha=0.3); ax[3].set_xlabel("t [s]")
        for k in range(4):
            if res.get("t_trigger") is not None: ax[k].axvline(res["t_trigger"], color="r", lw=0.8, ls="--")
            if res.get("t_estop") is not None: ax[k].axvline(res["t_estop"], color="m", lw=0.8, ls=":")
            if res.get("t_resume") is not None: ax[k].axvline(res["t_resume"], color="g", lw=0.8, ls="--")
        fig.suptitle(a.title or f"Scenario ④ stop ladder — {a.run}  (trigger {', '.join(res.get('trigger_names', []))})", fontsize=10); fig.tight_layout(); fig.savefig(a.out, dpi=130); print("plot:", a.out)


if __name__ == "__main__":
    main()
