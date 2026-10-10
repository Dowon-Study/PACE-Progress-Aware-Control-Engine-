"""공정 상태 추론기 (규칙 기반 대리 모델, 11단계): 제어기가 공개하는 계약(속도 배율·진행도)을 읽어 입열 지수 H = 아크출력 / 이동속도 를 일정 범위에 유지한다.
 - 플랫폼이 페이싱/감속으로 느려지면 입열이 늘어 과입열(번스루) 위험 → 아크 출력을 속도에 비례해 낮추는 PARAM(params[0] = 아크 출력 비율)을 보낸다.
 - 속도가 defect_speed 아래로 defect_hold 이상 머물면 EVENT DEFECT(결함 위험) 를 보내 정지 사다리를 태운다 (용접 규칙: 거의 멈춘 채 아크를 유지하면 불량).
학습 모델이 아니라 규칙이며, 실제 공정 상태 추론 모델(용융풀 영상 등)이 들어올 자리를 같은 메시지로 채운다.
사용: python -m pace_py.supplier.process_monitor [--rate 20] [--arc-min 0.3] [--defect-speed 0.15 --defect-hold 2.0] [--duration 45]"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.msg import Msg, MsgType, Supplier, Contract   # noqa: E402
from pace_py.shm import Shm, Q_OPERATOR                     # noqa: E402
NS = 1_000_000_000


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--shm", default="/pace"); ap.add_argument("--rate", type=float, default=20.0); ap.add_argument("--arc-min", type=float, default=0.3)
    ap.add_argument("--defect-speed", type=float, default=0.15); ap.add_argument("--defect-hold", type=float, default=2.0); ap.add_argument("--duration", type=float, default=45.0); ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(); sh = Shm(a.shm); c = Contract(); seq = 0; t0 = time.monotonic(); last_pct = None; low_since = None; defect_sent = False; n_param = 0
    while time.monotonic() - t0 < a.duration:
        time.sleep(1.0 / a.rate)
        if not sh.read_contract(c): continue
        v = max(0.0, min(1.0, float(c.speed_scale)))
        arc = max(a.arc_min, min(1.0, v))                                  # 입열 H ∝ arc / v 를 일정하게: arc = v (하한 arc_min 은 아크 유지 최소 출력)
        pct = int(round(arc * 100))
        if pct != last_pct:
            seq += 1; m = Msg().init(MsgType.PARAM, Supplier.OPERATOR, seq, time.monotonic_ns(), time.monotonic_ns() + 10 * NS, 1.0); m.body.param.speed_scale = -1.0; m.body.param.n_params = 1; m.body.param.params[0] = arc
            if sh.push_msg(Q_OPERATOR, m): n_param += 1; last_pct = pct
            if a.verbose: print(f"[proc] t={time.monotonic()-t0:5.1f}s speed={v:.2f} → arc power {pct}%", flush=True)
        if v < a.defect_speed: low_since = low_since or time.monotonic()
        else: low_since = None
        if low_since and time.monotonic() - low_since > a.defect_hold and not defect_sent:
            seq += 1; e = Msg().init(MsgType.EVENT, Supplier.OPERATOR, seq, time.monotonic_ns(), time.monotonic_ns() + 10 * NS, 1.0); e.body.event.code = 4; sh.push_msg(Q_OPERATOR, e); defect_sent = True
            print(f"[proc] t={time.monotonic()-t0:5.1f}s DEFECT: speed<{a.defect_speed} for {a.defect_hold}s with arc on → EVENT DEFECT", flush=True)
    print(f"[proc] done: param updates={n_param} defect={defect_sent}", flush=True)


if __name__ == "__main__":
    main()
