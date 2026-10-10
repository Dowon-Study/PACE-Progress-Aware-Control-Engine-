"""작은 눈: 토치 근접 카메라 영상에서 용접선을 고전 영상처리로 검출해 CORRECTION(가로 오프셋, 각도)을 보낸다.

렌더: 공유메모리의 로봇 상태(q)로 MuJoCo 장면을 그려 cam_tool 영상을 얻는다 (제어 PC 의 카메라 입력에 해당). 프레임은 공유 프레임 버퍼에도 기록 (AI 계층용).
검출: 그레이 → 어두운 선 마스크(적응 임계) → 중앙 ROI 에서 선 픽셀 → cv2.fitLine → 화면 중심(= 팁 투영) 기준 부호 있는 가로 거리(px) 와 각도.
보정: 픽셀 → m 선형 계수는 calibrate_eye.py 가 데이터셋 nominal 라벨로 맞춘 JSON (없으면 기하 추정값).
부호 규약: CORRECTION.lat = 기준 목표에 더해야 실제 선에 닿는 양 (= 선이 툴 왼쪽(+n)에 있으면 +).
"""
from __future__ import annotations
import argparse, signal, struct, json, os, sys, time
from pathlib import Path
import numpy as np
os.environ.setdefault("MUJOCO_GL", "egl")
import cv2, mujoco
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.msg import Msg, MsgType, Space, Supplier, RobotState   # noqa: E402
from pace_py.shm import Shm, Q_EYE, Frame                             # noqa: E402

NS = 1_000_000_000
W, H = 160, 120


def torch_mask_from_frames(imgs: np.ndarray, frac=0.9, thresh=100) -> np.ndarray:
    """카메라가 토치에 고정 → 토치는 모든 프레임에서 같은 자리에 어둡다. 프레임 묶음에서 '거의 항상 어두운' 픽셀 = 토치 마스크."""
    g = np.stack([cv2.cvtColor(im, cv2.COLOR_RGB2GRAY) for im in imgs]).astype(np.float32)
    m = ((g < thresh).mean(0) > frac).astype(np.uint8)
    return cv2.dilate(m, np.ones((5, 5), np.uint8))


def tip_from_mask(mask: np.ndarray):
    """토치 마스크의 꼭대기(가장 위 행의 중앙) = 용접 지점의 화면 투영."""
    rows = np.where(mask.any(1))[0]
    if len(rows) == 0: return (mask.shape[1] // 2, mask.shape[0] // 2)
    r = rows[0]; cols = np.where(mask[r])[0]
    return (float(cols.mean()), float(r))


def detect_seam(img_rgb: np.ndarray, torch_mask: np.ndarray, tip, dark_thresh=110, roi_up=30, roi_down=20, roi_half_w=60):
    """반환 (d_px 꼭대기→선 부호 있는 수직거리, angle_rad, inlier_ratio, ok). 선 방향은 화면 위쪽(진행 방향)으로 정규화, 법선 n=(-vy,vx)."""
    g = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY); h, w = g.shape
    r, gch, b = img_rgb[..., 0].astype(np.int16), img_rgb[..., 1].astype(np.int16), img_rgb[..., 2].astype(np.int16)
    blue = (b > r + 25)                                                          # 파란 바닥
    cand = (g < dark_thresh) & (torch_mask == 0) & (~blue)
    tx, ty = tip; y0, y1 = max(0, int(ty - roi_up)), min(h, int(ty + roi_down)); x0, x1 = max(0, int(tx - roi_half_w)), min(w, int(tx + roi_half_w))
    roi = np.zeros_like(cand); roi[y0:y1, x0:x1] = True; cand &= roi
    cand[:2, :] = cand[-2:, :] = False; cand[:, :2] = cand[:, -2:] = False
    # 두꺼운 덩어리(그림자 띠, 토치 끝) 제거: 5×5 침식에서 살아남는 픽셀 주변은 선이 아님 (선 폭 2~4px)
    c8 = cand.astype(np.uint8); thick = cv2.dilate(cv2.erode(c8, np.ones((5, 5), np.uint8)), np.ones((7, 7), np.uint8))
    cand &= thick == 0
    # 용접선은 꼭대기(용접 지점)를 지난다 → 꼭대기 행에서 멀리 떨어진 성분(그림자 경계 등)은 버림
    ncomp, lab, stats, cent = cv2.connectedComponentsWithStats(cand.astype(np.uint8), 8)
    keep = np.zeros_like(cand)
    for i in range(1, ncomp):
        x, y, ww, hh, area = stats[i]
        if area < 4: continue
        if not (y <= ty + roi_down and y + hh >= ty - roi_up + 4): continue    # 성분이 꼭대기 근처 띠와 겹쳐야 함
        keep[lab == i] = True
    cand = keep
    # 열별 중앙값으로 선 중심을 1점/열 로 줄이고(두께 영향 제거), 꼭대기 주변 ±fit_half_w 열만으로 2차 곡선을 Huber 로 적합 (곡선 용접선 대응)
    fit_half_w = 30
    cols = np.arange(max(x0, int(tx - fit_half_w)), min(x1, int(tx + fit_half_w)))
    xs_c, ys_c = [], []
    for x in cols:
        yy = np.nonzero(cand[:, x])[0]
        if len(yy): xs_c.append(x); ys_c.append(float(np.median(yy)))
    if len(xs_c) < 12: return 0.0, 0.0, 0.0, False
    X = np.array(xs_c, float) - tx; Y = np.array(ys_c, float); wgt = np.ones_like(X)
    for _ in range(4):                                                           # IRLS (Huber, δ=1.5px)
        A = np.stack([X * X, X, np.ones_like(X)], 1) * wgt[:, None]; coef = np.linalg.lstsq(A, Y * wgt, rcond=None)[0]
        res = Y - (coef[0] * X * X + coef[1] * X + coef[2]); wgt = np.minimum(1.0, 1.5 / np.maximum(np.abs(res), 1e-6))
    inl = np.abs(res) < 1.5
    if inl.sum() >= 8 and inl.mean() < 0.95:                                    # 인라이어로 재적합
        A = np.stack([X[inl] ** 2, X[inl], np.ones(inl.sum())], 1); coef = np.linalg.lstsq(A, Y[inl], rcond=None)[0]
        res = Y - (coef[0] * X * X + coef[1] * X + coef[2]); inl = np.abs(res) < 1.5
    d = float(coef[2] - ty); slope = float(coef[1])                              # 꼭대기 열에서의 세로 오프셋과 접선 기울기
    ok = inl.mean() >= 0.6 and inl.sum() >= 12 and abs(d) <= 25 and abs(slope) <= 0.7
    return d, float(np.arctan(slope)), float(inl.mean()), bool(ok)


def load_refpath(path):
    """RPTH 바이너리(make_refpath) → (pos n×3, tan n×3). 눈이 '현재 툴이 교시 경로에서 얼마나 벗어나 있는지'를 셈하는 데 쓴다."""
    b = open(path, "rb").read(); magic, n = struct.unpack_from("<II", b, 0); assert magic == 0x48545052
    a = np.frombuffer(b, np.float32, count=7 * n, offset=24).reshape(n, 7); return a[:, 1:4].copy(), a[:, 4:7].copy()


class Eye:
    def __init__(self, model_xml, calib_path=None, refpath=None, median_n=7, rate_m=0.0002, gate_m=0.003):
        self.m = mujoco.MjModel.from_xml_path(model_xml); self.d = mujoco.MjData(self.m); self.r = mujoco.Renderer(self.m, H, W)
        self.sid = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_SITE, "tool")
        self.ref = load_refpath(refpath) if refpath else None; self.median_n = median_n; self.hist = []   # (valid, lat_abs) 최근 프레임
        self.est = None; self.rate_m = rate_m; self.gate_m = gate_m; self.gated = 0; self.last_applied = None; self.last_t = 0.0; self.motion_mps = 0.010
        self.calib = {"a_m_per_px": 0.00092, "b_m": 0.0, "sign": 1.0}
        if calib_path and Path(calib_path).exists(): self.calib.update(json.load(open(calib_path)))
        self.frames = []; self.mask = None; self.tip = (W / 2, H / 2)
        if "torch_mask" in self.calib: self.mask = np.array(self.calib["torch_mask"], np.uint8); self.tip = tuple(self.calib["tip"])

    def render(self, q):
        self.d.qpos[:len(q)] = q; mujoco.mj_forward(self.m, self.d); self.r.update_scene(self.d, camera="cam_tool"); return self.r.render()

    def applied_lateral(self):
        """현재 툴 위치를 교시 경로에 사영해 이미 적용된 가로 오프셋 (p - ref)·n 을 구한다 (n = ẑ×t). 경로가 없으면 0."""
        if self.ref is None: return 0.0
        pos, tan = self.ref; p = self.d.site_xpos[self.sid]
        seg = pos[1:] - pos[:-1]; L2 = np.maximum((seg * seg).sum(1), 1e-12)
        u = np.clip(((p - pos[:-1]) * seg).sum(1) / L2, 0.0, 1.0); foot = pos[:-1] + u[:, None] * seg
        i = int(np.argmin(((p - foot) ** 2).sum(1))); t = seg[i] / np.sqrt(L2[i]); n = np.array([-t[1], t[0], 0.0]); n /= max(np.linalg.norm(n), 1e-9)
        return float(np.dot(p - foot[i], n))

    def measure(self, q):
        img = self.render(q)
        if self.mask is None:                                   # 첫 2초: 토치 마스크 학습 (항상 어두운 픽셀)
            self.frames.append(img)
            if len(self.frames) >= 60: self.mask = torch_mask_from_frames(np.stack(self.frames)); self.tip = tip_from_mask(self.mask)
            return img, 0.0, 0.0, 0.0, False, 0.0
        u, ang, inl, ok = detect_seam(img, self.mask, self.tip)
        lat_rel = self.calib["sign"] * (self.calib["a_m_per_px"] * u + self.calib["b_m"]) if ok else 0.0
        # 영상이 주는 것은 '지금 툴 기준' 잔차. 제어기는 '교시 경로 기준' 오프셋을 기대하므로 이미 적용된 오프셋을 더해 절대량으로 만든다.
        # 프레임 단위 검출이 ±3px 로 튀므로(렌더 앨리어싱) 절대량의 최근 N 프레임 중앙값을 보낸다 (N=7 → 3개까지 이상치 흡수).
        applied = self.applied_lateral(); now = time.monotonic()
        # 운동 게이트: 툴이 가로로 빠르게 움직이는 동안(> motion_mps)은 카메라 자세가 흔들려(IK 자세 수렴 지연 ~1°) 영상 측정이 틀어진다 → 그 프레임은 쓰지 않음
        if self.last_applied is not None and now > self.last_t and abs(applied - self.last_applied) / (now - self.last_t) > self.motion_mps: ok = False
        self.last_applied, self.last_t = applied, now
        lat_abs = applied + lat_rel
        # 이상치 게이트: 추정이 자리잡은 뒤에는 현재 추정에서 gate_m 이상 벗어난 프레임은 가짜 선(그림자 경계 등)으로 보고 버림
        if ok and self.est is not None and abs(lat_abs - self.est) > self.gate_m:
            ok = False; self.gated += 1
            if self.gated >= 15: self.est = None; self.hist = []; self.gated = 0          # 0.5초 연속으로 게이트에 걸리면 추정이 틀린 것 → 재초기화
        elif ok: self.gated = 0
        self.hist.append((ok, lat_abs)); self.hist = self.hist[-self.median_n:]
        vals = [v for o, v in self.hist if o]
        if len(vals) < (self.median_n + 1) // 2: return img, u, ang, inl, False, (self.est if self.est is not None else 0.0)
        med = float(np.median(vals))
        # 변화율 제한: 고정구 오차는 느리게 변하는 양(≤ 수 mm/s). 추정은 현재 적용값(처음엔 0)에서 출발해 프레임당 rate_m 까지만 따라간다 → 제어기에 계단 입력을 주지 않음
        if self.est is None: self.est = applied
        self.est = self.est + float(np.clip(med - self.est, -self.rate_m, self.rate_m))
        return img, u, ang, inl, True, self.est


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--model", required=True); ap.add_argument("--calib", default="pace_py/eye/calib.json"); ap.add_argument("--rate", type=float, default=30.0)
    ap.add_argument("--shm", default="/pace"); ap.add_argument("--min-inlier", type=float, default=0.6); ap.add_argument("--dropout-from", type=float, default=None); ap.add_argument("--dropout-to", type=float, default=None); ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--refpath", default=None, help="교시 경로(RPTH). 주면 이미 적용된 오프셋을 더해 절대 보정량을 보냄"); ap.add_argument("--median", type=int, default=7); ap.add_argument("--rate-mm", type=float, default=0.2, help="프레임당 추정 변화 상한 [mm] (30Hz → 6mm/s)"); ap.add_argument("--gate-mm", type=float, default=3.0)
    a = ap.parse_args()
    eye = Eye(a.model, a.calib, a.refpath, a.median, a.rate_mm * 1e-3, a.gate_mm * 1e-3); sh = Shm(a.shm); st = RobotState(); fr = Frame(); seq = 0; t_start = time.monotonic(); sent = fails = 0
    period = 1.0 / a.rate
    def _fin(*_): print(f"[eye] done: sent={sent} fails={fails} rate={sent/max(sent+fails,1):.2f}", flush=True); sys.exit(0)
    signal.signal(signal.SIGINT, _fin); signal.signal(signal.SIGTERM, _fin)
    while True:
        t0 = time.monotonic(); t_rel = t0 - t_start
        if sh.read_state(st) and st.dof > 0:
            q = np.array(st.q[:st.dof]); img, u, ang, inl, ok, lat = eye.measure(q)
            fr.t_ns = time.monotonic_ns(); fr.seq = seq; fr.width, fr.height, fr.channels, fr.camera_id = W, H, 3, 1
            buf = np.ascontiguousarray(img).tobytes(); fr.data[:len(buf)] = buf; sh.write_frame(fr)
            dropped = a.dropout_from is not None and a.dropout_from <= t_rel < a.dropout_to
            if ok and inl >= a.min_inlier and not dropped:
                seq += 1
                m = Msg().init(MsgType.CORRECTION, Supplier.EYE, seq, fr.t_ns, fr.t_ns + int(0.5 * NS), float(inl))
                m.hdr.space, m.hdr.dof, m.hdr.n_points = Space.TOOL, 3, 1
                c = m.body.correction; c.by_time = 1; c.t0_ns = fr.t_ns; c.dt_ns = int(period * NS); c.ref_id = 1
                c.pts[0][0], c.pts[0][1], c.pts[0][2], c.pts[0][3] = float(lat), 0.0, float(ang), float(u)
                sh.push_msg(Q_EYE, m); sent += 1
                if a.verbose and seq % 30 == 0: print(f"[eye] t={t_rel:5.1f}s u={u:+6.1f}px lat={lat*1e3:+5.2f}mm ang={np.degrees(ang):+5.1f}deg inl={inl:.2f}", flush=True)
            else: fails += 1
            if a.verbose and (sent + fails) % 150 == 0: print(f"[eye] t={t_rel:5.1f}s sent={sent} fails={fails} applied={eye.applied_lateral()*1e3:+.2f}mm", flush=True)
        dt = time.monotonic() - t0
        if dt < period: time.sleep(period - dt)


if __name__ == "__main__":
    main()
