"""AI 연산 부하 변화에 따른 실시간 제어 성능 비교 (과제 평가 항목): 같은 1kHz 루프를 공급자/부하 조건만 바꿔 돌리고 지터·실행시간·E2E 를 표로.
조건: none(공급자 없음) | fake(GT 청크) | fake_stress(GT 청크 + 비격리 코어 stress) | ai_gpu(실제 모델 GPU 추론) | ai_cpu(실제 모델 CPU 추론, 비격리 코어) | ai_gpu_stress
사용: python -m pace_py.tools.ai_load_sweep --conds none fake fake_stress [--dur 20] --tag s11"""
import argparse, json, os, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]


def run(cmd, env=None):
    subprocess.run(cmd, cwd=ROOT, env=dict(os.environ, **(env or {})), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, shell=isinstance(cmd, str))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--conds", nargs="+", default=["none", "fake", "fake_stress", "ai_gpu", "ai_cpu", "ai_gpu_stress"]); ap.add_argument("--dur", type=int, default=20); ap.add_argument("--tag", default="s11"); ap.add_argument("--episode", type=int, default=0)
    a = ap.parse_args(); rows = []
    for c in a.conds:
        name = f"{a.tag}_load_{c}"; stress = None
        if c.endswith("stress"): stress = subprocess.Popen(["taskset", "-c", "0-3,8-11,16-23", "stress-ng", "--cpu", "16", "--vm", "4", "--vm-bytes", "1G", "--timeout", f"{a.dur + 8}s"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if c == "none":
            run(f"pkill -INT pace_sim; sleep 0.3; pace/build/pace_sim --model pace/models/ur5e/_gen_ep{a.episode:04d}.xml --cpu 12 2>/dev/null & sleep 1; pace/build/pace_control --cpu 4 --prio 99 --duration {a.dur} --traj sine --amp 0.2 > docs/benchmarks/runs/{name}.summary.json 2>/dev/null; pkill -INT pace_sim")
        elif c.startswith("fake"):
            run(["bash", "pace_py/tools/run_episode.sh", str(a.episode), name, "--delay-ms", "100", "--delay-jitter-ms", "50"], {"DUR": str(a.dur)})
        elif c.startswith("ai_gpu"):
            run(["bash", "pace_py/tools/run_ai.sh", str(a.episode), name], {"DUR": str(a.dur)})
        elif c == "ai_cpu":
            run(["bash", "pace_py/tools/run_ai.sh", str(a.episode), name, "--device", "cpu"], {"DUR": str(a.dur)})
        if stress: stress.wait()
        s = json.load(open(ROOT / f"docs/benchmarks/runs/{name}.summary.json")); ai_log = ROOT / f"docs/benchmarks/runs/{name}.ai.log"; infer = ""
        if ai_log.exists():
            import re; m = re.search(r"infer p50=([\d.]+)ms max=([\d.]+)ms", ai_log.read_text()); infer = f"{m.group(1)}/{m.group(2)}" if m else ""
        r = {"cond": c, "wake_p99_us": s["wake_latency"]["p99_us"], "wake_max_us": s["wake_latency"]["max_us"], "exec_p99_us": s["loop_exec"]["p99_us"], "exec_max_us": s["loop_exec"]["max_us"], "chunks": s.get("chunks_adopted", 0), "infer_p50_max_ms": infer}
        rows.append(r); print(f"{c:14s} wake p99/max={r['wake_p99_us']}/{r['wake_max_us']} us  exec p99/max={r['exec_p99_us']}/{r['exec_max_us']} us  chunks={r['chunks']}  infer={infer}", flush=True)
    out = ROOT / f"docs/benchmarks/{a.tag}_ai_load.json"; prev = json.loads(out.read_text()) if out.exists() else []
    prev = [p for p in prev if p["cond"] not in {r["cond"] for r in rows}] + rows; out.write_text(json.dumps(prev, indent=1)); print("saved", out)


if __name__ == "__main__":
    main()
