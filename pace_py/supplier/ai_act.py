"""실제 AI 공급자 (10단계): 학습한 ACT급 모델이 카메라 영상(장면 XML 로 렌더, 실기에서는 카메라 입력) + 관절 상태로 1s 액션 청크를 만들어 PATH(supplier=AI) 로 보낸다.
GT 를 전혀 보지 않는다. 상태 인지(매 주기 현재 q 와 영상에서 다시 계획). 지연 주입·끊김·조언(PARAM) 옵션은 fake_ai 와 같은 뜻.
사용: python -m pace_py.supplier.ai_act --model pace/models/ur5e/_gen_ep0000.xml [--ckpt pace_py/ai/ckpt/act_lite.pt] [--period 0.1] [--delay-ms 100 --delay-jitter-ms 50] [--dropout-from 8 --dropout-to 12] [--advisor] [--duration 40]"""
import argparse, collections, sys, threading, time
from pathlib import Path
import numpy as np, torch, mujoco
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.msg import Msg, MsgType, Space, Supplier, RobotState   # noqa: E402
from pace_py.shm import Shm, Q_AI, Q_LOCAL                          # noqa: E402
from pace_py.ai.model import ActLite, HOR_N                          # noqa: E402
from pace_py.ai.data import scene_small, HOR_DT, CTX_N, CTX_DT        # noqa: E402
NS = 1_000_000_000


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--model", required=True); ap.add_argument("--ckpt", default="pace_py/ai/ckpt/act_lite.pt"); ap.add_argument("--shm", default="/pace")
    ap.add_argument("--period", type=float, default=0.10); ap.add_argument("--target-latency", type=float, default=0.0, help="청크 t0 = 촬영 시각 + 20ms + 이 값"); ap.add_argument("--validity", type=float, default=1.5); ap.add_argument("--confidence", type=float, default=0.9)
    ap.add_argument("--delay-ms", type=float, default=0.0); ap.add_argument("--delay-jitter-ms", type=float, default=0.0); ap.add_argument("--dropout-from", type=float, default=None); ap.add_argument("--dropout-to", type=float, default=None)
    ap.add_argument("--advisor", action="store_true"); ap.add_argument("--adv-eps", type=float, default=None); ap.add_argument("--adv-vmin", type=float, default=0.5)
    ap.add_argument("--duration", type=float, default=60.0); ap.add_argument("--ai-csv", default=None, help="AI 계층 로그 (validation/templates/control_loop_log_format.md §2): seq,t_capture_ns,t_infer_start_ns,t_infer_end_ns,t_publish_ns,valid_until_ns,confidence"); ap.add_argument("--max-delta", type=float, default=0.08, help="AI 래퍼 출력 가드: 1s 청크의 관절 변위 상한(rad). GT 1s 변위 p99 ≈ 0.03"); ap.add_argument("--device", default="cuda"); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(); rng = np.random.default_rng(a.seed)
    ck = torch.load(a.ckpt, map_location=a.device); net = ActLite().to(a.device); net.load_state_dict(ck["model"]); net.eval(); eps = a.adv_eps if a.adv_eps is not None else ck["meta"]["adv_label_p90"]
    m = mujoco.MjModel.from_xml_path(a.model); d = mujoco.MjData(m); r_tool = mujoco.Renderer(m, 120, 160); r_scene = mujoco.Renderer(m, 224, 224)
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):   # 워밍업 (CUDA 커널 적재): 첫 청크 지연을 줄인다
        for _ in range(3): net(torch.zeros(1, 120, 160, 3, dtype=torch.uint8, device=a.device), torch.zeros(1, 112, 112, 3, dtype=torch.uint8, device=a.device), torch.zeros(1, 6, device=a.device), torch.zeros(1, 30, 6, device=a.device))
    torch.cuda.synchronize()
    ai_rows = []
    sh = Shm(a.shm); st = RobotState(); hist = []; seq = 0; sent = dropped = 0; t_start = time.monotonic(); infer_ms = collections.deque(maxlen=200)
    pending = []   # (send_at, msg, qid) 지연 주입

    def flush():
        nonlocal sent
        now = time.monotonic(); keep = []
        for s_at, msg, qid in pending:
            if now >= s_at: sh.push_msg(qid, msg); sent += 1
            else: keep.append((s_at, msg, qid))
        pending[:] = keep

    t_next = time.monotonic()
    while time.monotonic() - t_start < a.duration:
        flush(); now = time.monotonic()
        if now < t_next: time.sleep(min(0.002, t_next - now)); continue
        t_next += a.period
        if not (sh.read_state(st) and st.dof > 0): continue
        q = np.array(st.q[:st.dof], np.float32); t_cap = time.monotonic_ns(); hist.append((t_cap, q)); hist = hist[-400:]
        ts = np.array([h[0] for h in hist], float); qs = np.stack([h[1] for h in hist]); want = t_cap - CTX_DT * 1e6 * np.arange(CTX_N, 0, -1)
        ctx = (np.stack([qs[np.argmin(np.abs(ts - w))] for w in want]) - q).astype(np.float32)            # 100ms 주기라 이력은 10ms 격자에 가장 가까운 샘플 (초기엔 반복)
        d.qpos[:len(q)] = q; mujoco.mj_forward(m, d)
        r_tool.update_scene(d, camera="cam_tool"); tool = r_tool.render(); r_scene.update_scene(d, camera="cam_scene"); scene = scene_small(r_scene.render())
        t0 = time.perf_counter(); t_inf0 = time.monotonic_ns()
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
            y, adv = net(torch.from_numpy(tool[None]).to(a.device), torch.from_numpy(scene[None]).to(a.device), torch.from_numpy(q[None]).to(a.device), torch.from_numpy(ctx[None]).to(a.device))
        dlt = y[0].float().cpu().numpy(); dev = float(adv[0]); infer_ms.append((time.perf_counter() - t0) * 1e3); t_inf1 = time.monotonic_ns()
        t_rel = now - t_start
        if a.dropout_from is not None and a.dropout_from <= t_rel < a.dropout_to: dropped += 1; continue
        # 평활: 회귀 출력의 점 단위 잡음이 검증기 RANGE_ACC(가속도 한계)에 걸린다. 1s 지평 용접 동작은 매끈하므로 원점을 지나는 3차 다항식 적합 (9단계와 동일)
        tau = HOR_DT * 1e-3 * np.arange(1, HOR_N + 1); Amat = np.stack([tau, tau ** 2, tau ** 3], 1); dlt = Amat @ np.linalg.lstsq(Amat, dlt, rcond=None)[0]
        dlt = np.clip(dlt, -a.max_delta, a.max_delta)                                 # 출력 가드 (검증기 RANGE 와 별개의 AI 래퍼 상한)
        pts = q[None] + dlt                                                           # 50점, 촬영 시각 + 20ms 부터
        seq += 1; t_gen = t_cap   # E2E 기준 = 촬영 시각 (추론 시간 포함)
        msg = Msg().init(MsgType.PATH, Supplier.AI, seq, t_gen, t_cap + int((HOR_N * HOR_DT * 1e-3 + a.validity) * NS), a.confidence)
        msg.hdr.space, msg.hdr.dof, msg.hdr.n_points = Space.JOINT, len(q), HOR_N; msg.body.path.t0_ns = t_cap + int((HOR_DT * 1e-3 + a.target_latency) * NS); msg.body.path.dt_ns = int(HOR_DT * 1e6)
        for i in range(HOR_N):
            for j in range(len(q)): msg.body.path.pts[i][j] = float(pts[i][j])
        delay = max(0.0, a.delay_ms + a.delay_jitter_ms * rng.uniform(-1, 1)) * 1e-3
        pending.append((time.monotonic() + delay, msg, Q_AI))
        if a.ai_csv: ai_rows.append((seq, t_cap, t_inf0, t_inf1, time.monotonic_ns() + int(delay * NS), t_cap + int((HOR_N * HOR_DT * 1e-3 + a.validity) * NS), a.confidence))
        if a.advisor:
            sug = float(np.clip(eps / max(dev, 1e-6), a.adv_vmin, 1.0)); p = Msg().init(MsgType.PARAM, Supplier.LOCAL, seq, t_gen, t_gen + int(0.5 * NS), 1.0); p.body.param.speed_scale = sug; pending.append((time.monotonic() + delay, p, Q_LOCAL))
        if a.verbose and seq <= 12: print(f"[ai] seq={seq} q={np.round(q,3).tolist()} |ctx|max={np.abs(ctx).max()*1e3:.2f}mrad |d(1s)|max={np.abs(dlt).max()*1e3:.1f}mrad first={np.round(dlt[0]*1e3,2).tolist()}", flush=True)
        if a.verbose and seq % 20 == 0: print(f"[ai] t={t_rel:5.1f}s seq={seq} infer={np.mean(infer_ms):.1f}ms |d(1s)|max={np.abs(dlt).max()*1e3:.1f}mrad adv_dev={dev*1e3:.2f}mrad", flush=True)
    flush(); print(f"[ai] done: sent={sent} dropped={dropped} infer p50={np.median(infer_ms):.1f}ms max={np.max(infer_ms):.1f}ms", flush=True)
    if a.ai_csv:
        import csv as _csv, subprocess as _sp
        with open(a.ai_csv, "w", newline="") as f:
            f.write(f"# kernel={_sp.run(['uname','-r'],capture_output=True,text=True).stdout.strip()}\n# load=ai-{a.device}\n# cmd={' '.join(sys.argv)}\n")
            w = _csv.writer(f); w.writerow(["seq", "t_capture_ns", "t_infer_start_ns", "t_infer_end_ns", "t_publish_ns", "valid_until_ns", "confidence"]); w.writerows(ai_rows)
        print(f"[ai] ai log: {a.ai_csv} ({len(ai_rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
