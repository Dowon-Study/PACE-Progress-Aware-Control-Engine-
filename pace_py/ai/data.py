"""실제 AI 모델(ACT급) 학습 데이터: GT ideal 에피소드의 30fps 프레임(토치 카메라 120×160 + 전경 카메라 224→112) + 그 시각의 관절 q
→ 앞 1.0s 관절 청크(20ms 간격 50점, 현재 q 기준 차분) + 300ms 앞 규칙 외삽 이탈(조언기 라벨). 전부 GPU 메모리에 uint8 로 올린다."""
import json
from pathlib import Path
import numpy as np, cv2, torch

HOR_N, HOR_DT, ADV_AHEAD = 50, 20, 300
CTX_N, CTX_DT = 30, 10
SCENE_HW = 112


def scene_small(img):   # [H,W,3] uint8 224 → 112 (학습·추론 공통)
    return cv2.resize(img, (SCENE_HW, SCENE_HW), interpolation=cv2.INTER_AREA)


def episode_samples(d):
    q = d["q"]; it = d["img_t"]; idx = np.clip(np.round(it * 1000).astype(int), 0, len(q) - 1)
    ok = (idx + HOR_N * HOR_DT < len(q)) & (idx >= CTX_N * CTX_DT); idx = idx[ok]
    ctx = np.stack([q[i - CTX_DT * np.arange(CTX_N, 0, -1)] - q[i] for i in idx]).astype(np.float32)
    tgt = np.stack([q[i + HOR_DT * np.arange(1, HOR_N + 1)] - q[i] for i in idx]).astype(np.float32)
    v = (q[idx] - q[np.maximum(idx - 10, 0)]) / 0.01; adv = np.abs(q[np.minimum(idx + ADV_AHEAD, len(q) - 1)] - (q[idx] + v * 0.3)).max(1).astype(np.float32)
    tool = d["img_tool"][ok]; scene = np.stack([scene_small(x) for x in d["img_scene"][ok]])
    return tool, scene, q[idx].astype(np.float32), ctx, tgt, adv


def load_dataset(root="data/gt", holdout_every=8, device="cuda", max_eps=None, aug_root="data/ai_aug"):
    """원본 GT 프레임 + (있으면) 흔들린 자세 증강 프레임(학습 에피소드만). 검증은 원본 보류 에피소드."""
    root = Path(root); index = json.loads((root / "index.json").read_text()); eps = [e for e in index if e["mode"] == "ideal"]
    if max_eps: eps = eps[:max_eps]
    tr, va = [[] for _ in range(6)], [[] for _ in range(6)]; val_eps = []; aug = Path(aug_root)
    for k, e in enumerate(eps):
        s = episode_samples(np.load(root / f"ep_{e['episode']:04d}.npz")); dst = va if k % holdout_every == 0 else tr
        if k % holdout_every == 0: val_eps.append(e["episode"])
        for L, x in zip(dst, s): L.append(x)
        f = aug / f"ep_{e['episode']:04d}.npz"
        if k % holdout_every != 0 and f.exists():
            g = np.load(f)
            for L, x in zip(tr, [g["img_tool"], g["img_scene_small"], g["q"], g["ctx"], g["tgt"], g["adv"]]): L.append(x)
    def pack(L): return [torch.from_numpy(np.concatenate(x)).to(device) for x in L]
    return pack(tr), pack(va), val_eps
