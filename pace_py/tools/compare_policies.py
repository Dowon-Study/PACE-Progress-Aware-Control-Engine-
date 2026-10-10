"""5단계 비교 실험: 정책 × 주입 지연 매트릭스 실행 → 지표 표 + 그림.
사용: python -m pace_py.tools.compare_policies --episode 0 --policies timeidx immediate progress --delays 0 100 200 300 --jitter 50"""
import argparse, json, subprocess, sys, os
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.eval_run import evaluate   # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def run(name, episode, policy, delay, jitter, dur, msg, extra, sim_args=""):
    env = dict(os.environ, DUR=str(dur), POLICY=policy, SIM_ARGS=sim_args)
    cmd = ["bash", "pace_py/tools/run_episode.sh", str(episode), name, "--delay-ms", str(delay), "--delay-jitter-ms", str(jitter), "--msg", msg] + extra
    subprocess.run(cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return evaluate(name, episode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", type=int, default=0); ap.add_argument("--policies", nargs="+", default=["timeidx", "immediate", "progress"])
    ap.add_argument("--delays", nargs="+", type=int, default=[0, 100, 200, 300]); ap.add_argument("--jitter", type=int, default=50)
    ap.add_argument("--dur", type=int, default=32); ap.add_argument("--msg", default="path"); ap.add_argument("--tag", default="s5"); ap.add_argument("--extra", nargs="*", default=[]); ap.add_argument("--sim-args", default="")
    ap.add_argument("--scenario", default=None, help="프리셋: disturb | pacing | dropout | openloop_dropout")
    a = ap.parse_args()
    # 시나리오 프리셋 (에피소드 시간 기준; 시뮬 시간은 제어기 시작 후 약 1.5s + transit 3s 뒤에 에피소드 시작 → 시뮬 외란 시각은 약 +4.6s)
    PRESETS = {
        "disturb":          ([], "--disturb-at 12.6 --disturb-dur 0.6 --disturb-tau 60 --disturb-joint 1"),   # 에피소드 8초쯤 어깨에 60Nm 0.6s
        "pacing":           (["--speed-scale", "0.5"], ""),                                                       # 운영자 속도 지령 0.5배
        "dropout":          (["--dropout-from", "8", "--dropout-to", "10.5"], ""),                                  # 2.5초 공급 중단 후 복귀
        "openloop_dropout": (["--open-loop", "--dropout-from", "8", "--dropout-to", "10.5"], ""),                   # 상태 무시 AI + 중단
        # 관측 시각부터 시작하는 청크(미래 겨냥 없음, RTC 이전 VLA 관습): 도착 시 앞부분이 이미 과거 → 접합 방식이 갈림
        "openloop_lag":          (["--open-loop", "--target-latency", "0"], ""),
        "openloop_lag_pacing":   (["--open-loop", "--target-latency", "0", "--speed-scale", "0.5"], ""),
        "openloop_lag_disturb":  (["--open-loop", "--target-latency", "0"], "--disturb-at 12.6 --disturb-dur 0.6 --disturb-tau 60 --disturb-joint 1"),
        "openloop_lag_dropout":  (["--open-loop", "--target-latency", "0", "--dropout-from", "8", "--dropout-to", "10.5"], ""),
    }
    if a.scenario:
        ex, sa = PRESETS[a.scenario][:2]; a.extra = list(a.extra) + ex; a.sim_args = (a.sim_args + " " + sa).strip(); a.tag = f"{a.tag}_{a.scenario}"
        if "pacing" in a.scenario and a.dur < 60: a.dur = 60                   # 0.5배 페이싱은 용접 완주에 약 2배 시간
    results = []
    for pol in a.policies:
        for dl in a.delays:
            name = f"{a.tag}_{pol}_d{dl}_ep{a.episode}"
            r = run(name, a.episode, pol, dl, a.jitter, a.dur, a.msg, a.extra, a.sim_args); r["delay_ms"] = dl; r["scenario"] = a.scenario; results.append(r)
            print(f"{pol:9s} delay={dl:3d}ms  lat mean/p95/max = {r['lat_err_mm_mean'] or float('nan'):.2f}/{r['lat_err_mm_p95'] or float('nan'):.2f}/{r['lat_err_mm_max'] or float('nan'):.2f} mm  jerk max={r['jerk_max_rad_s3']:.0f} p99={r['jerk_p99_rad_s3']:.0f}  rejects={r['rejects']} no_overlap={r['no_overlap']} stop_mid={r['stop_ticks_mid']} e2e p50={r['e2e_ms_p50']}", flush=True)
    out = ROOT / "docs/benchmarks" / f"{a.tag}_compare_ep{a.episode}.json"; out.write_text(json.dumps(results, indent=1))
    # 그림
    import matplotlib; matplotlib.use("Agg")
    from matplotlib import font_manager as fm
    c = [f for f in fm.findSystemFonts() if "NotoSansCJK" in f]
    if c: fm.fontManager.addfont(c[0]); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=c[0]).get_name()
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 4, figsize=(18, 4.2))
    for pol in a.policies:
        rs = [r for r in results if r["policy"] == pol]; x = [r["delay_ms"] for r in rs]
        ax[0].plot(x, [r["lat_err_mm_mean"] or np.nan for r in rs], "o-", label=pol); ax[1].plot(x, [r["lat_err_mm_max"] or np.nan for r in rs], "o-", label=pol)
        ax[2].plot(x, [r["jerk_p99_rad_s3"] for r in rs], "o-", label=pol); ax[3].plot(x, [r["rejects"] for r in rs], "o-", label=pol)
    for k, (t, y) in enumerate([("용접선 추종 오차 평균 [mm]", None), ("추종 오차 최대 [mm]", None), ("저크 p99 [rad/s³]", None), ("거부 청크 수", None)]):
        ax[k].set_title(t); ax[k].set_xlabel("주입 추론 지연 [ms]"); ax[k].grid(alpha=.3); ax[k].legend(fontsize=8)
    fig.suptitle(f"반영 정책 비교 (ep{a.episode}, {a.msg}, 지터 ±{a.jitter}ms)"); fig.savefig(ROOT / "docs/figures" / f"{a.tag}_policy_compare_ep{a.episode}.png", dpi=90, bbox_inches="tight")
    print("saved", out)


if __name__ == "__main__":
    main()
