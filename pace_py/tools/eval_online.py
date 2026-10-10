"""온라인 학습 비교 평가: 같은 공급 중단 실험을 여러 모델로 돌린 실행들의 '중단 구간' 지표와 전체 용접 지표를 한 표로.
중단 구간 정의는 gap_post 와 같다 (10 s 이후 처음 NORMAL 을 벗어난 틱부터 중단 길이 + 2.5 s).
사용: python -m pace_py.tools.eval_online --gap 6 --runs s16_base_gap6_ep20:20 s16_lr3e-5_gap6_ep20:20 ... --json docs/benchmarks/s16_online_compare.json"""
import argparse, csv, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.trace import load_trace      # noqa: E402
from pace_py.tools.eval_run import evaluate     # noqa: E402
RUNS = Path("docs/benchmarks/runs")


def gap_metrics(name, ep, gap_s):
    from scipy.spatial import cKDTree
    seam = np.load(f"data/gt/ep_{ep:04d}.npz")["seam_pts"]; tree = cKDTree(seam[:, :2])
    rows = list(csv.DictReader(open(RUNS / f"{name}.csv"))); t0 = int(rows[0]["t_sched_ns"])
    t = np.array([(int(x["t_sched_ns"]) - t0) * 1e-9 for x in rows]); mode = np.array([int(x["mode"]) for x in rows]); spd = np.array([float(x["speed_scale"]) for x in rows])
    on = np.nonzero((mode != 1) & (mode != 7) & (t > 10.0))[0]
    if not len(on): return {"gap_onset_s": None}
    g0 = t[on[0]]; g1 = g0 + gap_s + 2.5; w = (t >= g0) & (t <= g1)
    tr = load_trace(RUNS / f"{name}.trace.bin"); tt = (tr["t_ns"] - tr["t_ns"][0]) * 1e-9; wt = (tt >= g0) & (tt <= g1)
    dist, _ = tree.query(tr["tool"][wt][::5, :2]); summ = json.load(open(RUNS / f"{name}.summary.json"))
    return {"gap_onset_s": float(g0), "stop_ticks_gap": int(((mode == 6) & w).sum()), "local_ticks_gap": int(((mode == 3) & w).sum()), "extrap_ticks_gap": int(((mode == 4) & w).sum()),
            "min_speed_gap": float(spd[w].min()), "lat_mm_max_gap": float(dist.max() * 1e3), "lat_mm_mean_gap": float(dist.mean() * 1e3), "lat_mm_p95_gap": float(np.percentile(dist, 95) * 1e3),
            "local_adopted": summ.get("local", {}).get("adopted", 0), "wake_max_us": summ["wake_latency"]["max_us"], "exec_max_us": summ["loop_exec"]["max_us"]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", nargs="+", required=True, help="이름:에피소드"); ap.add_argument("--gap", type=float, default=6.0); ap.add_argument("--json", default=None)
    a = ap.parse_args(); out = []
    for spec in a.runs:
        name, ep = spec.rsplit(":", 1); ep = int(ep); g = gap_metrics(name, ep, a.gap); e = evaluate(name, ep)
        r = {"name": name, "episode": ep, **g, "weld_completed": bool(e["weld_completed"]), "stopped_any_mid": bool(e["stopped_any_mid"]), "lat_err_mm_mean": float(e["lat_err_mm_mean"]), "lat_err_mm_max": float(e["lat_err_mm_max"])}
        out.append(r)
        print(f"{name:28s} ep{ep:<3d} 완주={'O' if r['weld_completed'] else 'X'} 정지틱={r.get('stop_ticks_gap')} 보조궤적틱={r.get('local_ticks_gap')} | 중단구간 오차 mean {r.get('lat_mm_mean_gap', float('nan')):.2f} p95 {r.get('lat_mm_p95_gap', float('nan')):.2f} max {r.get('lat_mm_max_gap', float('nan')):.2f} mm | 전체 mean {r['lat_err_mm_mean']:.2f} max {r['lat_err_mm_max']:.2f} mm | wake max {r.get('wake_max_us')} μs")
    if a.json: Path(a.json).write_text(json.dumps(out, indent=1, ensure_ascii=False)); print("saved", a.json)


if __name__ == "__main__":
    main()
