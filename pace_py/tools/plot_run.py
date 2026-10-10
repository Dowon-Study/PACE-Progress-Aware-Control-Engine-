"""한 번의 실행(metrics CSV + trace npz)에서 4단계 그래프: 모드/판정/거부 타임라인, E2E 분포, 관절 추종, 지터."""
import argparse, json, sys
from pathlib import Path
import numpy as np, matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager as fm
_c = [f for f in fm.findSystemFonts() if "NotoSansCJK" in f]
if _c: fm.fontManager.addfont(_c[0]); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_c[0]).get_name()
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.msg import Mode   # noqa: E402
from pace_py.tools.trace import load_trace   # noqa: E402

REJ = ["NONE", "HEADER", "RANGE_POS", "RANGE_VEL", "RANGE_ACC", "WORKSPACE", "EXPIRED", "SEQ_ORDER", "TOO_OLD", "DEVIATION", "CONFIDENCE", "NO_OVERLAP"]
TRIG = ["JOINT", "VEL", "ACC", "WORKSPACE", "DEVIATION", "TRACK_ERR", "EXTRAP_CAP", "HAL_FAULT", "BLIND", "EVENT", "BUFFER_LOW", "EYE_STALE"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--csv", required=True); ap.add_argument("--trace", default=None); ap.add_argument("--out", required=True); ap.add_argument("--title", default="")
    a = ap.parse_args()
    import csv
    rows = list(csv.DictReader(open(a.csv)))
    t = (np.array([int(r["t_sched_ns"]) for r in rows]) - int(rows[0]["t_sched_ns"])) / 1e9
    wake = np.array([int(r["st_wake_ns"]) for r in rows]) / 1e3
    mode = np.array([int(r["mode"]) for r in rows]); mon = np.array([int(r["monitor"]) for r in rows]); rej = np.array([int(r["reject"]) for r in rows]); trig = np.array([int(r["triggers"]) for r in rows])
    speed = np.array([float(r["speed_scale"]) for r in rows]); margin = np.array([float(r["buffer_margin_ms"]) for r in rows])
    seq = np.array([int(r["chunk_seq"]) for r in rows]); tgen = np.array([int(r["chunk_t_gen_ns"]) for r in rows]); tsched = np.array([int(r["t_sched_ns"]) for r in rows])
    # E2E: 청크 시퀀스가 바뀐 첫 틱의 (틱 시각 - 생성 시각)
    chg = np.where(np.diff(seq) != 0)[0] + 1; e2e = (tsched[chg] - tgen[chg]) / 1e6; e2e = e2e[(tgen[chg] > 0) & (e2e > 0) & (e2e < 5000)]
    fig, ax = plt.subplots(5, 1, figsize=(14, 13), sharex=True, gridspec_kw={"height_ratios": [1.2, 1, 1, 1, 1.2]})
    ax[0].step(t, mode, where="post", label="mode"); ax[0].set_yticks(range(8)); ax[0].set_yticklabels([Mode(i).name for i in range(8)], fontsize=7); ax[0].set_title(a.title or Path(a.csv).stem); ax[0].grid(alpha=.3)
    ax[1].step(t, mon, where="post", color="C3", label="감시기 판정 (0 OK, 1 SLOW, 2 STOP)"); ax[1].step(t, speed, where="post", color="C2", label="속도 배율"); ax[1].legend(fontsize=8, loc="upper right"); ax[1].grid(alpha=.3)
    for b, name in enumerate(TRIG):
        on = (trig >> b) & 1
        if on.any(): ax[1].fill_between(t, 0, 2.2 * on, step="post", alpha=0.12, label=name); ax[1].text(t[np.argmax(on)], 2.3 - 0.15 * (b % 4), name, fontsize=7)
    rj = rej > 0
    ax[2].plot(t, margin, color="C0", lw=0.8, label="버퍼 여유 ms"); ax[2].axhline(0, color="k", lw=0.5); ax[2].legend(fontsize=8, loc="upper right"); ax[2].grid(alpha=.3)
    if rj.any():
        ax[2].scatter(t[rj], np.full(rj.sum(), margin.max() if margin.max() > 0 else 100), marker="x", color="C3", s=30, label="거부")
        for tt, rr in zip(t[rj], rej[rj]): ax[2].text(tt, (margin.max() if margin.max() > 0 else 100) * 1.05, REJ[rr], fontsize=7, rotation=90, color="C3")
    ax[3].plot(t, wake, lw=0.5); ax[3].set_ylabel("깨어남 지연 μs"); ax[3].axhline(100, color="r", ls="--", lw=0.8); ax[3].grid(alpha=.3)
    if a.trace and Path(a.trace).exists():
        tr = load_trace(a.trace); err = np.abs(tr["q_cmd"] - tr["q_meas"]).max(axis=1)
        tt = (tr["t_ns"] - tr["t_ns"][0]) / 1e9
        ax[4].plot(tt, err, lw=0.7, label="|q_cmd − q_meas| 최대 (rad)"); ax[4].plot(tt, tr["q_cmd"][:, 0], lw=0.7, alpha=0.6, label="q_cmd[0]"); ax[4].plot(tt, tr["q_meas"][:, 0], lw=0.7, alpha=0.6, label="q_meas[0]")
        ax[4].legend(fontsize=8, loc="upper right"); ax[4].grid(alpha=.3)
    ax[4].set_xlabel("t [s]")
    txt = f"ticks={len(rows)} wake max={wake.max():.1f}us p99={np.percentile(wake,99):.1f}us | 거부 {rj.sum()}건 " + ", ".join(f"{REJ[k]}:{(rej==k).sum()}" for k in np.unique(rej[rj])) + f" | STOP 틱 {(mon==2).sum()} SLOW 틱 {(mon==1).sum()}"
    if len(e2e): txt += f" | E2E(청크 {len(e2e)}개) p50={np.percentile(e2e,50):.0f} p95={np.percentile(e2e,95):.0f} max={e2e.max():.0f} ms"
    fig.text(0.01, 0.005, txt, fontsize=8)
    fig.savefig(a.out, dpi=90, bbox_inches="tight"); print(txt); print("saved", a.out)


if __name__ == "__main__":
    main()
