"""폐루프 복귀 증강(DAgger 식 잡음 주입): GT 프레임마다 관절을 σ 만큼 흔든 자세에서 두 카메라를 다시 렌더하고,
목표 청크는 '흔들린 자세 → GT 궤적' 차분으로 둔다. 모델이 궤적을 벗어났을 때 되돌아오는 법을 배운다.
사용: python -m pace_py.ai.augment --sigma 0.01 --out data/ai_aug --workers 6"""
import argparse, json, sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np, mujoco
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.ai.data import scene_small, HOR_N, HOR_DT, CTX_N, CTX_DT, ADV_AHEAD   # noqa: E402
ROOT = Path(__file__).resolve().parents[2]


def one(args):
    ep, sigma, out, seed, stride = args
    d = np.load(ROOT / f"data/gt/ep_{ep:04d}.npz"); q = d["q"]; it = d["img_t"]; rng = np.random.default_rng([seed, ep])
    idx = np.clip(np.round(it * 1000).astype(int), 0, len(q) - 1); ok = (idx + HOR_N * HOR_DT < len(q)) & (idx >= CTX_N * CTX_DT); idx = idx[ok]
    m = mujoco.MjModel.from_xml_path(str(ROOT / f"pace/models/ur5e/_gen_ep{ep:04d}.xml")); dd = mujoco.MjData(m); rt = mujoco.Renderer(m, 120, 160); rs = mujoco.Renderer(m, 224, 224)
    tool, scene, qp, ctx, tgt, adv = [], [], [], [], [], []
    for i in idx:
        pert = (rng.normal(0, 1, 6) * np.asarray(sigma)).astype(np.float32) * rng.uniform(0.2, 1.0); qi = q[i] + pert
        dd.qpos[:6] = qi; mujoco.mj_forward(m, dd); rt.update_scene(dd, camera="cam_tool"); tool.append(rt.render().copy()); rs.update_scene(dd, camera="cam_scene"); scene.append(scene_small(rs.render()))
        qp.append(qi); ctx.append(q[i - CTX_DT * np.arange(CTX_N, 0, -1)] - qi); tgt.append(q[i + HOR_DT * np.arange(1, HOR_N + 1)] - qi)
        v = (q[i] - q[i - 10]) / 0.01; adv.append(np.abs(q[min(i + ADV_AHEAD, len(q) - 1)] - (q[i] + v * 0.3)).max())
    np.savez(out / f"ep_{ep:04d}.npz", img_tool=np.stack(tool), img_scene_small=np.stack(scene), q=np.stack(qp).astype(np.float32), ctx=np.stack(ctx).astype(np.float32), tgt=np.stack(tgt).astype(np.float32), adv=np.array(adv, np.float32))
    return ep, len(idx)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--sigma", type=float, nargs="+", default=[0.01], help="관절별 σ(rad), 1개면 공통. 손목 회전(5번)은 카메라가 같이 돌아 폐루프 발산의 주범 → 크게"); ap.add_argument("--out", default="data/ai_aug"); ap.add_argument("--workers", type=int, default=6); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--stride", type=int, default=1, help="프레임 간격 (2 = 절반만 렌더)")
    a = ap.parse_args(); out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True); a.sigma = a.sigma * 6 if len(a.sigma) == 1 else a.sigma
    eps = [e["episode"] for e in json.loads((ROOT / "data/gt/index.json").read_text()) if e["mode"] == "ideal"]
    with Pool(a.workers) as p:
        n = 0
        for ep, k in p.imap_unordered(one, [(e, a.sigma, out, a.seed, a.stride) for e in eps]): n += k
    print(f"augmented {len(eps)} episodes, {n} frames, sigma={a.sigma} → {out}")


if __name__ == "__main__":
    main()
