"""7단계 평가: 기준 경로 모드 trace 의 툴 궤적을 '실제 용접선'(data/refpath/ep_XXXX_real.bin)에 사영해 가로 오차를 잰다.
사용: python -m pace_py.tools.eval_refpath --episode 1 --runs s7_teach_only_ep1 s7_eye_ep1 [--plot docs/figures/s7_ep1.png]
용접 구간 = 전이(transit) 이후 툴이 실제 선의 양 끝 5mm 안쪽에 사영되는 구간. 출력: 각 run 의 mean/p95/max(mm), SLOW(EYE_STALE) 틱, 속도 배율 최소."""
import argparse, json, struct, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.trace import load_trace          # noqa: E402

MON_SLOW = 1   # trace.monitor = 감시기 판정 (0 OK, 1 SLOW, 2 STOP); 기준 경로 모드에서 SLOW 는 EYE_STALE 뿐
RUNS = Path("docs/benchmarks/runs")


def load_rpth(path):
    b = open(path, "rb").read(); magic, n = struct.unpack_from("<II", b, 0); assert magic == 0x48545052
    a = np.frombuffer(b, np.float32, count=7 * n, offset=24).reshape(n, 7).astype(np.float64); return a[:, 0], a[:, 1:4], a[:, 4:7]


def project(poly, p):
    """점 p 를 폴리라인에 사영 → (가로 부호 오차 (n=ẑ×t 방향), 호 길이 s, 끝점 여부)."""
    seg = poly[1:] - poly[:-1]; L = np.linalg.norm(seg, axis=1); L2 = np.maximum(L * L, 1e-12)
    u = np.clip(((p - poly[:-1]) * seg).sum(1) / L2, 0.0, 1.0); foot = poly[:-1] + u[:, None] * seg
    i = int(np.argmin(((p - foot) ** 2).sum(1))); t = seg[i] / L[i]; n = np.array([-t[1], t[0], 0.0]); n /= max(np.linalg.norm(n), 1e-9)
    s = float(np.cumsum(np.r_[0.0, L])[i] + u[i] * L[i]); return float(np.dot(p - foot[i], n)), s, (i == 0 and u[i] <= 0.0) or (i == len(seg) - 1 and u[i] >= 1.0)


def evaluate(trace_path, real_poly, transit_s=3.0, margin=0.005):
    tr = load_trace(trace_path); t = (tr["t_ns"] - tr["t_ns"][0]) * 1e-9
    total = float(np.sum(np.linalg.norm(real_poly[1:] - real_poly[:-1], axis=1)))
    lat = np.full(len(t), np.nan); svals = np.full(len(t), np.nan); on = np.zeros(len(t), bool)
    for k in range(0, len(t), 5):                                   # 5ms 간격이면 충분
        e, s, endpt = project(real_poly, tr["tool"][k, :3].astype(np.float64)); lat[k] = e; svals[k] = s; on[k] = (t[k] >= transit_s) and (not endpt) and (margin <= s <= total - margin)
    ok = on & np.isfinite(lat); ae = np.abs(lat[ok]) * 1e3
    stale = int(np.sum(tr["monitor"] == MON_SLOW)); spd = tr["speed"]
    return {"t": t, "lat_mm": lat * 1e3, "weld_mask": ok, "s": svals, "speed": spd,
            "summary": {"lat_mean_mm": float(ae.mean()) if ae.size else None, "lat_p95_mm": float(np.percentile(ae, 95)) if ae.size else None, "lat_max_mm": float(ae.max()) if ae.size else None,
                        "weld_window_s": [float(t[ok][0]), float(t[ok][-1])] if ae.size else None, "s_reached_m": float(np.nanmax(svals)), "seam_len_m": total,
                        "slow_ticks": stale, "speed_min": float(spd[t >= transit_s].min()) if np.any(t >= transit_s) else None}}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--episode", type=int, required=True); ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--labels", nargs="*", default=None); ap.add_argument("--plot", default=None); ap.add_argument("--json", default=None); ap.add_argument("--transit", type=float, default=3.0)
    a = ap.parse_args()
    real = Path(f"data/refpath/ep_{a.episode:04d}_real.bin")
    if not real.exists():
        import subprocess; subprocess.run([sys.executable, "-m", "pace_py.tools.make_refpath", "--episode", str(a.episode), "--real"], check=True, stdout=subprocess.DEVNULL)
    _, poly, _ = load_rpth(real)
    teach = Path(f"data/refpath/ep_{a.episode:04d}_teach.bin"); _, tpoly, _ = load_rpth(teach)
    off = np.array([project(tpoly, p)[0] for p in poly]) * 1e3                 # 실제 선 vs 교시 경로 (고정구 오차)
    res = {"episode": a.episode, "fixture_offset_mm": {"mean": float(np.abs(off).mean()), "min": float(off.min()), "max": float(off.max())}, "runs": {}}
    evs = {}
    for r in a.runs:
        ev = evaluate(RUNS / f"{r}.trace.bin", poly, a.transit); evs[r] = ev; res["runs"][r] = ev["summary"]
        s = ev["summary"]; print(f"{r:28s} lat mean={s['lat_mean_mm']:.2f} p95={s['lat_p95_mm']:.2f} max={s['lat_max_mm']:.2f} mm | weld {s['weld_window_s'][0]:.1f}-{s['weld_window_s'][1]:.1f}s | s={s['s_reached_m']:.3f}/{s['seam_len_m']:.3f} | slow_ticks={s['slow_ticks']} speed_min={s['speed_min']:.2f}")
    print(f"fixture offset (real vs teach): |mean|={res['fixture_offset_mm']['mean']:.2f} range {res['fixture_offset_mm']['min']:+.2f}..{res['fixture_offset_mm']['max']:+.2f} mm")
    if a.json: Path(a.json).write_text(json.dumps(res, indent=1, ensure_ascii=False))
    if a.plot:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        labels = a.labels or a.runs
        fig, ax = plt.subplots(2, 1, figsize=(9, 5.2), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
        for r, lb in zip(a.runs, labels):
            ev = evs[r]; m = ev["weld_mask"]; ax[0].plot(ev["t"][m], ev["lat_mm"][m], lw=1.2, label=f"{lb} (mean {ev['summary']['lat_mean_mm']:.2f} mm)"); ax[1].plot(ev["t"], ev["speed"], lw=1.0, label=lb)
        ax[0].axhline(0, color="k", lw=0.6); ax[0].set_ylabel("lateral error vs real seam [mm]"); ax[0].legend(fontsize=8); ax[0].grid(alpha=0.3)
        ax[1].set_ylabel("speed scale"); ax[1].set_xlabel("t [s]"); ax[1].set_ylim(-0.05, 1.1); ax[1].grid(alpha=0.3)
        fig.suptitle(f"Step 7 — seam tracking, episode {a.episode} (fixture offset {res['fixture_offset_mm']['min']:+.1f}..{res['fixture_offset_mm']['max']:+.1f} mm)", fontsize=10)
        fig.tight_layout(); fig.savefig(a.plot, dpi=130); print("plot:", a.plot)


if __name__ == "__main__":
    main()
