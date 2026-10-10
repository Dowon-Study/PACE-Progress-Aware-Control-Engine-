"""시나리오 × 정책 비교 그림: (1) 지표 막대 (2) 시나리오별 시간축 오버레이 (툴 가로 오차, 속도 배율, 모드)."""
import json, sys, csv, os
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
SCEN = ["disturb", "pacing", "dropout", "openloop_dropout"]; POL = ["timeidx", "immediate", "progress"]
LABEL = {"disturb": "외란 (어깨 60Nm 0.6s)", "pacing": "속도 지령 0.5배", "dropout": "공급 중단 2.5s", "openloop_dropout": "상태 무시 AI + 중단"}


def seam_err(name, episode, m, sid, seam):
    tr = load_trace(RUNS / f"{name}.trace.bin"); d = mujoco.MjData(m); t = (tr["t_ns"] - tr["t_ns"][0]) / 1e9
    tool = np.zeros((len(t), 3))
    for i in range(len(t)): d.qpos[:] = tr["q_meas"][i]; mujoco.mj_kinematics(m, d); tool[i] = d.site_xpos[sid]
    from scipy.spatial import cKDTree
    _, idx = cKDTree(seam[:, :2]).query(tool[:, :2]); err = np.linalg.norm(tool[:, :2] - seam[idx, :2], axis=1)
    speed = np.r_[0, np.linalg.norm(np.diff(tool, axis=0), axis=1)] / 1e-3   # m/s
    return t, err, speed, tr


def main(episode=0, delay=100, tag="s5"):
    res = {}
    for sc in SCEN:
        p = ROOT / "docs/benchmarks" / f"{tag}_{sc}_compare_ep{episode}.json"
        if p.exists(): res[sc] = {r["policy"]: r for r in json.load(p.open())}
    # (1) 지표 막대
    metrics = [("lat_err_mm_max", "추종 오차 최대 [mm]"), ("lat_err_mm_mean", "추종 오차 평균 [mm]"), ("jerk_p99_rad_s3", "저크 p99 [rad/s³]"), ("stop_ticks_mid", "용접 중 정지 틱"), ("rejects", "거부+NO_OVERLAP")]
    fig, ax = plt.subplots(1, len(metrics), figsize=(4.2 * len(metrics), 4.2)); w = 0.26
    for k, (key, lab) in enumerate(metrics):
        for j, pol in enumerate(POL):
            vals = [(res[sc][pol].get(key) or 0) + (res[sc][pol].get("no_overlap", 0) if key == "rejects" else 0) if sc in res and pol in res[sc] else 0 for sc in SCEN]
            ax[k].bar(np.arange(len(SCEN)) + (j - 1) * w, vals, w, label=pol)
        ax[k].set_xticks(range(len(SCEN))); ax[k].set_xticklabels([LABEL[s] for s in SCEN], rotation=20, fontsize=8); ax[k].set_title(lab); ax[k].grid(alpha=.3, axis="y")
    ax[0].legend(fontsize=8); fig.suptitle(f"반영 정책 비교 — 어려운 시나리오 {len(SCEN)}종 (ep{episode}, 지연 {delay}±50ms)")
    fig.savefig(ROOT / "docs/figures" / f"{tag}_scenarios_bars_ep{episode}.png", dpi=90, bbox_inches="tight")
    # (2) 시간축 오버레이
    ep = np.load(ROOT / f"data/gt/ep_{episode:04d}.npz"); seam = ep["seam_pts"].astype(float)
    m = mujoco.MjModel.from_xml_path(str(ROOT / f"pace/models/ur5e/_gen_ep{episode:04d}.xml")); sid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "tool")
    fig, ax = plt.subplots(3, len(SCEN), figsize=(5.2 * len(SCEN), 9), sharex="col")
    for col, sc in enumerate(SCEN):
        for pol in POL:
            name = f"{tag}_{sc}_{pol}_d{delay}_ep{episode}"
            if not (RUNS / f"{name}.trace.bin").exists(): continue
            t, err, speed, tr = seam_err(name, episode, m, sid, seam)
            ax[0, col].plot(t, err * 1e3, lw=0.8, label=pol); ax[1, col].plot(t, speed * 1e3, lw=0.8, label=pol); ax[2, col].step(t, tr["speed"], where="post", lw=0.8, label=pol)
        ax[0, col].set_title(LABEL[sc]); ax[0, col].set_ylabel("용접선 가로 오차 [mm]"); ax[0, col].set_ylim(0, 8); ax[1, col].set_ylabel("툴 속도 [mm/s]"); ax[1, col].set_ylim(0, 40); ax[2, col].set_ylabel("속도 배율"); ax[2, col].set_xlabel("t [s]")
        for r in range(3): ax[r, col].grid(alpha=.3); ax[r, col].set_xlim(4, 30)
    ax[0, 0].legend(fontsize=8)
    fig.suptitle(f"시나리오별 시간축 (ep{episode}): 가로 오차 · 툴 속도 · 속도 배율")
    fig.savefig(ROOT / "docs/figures" / f"{tag}_scenarios_timeline_ep{episode}.png", dpi=85, bbox_inches="tight"); print("figures saved")


if __name__ == "__main__":
    main()
