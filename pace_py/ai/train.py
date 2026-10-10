"""학습: python -m pace_py.ai.train --epochs 20 --out pace_py/ai/ckpt/act_lite.pt
검증(보류 에피소드): 청크 오차 300ms/1s (관절 max abs) vs 규칙 외삽 vs 9단계 로컬 정책, 조언기 MAE vs 평균 예측."""
import argparse, json, time
from pathlib import Path
import numpy as np, torch
from pace_py.ai.data import load_dataset, HOR_DT
from pace_py.ai.model import ActLite


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--epochs", type=int, default=20); ap.add_argument("--batch", type=int, default=256); ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--out", default="pace_py/ai/ckpt/act_lite.pt"); ap.add_argument("--max-eps", type=int, default=None)
    a = ap.parse_args(); dev = "cuda"; torch.manual_seed(0); t0 = time.time()
    (T, S, Q, X, Y, A), (VT, VS, VQ, VX, VY, VA), val_eps = load_dataset(device=dev, max_eps=a.max_eps)
    print(f"train {len(T)} val {len(VT)} (val episodes {val_eps}) load {time.time()-t0:.0f}s", flush=True)
    m = ActLite().to(dev); m.q_mean.copy_(Q.mean(0)); m.q_std.copy_(Q.std(0) + 1e-6); m.y_std.copy_(Y.std(0) + 1e-6); m.adv_scale.fill_(float(A.mean())); m.ctx_std.fill_(float(X.std()) + 1e-6)
    opt = torch.optim.AdamW(m.parameters(), lr=a.lr, weight_decay=1e-4); sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.epochs * ((len(T) + a.batch - 1) // a.batch))
    scaler = torch.amp.GradScaler("cuda")
    for ep in range(a.epochs):
        m.train(); perm = torch.randperm(len(T), device=dev); tot = tot_a = 0.0; nb = 0
        for i in range(0, len(T), a.batch):
            b = perm[i:i + a.batch]; tool = T[b]; scene = S[b]
            if True:   # 증강: 밝기·대비 ±15 %, 1~3px 이동 (렌더 차이·조명 차이에 대한 내성)
                g = (1 + 0.3 * (torch.rand(len(b), 1, 1, 1, device=dev) - 0.5)); tool = (tool.float() * g).clamp(0, 255); scene = (scene.float() * g).clamp(0, 255)
                dx, dy = np.random.randint(-3, 4), np.random.randint(-3, 4); tool = torch.roll(tool, (dy, dx), (1, 2))
            with torch.autocast("cuda", dtype=torch.bfloat16):
                y, adv = m(tool, scene, Q[b], X[b]); loss = ((y - Y[b]).abs() / m.y_std).mean(); loss_a = ((torch.log1p(adv / m.adv_scale) - torch.log1p(A[b] / m.adv_scale)) ** 2).mean()
            opt.zero_grad(); scaler.scale(loss + 0.5 * loss_a).backward(); scaler.unscale_(opt); torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0); scaler.step(opt); scaler.update(); sched.step()
            tot += loss.item(); tot_a += loss_a.item(); nb += 1
        m.eval(); errs = []; errs300 = []; advs = []
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
            for i in range(0, len(VT), 512):
                y, adv = m(VT[i:i + 512], VS[i:i + 512], VQ[i:i + 512], VX[i:i + 512]); e = (y.float() - VY[i:i + 512]).abs(); errs.append(e.max(2).values.max(1).values); errs300.append(e[:, int(300 / HOR_DT) - 1].max(1).values); advs.append(adv.float())
        e_all = torch.cat(errs); e300 = torch.cat(errs300); pa = torch.cat(advs)
        a_err = (pa - VA).abs().mean(); a_base = (VA - VA.mean()).abs().mean()
        print(f"ep {ep+1:2d} l1={tot/nb:.4f} adv={tot_a/nb:.4f} | val chunk err 1s mean={e_all.mean()*1e3:.2f} p95={e_all.quantile(.95)*1e3:.2f} mrad | 300ms mean={e300.mean()*1e3:.2f} | advisor mae={a_err*1e3:.2f} (mean-baseline {a_base*1e3:.2f}) | {time.time()-t0:.0f}s", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model": m.state_dict(), "meta": {"epochs": a.epochs, "train": len(T), "val": len(VT), "val_eps": val_eps, "adv_label_mean": float(A.mean()), "adv_label_p90": float(A.quantile(.9)), "val_err_1s_mean_mrad": float(e_all.mean() * 1e3), "val_err_300_mean_mrad": float(e300.mean() * 1e3), "advisor_mae_mrad": float(a_err * 1e3), "advisor_base_mrad": float(a_base * 1e3)}}, a.out)
    print("saved", a.out)


if __name__ == "__main__":
    main()
