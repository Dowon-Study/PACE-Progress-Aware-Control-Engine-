"""가짜 AI 공급자: GT 에피소드의 관절 궤적을 청크로 잘라 Q_AI 큐에 보낸다. 장애 주입 포함.

흐름: (1) 현재 로봇 상태를 읽어 에피소드 시작 자세까지 접근 청크(transit)를 보냄 → (2) 에피소드 궤적을 주기적으로 청크로 발행.
모든 시각은 time.monotonic_ns() (제어기와 같은 CLOCK_MONOTONIC).
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.msg import Msg, MsgType, Space, Supplier, EventCode, RobotState   # noqa: E402
from pace_py.shm import Shm, Q_AI, Q_OPERATOR                                    # noqa: E402

NS = 1_000_000_000


class FaultPlan:
    """장애 스케줄. 시각은 에피소드 시작 기준 초."""
    def __init__(self, a):
        self.delay_ms = a.delay_ms; self.delay_jitter_ms = a.delay_jitter_ms
        self.dropout = (a.dropout_from, a.dropout_to) if a.dropout_from is not None else None
        self.outliers = []   # [(t, kind)]
        if a.outlier_at:
            for tok in str(a.outlier_at).split(","):
                if ":" in tok: t_, k_ = tok.split(":"); self.outliers.append((float(t_), k_))
                else: self.outliers.append((float(tok), a.outlier_kind))
        self.stale_at = a.stale_at; self.lowconf_at = a.lowconf_at
        self.burst_at = a.burst_at; self.burst_ms = a.burst_ms
        self.rng = np.random.default_rng(a.seed)

    def extra_delay_s(self, t_ep):
        d = self.delay_ms + (self.rng.uniform(0, self.delay_jitter_ms) if self.delay_jitter_ms else 0.0)
        if self.burst_at is not None and self.burst_at <= t_ep < self.burst_at + 1.0: d += self.burst_ms
        return d / 1000.0

    def dropped(self, t_ep):
        return self.dropout is not None and self.dropout[0] <= t_ep < self.dropout[1]

    def fire(self, key, at, t_ep):
        """원샷: at 을 지난 첫 발행에서 한 번만 True (지연으로 발행이 건너뛰어도 반드시 발사)."""
        if at is None or t_ep < at: return False
        fired = getattr(self, "_fired", set())
        if key in fired: return False
        fired.add(key); self._fired = fired; return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", type=int, required=True); ap.add_argument("--data", default="data/gt"); ap.add_argument("--shm", default="/pace")
    ap.add_argument("--period", type=float, default=0.10, help="발행 주기 s"); ap.add_argument("--horizon", type=float, default=1.0, help="청크 길이 s")
    ap.add_argument("--dt", type=float, default=0.02, help="청크 점 간격 s"); ap.add_argument("--target-latency", type=float, default=0.06, help="미래 겨냥 s")
    ap.add_argument("--validity", type=float, default=None, help="유효기간 s (기본 horizon+0.5)"); ap.add_argument("--confidence", type=float, default=0.9)
    ap.add_argument("--transit", type=float, default=3.0, help="시작 자세까지 접근 시간 s"); ap.add_argument("--speed-scale", type=float, default=None, help="PARAM 속도 배율 1회 발행")
    # 장애
    ap.add_argument("--delay-ms", type=float, default=0.0); ap.add_argument("--delay-jitter-ms", type=float, default=0.0)
    ap.add_argument("--burst-at", type=float, default=None); ap.add_argument("--burst-ms", type=float, default=500.0)
    ap.add_argument("--dropout-from", type=float, default=None); ap.add_argument("--dropout-to", type=float, default=None)
    ap.add_argument("--outlier-at", type=str, default=None, help="예: 6 또는 5:nan,8:range,11:fast"); ap.add_argument("--outlier-kind", choices=["jump", "nan", "range", "fast"], default="jump")
    ap.add_argument("--stale-at", type=float, default=None, help="이 시각의 청크를 시퀀스 역전으로 보냄"); ap.add_argument("--lowconf-at", type=float, default=None)
    ap.add_argument("--msg", choices=["path", "path_s"], default="path", help="에피소드 구간 청크 형식"); ap.add_argument("--estop-at", type=float, default=None); ap.add_argument("--open-loop", action="store_true", help="로봇 상태 무시, 벽시계 기준 청크 (상태를 안 보는 AI 의 최악 사례)"); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    plan = FaultPlan(a)
    ep = np.load(Path(a.data) / f"ep_{a.episode:04d}.npz"); q_gt = ep["q"].astype(np.float64); t_gt = ep["t"].astype(np.float64); s_gt = ep["s"].astype(np.float64)
    dof = q_gt.shape[1]; T_ep = t_gt[-1]
    sh = Shm(a.shm)
    # 현재 상태
    st = RobotState()
    for _ in range(200):
        if sh.read_state(st) and st.dof == dof: break
        time.sleep(0.01)
    else:
        print("state 없음 (pace_control 이 떠 있어야 함)"); return 1
    q_now = np.array(st.q[:dof])
    validity = a.validity if a.validity is not None else a.horizon + 0.5
    n_pts = int(round(a.horizon / a.dt)) + 1
    seq = 0

    def send_path_s(i_start: int, conf: float, t_gen_ns=None, seq_override=None):
        """PATH_S: i_start 부터 horizon 초에 해당하는 진행도 구간을 n_pts 로 균등 샘플 (속도 = 에피소드 명목 속도)"""
        nonlocal seq
        seq += 1; sq = seq if seq_override is None else seq_override
        i_end = min(len(q_all) - 1, i_start + int(a.horizon / 0.001))
        s0, s1 = float(s_mono[i_start]), float(s_mono[i_end])
        if s1 - s0 < 1e-6: s1 = s0 + 1e-6
        ss = np.linspace(s0, s1, n_pts)
        idx = np.clip(np.searchsorted(s_mono, ss), 0, len(q_all) - 1)
        pts = q_all[idx]
        sdot = (s1 - s0) / max(1e-3, (i_end - i_start) * 0.001)
        m = Msg().init(MsgType.PATH_S, Supplier.AI, sq, t_gen_ns or time.monotonic_ns(), (t_gen_ns or time.monotonic_ns()) + int(validity * NS), conf)
        m.hdr.space, m.hdr.dof, m.hdr.n_points = Space.JOINT, dof, n_pts
        m.body.path_s.s0, m.body.path_s.s1, m.body.path_s.ref_id, m.body.path_s.sdot_nominal = s0, s1, 1, float(sdot)
        for i, row in enumerate(pts):
            for j in range(dof): m.body.path_s.pts[i][j] = float(row[j])
        return sh.push_msg(Q_AI, m), sq

    def send_path(q_pts: np.ndarray, t0_ns: int, conf: float, seq_override=None, t_gen_ns=None):
        nonlocal seq
        seq += 1; s = seq if seq_override is None else seq_override
        m = Msg().init(MsgType.PATH, Supplier.AI, s, t_gen_ns or time.monotonic_ns(), t0_ns + int(validity * NS), conf)
        m.hdr.space, m.hdr.dof, m.hdr.n_points = Space.JOINT, dof, len(q_pts)
        m.body.path.t0_ns, m.body.path.dt_ns = t0_ns, int(a.dt * NS)
        for i, row in enumerate(q_pts):
            for j in range(dof): m.body.path.pts[i][j] = float(row[j])
        ok = sh.push_msg(Q_AI, m)
        return ok, s

    # 통합 타임라인: [접근 transit (현재 → 에피소드 시작, 코사인 블렌딩)] + [에피소드 GT]. 1kHz 샘플.
    n_tr = int(a.transit / 0.001)
    tau = np.linspace(0, 1, n_tr, endpoint=False); blend = 0.5 - 0.5 * np.cos(np.pi * tau)
    q_tr = q_now[None, :] + blend[:, None] * (q_gt[0] - q_now)[None, :]
    q_all = np.vstack([q_tr, q_gt]); T_all = len(q_all) * 0.001
    s_all = np.concatenate([np.linspace(-0.001 * n_tr, -0.001, n_tr), s_gt])   # 접근 구간은 음수 s 로 단조화
    # PATH_S 용: s 가 평평한 구간(리드인 정지)도 단조 증가하도록 미세 기울기 추가
    s_mono = np.maximum.accumulate(s_all + np.arange(len(s_all)) * 1e-9)
    t0_ns_base = time.monotonic_ns() + int(0.05 * NS)        # 타임라인 원점 (제어기 시계)
    if a.speed_scale is not None:
        p = Msg().init(MsgType.PARAM, Supplier.OPERATOR, 1, time.monotonic_ns(), time.monotonic_ns() + 3600 * NS, 1.0); p.body.param.speed_scale = a.speed_scale; sh.push_msg(Q_OPERATOR, p)

    # 매 period 마다 "지금 + target_latency" 시각부터 horizon 만큼의 청크를 보냄 (접근 구간도 같은 방식 → 검증기가 똑같이 검사)
    sent = dropped = 0; estop_done = False; k_pub = 0; last_i = 0; last_t0_ns = 0; resyncs = 0
    while True:
        now_ns = time.monotonic_ns(); t_tl = (now_ns - t0_ns_base) / NS          # 타임라인 시각
        t_ep = t_tl - a.transit                                                   # 에피소드 기준 시각 (장애 스케줄용, 접근 중은 음수)
        if last_i >= len(q_all) - 2: break                                   # 로봇이 끝에 닿음 (상태 인지)
        if (a.open_loop and t_tl > T_all + 0.3) or t_tl > 3 * T_all + 10: break   # open-loop 는 벽시계 기준, 그 외는 안전 상한
        if a.estop_at is not None and t_ep >= a.estop_at and not estop_done:
            e = Msg().init(MsgType.EVENT, Supplier.OPERATOR, 2, now_ns, now_ns + 10 * NS, 1.0); e.body.event.code = EventCode.ESTOP; sh.push_msg(Q_OPERATOR, e); estop_done = True
            print(f"[fake] ESTOP at t_ep={t_ep:.2f}s", flush=True)
        if t_ep >= 0 and plan.dropped(t_ep):
            dropped += 1
        else:
            delay = plan.extra_delay_s(t_ep) if t_ep >= 0 else 0.0
            if a.open_loop or not sh.read_state(st):
                i_start = int(round((t_tl + a.target_latency) / 0.001))
            else:
                # 진행 위치 추정: 직전 청크의 시간 장부로 예측한 인덱스 근방 [-300, +100] 에서 실측 관절에 가장 가까운 점 (항상 국소 재동기화 →
                # 로봇이 느려지거나(페이싱) 멈추면 그 자리에서 다음 청크 시작. 큰 불일치(정지 후 등)는 넓은 창으로 재탐색)
                q_m = np.array(st.q[:dof])
                i_pred = int(np.clip(last_i + round((now_ns - last_t0_ns) / 1e6), 0, len(q_all) - 1)) if last_t0_ns else int(round(t_tl / 0.001))
                def nearest(lo, hi):
                    dist = np.abs(q_all[lo:hi] - q_m).max(axis=1); cand = np.where(dist <= dist.min() + 1e-4)[0]
                    k = cand[np.argmin(np.abs(cand + lo - i_pred))]          # 동률(정지 구간)이면 예측 인덱스에 가장 가까운 점
                    return lo + int(k), float(dist.min())
                i_est, dmin = nearest(max(0, i_pred - 300), min(len(q_all), i_pred + 100))
                if dmin > 0.03:
                    i_est, dmin = nearest(max(0, i_pred - 3000), min(len(q_all), i_pred + 200)); resyncs += 1
                i_start = i_est + int(round(a.target_latency / 0.001))
            last_i = i_start; last_t0_ns = t0_ns_base + int((t_tl + a.target_latency) * NS)
            # 청크 시각은 항상 벽시계 "지금 + 겨냥 지연" (AI 가 현재 관측 기준으로 "60ms 뒤부터 이 점들" 이라고 말하는 것)
            t0 = t_tl + a.target_latency
            idx = np.clip(i_start + np.round(np.arange(n_pts) * a.dt / 0.001).astype(int), 0, len(q_all) - 1)
            pts = q_all[idx].copy(); conf = a.confidence; kind = None
            for oi, (ot, ok_) in enumerate(plan.outliers):
                if t_ep >= 0 and plan.fire(f"out{oi}", ot, t_ep): kind = ok_
            if kind:
                if kind == "jump": pts[n_pts // 2:, 0] += 1.0
                elif kind == "nan": pts[3, 2] = np.nan
                elif kind == "range": pts[:, 1] = 7.0
                elif kind == "fast": pts[5, 0] += 0.3
            if t_ep >= 0 and plan.fire("lowconf", a.lowconf_at, t_ep): conf = 0.05; kind = "lowconf"
            seq_override = None
            if t_ep >= 0 and plan.fire("stale", a.stale_at, t_ep): seq_override = 1; kind = "stale"
            t_gen_ns = now_ns
            if delay > 0: time.sleep(delay)
            if a.msg == "path_s" and t_ep >= 0 and not kind:
                ok, s = send_path_s(i_start, conf, t_gen_ns, seq_override)
            else:
                ok, s = send_path(pts, t0_ns_base + int(t0 * NS), conf, seq_override, t_gen_ns)
            sent += 1
            if a.verbose or kind: print(f"[fake] t_ep={t_ep:6.2f}s seq={s} delay={delay*1e3:.0f}ms {kind or ''} ok={ok}", flush=True)
        k_pub += 1
        next_ns = t0_ns_base + int(k_pub * a.period * NS)
        rem = (next_ns - time.monotonic_ns()) / NS
        if rem > 0: time.sleep(rem)
    T_ep = T_all - a.transit
    print(f"[fake] done: sent={sent} dropped={dropped} resyncs={resyncs} T={T_ep:.1f}s")
    sh.close(); return 0


if __name__ == "__main__":
    sys.exit(main())
