"""한 중단 길이 T 에 대해 구성(hold / pacing / pacing_ext)의 시간축 비교: 속도 배율·모드·용접선 오차·툴 속도."""
import csv, os, sys
from pathlib import Path
import numpy as np
os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco, matplotlib; matplotlib.use("Agg")
from matplotlib import font_manager as fm
c = [f for f in fm.findSystemFonts() if "NotoSansCJK" in f]
if c: fm.fontManager.addfont(c[0]); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=c[0]).get_name()
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.trace import load_trace   # noqa: E402
ROOT = Path(__file__).resolve().parents[2]; RUNS = ROOT / "docs/benchmarks/runs"
MODES = ["INIT", "NORMAL", "PACING", "LOCAL", "EXTRAP", "HOLD", "STOPPED", "RECOVER"]


def main(gap="3", episode=0, tag="s6", configs=("hold", "pacing", "pacing_ext"), t_lo=10, t_hi=24):
    ep = np.load(ROOT / f"data/gt/ep_{episode:04d}.npz"); seam = ep["seam_pts"].astype(float)
    m = mujoco.MjModel.from_xml_path(str(ROOT / f"pace/models/ur5e/_gen_ep{episode:04d}.xml")); d = mujoco.MjData(m); sid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "tool")
    from scipy.spatial import cKDTree; kd = cKDTree(seam[:, :2])
    fig, ax = plt.subplots(4, 1, figsize=(13, 11), sharex=True)
    for cfg in configs:
        name = f"{tag}_{cfg}_gap{gap}_ep{episode}"
        if not (RUNS / f"{name}.csv").exists(): continue
        rows = list(csv.DictReader(open(RUNS / f"{name}.csv"))); t0 = int(rows[0]["t_sched_ns"])
        t = (np.array([int(r["t_sched_ns"]) for r in rows]) - t0) / 1e9; sp = np.array([float(r["speed_scale"]) for r in rows]); mode = np.array([int(r["mode"]) for r in rows])
        tr = load_trace(RUNS / f"{name}.trace.bin"); tt = (tr["t_ns"] - tr["t_ns"][0]) / 1e9
        tool = np.zeros((len(tt), 3))
        for i in range(len(tt)): d.qpos[:] = tr["q_meas"][i]; mujoco.mj_kinematics(m, d); tool[i] = d.site_xpos[sid]
        dist, _ = kd.query(tool[:, :2]); v = np.r_[0, np.linalg.norm(np.diff(tool, axis=0), axis=1)] * 1e6
        vs = np.convolve(v, np.ones(50) / 50, mode="same")
        ax[0].step(t, sp, where="post", lw=1.2, label=cfg); ax[1].step(t, mode, where="post", lw=1.2, label=cfg)
        ax[2].plot(tt, dist * 1e3, lw=0.9, label=cfg); ax[3].plot(tt, vs, lw=0.9, label=cfg)
    ax[0].set_ylabel("속도 배율"); ax[1].set_ylabel("모드"); ax[1].set_yticks(range(8)); ax[1].set_yticklabels(MODES, fontsize=8)
    ax[2].set_ylabel("용접선 가로 오차 [mm]"); ax[2].set_ylim(0, 6); ax[3].set_ylabel("툴 속도 [mm/s] (50ms 평균)"); ax[3].set_ylim(0, 40); ax[3].set_xlabel("t [s]")
    for a in ax: a.grid(alpha=.3); a.set_xlim(t_lo, t_hi)
    ax[0].legend(fontsize=9); fig.suptitle(f"공급 중단 {gap}s 동안의 사다리 동작 비교 (ep{episode}, progress): hold vs 페이싱 vs 페이싱+외삽")
    out = ROOT / "docs/figures" / f"{tag}_gap{gap}_timeline_ep{episode}.png"; fig.savefig(out, dpi=90, bbox_inches="tight"); print("saved", out)


if __name__ == "__main__":
    main(*(sys.argv[1:2] or ["3"]))
