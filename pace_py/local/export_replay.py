"""온라인 학습용 오프라인 재생 버퍼: GT ideal 학습 창에서 N 개를 골라 float16 npz 로 저장 (잊음 방지 + 재생 검증 기준).
사용: python -m pace_py.local.export_replay --n 8000 --out pace_py/local/ckpt/replay_ideal.npz   (data/gt 필요)"""
import argparse
from pathlib import Path
import numpy as np
from pace_py.local.data import load_dataset
from pace_py.local.train import feats


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=8000); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--out", default="pace_py/local/ckpt/replay_ideal.npz")
    a = ap.parse_args(); (ctx, qabs, tgt, _), _, n_eps = load_dataset(stride=10)
    X = feats(ctx, qabs); Y = tgt.reshape(len(tgt), -1); idx = np.random.default_rng(a.seed).choice(len(X), size=min(a.n, len(X)), replace=False)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True); np.savez_compressed(a.out, X=X[idx].astype(np.float16), Y=Y[idx].astype(np.float16))
    print(f"saved {a.out}: {len(idx)} windows from {len(X)} ({n_eps} episodes), {Path(a.out).stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    main()
