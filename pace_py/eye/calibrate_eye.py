"""작은 눈 보정·평가: 데이터셋 nominal 에피소드의 근접 카메라 프레임에서 선을 검출하고, 픽셀 오프셋 u 와 라벨(실제 선 대비 툴 가로 오프셋)을
선형 회귀해 a·u + b = lat_corr (m) 를 맞춘다. 결과: pace_py/eye/calib.json, 잔차(mm)·검출률 보고.
CORRECTION.lat = -(라벨 correction_lat) : 라벨은 "툴이 선 대비 얼마나", 보정은 "목표를 얼마나 옮겨야 선에 닿나"."""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.eye.seam_eye import detect_seam, torch_mask_from_frames, tip_from_mask   # noqa: E402

def main(n_ep=40, out="pace_py/eye/calib.json"):
    idx = json.load(open("data/gt/index.json")); eps = [m for m in idx if m["mode"] == "nominal"][:n_ep]
    U, Y, INL, det, tot = [], [], [], 0, 0
    d0 = np.load(f"data/gt/ep_{eps[0]['episode']:04d}.npz"); mask = torch_mask_from_frames(d0["img_tool"][::5]); tip = tip_from_mask(mask)
    print(f"torch mask: {int(mask.sum())} px, tip at {tip}")
    for m in eps:
        d = np.load(f"data/gt/ep_{m['episode']:04d}.npz"); imgs = d["img_tool"]; lab = -d["correction_lat"]; t = d["img_t"]
        for i in range(len(imgs)):
            if t[i] < 1.2: continue                                   # 리드인 제외
            tot += 1; u, ang, inl, ok = detect_seam(imgs[i], mask, tip)
            if ok: det += 1; U.append(u); Y.append(lab[i]); INL.append(inl)
    U, Y = np.array(U), np.array(Y)
    A = np.stack([U, np.ones_like(U)], 1)
    # RANSAC 선형 회귀 (잔차 1mm 이내를 인라이어로)
    rng = np.random.default_rng(0); best = None
    for _ in range(500):
        k = rng.choice(len(U), 2, replace=False); (a, b), *_ = np.linalg.lstsq(A[k], Y[k], rcond=None)
        inl = np.abs(a * U + b - Y) < 0.001
        if best is None or inl.sum() > best[0]: best = (inl.sum(), inl)
    rob = best[1]; (a2, b2), *_ = np.linalg.lstsq(A[rob], Y[rob], rcond=None); res2 = (a2 * U[rob] + b2 - Y[rob]) * 1e3
    print(f"RANSAC inliers: {rob.sum()}/{len(U)} ({rob.mean():.1%})  outlier |res| median {np.median(np.abs(a2*U[~rob]+b2-Y[~rob]))*1e3:.1f} mm" if (~rob).any() else "no outliers")
    calib = {"a_m_per_px": float(a2), "b_m": float(b2), "sign": 1.0, "torch_mask": mask.tolist(), "tip": [float(tip[0]), float(tip[1])], "n_samples": int(rob.sum()), "resid_mm_rms": float(np.sqrt((res2**2).mean())), "resid_mm_p95": float(np.percentile(np.abs(res2), 95)), "detect_rate": det / max(tot, 1), "inlier_rate": float(rob.mean())}
    json.dump(calib, open(out, "w"), indent=1)
    print(f"episodes={len(eps)} frames={tot} detected={det} ({det/tot:.1%})  fit: lat_m = {a2:.6f}·u_px + {b2:.5f}  → {a2*1e3:.3f} mm/px")
    print(f"residual: rms {calib['resid_mm_rms']:.2f} mm, p95 {calib['resid_mm_p95']:.2f} mm (라벨 범위 {Y.min()*1e3:.1f}~{Y.max()*1e3:.1f} mm)")
    return calib

if __name__ == "__main__":
    main()
