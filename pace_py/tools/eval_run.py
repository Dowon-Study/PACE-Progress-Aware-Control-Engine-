"""한 실행의 품질 지표: 용접선 추종 오차(툴 FK vs 실제 용접선 GT), 최대·RMS 저크, 정지/감속/거부/접합 수, E2E.
사용: python -m pace_py.tools.eval_run --name s5_xxx --episode 0  → JSON 출력 (+ 파일)"""
import argparse, csv, json, os, sys
from pathlib import Path
import numpy as np
os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.tools.trace import load_trace   # noqa: E402

RUNS = Path("docs/benchmarks/runs")


def evaluate(name: str, episode: int, settle_s: float = 4.5, data="data/gt"):
    tr = load_trace(RUNS / f"{name}.trace.bin"); rows = list(csv.DictReader(open(RUNS / f"{name}.csv"))); summ = json.load(open(RUNS / f"{name}.summary.json"))
    ep = np.load(Path(data) / f"ep_{episode:04d}.npz"); seam = ep["seam_pts"].astype(float)
    m = mujoco.MjModel.from_xml_path(f"pace/models/ur5e/_gen_ep{episode:04d}.xml"); d = mujoco.MjData(m); sid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "tool")
    t = (tr["t_ns"] - tr["t_ns"][0]) / 1e9; n = len(t)
    tool = np.zeros((n, 3))
    for i in range(0, n):
        d.qpos[:] = tr["q_meas"][i]; mujoco.mj_kinematics(m, d); tool[i] = d.site_xpos[sid]
    # 용접 구간: 접근(transit) 이후 + 툴이 판 위(z < 0.33)에 있고 움직이는 동안
    moving = np.r_[0, np.linalg.norm(np.diff(tool, axis=0), axis=1)] > 1e-6
    # 용접 구간 시작 = 접근 후 툴이 처음으로 용접선 1mm 안·판 위에 닿는 시각 (페이싱으로 접근이 길어져도 안전)
    from scipy.spatial import cKDTree as _KD
    _d0, _ = _KD(seam[:, :2]).query(tool[:, :2]); near = (_d0 < 0.0003) & (tool[:, 2] < 0.33) & (t > 1.0)
    t_weld0 = (t[np.argmax(near)] + 0.3) if near.any() else settle_s   # 접촉 후 0.3s 부터 (접근 블렌딩 꼬리 제외)
    weld = (t >= t_weld0) & (tool[:, 2] < 0.33) & moving
    # 용접선까지 거리: xy 최근접 + z 간격(2mm 기준) 오차
    err_lat = np.full(n, np.nan); err_z = np.full(n, np.nan)
    from scipy.spatial import cKDTree
    kd = cKDTree(seam[:, :2]); _, idx = kd.query(tool[:, :2])
    # 최근접 점의 양쪽 선분에 투영해 양자화 바닥 제거 (참값 1mm 간격)
    for i in range(n):
        k = idx[i]; best = np.inf
        for a, b in ((max(k - 1, 0), k), (k, min(k + 1, len(seam) - 1))):
            if a == b: continue
            pa, pb = seam[a, :2], seam[b, :2]; v = pb - pa; L2 = float(v @ v)
            tt = 0.0 if L2 < 1e-16 else float(np.clip((tool[i, :2] - pa) @ v / L2, 0, 1))
            dd = float(np.linalg.norm(tool[i, :2] - (pa + tt * v)))
            if dd < best: best = dd
        err_lat[i] = best if np.isfinite(best) else np.linalg.norm(tool[i, :2] - seam[k, :2])
    err_z[:] = tool[:, 2] - seam[idx, 2] - 0.002
    # 저크 (명령 기준, 3차 차분 / dt^3), 축 최대
    q = tr["q_cmd"]; dt = 1e-3
    jerk = np.abs(np.diff(q, n=3, axis=0)).max(axis=1) / dt**3 if len(q) > 3 else np.zeros(1)
    acc = np.abs(np.diff(q, n=2, axis=0)).max(axis=1) / dt**2
    mode = np.array([int(r["mode"]) for r in rows]); mon = np.array([int(r["monitor"]) for r in rows]); rej = np.array([int(r["reject"]) for r in rows])
    seq = np.array([int(r["chunk_seq"]) for r in rows]); tgen = np.array([int(r["chunk_t_gen_ns"]) for r in rows]); ts = np.array([int(r["t_sched_ns"]) for r in rows])
    chg = np.where(np.diff(seq) != 0)[0] + 1; e2e = (ts[chg] - tgen[chg]) / 1e6; e2e = e2e[(tgen[chg] > 0) & (e2e > 0) & (e2e < 5000)]
    stopped_weld = ((mode == 6) & (t[:len(mode)] >= t_weld0) & (t[:len(mode)] < t[-1] - 2.0)).sum() if len(mode) == n else int((mode == 6).sum())
    meta = json.load(open(Path(data) / f"ep_{episode:04d}.json")); v_gt = meta["speed_mps"]
    tool_speed = np.r_[0, np.linalg.norm(np.diff(tool, axis=0), axis=1)] / 1e-3
    sp_mean = float(tool_speed[weld].mean()) if weld.any() else 0.0
    reached_end = bool(np.linalg.norm(tool[weld][-1, :2] - seam[-1, :2]) < 0.005) if weld.any() else False
    sp_scale = np.array([float(r["speed_scale"]) for r in rows]); tt = (ts - ts[0]) / 1e9
    t_weld_end = float(t[weld][-1]) if weld.any() else float(tt[-1])   # 툴이 용접선 위에서 마지막으로 움직인 시각 (에피소드 끝 정지 제외)
    mid = (tt >= t_weld0) & (tt <= t_weld_end)
    stopped_any = bool(((sp_scale <= 1e-3) & mid).sum() > 0); stop_time_s = float(((sp_scale <= 1e-3) & mid).sum() * 1e-3)
    min_speed_mid = float(sp_scale[mid].min()) if mid.any() else None
    mode_mid = mode[mid] if mid.any() else mode[:0]
    out = {"name": name, "episode": episode, "policy": summ.get("policy", "?"), "ticks": int(n), "t_weld_start_s": float(t_weld0), "weld_completed": reached_end,
           "t_weld_end_s": t_weld_end, "stopped_any_mid": stopped_any, "stop_time_s_mid": stop_time_s, "min_speed_scale_mid": min_speed_mid,
           "pacing_ticks": int((mode_mid == 2).sum()), "local_ticks": int((mode_mid == 3).sum()), "extrap_ticks": int((mode_mid == 4).sum()), "hold_ticks_mid": int((mode_mid == 5).sum()), "extrapolations": summ.get("extrapolations", 0),
           "tool_speed_mm_s_mean": sp_mean * 1e3, "tool_speed_ratio_to_gt": sp_mean / v_gt if v_gt else None,
           "tool_speed_mm_s_p95": float(np.percentile(tool_speed[weld], 95) * 1e3) if weld.any() else None,
           "lat_err_mm_mean": float(np.nanmean(err_lat[weld]) * 1e3) if weld.any() else None, "lat_err_mm_p95": float(np.nanpercentile(err_lat[weld], 95) * 1e3) if weld.any() else None,
           "lat_err_mm_max": float(np.nanmax(err_lat[weld]) * 1e3) if weld.any() else None, "z_err_mm_mean": float(np.nanmean(np.abs(err_z[weld])) * 1e3) if weld.any() else None,
           "jerk_max_rad_s3": float(jerk.max()), "jerk_p99_rad_s3": float(np.percentile(jerk, 99)), "acc_max_rad_s2": float(acc.max()),
           "rejects": int((rej > 0).sum()), "no_overlap": summ.get("no_overlap", 0), "splices": summ.get("splices", 0),
           "stop_ticks_mid": int(stopped_weld), "slow_ticks": int((mon == 1).sum()), "weld_ticks": int(weld.sum()),
           "e2e_ms_p50": float(np.percentile(e2e, 50)) if len(e2e) else None, "e2e_ms_max": float(e2e.max()) if len(e2e) else None,
           "wake_max_us": summ["wake_latency"]["max_us"], "exec_max_us": summ["loop_exec"]["max_us"]}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--name", required=True); ap.add_argument("--episode", type=int, required=True)
    a = ap.parse_args(); o = evaluate(a.name, a.episode); (RUNS / f"{a.name}.eval.json").write_text(json.dumps(o, indent=1)); print(json.dumps(o, indent=1, ensure_ascii=False))
