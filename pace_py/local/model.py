"""로컬 감독 계층 모델 (작음, CPU 추론 ms 급):
 - 연속 정책: 조건부 flow matching. 속도장 v(x_t, t | ctx) 를 MLP 로, x = 1.0s 연속 청크(50×6 차분, 정규화). 추론 = Euler N 스텝.
 - 감속 조언기: 같은 문맥에서 300ms 앞 규칙 외삽 이탈을 회귀 → 속도 제안 = clip(eps / dev, v_min, 1)."""
import torch, torch.nn as nn

CTX_DIM, X_DIM = 30 * 6 + 6, 50 * 6


class FlowPolicy(nn.Module):
    def __init__(self, hidden=512, depth=4):
        super().__init__()
        layers = [nn.Linear(CTX_DIM + X_DIM + 1, hidden), nn.SiLU()]
        for _ in range(depth - 1): layers += [nn.Linear(hidden, hidden), nn.SiLU()]
        layers += [nn.Linear(hidden, X_DIM)]
        self.net = nn.Sequential(*layers)
        self.register_buffer("ctx_mean", torch.zeros(CTX_DIM)); self.register_buffer("ctx_std", torch.ones(CTX_DIM))
        self.register_buffer("x_std", torch.ones(X_DIM))

    def forward(self, x_t, t, ctx):            # x_t [B,X], t [B,1], ctx [B,CTX] (정규화된 값)
        return self.net(torch.cat([ctx, x_t, t], 1))

    @torch.no_grad()
    def sample(self, ctx_raw, steps=8, x0=None):
        ctx = (ctx_raw - self.ctx_mean) / self.ctx_std
        x = torch.zeros(ctx.shape[0], X_DIM, device=ctx.device) if x0 is None else x0
        for k in range(steps):
            t = torch.full((ctx.shape[0], 1), k / steps, device=ctx.device)
            x = x + self(x, t, ctx) / steps
        return x * self.x_std


class Advisor(nn.Module):
    def __init__(self, hidden=256):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(CTX_DIM, hidden), nn.SiLU(), nn.Linear(hidden, hidden), nn.SiLU(), nn.Linear(hidden, 1))
        self.register_buffer("ctx_mean", torch.zeros(CTX_DIM)); self.register_buffer("ctx_std", torch.ones(CTX_DIM))
        self.register_buffer("adv_scale", torch.ones(1))

    def forward(self, ctx_raw):                # → 예측 이탈 [B] (rad)
        ctx = (ctx_raw - self.ctx_mean) / self.ctx_std
        return torch.nn.functional.softplus(self.net(ctx).squeeze(1)) * self.adv_scale


class Regressor(nn.Module):
    """비교용 회귀 MLP: 같은 문맥 → 1s 청크 차분을 직접 회귀 (flow matching 과 같은 크기·입력·출력, 생성 모델 아님)"""
    def __init__(self, hidden=512, depth=4):
        super().__init__()
        layers = [nn.Linear(CTX_DIM, hidden), nn.SiLU()]
        for _ in range(depth - 1): layers += [nn.Linear(hidden, hidden), nn.SiLU()]
        layers += [nn.Linear(hidden, X_DIM)]
        self.net = nn.Sequential(*layers)
        self.register_buffer("ctx_mean", torch.zeros(CTX_DIM)); self.register_buffer("ctx_std", torch.ones(CTX_DIM)); self.register_buffer("x_std", torch.ones(X_DIM))

    def forward(self, ctx_raw): return self.net((ctx_raw - self.ctx_mean) / self.ctx_std) * self.x_std

    @torch.no_grad()
    def sample(self, ctx_raw, steps=None): return self(ctx_raw)
