"""비교용 회귀 MLP 학습 (flow matching 과 같은 데이터·입력·출력). python -m pace_py.local.train_mlp --epochs 300 --out pace_py/local/ckpt/local_mlp.pt"""
import argparse, time
from pathlib import Path
import numpy as np, torch
from pace_py.local.data import load_dataset, HOR_DT
from pace_py.local.model import Regressor
from pace_py.local.train import feats


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--epochs", type=int, default=300); ap.add_argument("--batch", type=int, default=2048); ap.add_argument("--lr", type=float, default=1e-3); ap.add_argument("--out", default="pace_py/local/ckpt/local_mlp.pt")
    ap.add_argument("--noise", type=float, default=0.5e-3); ap.add_argument("--offset", type=float, default=5e-3); ap.add_argument("--recover-sigma", type=float, nargs="*", default=None)
    a = ap.parse_args(); dev = "cuda"; torch.manual_seed(0)
    (ctx, qabs, tgt, adv), (vctx, vqabs, vtgt, vadv), n_eps = load_dataset(stride=10)
    X = torch.tensor(feats(ctx, qabs)).to(dev); Y = torch.tensor(tgt.reshape(len(tgt), -1)).to(dev); VX = torch.tensor(feats(vctx, vqabs)).to(dev); VY = torch.tensor(vtgt.reshape(len(vtgt), -1)).to(dev)
    m = Regressor().to(dev); m.ctx_mean.copy_(X.mean(0)); m.ctx_std.copy_(X.std(0) + 1e-6); m.x_std.copy_(Y.std(0) + 1e-6)
    rec_sig = torch.tensor(a.recover_sigma, device=dev) if a.recover_sigma else None
    opt = torch.optim.AdamW(m.parameters(), lr=a.lr, weight_decay=1e-4); sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, a.epochs); t0 = time.time()
    for ep in range(a.epochs):
        perm = torch.randperm(len(X), device=dev); tot = 0; nb = 0
        for i in range(0, len(X), a.batch):
            b = perm[i:i + a.batch]; xb = X[b].clone(); yb = Y[b]; xb[:, :180] += a.noise * torch.randn_like(xb[:, :180]) + (a.offset * (2 * torch.rand(len(b), 1, device=dev) - 1)) * torch.randn(len(b), 180, device=dev).sign() * 0.3
            if rec_sig is not None:
                delta = torch.randn(len(b), 6, device=dev) * rec_sig * torch.rand(len(b), 1, device=dev); xb[:, :180] -= delta.repeat(1, 30); xb[:, 180:186] += delta; yb = yb - delta.repeat(1, 50)
            loss = ((m(xb) - yb).abs() / m.x_std).mean(); opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item(); nb += 1
        sched.step()
        if ep % 50 == 49 or ep == a.epochs - 1:
            m.eval()
            with torch.no_grad(): e = (m(VX) - VY).abs().view(-1, 50, 6); e_all = e.max(2).values.max(1).values; e300 = e[:, int(300 / HOR_DT) - 1].max(1).values
            print(f"ep {ep+1} l1={tot/nb:.4f} | val 1s mean={e_all.mean()*1e3:.2f} p95={e_all.quantile(.95)*1e3:.2f} mrad | 300ms {e300.mean()*1e3:.2f} mrad | {time.time()-t0:.0f}s", flush=True); m.train()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True); torch.save({"policy_mlp": m.state_dict(), "meta": {"epochs": a.epochs, "val_err_1s_mean_mrad": float(e_all.mean() * 1e3), "val_err_300_mean_mrad": float(e300.mean() * 1e3)}}, a.out); print("saved", a.out)


if __name__ == "__main__":
    main()
