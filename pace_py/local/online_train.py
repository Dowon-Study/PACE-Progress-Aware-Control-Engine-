"""보조 궤적 생성기(회귀 MLP) 온라인 학습 — 보조 판단 계층의 비실시간 프로세스 (격리 코어 밖, 기본 CPU 0-3).

정답 = AI 계층의 액션 중 '검증기를 통과해 실제로 실행된' 궤적.
  AI 큐는 제어기만 꺼내 쓰는 단일 소비자 링이라 엿보지 않는다. 대신 제어기가 10 ms 마다 쓰는 계약(Contract)의
  실행 상태(모드·공급자·감시 판정·정지 단계·누적 거부 수·누적 비정상 틱 수)로, 1.3 s 창(문맥 300 ms + 지평 1 s) 동안
  'NORMAL · 공급자 AI · 감시 OK · 정지 0 · 거부 0' 이 한 틱도 깨지지 않은 구간만 골라 학습 쌍으로 쓴다.
  (누적 카운터 n_unclean 이 창 시작 전과 끝 뒤에서 같으면 그 사이 비정상 틱이 0 이었다는 뜻) → 어떤 AI 모델이 붙어도 그대로 동작.

갱신 (update_every 초마다): 도전자 모델을 실시간 버퍼 + 오프라인 재생 버퍼 섞어 작은 학습률로 K 스텝
  · 복귀 증강·잡음 증강은 오프라인 학습(train_mlp)과 같게 유지 (AI 없을 때 쓰이는 상황과 배우는 상황의 차이를 줄임)
  · 초기 가중치 쪽으로 L2 당김 (L2-SP) — 예전 형상을 잊지 않도록
교체 (챔피언/도전자): 도전자가 최근 실시간 검증 데이터에서 챔피언보다 margin 이상 낫고, 오프라인 재생 검증이 tol 이상 나빠지지 않을 때만 배포.
  배포 = 임시 파일에 쓴 뒤 os.replace (원자적). local_block 이 파일 갱신을 감지해 추론 사이에 바꿔 끼운다. 이전 버전은 versions/ 에 보관.
  도전자가 크게 나빠지면 챔피언으로 되돌린다.
1 ms 루프에는 아무 영향이 없다: 공유메모리는 읽기만 하고(seqlock), 학습 모델 출력은 여전히 검증기·안전 감시기를 거친다.

사용: taskset -c 0-3 python -m pace_py.local.online_train --shm /pace --base pace_py/local/ckpt/local_mlp_rec.pt \\
        --deploy docs/benchmarks/runs/<name>.online/current.pt [--replay pace_py/local/ckpt/replay_ideal.npz] [--state <state.pt>]"""
import argparse, collections, copy, json, math, os, signal, sys, threading, time
from pathlib import Path
import numpy as np, torch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.msg import RobotState, Contract, Supplier, Mode           # noqa: E402
from pace_py.shm import Shm                                          # noqa: E402
from pace_py.local.model import Regressor                            # noqa: E402
from pace_py.local.features import context, target                    # noqa: E402

NS = 1_000_000_000
CTX_SPAN_NS, HOR_SPAN_NS = 300_000_000, 1_000_000_000
REC_SIGMA = [0.01, 0.01, 0.01, 0.02, 0.02, 0.08]      # 복귀 증강 σ (rad), 오프라인 local_mlp_rec 와 같음


def augment(xb, yb, noise=0.5e-3, offset=5e-3, rec_sig=None):
    """오프라인 train_mlp 와 같은 증강: 이력 잡음 + 이력 오프셋 + 복귀 증강(현재 자세를 흔들고 이력·정답을 일관되게 보정)."""
    xb = xb.clone(); yb = yb.clone(); n = len(xb)
    xb[:, :180] += noise * torch.randn_like(xb[:, :180]) + (offset * (2 * torch.rand(n, 1) - 1)) * torch.randn(n, 180).sign() * 0.3
    if rec_sig is not None:
        delta = torch.randn(n, 6) * rec_sig * torch.rand(n, 1); xb[:, :180] -= delta.repeat(1, 30); xb[:, 180:186] += delta; yb = yb - delta.repeat(1, 50)
    return xb, yb


@torch.no_grad()
def evaluate(m, X, Y):
    """정규화 L1 (학습 손실과 같은 척도) 과 1 s 지평 관절 최대 오차 평균 [mrad]."""
    if X is None or len(X) == 0: return float("nan"), float("nan")
    p = m(X); l1 = float(((p - Y).abs() / m.x_std).mean()); e1s = float((p - Y).abs().view(-1, 50, 6).max(2).values.max(1).values.mean() * 1e3)
    return l1, e1s


class Collector:
    """공유메모리에서 상태·계약을 읽어 깨끗한 창만 학습 쌍으로 만든다."""
    def __init__(self, shm, period_s=0.1, still_mrad=0.5, max_gap_ns=8_000_000):
        self.sh = shm; self.st = RobotState(); self.ct = Contract(); self.period_ns = int(period_s * NS); self.still = still_mrad * 1e-3; self.max_gap = max_gap_ns
        self.ts = collections.deque(maxlen=4000); self.qs = collections.deque(maxlen=4000)          # 상태 (읽은 시각, q)
        self.cs = collections.deque(maxlen=400)                                                     # 계약 스냅샷 (t_ns, mode, supplier, n_unclean, hal_fault_seen)
        self.next_anchor = None; self.last_ct = -1; self.fault_since = 0
        self.stats = collections.Counter(); self.lock = threading.Lock(); self.running = False

    def start(self, period_s=0.002):
        """학습 스텝(수백 ms)이 상태 읽기를 막지 않도록 별도 스레드에서 폴링 (torch 연산은 GIL 을 놓는다)."""
        self.running = True
        def loop():
            while self.running: self.poll(); time.sleep(period_s)
        threading.Thread(target=loop, daemon=True).start()

    def stop(self): self.running = False

    def poll(self):
        now = time.monotonic_ns()
        if self.sh.read_state(self.st) and self.st.dof > 0:
            if self.st.hal_fault: self.fault_since = now
            with self.lock: self.ts.append(now); self.qs.append(np.array(self.st.q[: self.st.dof], np.float32))
        if self.sh.read_contract(self.ct) and self.ct.t_ns != self.last_ct:
            self.last_ct = self.ct.t_ns
            with self.lock: self.cs.append((int(self.ct.t_ns), int(self.ct.mode), int(self.ct.supplier), int(self.ct.n_unclean)))

    def harvest(self):
        """지평 1 s 가 다 지난 기준 시각(now − 1.05 s)에서 100 ms 마다 창 하나씩. 반환 (x, y) 목록."""
        out = []; now = time.monotonic_ns()
        with self.lock:
            if len(self.ts) < 50 or len(self.cs) < 3: return out
            ts = np.fromiter(self.ts, np.int64, len(self.ts)); qs = np.stack(self.qs); cs = list(self.cs)
        if self.next_anchor is None: self.next_anchor = now - HOR_SPAN_NS - 50_000_000
        ct_t = np.array([c[0] for c in cs], np.int64)
        while self.next_anchor <= now - HOR_SPAN_NS - 50_000_000:
            ta = self.next_anchor; self.next_anchor += self.period_ns; self.stats["anchors"] += 1
            t0, t1 = ta - CTX_SPAN_NS, ta + HOR_SPAN_NS
            if ts[0] > t0 - 5_000_000 or ts[-1] < t1 + 5_000_000: self.stats["skip_span"] += 1; continue
            i0 = np.searchsorted(ct_t, t0, side="right") - 1; i1 = np.searchsorted(ct_t, t1, side="left")       # 창 시작 직전 · 끝 직후 계약
            if i0 < 0 or i1 >= len(cs): self.stats["skip_contract"] += 1; continue
            c0, c1 = cs[i0], cs[i1]
            if not (c0[1] == Mode.NORMAL and c0[2] == Supplier.AI and c1[1] == Mode.NORMAL and c1[2] == Supplier.AI and c0[3] == c1[3]):
                self.stats["skip_unclean"] += 1; continue
            if self.fault_since and self.fault_since >= t0: self.stats["skip_fault"] += 1; continue
            i_now = int(np.clip(np.searchsorted(ts, ta), 1, len(ts) - 1)); i_now = i_now - 1 if abs(ts[i_now - 1] - ta) <= abs(ts[i_now] - ta) else i_now
            x, ctx, g0 = context(ts, qs, i_now); y, g1 = target(ts, qs, i_now)
            if max(g0, g1) > self.max_gap: self.stats["skip_gap"] += 1; continue
            if np.abs(ctx).max() < self.still and np.abs(y).max() < 2 * self.still: self.stats["skip_still"] += 1; continue
            if len(x) != 186 or len(y) != 300: self.stats["skip_dof"] += 1; continue
            out.append((x, y)); self.stats["samples"] += 1
        return out


def save_atomic(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True); tmp = path.with_suffix(path.suffix + ".tmp"); torch.save(obj, tmp); os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shm", default="/pace"); ap.add_argument("--base", default="pace_py/local/ckpt/local_mlp_rec.pt"); ap.add_argument("--deploy", required=True)
    ap.add_argument("--replay", default=None, help="오프라인 재생 버퍼 npz (export_replay 로 생성). 없으면 L2-SP 만으로 잊음 방지"); ap.add_argument("--state", default=None, help="실시간 버퍼·챔피언을 저장/복원 (에피소드를 넘어 누적)")
    ap.add_argument("--log", default=None); ap.add_argument("--duration", type=float, default=0.0, help="0 이면 SIGTERM 까지")
    ap.add_argument("--update-every", type=float, default=2.0); ap.add_argument("--steps", type=int, default=20, help="갱신당 최대 스텝 (실제 = min(steps, 실시간 버퍼 한 바퀴))"); ap.add_argument("--batch", type=int, default=64); ap.add_argument("--lr", type=float, default=1e-5, help="Adam 학습률. 1e-4 는 첫 스텝부터 재생 검증이 40%% 넘게 나빠져(가중치 전체가 lr 만큼 움직임) 미세조정에 너무 큼")
    ap.add_argument("--l2sp", type=float, default=1e-4); ap.add_argument("--min-live", type=int, default=48); ap.add_argument("--min-val", type=int, default=12); ap.add_argument("--val-every", type=int, default=5)
    ap.add_argument("--live-max", type=int, default=20000); ap.add_argument("--margin", type=float, default=0.02, help="배포 조건: 실시간 검증 L1 이 이 비율 이상 개선"); ap.add_argument("--tol", type=float, default=0.05, help="배포 조건: 재생 검증 L1 악화 허용 비율")
    ap.add_argument("--keep", type=int, default=5); ap.add_argument("--no-recover", action="store_true"); ap.add_argument("--threads", type=int, default=2)
    a = ap.parse_args(); torch.set_num_threads(a.threads); torch.manual_seed(0)
    deploy = Path(a.deploy); vers = deploy.parent / "versions"; logf = open(a.log, "a") if a.log else None
    def log(rec):
        line = json.dumps(rec, ensure_ascii=False); print("[online] " + line, flush=True)
        if logf: logf.write(line + "\n"); logf.flush()

    base = torch.load(a.base, map_location="cpu", weights_only=True)
    champ = Regressor(); champ.load_state_dict(base["policy_mlp"]); live_x, live_y, val_x, val_y = [], [], [], []; version = 0
    if a.state and Path(a.state).exists():
        S = torch.load(a.state, map_location="cpu", weights_only=True); champ.load_state_dict(S["champion"]); version = int(S.get("version", 0))
        live_x, live_y, val_x, val_y = [[r.numpy() for r in S[k]] for k in ("live_x", "live_y", "val_x", "val_y")]
        log({"event": "state_loaded", "version": version, "live": len(live_x), "val": len(val_x)})
    champ.eval(); chall = copy.deepcopy(champ); chall.train()
    theta0 = [p.detach().clone() for p in champ.parameters()]   # L2-SP 기준 = 시작 시 챔피언
    opt = torch.optim.Adam(chall.parameters(), lr=a.lr)
    RX = RY = RVX = RVY = None
    if a.replay and Path(a.replay).exists():
        R = np.load(a.replay); n = len(R["X"]); nv = max(1, n // 10)
        RX, RY = torch.tensor(R["X"][nv:], dtype=torch.float32), torch.tensor(R["Y"][nv:], dtype=torch.float32); RVX, RVY = torch.tensor(R["X"][:nv], dtype=torch.float32), torch.tensor(R["Y"][:nv], dtype=torch.float32)
    rec_sig = None if a.no_recover else torch.tensor(REC_SIGMA)
    save_atomic({"policy_mlp": champ.state_dict(), "meta": {"version": version, "source": str(a.state if version else a.base)}}, deploy)   # 시작 시 챔피언을 바로 배포 (복원한 경우 그 버전)
    log({"event": "start", "base": a.base, "deploy": str(deploy), "replay": len(RX) if RX is not None else 0, "replay_val": len(RVX) if RVX is not None else 0, "recover_aug": rec_sig is not None})

    sh = Shm(a.shm); col = Collector(sh); col.start(); stop = {"flag": False}
    for sgn in (signal.SIGTERM, signal.SIGINT): signal.signal(sgn, lambda *_: stop.__setitem__("flag", True))
    t_start = time.monotonic(); t_next = t_start + a.update_every; n_updates = n_deploy = n_rollback = 0; k_seen = len(live_x) + len(val_x)

    def finish():
        col.stop()
        if a.state:
            T = lambda L, d: torch.tensor(np.array(L), dtype=torch.float32) if len(L) else torch.zeros(0, d)       # 텐서만 저장 → weights_only 로 안전하게 복원
            save_atomic({"champion": champ.state_dict(), "version": version, "live_x": T(live_x[-a.live_max:], 186), "live_y": T(live_y[-a.live_max:], 300), "val_x": T(val_x[-2000:], 186), "val_y": T(val_y[-2000:], 300)}, Path(a.state))
        log({"event": "done", "elapsed_s": round(time.monotonic() - t_start, 1), "version": version, "updates": n_updates, "deploys": n_deploy, "rollbacks": n_rollback, "live": len(live_x), "val": len(val_x), "collector": dict(col.stats)})

    while not stop["flag"] and not (a.duration and time.monotonic() - t_start > a.duration):
        for x, y in col.harvest():
            k_seen += 1
            if k_seen % a.val_every == 0: val_x.append(x); val_y.append(y); val_x = val_x[-2000:]; val_y = val_y[-2000:]
            else: live_x.append(x); live_y.append(y); live_x = live_x[-a.live_max:]; live_y = live_y[-a.live_max:]
        if time.monotonic() >= t_next:
            t_next += a.update_every
            if len(live_x) < a.min_live: continue
            LX = torch.tensor(np.array(live_x)); LY = torch.tensor(np.array(live_y)); t0 = time.perf_counter(); tot = 0.0
            n_steps = max(2, min(a.steps, math.ceil(len(LX) / a.batch)))      # 갱신당 실시간 데이터 약 한 바퀴 → 적은 데이터에 과적합 방지
            for _ in range(n_steps):
                b = torch.randint(0, len(LX), (min(a.batch, len(LX)),)); xb, yb = LX[b], LY[b]
                if RX is not None: r = torch.randint(0, len(RX), (a.batch,)); xb = torch.cat([xb, RX[r]]); yb = torch.cat([yb, RY[r]])
                xb, yb = augment(xb, yb, rec_sig=rec_sig)
                loss = ((chall(xb) - yb).abs() / chall.x_std).mean() + a.l2sp * sum(((p - p0) ** 2).sum() for p, p0 in zip(chall.parameters(), theta0))
                opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item()
            n_updates += 1; chall.eval()
            VX = torch.tensor(np.array(val_x)) if val_x else None; VY = torch.tensor(np.array(val_y)) if val_y else None
            ch_live, ch_live_e = evaluate(champ, VX, VY); cl_live, cl_live_e = evaluate(chall, VX, VY)
            ch_rep, ch_rep_e = evaluate(champ, RVX, RVY); cl_rep, cl_rep_e = evaluate(chall, RVX, RVY)
            rep_ok = (RVX is None) or (cl_rep <= ch_rep * (1 + a.tol)); decision = "hold"
            if len(val_x) >= a.min_val and cl_live <= ch_live * (1 - a.margin) and rep_ok:
                champ = copy.deepcopy(chall); champ.eval(); version += 1; n_deploy += 1; decision = "deploy"
                meta = {"version": version, "t_s": round(time.monotonic() - t_start, 2), "live": len(live_x), "val": len(val_x), "val_l1": cl_live, "val_err_1s_mrad": cl_live_e, "replay_l1": cl_rep, "base": str(a.base)}
                obj = {"policy_mlp": champ.state_dict(), "meta": meta}; save_atomic(obj, deploy); save_atomic(obj, vers / f"v{version:04d}.pt")
                for old in sorted(vers.glob("v*.pt"))[: -a.keep]: old.unlink(missing_ok=True)
            elif len(val_x) >= a.min_val and cl_live > ch_live * 1.25 and not rep_ok:
                chall = copy.deepcopy(champ); opt = torch.optim.Adam(chall.parameters(), lr=a.lr); n_rollback += 1; decision = "rollback"
            chall.train()
            log({"event": "update", "t_s": round(time.monotonic() - t_start, 2), "n": n_updates, "decision": decision, "version": version, "live": len(live_x), "val": len(val_x), "steps": n_steps, "loss": round(tot / n_steps, 5),
                 "val_l1": {"champ": round(ch_live, 5), "chall": round(cl_live, 5)}, "val_err_1s_mrad": {"champ": round(ch_live_e, 2), "chall": round(cl_live_e, 2)},
                 "replay_l1": {"champ": round(ch_rep, 5), "chall": round(cl_rep, 5)} if RVX is not None else None, "train_ms": round((time.perf_counter() - t0) * 1e3, 1)})
        time.sleep(0.01)
    finish()


if __name__ == "__main__":
    main()
