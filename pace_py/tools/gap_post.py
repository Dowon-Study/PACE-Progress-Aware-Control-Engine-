"""9단계 스윕 후처리: 각 실행의 틱 레코드에서 '공급 중단 구간' 자체를 잘라 정지·LOCAL·외삽·속도·오차를 다시 센다 (용접 창 추정에 기대지 않음).
구간 = 10s 이후 처음 NORMAL 을 벗어난 틱부터 중단 길이 T + 2.5s 까지. 사용: python -m pace_py.tools.gap_post --json docs/benchmarks/s9_gap_sweep_ep0.json --episode 0"""
import argparse, csv, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.trace import load_trace   # noqa: E402
RUNS = Path("docs/benchmarks/runs")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--json", required=True); ap.add_argument("--episode", type=int, default=0); ap.add_argument("--out", default=None)
    a = ap.parse_args(); res = json.loads(Path(a.json).read_text()); seam = np.load(f"data/gt/ep_{a.episode:04d}.npz")["seam_pts"]
    from scipy.spatial import cKDTree; tree = cKDTree(seam[:, :2]); out = []   # 수평 거리 = 가로 오차 (standoff 2mm 제외)
    for r in res:
        name = f"{Path(a.json).stem.split('_gap_sweep')[0]}_{r['config']}_gap{r['gap_s']:g}_ep{a.episode}"
        rows = list(csv.DictReader(open(RUNS / f"{name}.csv"))); t0 = int(rows[0]["t_sched_ns"])
        t = np.array([(int(x["t_sched_ns"]) - t0) * 1e-9 for x in rows]); mode = np.array([int(x["mode"]) for x in rows]); spd = np.array([float(x["speed_scale"]) for x in rows])
        on = np.nonzero((mode != 1) & (mode != 7) & (t > 10.0))[0]   # 중단 시작 = 10s 이후 처음 NORMAL 을 벗어난 틱 (페이싱이 없는 hold 구성도 포함)
        if not len(on): out.append({**r, "gap_onset_s": None}); continue
        g0 = t[on[0]]; g1 = g0 + r["gap_s"] + 2.5; w = (t >= g0) & (t <= g1)
        tr = load_trace(RUNS / f"{name}.trace.bin"); tt = (tr["t_ns"] - tr["t_ns"][0]) * 1e-9; p = tr["tool"][:, :3]; wt = (tt >= g0) & (tt <= g1)
        dist, _ = tree.query(p[wt][::5, :2]); summ = json.load(open(RUNS / f"{name}.summary.json"))
        d = {**r, "gap_onset_s": float(g0), "stop_ticks_gap": int(((mode == 6) & w).sum()), "hold_ticks_gap": int(((mode == 5) & w).sum()), "local_ticks_gap": int(((mode == 3) & w).sum()), "extrap_ticks_gap": int(((mode == 4) & w).sum()), "pacing_ticks_gap": int(((mode == 2) & w).sum()),
             "min_speed_gap": float(spd[w].min()), "lat_mm_max_gap": float(dist.max() * 1e3), "lat_mm_mean_gap": float(dist.mean() * 1e3), "local_adopted": summ.get("local", {}).get("adopted", 0), "local_expired_ticks": summ.get("local", {}).get("expired", 0)}
        out.append(d); print(f"{r['config']:11s} gap={r['gap_s']:4.1f}s onset={g0:5.1f}s stop={d['stop_ticks_gap']:5d} hold={d['hold_ticks_gap']:5d} local={d['local_ticks_gap']:5d} extrap={d['extrap_ticks_gap']:5d} pacing={d['pacing_ticks_gap']:5d} min_speed={d['min_speed_gap']:.2f} lat max={d['lat_mm_max_gap']:.2f} mean={d['lat_mm_mean_gap']:.2f} mm adopted={d['local_adopted']}")
    Path(a.out or a.json.replace(".json", "_post.json")).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
