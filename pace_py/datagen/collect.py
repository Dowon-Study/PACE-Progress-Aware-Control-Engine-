"""GT 데이터 수집: 용접선 형상 랜덤 생성 → 궤적 GT → MuJoCo 실행(중력 보상 위치 서보) → 카메라 2대 렌더 → npz 저장.

episode 모드
  ideal   : 로봇이 실제 용접선을 정확히 따라감. 로컬 연속 정책 학습용 (이미지+상태 → 앞으로의 경로).
  nominal : 로봇은 "교시된" 용접선(실제와 고정구 오차만큼 다름)을 따라감. 카메라에는 어긋난 실제 용접선이 보임.
            라벨 = 실제 선 대비 (가로, 높이) 보정량 → 작은 눈 / CORRECTION 학습용.
저장 (data/gt/ep_XXXX.npz):
  t, s, q, qd, tool_pos, tool_quat (GT, 1kHz)  /  q_meas, tool_pos_meas (시뮬 실측, 1kHz)
  img_scene[F,H,W,3], img_tool[F,h,w,3], img_t[F]  (fps)
  seam_pts[N,3], seam_s[N], seam_tan[N,3]  (실제 용접선 GT, 1mm)
  nominal_seam_pts (nominal 모드), correction_lat[F], correction_h[F]  (프레임별 라벨)
  meta.json 옆에 저장.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.datagen import seams as S                      # noqa: E402
from pace_py.datagen.trajectory import weld_trajectory      # noqa: E402

HOME_Q = None   # weld_home 키프레임에서 읽음


def lateral_offset(tool_xy: np.ndarray, seam_pts: np.ndarray, seam_tan: np.ndarray, s_hint_idx: int, window: int = 400):
    """툴 xy 와 가장 가까운 실제 용접선 점(힌트 주변 창 안)을 찾아 부호 있는 가로 오프셋과 인덱스 반환."""
    lo, hi = max(0, s_hint_idx - window), min(len(seam_pts), s_hint_idx + window)
    d = seam_pts[lo:hi, :2] - tool_xy
    k = lo + int(np.argmin(np.einsum("ij,ij->i", d, d)))
    tan = seam_tan[k, :2]; nrm = np.array([-tan[1], tan[0]])
    return float(np.dot(tool_xy - seam_pts[k, :2], nrm)), k


FF_TAU = 0.2   # UR5e Menagerie 서보 kv/kp (400/2000, 100/500) → 속도 피드포워드 시간상수


def run_episode(ep: int, rng: np.random.Generator, out_dir: Path, mode: str, fps: float, family: str | None,
                img_scene_wh=(224, 224), img_tool_wh=(160, 120), speed_range=(0.008, 0.014), feedforward: bool = True):
    spec = S.random_spec(rng, family)
    tex_rel = f"textures/ep_{ep:04d}.png"; S.render_texture(spec, S.MODEL_DIR / tex_rel, rng=rng)
    xml = S.write_scene(spec, f"_gen_ep{ep:04d}", tex_rel)
    m = mujoco.MjModel.from_xml_path(str(xml)); d = mujoco.MjData(m)
    key = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_KEY, "weld_home"); q_home = m.key_qpos[key].copy() if key >= 0 else np.zeros(m.nv)
    seam_pts, seam_s, seam_tan = S.seam_world(spec, 0.001)
    # nominal 모드: 교시 선 = 실제 선에 고정구 오차 적용 (이동 ≤ 8mm, 회전 ≤ 2°)
    if mode == "nominal":
        dx, dy, dyaw = rng.uniform(-0.008, 0.008), rng.uniform(-0.008, 0.008), rng.uniform(-0.035, 0.035)
        c, s_ = np.cos(dyaw), np.sin(dyaw); Rz = np.array([[c, -s_], [s_, c]]); ctr = seam_pts[:, :2].mean(axis=0)
        nominal = seam_pts.copy(); nominal[:, :2] = (seam_pts[:, :2] - ctr) @ Rz.T + ctr + [dx, dy]
        nominal_tan = seam_tan.copy(); nominal_tan[:, :2] = seam_tan[:, :2] @ Rz.T
    else:
        nominal, nominal_tan = seam_pts, seam_tan
    speed = float(rng.uniform(*speed_range)); travel = float(np.deg2rad(rng.uniform(5, 15)))
    traj = weld_trajectory(m, nominal, seam_s, nominal_tan, q_home, speed=speed, travel_angle=travel)
    if traj.get("fail") or traj["ik_pos_err_max"] > 1e-3:
        return None, f"ik {traj.get('fail','')} err {traj['ik_pos_err_max']*1e3:.2f}mm"
    # ---- 실행 + 렌더 ----
    sid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "tool")
    r_scene = mujoco.Renderer(m, img_scene_wh[1], img_scene_wh[0]); r_tool = mujoco.Renderer(m, img_tool_wh[1], img_tool_wh[0])
    n = len(traj["t"]); frame_every = max(1, int(round(1.0 / (fps * 0.001))))
    q_meas = np.zeros_like(traj["q"]); tool_meas = np.zeros((n, 3)); imgs_s, imgs_t, img_t, corr_lat, corr_h, seam_idx = [], [], [], [], [], []
    d.qpos[:] = traj["q"][0]; d.qvel[:] = 0; d.ctrl[:] = traj["q"][0]; mujoco.mj_forward(m, d)
    hint = 0
    for i in range(n):
        d.ctrl[:m.nu] = traj["q"][i] + (FF_TAU * traj["qd"][i] if feedforward else 0.0)
        d.qfrc_applied[:] = d.qfrc_bias
        mujoco.mj_step(m, d)
        q_meas[i] = d.qpos; tool_meas[i] = d.site_xpos[sid]
        if i % frame_every == 0:
            r_scene.update_scene(d, camera="cam_scene"); imgs_s.append(r_scene.render().copy())
            r_tool.update_scene(d, camera="cam_tool"); imgs_t.append(r_tool.render().copy())
            img_t.append(traj["t"][i])
            lat, hint = lateral_offset(tool_meas[i, :2], seam_pts, seam_tan, hint)
            corr_lat.append(lat); corr_h.append(float(tool_meas[i, 2] - seam_pts[hint, 2] - 0.002)); seam_idx.append(hint)
    r_scene.close(); r_tool.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_dir / f"ep_{ep:04d}.npz",
        t=traj["t"].astype(np.float32), s=traj["s"].astype(np.float32), q=traj["q"].astype(np.float32), qd=traj["qd"].astype(np.float32),
        tool_pos=traj["tool_pos"].astype(np.float32), tool_quat=traj["tool_quat"].astype(np.float32),
        q_meas=q_meas.astype(np.float32), tool_pos_meas=tool_meas.astype(np.float32),
        img_scene=np.stack(imgs_s), img_tool=np.stack(imgs_t), img_t=np.array(img_t, np.float32),
        seam_pts=seam_pts.astype(np.float32), seam_s=seam_s.astype(np.float32), seam_tan=seam_tan.astype(np.float32),
        nominal_seam_pts=nominal.astype(np.float32), correction_lat=np.array(corr_lat, np.float32), correction_h=np.array(corr_h, np.float32),
        seam_idx=np.array(seam_idx, np.int32))
    track_err = np.linalg.norm(tool_meas[int(traj["lead_in"] / 0.001):] - traj["tool_pos"][int(traj["lead_in"] / 0.001):], axis=1)
    meta = {"episode": ep, "mode": mode, "spec": spec.to_json(), "speed_mps": speed, "travel_angle_deg": float(np.rad2deg(travel)),
            "length_m": traj["length"], "duration_s": float(traj["t"][-1]), "frames": len(img_t), "fps": fps,
            "ik_pos_err_max_mm": traj["ik_pos_err_max"] * 1e3, "track_err_mean_mm": float(track_err.mean() * 1e3), "track_err_max_mm": float(track_err.max() * 1e3),
            "correction_lat_abs_max_mm": float(np.abs(corr_lat).max() * 1e3), "scene_xml": str(xml.name), "texture": tex_rel}
    (out_dir / f"ep_{ep:04d}.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    return meta, None


def _one(args):
    ep, seed, out, mode_opt, fps, family_opt, cycle = args
    rng = np.random.default_rng([seed, ep])                      # 에피소드별 결정적 시드 (병렬·재현 가능)
    mode = mode_opt if mode_opt != "mixed" else ("ideal" if ep % 2 == 0 else "nominal")
    family = family_opt or (S.FAMILIES[(ep // 2) % len(S.FAMILIES)] if cycle else None)
    try:
        meta, err = run_episode(ep, rng, Path(out), mode, fps, family)
    except Exception as e:                                       # 한 에피소드 실패가 전체를 멈추지 않게
        meta, err = None, f"exception {type(e).__name__}: {e}"
    return ep, mode, meta, err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--out", default="data/gt"); ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--mode", choices=["ideal", "nominal", "mixed"], default="mixed"); ap.add_argument("--family", default=None)
    ap.add_argument("--workers", type=int, default=1); ap.add_argument("--no-cycle", action="store_true", help="형상 순환 대신 랜덤")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); t0 = time.time()
    jobs = [(ep, a.seed, str(out), a.mode, a.fps, a.family, not a.no_cycle) for ep in range(a.start, a.start + a.n)]
    results = []
    if a.workers > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(a.workers) as pool:
            for r in pool.imap_unordered(_one, jobs): results.append(r); _report(r)
    else:
        for j in jobs: r = _one(j); results.append(r); _report(r)
    # 색인: 기존 index.json 과 병합 (episode 번호 기준)
    idx_path = out / "index.json"; old = {m["episode"]: m for m in json.load(idx_path.open())} if idx_path.exists() else {}
    for ep, mode, meta, err in results:
        if meta: old[meta["episode"]] = meta
    metas = [old[k] for k in sorted(old)]
    idx_path.write_text(json.dumps(metas, indent=1, ensure_ascii=False))
    ok = sum(1 for r in results if r[2]); print(f"done: {ok}/{len(results)} episodes in {time.time()-t0:.0f}s → {out} (index: {len(metas)} total)")


def _report(r):
    ep, mode, meta, err = r
    if err: print(f"ep {ep:04d} SKIP ({err})", flush=True); return
    print(f"ep {ep:04d} {mode:7s} {meta['spec']['family']:8s} L={meta['length_m']:.3f}m v={meta['speed_mps']*1e3:.1f}mm/s T={meta['duration_s']:.1f}s frames={meta['frames']} track_err max={meta['track_err_max_mm']:.2f}mm corr_max={meta['correction_lat_abs_max_mm']:.1f}mm", flush=True)


if __name__ == "__main__":
    main()
