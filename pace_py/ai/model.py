"""ACT 급 경량 모델: 카메라 2개 CNN 토큰 + 관절 토큰 → Transformer 인코더 → 50개 쿼리 디코더 → 1s 관절 청크(차분). 조언기 머리 = 인코더 풀링 → 300ms 앞 이탈.
(CVAE 생략: 용접 추종은 단봉 분포라 L1 회귀로 충분. 파라미터 ~5M, GPU 추론 수 ms)"""
import torch, torch.nn as nn
HOR_N, DOF, CTX_N = 50, 6, 30


def conv_block(cin, cout, s): return nn.Sequential(nn.Conv2d(cin, cout, 3, s, 1), nn.BatchNorm2d(cout), nn.ReLU(inplace=True))


class CamEncoder(nn.Module):
    def __init__(self, d=256, n_tokens=80):
        super().__init__()
        self.net = nn.Sequential(conv_block(3, 32, 2), conv_block(32, 64, 2), conv_block(64, 128, 2), conv_block(128, d, 2))   # /16
        self.pos = nn.Parameter(torch.zeros(1, n_tokens, d)); nn.init.normal_(self.pos, std=0.02); self.d = d
    def forward(self, x):                       # x [B,3,H,W] float 0..1
        f = self.net(x); tok = f.flatten(2).transpose(1, 2)          # [B,HW,C]
        return tok + self.pos[:, :tok.shape[1]]


class ActLite(nn.Module):
    def __init__(self, d=256, heads=8, enc_layers=3, dec_layers=3):
        super().__init__()
        self.enc_tool = CamEncoder(d, 8 * 10); self.enc_scene = CamEncoder(d, 7 * 7)   # 120×160/16, 112×112/16
        self.q_proj = nn.Linear(DOF + CTX_N * DOF, d)                                  # 현재 q + 최근 300ms 이력(차분): 영상 한 장에는 속도·위상이 없다
        self.encoder = nn.TransformerEncoder(nn.TransformerEncoderLayer(d, heads, 4 * d, 0.1, batch_first=True), enc_layers)
        self.queries = nn.Parameter(torch.randn(1, HOR_N, d) * 0.02)
        self.decoder = nn.TransformerDecoder(nn.TransformerDecoderLayer(d, heads, 4 * d, 0.1, batch_first=True), dec_layers)
        self.head = nn.Linear(d, DOF); self.adv_head = nn.Sequential(nn.Linear(d, 128), nn.ReLU(), nn.Linear(128, 1))
        self.register_buffer("q_mean", torch.zeros(DOF)); self.register_buffer("q_std", torch.ones(DOF)); self.register_buffer("y_std", torch.ones(HOR_N, DOF)); self.register_buffer("adv_scale", torch.ones(1)); self.register_buffer("ctx_std", torch.ones(1))
        self.img_mean = nn.Parameter(torch.tensor([0.5, 0.5, 0.5]).view(1, 3, 1, 1), requires_grad=False)

    def forward(self, tool_u8, scene_u8, q, ctx):   # uint8 [B,H,W,3] ×2, q [B,6] (rad), ctx [B,30,6] (과거 300ms q − 현재 q) → (청크 차분 [B,50,6] rad, 조언 [B] rad)
        t = (tool_u8.permute(0, 3, 1, 2).float() / 255.0 - self.img_mean); s = (scene_u8.permute(0, 3, 1, 2).float() / 255.0 - self.img_mean)
        qn = torch.cat([(q - self.q_mean) / self.q_std, (ctx / self.ctx_std).flatten(1)], 1)
        tok = torch.cat([self.q_proj(qn)[:, None], self.enc_tool(t), self.enc_scene(s)], 1)
        mem = self.encoder(tok); out = self.decoder(self.queries.expand(q.shape[0], -1, -1), mem)
        y = self.head(out) * self.y_std; adv = torch.nn.functional.softplus(self.adv_head(mem[:, 0]).squeeze(1)) * self.adv_scale
        return y, adv
