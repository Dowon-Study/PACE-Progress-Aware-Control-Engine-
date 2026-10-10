"""6단계: 공급 중단 길이 T 스윕 × 구성(hold / pacing / pacing+ext) → "정지 0회 한계 T", 정지 시간, 오차, 복귀 저크.
사용: python -m pace_py.tools.gap_sweep --episode 0 --gaps 0.5 1 1.5 2 3 4 5 --configs hold pacing pacing_ext --policy progress"""
import argparse, json, os, subprocess, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.eval_run import evaluate   # noqa: E402
ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", type=int, default=0); ap.add_argument("--gaps", nargs="+", type=float, default=[0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0])
    ap.add_argument("--configs", nargs="+", default=["hold", "pacing", "pacing_ext"]); ap.add_argument("--policy", default="progress")
    ap.add_argument("--gap-start", type=float, default=8.0); ap.add_argument("--delay", type=int, default=100); ap.add_argument("--jitter", type=int, default=50); ap.add_argument("--dur", type=int, default=45); ap.add_argument("--tag", default="s6")
    a = ap.parse_args(); results = []
    for cfg in a.configs:
        for T in a.gaps:
            name = f"{a.tag}_{cfg}_gap{T:g}_ep{a.episode}"
            env = dict(os.environ, DUR=str(a.dur), POLICY=a.policy, CFG=f"pace/config/gap_{cfg}.cfg", LOCAL="1" if cfg.startswith("local") else "0")   # 9단계: local* 구성은 로컬 감독 블록을 띄움
            cmd = ["bash", "pace_py/tools/run_episode.sh", str(a.episode), name, "--delay-ms", str(a.delay), "--delay-jitter-ms", str(a.jitter), "--dropout-from", str(a.gap_start), "--dropout-to", str(a.gap_start + T)]
            subprocess.run(cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            r = evaluate(name, a.episode); r["config"] = cfg; r["gap_s"] = T; results.append(r)
            print(f"{cfg:11s} gap={T:3.1f}s  stopped={str(r['stopped_any_mid'])[0]} stop_time={r['stop_time_s_mid']:.2f}s min_speed={r['min_speed_scale_mid']:.2f} pacing={r['pacing_ticks']} local={r.get('local_ticks',0)} extrap={r['extrap_ticks']} hold={r['hold_ticks_mid']} | lat max={r['lat_err_mm_max']:.2f} mean={r['lat_err_mm_mean']:.3f} | jerk p99={r['jerk_p99_rad_s3']:.0f} | done={str(r['weld_completed'])[0]}", flush=True)
    out = ROOT / "docs/benchmarks" / f"{a.tag}_gap_sweep_ep{a.episode}.json"; out.write_text(json.dumps(results, indent=1))
    import matplotlib; matplotlib.use("Agg")
    from matplotlib import font_manager as fm
    c = [f for f in fm.findSystemFonts() if "NotoSansCJK" in f]
    if c: fm.fontManager.addfont(c[0]); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=c[0]).get_name()
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 4, figsize=(18, 4.2))
    for cfg in a.configs:
        rs = [r for r in results if r["config"] == cfg]; x = [r["gap_s"] for r in rs]
        ax[0].plot(x, [r["stop_time_s_mid"] for r in rs], "o-", label=cfg); ax[1].plot(x, [r["min_speed_scale_mid"] for r in rs], "o-", label=cfg)
        ax[2].plot(x, [r["lat_err_mm_max"] for r in rs], "o-", label=cfg); ax[3].plot(x, [r["jerk_p99_rad_s3"] for r in rs], "o-", label=cfg)
    for k, t in enumerate(["용접 중 정지 시간 [s]", "최소 속도 배율", "추종 오차 최대 [mm]", "저크 p99 [rad/s³]"]):
        ax[k].set_title(t); ax[k].set_xlabel("공급 중단 길이 T [s]"); ax[k].grid(alpha=.3); ax[k].legend(fontsize=8)
    fig.suptitle(f"공급 중단 길이 스윕 (ep{a.episode}, {a.policy}, 지연 {a.delay}±{a.jitter}ms): hold vs 페이싱 vs 페이싱+외삽")
    fig.savefig(ROOT / "docs/figures" / f"{a.tag}_gap_sweep_ep{a.episode}.png", dpi=90, bbox_inches="tight"); print("saved", out)


if __name__ == "__main__":
    main()
