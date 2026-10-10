"""계측 링버퍼(공유메모리)를 비워 CSV 로 저장하고 요약을 출력한다.
사용: .venv/bin/python -m pace_py.tools.metrics_dump --shm /pace --out docs/benchmarks/run.csv"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.msg import TickRecord, ST_COUNT, Mode   # noqa: E402
from pace_py.shm import Shm                          # noqa: E402

STAGES = ["wake", "read", "select", "validate", "splice", "pace", "command", "monitor", "write", "log"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shm", default="/pace"); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sh = Shm(a.shm)
    rows = []
    r = TickRecord()
    while sh.pop_record(r):
        rows.append([r.tick, r.t_sched_ns, r.t_wake_ns, *[r.stage_ns[i] for i in range(ST_COUNT)], r.chunk_seq, r.chunk_t_gen_ns,
                     r.progress_s, r.deviation, r.speed_scale, r.buffer_margin_ms, r.mode, r.supplier, r.reject, r.monitor, r.triggers, r.stop_level, r.arc_on, r.arc_power_pct, r.tool_force_cN / 100.0])
    sh.close()
    if not rows:
        print("레코드 없음"); return 1
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tick", "t_sched_ns", "t_wake_ns", *[f"st_{s}_ns" for s in STAGES], "chunk_seq", "chunk_t_gen_ns",
                    "progress_s", "deviation", "speed_scale", "buffer_margin_ms", "mode", "supplier", "reject", "monitor", "triggers", "stop_level", "arc_on", "arc_power_pct", "tool_force_N"])
        w.writerows(rows)
    A = np.array(rows, dtype=np.float64)
    wake = A[:, 3] / 1e3
    exec_us = A[:, 4:13].sum(axis=1) / 1e3
    print(f"records={len(rows)}  saved={out}")
    print(f"wake latency us: p50={np.percentile(wake,50):.1f} p99={np.percentile(wake,99):.1f} p99.9={np.percentile(wake,99.9):.1f} max={wake.max():.1f}  >100us: {(wake>100).sum()}")
    print(f"loop exec   us: p50={np.percentile(exec_us,50):.1f} p99={np.percentile(exec_us,99):.1f} max={exec_us.max():.1f}")
    for i, s in enumerate(STAGES[1:], start=1):
        col = A[:, 3 + i] / 1e3
        if col.max() > 0: print(f"  stage {s:9s} us: avg={col.mean():.2f} p99={np.percentile(col,99):.1f} max={col.max():.1f}")
    lag = A[:, 13]
    print(f"sim lag ticks: avg={lag.mean():.3f} max={lag.max():.0f}  (>1 tick: {(lag>1).sum()})")
    modes = {int(k): int(v) for k, v in zip(*np.unique(A[:, 19], return_counts=True))}
    print("modes:", {Mode(k).name: v for k, v in modes.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
