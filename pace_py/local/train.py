"""학습: python -m pace_py.local.train --epochs 30 --out pace_py/local/ckpt/local_block.pt
검증 지표: 연속 청크 오차(관절 max abs, 1s 지평·300ms) vs 규칙 외삽(등속) 기준선, 조언기 회귀 오차."""
import argparse, json, time
from pathlib import Path
import numpy as np, torch
from pace_py.local.data import load_dataset, HOR_DT
from pace_py.local.model import FlowPolicy, Advisor, CTX_DIM, X_DIM


def feats(ctx, qabs): return np.concatenate([ctx.reshape(len(ctx), -1), qabs], 1)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--epochs", type=int, default=30); ap.add_argument("--batch", type=int, default=2048); ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--out", default="pace_py/local/ckpt/local_block.pt"); ap.add_argument("--stride", type=int, default=10); ap.add_argument("--noise", type=float, default=0.5e-3); ap.add_argument("--offset", type=float, default=5e-3)
    ap.add_argument("--recover-sigma", type=float, nargs="*", default=None, help="복귀 증강 σ(rad) 관절별 6개 (예: 0.01 0.01 0.01 0.02 0.02 0.08). 없으면 끔")
    a = ap.parse_args(); dev = "cuda" if torch.cuda.is_available() else "cpu"; torch.manual_seed(0)
    (ctx, qabs, tgt, adv), (vctx, vqabs, vtgt, vadv), n_eps = load_dataset(stride=a.stride)
    print(f"episodes={n_eps} train windows={len(ctx)} val windows={len(vctx)}", flush=True)
    X = torch.tensor(feats(ctx, qabs)); Y = torch.tensor(tgt.reshape(len(tgt), -1)); A = torch.tensor(adv)
    VX = torch.tensor(feats(vctx, vqabs)).to(dev); VY = torch.tensor(vtgt.reshape(len(vtgt), -1)).to(dev); VA = torch.tensor(vadv).to(dev)
    ctx_mean, ctx_std = X.mean(0), X.std(0) + 1e-6; x_std = Y.std(0) + 1e-6
    pol = FlowPolicy().to(dev); advm = Advisor().to(dev)
    pol.ctx_mean.copy_(ctx_mean); pol.ctx_std.copy_(ctx_std); pol.x_std.copy_(x_std); advm.ctx_mean.copy_(ctx_mean); advm.ctx_std.copy_(ctx_std); advm.adv_scale.fill_(float(A.mean()))
    rec_sig = torch.tensor(a.recover_sigma, device=dev) if a.recover_sigma else None
    opt = torch.optim.AdamW(list(pol.parameters()) + list(advm.parameters()), lr=a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, a.epochs); X, Y, A = X.to(dev), Y.to(dev), A.to(dev); t0 = time.time()
    for ep in range(a.epochs):
        perm = torch.randperm(len(X), device=dev); tot = 0.0; tot_a = 0.0; nb = 0
        for i in range(0, len(X), a.batch):
            b = perm[i:i + a.batch]; xb = X[b].clone(); yb = Y[b]
            # 문맥 증강: 실측 잡음 + 이력 전체 상수 오프셋 (접합 뒤 '살짝 어긋난 상태' 에서도 매끈하게 잇도록)
            xb[:, :180] += a.noise * torch.randn_like(xb[:, :180]) + (a.offset * (2 * torch.rand(len(b), 1, device=dev) - 1)) * torch.randn(len(b), 180, device=dev).sign() * 0.3
            # 복귀 증강(폐루프 드리프트 대책): 현재 자세를 δ 만큼 흔든다 → 이력 차분은 −δ, 절대 q 는 +δ, 목표(GT 미래 − 현재)는 −δ.
            # 즉 "GT 에서 벗어난 자세에서는 GT 로 돌아가라" 를 가르친다. 손목(5번)은 카메라·용접 지표에 안 보이는 방향이라 σ 를 크게.
            if rec_sig is not None:
                delta = torch.randn(len(b), 6, device=dev) * rec_sig * torch.rand(len(b), 1, device=dev)
                xb[:, :180] -= delta.repeat(1, 30); xb[:, 180:186] += delta; yb = yb - delta.repeat(1, 50)
            cn = (xb - ctx_mean.to(dev)) / ctx_std.to(dev); x1 = yb / x_std.to(dev); x0 = torch.randn_like(x1); t = torch.rand(len(b), 1, device=dev)
            xt = (1 - t) * x0 + t * x1; v = pol(xt, t, cn); loss = ((v - (x1 - x0)) ** 2).mean()
            pa = advm(xb); loss_a = ((torch.log1p(pa / advm.adv_scale) - torch.log1p(A[b] / advm.adv_scale)) ** 2).mean()
            opt.zero_grad(); (loss + loss_a).backward(); opt.step(); tot += loss.item(); tot_a += loss_a.item(); nb += 1
        sched.step()
        if ep % max(1, a.epochs // 6) == max(1, a.epochs // 6) - 1 or ep == a.epochs - 1:
            pol.eval(); advm.eval()
            with torch.no_grad():
                pred = pol.sample(VX[:4096], steps=8); err = (pred - VY[:4096]).abs().view(-1, 50, 6)
                e_all = err.max(2).values.max(1).values; e300 = err[:, int(300 / HOR_DT) - 1].max(1).values
                # 기준선: 등속 외삽 (문맥 마지막 10ms 속도)
                v = (VX[:4096, 174:180] - VX[:4096, 168:174]) / 0.01; ts = torch.arange(1, 51, device=dev).float()[None, :, None] * HOR_DT * 1e-3
                base = (v[:, None, :] * ts); berr = (base - VY[:4096].view(-1, 50, 6)).abs(); b_all = berr.max(2).values.max(1).values; b300 = berr[:, int(300 / HOR_DT) - 1].max(1).values
                pa = advm(VX); a_err = (pa - VA).abs().mean(); a_base = (VA - VA.mean()).abs().mean()
            print(f"ep {ep+1:3d} fm_loss={tot/nb:.4f} adv_loss={tot_a/nb:.4f} | val cont err 1s: policy mean={e_all.mean()*1e3:.2f} p95={e_all.quantile(.95)*1e3:.2f} mrad vs extrap {b_all.mean()*1e3:.2f}/{b_all.quantile(.95)*1e3:.2f} | 300ms: {e300.mean()*1e3:.2f} vs {b300.mean()*1e3:.2f} mrad | advisor mae={a_err*1e3:.2f} mrad (predict-mean baseline {a_base*1e3:.2f}, label mean {VA.mean()*1e3:.2f}) | {time.time()-t0:.0f}s", flush=True)
            pol.train(); advm.train()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    torch.save({"policy": pol.state_dict(), "advisor": advm.state_dict(), "meta": {"epochs": a.epochs, "train_windows": len(X), "val_windows": len(VX), "episodes": n_eps, "adv_label_mean": float(A.mean()), "adv_label_p90": float(A.quantile(.9))}}, a.out)
    print("saved", a.out)


if __name__ == "__main__":
    main()
