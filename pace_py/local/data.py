"""로컬 감독 계층 학습 데이터: GT ideal 에피소드의 1kHz 관절 궤적에서 (문맥, 연속 청크, 300ms 앞 이탈) 창을 만든다.
문맥   = 최근 300ms 의 q (10ms 간격 30점, 현재 q 기준 차분) + 현재 q (절대)
목표   = 앞으로 1.0s 의 q (20ms 간격 50점, 현재 q 기준 차분)  → PATH 청크 (현재 q 를 첫 점으로 51점)
조언기 라벨 = max_j |q(t+300ms) − (q(t) + v(t)·0.3)|  (규칙 외삽이 300ms 뒤에 얼마나 틀리는가 = 곡률·속도 변화)"""
import json
from pathlib import Path
import numpy as np

CTX_N, CTX_DT = 30, 10      # 30 × 10ms = 300ms
HOR_N, HOR_DT = 50, 20      # 50 × 20ms = 1.0s
ADV_AHEAD = 300             # ms


def episode_windows(q: np.ndarray, stride: int = 10):
    """q: [N,6] 1kHz. 반환 ctx[K,30,6], qabs[K,6], tgt[K,50,6], adv[K]"""
    N = len(q); i0 = CTX_N * CTX_DT; i1 = N - HOR_N * HOR_DT - 1
    idx = np.arange(i0, i1, stride)
    ctx = np.stack([q[i - CTX_DT * np.arange(CTX_N, 0, -1)] - q[i] for i in idx])          # 과거 → 현재 순, 현재 q 기준
    tgt = np.stack([q[i + HOR_DT * np.arange(1, HOR_N + 1)] - q[i] for i in idx])
    v = (q[idx] - q[idx - CTX_DT]) / (CTX_DT * 1e-3)
    adv = np.abs(q[idx + ADV_AHEAD] - (q[idx] + v * ADV_AHEAD * 1e-3)).max(1)
    return ctx.astype(np.float32), q[idx].astype(np.float32), tgt.astype(np.float32), adv.astype(np.float32)


def load_dataset(root="data/gt", mode="ideal", stride=10, holdout_every=8):
    """ideal 에피소드를 학습/검증으로 나눠 창을 모은다 (holdout_every 번째 에피소드마다 검증)."""
    root = Path(root); index = json.loads((root / "index.json").read_text())
    eps = [e for e in index if e["mode"] == mode]
    tr, va = [[], [], [], []], [[], [], [], []]
    for k, e in enumerate(eps):
        q = np.load(root / f"ep_{e['episode']:04d}.npz")["q"]
        w = episode_windows(q, stride); dst = va if (k % holdout_every == 0) else tr
        for d, x in zip(dst, w): d.append(x)
    cat = lambda L: [np.concatenate(x) for x in L]
    return cat(tr), cat(va), len(eps)
