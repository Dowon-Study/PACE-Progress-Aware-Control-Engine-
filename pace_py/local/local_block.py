"""로컬 감독 계층 블록 (비실시간 프로세스, CPU 추론): docs/IDEA_FIXED.md 7절.
 - 공유메모리의 로봇 상태를 100Hz 로 읽어 최근 300ms 문맥을 만들고, period 마다 연속 정책으로 앞 1.0s 청크를 생성해
   PATH(supplier=LOCAL) 로 보낸다. 제어기는 AI 참조가 바닥났을 때만 이 청크를 채택한다 (사다리 ②).
 - 감속 조언기: 300ms 앞 이탈 예측 → PARAM(supplier=LOCAL) 속도 제안 (제어기에서 상한으로만 작용).
온라인 학습(선택): --online-ckpt 파일이 갱신되면(online_train 이 원자적으로 교체) 추론과 추론 사이에 새 가중치로 바꿔 끼운다.
  바꾸기 전 점검: 값이 모두 유한한가, 현재 입력에서 기존 모델과의 1 s 출력 차이가 --online-max-dev 이하인가. 실패하면 기존 모델 유지.
사용: python -m pace_py.local.local_block --ckpt pace_py/local/ckpt/local_mlp_rec.pt [--period 0.1] [--online-ckpt <current.pt>] [--verbose]"""
import argparse, os, sys, time
from pathlib import Path
import numpy as np, torch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.msg import Msg, MsgType, Space, Supplier, RobotState   # noqa: E402
from pace_py.shm import Shm, Q_LOCAL                               # noqa: E402
from pace_py.local.model import FlowPolicy, Advisor, Regressor      # noqa: E402
from pace_py.local.data import CTX_N, CTX_DT, HOR_N, HOR_DT          # noqa: E402
from pace_py.local.features import context                          # noqa: E402
NS = 1_000_000_000


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--ckpt", default="pace_py/local/ckpt/local_mlp_rec.pt"); ap.add_argument("--shm", default="/pace")
    ap.add_argument("--period", type=float, default=0.10); ap.add_argument("--steps", type=int, default=8); ap.add_argument("--confidence", type=float, default=0.8)
    ap.add_argument("--advisor", action="store_true", help="감속 조언기 PARAM 발행 (기본 꺼짐: 관절 이력만으로는 300ms 앞 이탈 예측이 평균 예측보다 낫지 않음 → 10단계에서 영상 문맥과 함께)"); ap.add_argument("--adv-eps", type=float, default=None, help="이탈 허용 (rad). 기본: 학습 라벨 p90"); ap.add_argument("--adv-vmin", type=float, default=0.5)
    ap.add_argument("--threads", type=int, default=2); ap.add_argument("--kind", choices=["fm", "mlp"], default="mlp", help="연속 정책 종류: 회귀 MLP(기본, 9c 절제에서 폐루프 가장 안정) | flow matching (--ckpt pace_py/local/ckpt/local_block.pt)"); ap.add_argument("--still-mrad", type=float, default=0.5, help="최근 300ms 관절 변화가 이보다 작으면 정지 유지 청크"); ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--online-ckpt", default=None, help="온라인 학습 배포 파일 (online_train --deploy). 갱신되면 바꿔 끼움 (mlp 만)"); ap.add_argument("--online-check", type=float, default=1.0); ap.add_argument("--online-max-dev", type=float, default=0.3, help="교체 점검: 기존 모델 대비 1 s 출력 차이 상한 [rad]")
    a = ap.parse_args(); torch.set_num_threads(a.threads)
    ck = torch.load(a.ckpt, map_location="cpu")
    if a.kind == "mlp": pol = Regressor(); pol.load_state_dict(ck["policy_mlp"]); adv = None; eps = 0.0
    else: pol = FlowPolicy(); pol.load_state_dict(ck["policy"]); adv = Advisor(); adv.load_state_dict(ck["advisor"]); adv.eval(); eps = a.adv_eps if a.adv_eps is not None else ck["meta"]["adv_label_p90"]
    pol.eval()
    sh = Shm(a.shm); st = RobotState(); hist = []   # (t_ns, q)
    seq = 0; sent = 0; t_next = time.monotonic(); last_infer_ms = 0.0; t_start = time.monotonic(); n_adv = 0
    on_mtime = 0.0; on_next = time.monotonic(); on_ver = 0; on_swaps = on_refused = 0; last_x = None
    while True:
        now = time.monotonic()
        if sh.read_state(st) and st.dof > 0:
            q = np.array(st.q[:st.dof], np.float32); hist.append((time.monotonic_ns(), q)); hist = hist[-400:]
        if a.online_ckpt and a.kind == "mlp" and now >= on_next:             # 온라인 학습 가중치 교체 (추론 사이, 이 프로세스 안에서만)
            on_next = now + a.online_check
            try:
                mt = os.stat(a.online_ckpt).st_mtime
                if mt != on_mtime:
                    on_mtime = mt; ck_new = torch.load(a.online_ckpt, map_location="cpu", weights_only=True); new = Regressor(); new.load_state_dict(ck_new["policy_mlp"]); new.eval(); ver = int(ck_new.get("meta", {}).get("version", 0))
                    ok = all(torch.isfinite(v).all() for v in new.state_dict().values()); dev_max = 0.0
                    if ok and last_x is not None:
                        with torch.no_grad(): dev_max = float((new(last_x) - pol(last_x)).abs().max()); ok = dev_max <= a.online_max_dev
                    if ok and ver != on_ver: pol = new; on_ver = ver; on_swaps += 1; print(f"[local] online swap -> v{ver} (dev {dev_max*1e3:.1f} mrad)", flush=True)
                    elif not ok: on_refused += 1; print(f"[local] online swap REFUSED v{ver} (finite={ok}, dev {dev_max*1e3:.1f} mrad)", flush=True)
            except (FileNotFoundError, RuntimeError, KeyError, EOFError) as e:
                pass
        if now >= t_next:
            t_next += a.period
            if len(hist) >= 2 and (hist[-1][0] - hist[0][0]) >= CTX_N * CTX_DT * 1e6:
                t_now = hist[-1][0]; q_now = hist[-1][1]; dof = len(q_now)
                ts = np.array([h[0] for h in hist], np.int64); qs = np.stack([h[1] for h in hist])
                xv, ctx, _ = context(ts, qs, len(ts) - 1)                                         # 가장 가까운 샘플 (폴링 ≤5ms 오차) — 온라인 학습과 같은 함수
                x = torch.tensor(xv[None]); last_x = x
                t0 = time.perf_counter(); sug = 1.0
                with torch.no_grad():
                    d = pol.sample(x, steps=a.steps)[0].view(HOR_N, dof).numpy(); dev = float(adv(x)[0]) if (a.advisor and adv is not None) else 0.0
                last_infer_ms = (time.perf_counter() - t0) * 1e3
                # 평활: 흐름 샘플은 점 단위 잡음(가속도 20 rad/s² 급)이 있어 검증기 RANGE_ACC 에 걸린다. 용접 연속 동작은 1초 지평에서 매끈하므로
                # 관절별로 원점을 지나는 3차 다항식 d(τ)=aτ+bτ²+cτ³ 을 최소제곱 적합해 쓴다 (잡음 제거 + 속도 연속)
                tau = HOR_DT * 1e-3 * np.arange(1, HOR_N + 1); A = np.stack([tau, tau ** 2, tau ** 3], 1)
                coef = np.linalg.lstsq(A, d, rcond=None)[0]; d = A @ coef
                if np.abs(ctx).max() < a.still_mrad * 1e-3: d[:] = 0.0                            # 운동 게이트: 이력에 움직임이 없으면 '이어 그릴 것' 도 없다 (작업 끝에서 밀고 나가지 않도록)
                pts = np.vstack([q_now, q_now + d])                                               # 첫 점 = 현재 q
                seq += 1; m = Msg().init(MsgType.PATH, Supplier.LOCAL, seq, time.monotonic_ns(), t_now + int((HOR_N * HOR_DT * 1e-3 + 0.5) * NS), a.confidence)
                m.hdr.space, m.hdr.dof, m.hdr.n_points = Space.JOINT, dof, len(pts); m.body.path.t0_ns, m.body.path.dt_ns = t_now, int(HOR_DT * 1e6)
                for i, row in enumerate(pts):
                    for j in range(dof): m.body.path.pts[i][j] = float(row[j])
                if sh.push_msg(Q_LOCAL, m): sent += 1
                if a.advisor:
                    sug = float(np.clip(eps / max(dev, 1e-6), a.adv_vmin, 1.0))
                    p = Msg().init(MsgType.PARAM, Supplier.LOCAL, seq, time.monotonic_ns(), time.monotonic_ns() + int(0.5 * NS), 1.0); p.body.param.speed_scale = sug
                    if sh.push_msg(Q_LOCAL, p): n_adv += 1
                if a.verbose and seq % 20 == 0: print(f"[local] t={now-t_start:5.1f}s seq={seq} infer={last_infer_ms:.2f}ms |ctx|max={np.abs(ctx).max()*1e3:.2f}mrad |d(1s)|max={np.abs(d).max()*1e3:.1f}mrad adv_dev={dev*1e3:.2f}mrad sug={sug if a.advisor else 1.0:.2f}", flush=True)
        time.sleep(0.005)


if __name__ == "__main__":
    main()
