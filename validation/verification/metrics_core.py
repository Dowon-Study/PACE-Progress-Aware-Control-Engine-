"""성능지표 검증 공통 모듈 ("계산기" + 파서 + 지표 함수).

reference/성능지표_정리.pdf 4절("측정은 일기장 3권 → 빼기 → 그림")을 그대로 코드로 옮긴 것.
모든 지표는 아래 세 가지 재료만 쓴다.
  1) stats()            : 숫자 목록 → min / avg / p50 / p99 / p99.9 / max / 기준 초과 개수
  2) parse_cyclictest() : cyclictest -h 출력(히스토그램) → 지연 분포
  3) load_ctrl()        : 제어루프 로그 CSV → 공통 열 이름의 표 (두 포맷 모두 지원)

지원하는 제어루프 로그 포맷
  - "contract" : validation/templates/control_loop_log_format.md 의 약속 포맷
                 (iter, t_expected_ns, t_wake_ns, t_cmd_ns, ai_seq, ai_t_recv_ns, ai_state, ...)
  - "pace"     : 현재 플랫폼(pace_control)이 실제로 내보내는 포맷
                 (tick, t_sched_ns, t_wake_ns, st_*_ns, chunk_seq, chunk_t_gen_ns, mode, reject, ...)
  load_ctrl() 이 자동으로 구분해 공통 열로 바꿔 주므로, 지표 함수는 포맷을 몰라도 된다.

이 파일은 라이브러리다. 실행은 verify.py 로 한다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

PERIOD_NS = 1_000_000          # 제어주기 1ms
JITTER_LIMIT_US = 100.0        # 과제 기준: 지터(최대 지연) ±100μs

# 현재 플랫폼의 mode 번호 → 약속 포맷의 ai_state 이름 (pace_py/msg.py Mode 와 같은 순서)
PACE_MODE_NAMES = {0: "init", 1: "fresh", 2: "pacing", 3: "local", 4: "extrap", 5: "hold", 6: "stop", 7: "recover"}
# 현재 플랫폼의 st_*_ns 단계 열 (metrics_dump.py STAGES 와 같은 순서). st_wake 는 깨어남 지연, 나머지는 실행 단계.
PACE_STAGES = ["wake", "read", "select", "validate", "splice", "pace", "command", "monitor", "write", "log"]
# 현재 플랫폼의 reject 번호 → 사유 이름 (pace/include/pace/state.h PACE_REJ_*). 약속 포맷의 range/time/validity 로도 묶어 준다.
PACE_REJECT_NAMES = {0: "", 1: "HEADER", 2: "RANGE_POS", 3: "RANGE_VEL", 4: "RANGE_ACC", 5: "WORKSPACE", 6: "EXPIRED",
                     7: "SEQ_ORDER", 8: "TOO_OLD", 9: "DEVIATION", 10: "CONFIDENCE", 11: "NO_OVERLAP"}
REJECT_GROUP = {"HEADER": "validity", "RANGE_POS": "range", "RANGE_VEL": "range", "RANGE_ACC": "range", "WORKSPACE": "range",
                "EXPIRED": "time", "SEQ_ORDER": "time", "TOO_OLD": "time", "DEVIATION": "validity", "CONFIDENCE": "validity", "NO_OVERLAP": "validity"}
STATE_ORDER = ["fresh", "pacing", "local", "extrap", "hold", "decel", "stop", "recover", "reject", "init"]


# ──────────────────────────────────────────────────────────────────────────────
# 1) 계산기
# ──────────────────────────────────────────────────────────────────────────────
def stats(values, threshold: float | None = JITTER_LIMIT_US, unit: str = "us") -> dict:
    """숫자 목록 하나 → 요약 한 줄. 모든 지표가 이 함수를 돌려 쓴다.

    threshold 를 주면 '기준 넘은 개수/비율'도 함께 돌려준다 (A2: 100μs, A1: 1000μs 등)."""
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"n": 0, "unit": unit}
    out = {
        "n": int(v.size), "unit": unit,
        "min": float(v.min()), "avg": float(v.mean()), "p50": float(np.percentile(v, 50)),
        "p99": float(np.percentile(v, 99)), "p999": float(np.percentile(v, 99.9)), "max": float(v.max()),
    }
    if threshold is not None:
        over = int((v > threshold).sum())
        out.update({"threshold": float(threshold), "over": over, "over_ratio": over / v.size})
    return out


def stats_from_hist(bins_us, counts, threshold: float | None = JITTER_LIMIT_US, overflow: int = 0) -> dict:
    """히스토그램(값 → 개수)에서 같은 요약을 만든다. cyclictest 출력은 원시 샘플이 아니라 히스토그램이라 이 길을 탄다.
    percentile 은 누적 개수가 p% 를 처음 넘는 구간의 값으로 잡는다 (1μs 해상도)."""
    b = np.asarray(bins_us, dtype=np.float64); c = np.asarray(counts, dtype=np.float64)
    total = c.sum() + overflow
    if total == 0:
        return {"n": 0, "unit": "us"}
    cum = np.cumsum(c)

    def pct(p):
        idx = int(np.searchsorted(cum, p / 100.0 * total, side="left"))
        return float(b[min(idx, len(b) - 1)])

    nz = np.nonzero(c)[0]
    out = {"n": int(total), "unit": "us", "min": float(b[nz[0]]), "avg": float((b * c).sum() / c.sum()),
           "p50": pct(50), "p99": pct(99), "p999": pct(99.9), "max": float(b[nz[-1]]) if overflow == 0 else float("inf"),
           "overflow": int(overflow)}
    if threshold is not None:
        over = int(c[b > threshold].sum()) + overflow
        out.update({"threshold": float(threshold), "over": over, "over_ratio": over / total})
    return out


def fmt_stats(s: dict, digits: int = 1) -> str:
    """요약 dict → 표에 넣을 한 줄 문자열."""
    if s.get("n", 0) == 0:
        return "데이터 없음"
    f = lambda k: ("∞" if s[k] == float("inf") else f"{s[k]:.{digits}f}")
    txt = f"n={s['n']}  min {f('min')} / avg {f('avg')} / p50 {f('p50')} / p99 {f('p99')} / p99.9 {f('p999')} / max {f('max')} {s['unit']}"
    if "over" in s:
        txt += f"  | >{s['threshold']:g}{s['unit']}: {s['over']} ({s['over_ratio']*100:.4f}%)"
    return txt


# ──────────────────────────────────────────────────────────────────────────────
# 2) cyclictest 파서
# ──────────────────────────────────────────────────────────────────────────────
def parse_cyclictest(path) -> dict:
    """cyclictest -h <N> 출력 파일을 읽는다.

    본문: '000003 027460\t027651 ...' → 첫 칸이 지연(μs), 뒤 칸들이 CPU(스레드)별 개수.
    꼬리: '# Min Latencies: 00004 00005 ...' 식의 요약.  -a 4 -t 1 이면 열이 하나다.
    반환: {"bins": [...], "counts": [[cpu0...], ...] (shape [bins, threads]), "min":[], "avg":[], "max":[], "overflow":[], "total":[]}"""
    bins, rows, meta = [], [], {}
    for line in Path(path).read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        if line.startswith("#"):
            m = re.match(r"#\s*(Total|Min Latencies|Avg Latencies|Max Latencies|Histogram Overflows):\s*(.*)", line)
            if m:
                meta[m.group(1)] = [int(x) for x in re.findall(r"\d+", m.group(2))]
            continue
        parts = line.split()
        if parts and parts[0].isdigit():
            bins.append(int(parts[0])); rows.append([int(x) for x in parts[1:]])
    if not rows:
        raise ValueError(f"{path}: cyclictest 히스토그램을 찾지 못함")
    counts = np.array(rows, dtype=np.int64)
    return {"path": str(path), "bins": np.array(bins), "counts": counts, "n_threads": counts.shape[1],
            "min": meta.get("Min Latencies", []), "avg": meta.get("Avg Latencies", []), "max": meta.get("Max Latencies", []),
            "overflow": meta.get("Histogram Overflows", [0] * counts.shape[1]), "total": meta.get("Total", [])}


def cyclictest_stats(ct: dict, thread: int | None = None, threshold=JITTER_LIMIT_US) -> dict:
    """스레드(CPU 열) 하나 또는 전체 합(thread=None → 각 열의 최악값을 쓰기 위해 열별로 계산 후 worst 선택)."""
    if thread is not None:
        ov = ct["overflow"][thread] if thread < len(ct["overflow"]) else 0
        s = stats_from_hist(ct["bins"], ct["counts"][:, thread], threshold, overflow=ov)
        s["thread"] = thread
        if ov > 0 and thread < len(ct["max"]):      # 히스토그램 범위를 넘친 샘플이 있으면 cyclictest 꼬리의 'Max Latencies' 가 진짜 최대
            s["max"] = float(ct["max"][thread]); s["max_source"] = "footer(# Max Latencies)"
        return s
    per = [cyclictest_stats(ct, t, threshold) for t in range(ct["n_threads"])]
    worst = max(per, key=lambda s: (s.get("max", 0), s.get("over", 0)))
    worst = dict(worst); worst["thread"] = f"worst of {ct['n_threads']} (col {worst['thread']})"
    worst["over_threads"] = int(sum(1 for s in per if s.get("over", 0) > 0))
    return worst


# ──────────────────────────────────────────────────────────────────────────────
# 3) 제어루프 로그 로더 (두 포맷 → 공통 열)
# ──────────────────────────────────────────────────────────────────────────────
def read_csv_with_meta(path) -> tuple[pd.DataFrame, dict]:
    """'# key=value' 머리말을 떼어 메타데이터로, 나머지를 표로 읽는다."""
    meta = {}
    with open(path, "r", errors="replace") as f:
        pos = 0
        for line in f:
            if line.startswith("#"):
                if "=" in line:
                    k, v = line[1:].split("=", 1); meta[k.strip()] = v.strip()
                pos += len(line)
            else:
                break
    df = pd.read_csv(path, skiprows=len(meta) if meta else 0, comment="#")
    return df, meta


def detect_format(df: pd.DataFrame) -> str:
    cols = set(df.columns)
    if {"t_sched_ns", "t_wake_ns", "st_wake_ns"} <= cols:
        return "pace"
    if {"t_expected_ns", "t_wake_ns"} <= cols:
        return "contract"
    raise ValueError(f"알 수 없는 제어루프 로그 포맷. 열: {sorted(cols)[:12]} ...")


def load_ctrl(path) -> tuple[pd.DataFrame, dict]:
    """제어루프 CSV → 공통 열을 가진 DataFrame.

    공통 열 (없으면 NaN):
      iter, t_expected_ns, t_wake_ns, t_cmd_ns, latency_us(=wake−expected), exec_us(=cmd−wake),
      ai_seq, ai_t_capture_ns, ai_t_recv_ns, ai_t_gen_ns, ai_state, reject_reason, speed_scale
    meta["format"] 에 어느 포맷이었는지 적어 둔다."""
    raw, meta = read_csv_with_meta(path)
    fmt = detect_format(raw); meta["format"] = fmt; meta["path"] = str(path)
    d = pd.DataFrame()
    if fmt == "contract":
        d["iter"] = raw["iter"] if "iter" in raw else np.arange(len(raw))
        d["t_expected_ns"] = raw["t_expected_ns"].astype("int64")
        d["t_wake_ns"] = raw["t_wake_ns"].astype("int64")
        d["t_cmd_ns"] = raw["t_cmd_ns"].astype("int64") if "t_cmd_ns" in raw else np.nan
        d["ai_seq"] = raw.get("ai_seq", pd.Series(-1, index=raw.index))
        d["ai_t_capture_ns"] = raw.get("ai_t_capture_ns", np.nan)
        d["ai_t_recv_ns"] = raw.get("ai_t_recv_ns", np.nan)
        d["ai_t_gen_ns"] = np.nan
        d["ai_state"] = raw.get("ai_state", "fresh").astype(str).str.lower()
        d["reject_reason"] = raw.get("reject_reason", "").fillna("").astype(str)
        d["speed_scale"] = raw.get("speed_scale", np.nan)
        for c in raw.columns:                       # q_ref*, q_act*, v_cmd* 는 그대로 넘긴다 (B2 용)
            if c.startswith(("q_ref", "q_act", "v_cmd")):
                d[c] = raw[c]
    else:  # pace
        d["iter"] = raw["tick"]
        d["t_expected_ns"] = raw["t_sched_ns"].astype("int64")
        d["t_wake_ns"] = raw["t_wake_ns"].astype("int64")
        exec_cols = [f"st_{s}_ns" for s in PACE_STAGES[1:-1] if f"st_{s}_ns" in raw]   # read..write (log 는 송출 뒤)
        d["t_cmd_ns"] = d["t_wake_ns"] + raw[exec_cols].sum(axis=1).astype("int64")
        d["ai_seq"] = raw["chunk_seq"]
        d["ai_t_capture_ns"] = np.nan                                   # 현재 포맷에 없음 (A6 불가 → README 참고)
        d["ai_t_recv_ns"] = np.nan                                      # 현재 포맷에 없음 (A5 는 생성시각 기준으로 근사)
        d["ai_t_gen_ns"] = raw["chunk_t_gen_ns"].replace(0, np.nan)
        state = raw["mode"].map(PACE_MODE_NAMES).fillna("unknown")
        if "reject" in raw:
            state = state.where(raw["reject"] == 0, "reject")
        d["ai_state"] = state
        d["reject_reason"] = raw["reject"].map(PACE_REJECT_NAMES).fillna("UNKNOWN") if "reject" in raw else ""
        d["speed_scale"] = raw.get("speed_scale", np.nan)
        for c in ("monitor", "triggers", "stop_level", "arc_on", "supplier", "buffer_margin_ms", "deviation", "progress_s"):
            if c in raw:
                d[c] = raw[c]
        for s in PACE_STAGES:                                            # 단계별 소요도 넘긴다 (루프 실행 분해용)
            if f"st_{s}_ns" in raw:
                d[f"st_{s}_us"] = raw[f"st_{s}_ns"] / 1e3
    d["latency_us"] = (d["t_wake_ns"] - d["t_expected_ns"]) / 1e3
    d["exec_us"] = (d["t_cmd_ns"] - d["t_wake_ns"]) / 1e3
    d["t_s"] = (d["t_expected_ns"] - d["t_expected_ns"].iloc[0]) / 1e9
    return d, meta


def load_trace(path) -> dict | None:
    """pace_control --trace 바이너리 (q_cmd/q_meas/tool 1kHz). 없으면 None.
    헤더: u64 n, u32 dof, u32 record_size. 레코드: t_ns u8, q_cmd f4×8, q_meas f4×8, tool f4×7, speed f4, mode u2, monitor u2."""
    p = Path(path)
    if not p.exists():
        return None
    with open(p, "rb") as f:
        n = int(np.frombuffer(f.read(8), np.uint64)[0]); dof, sz = np.frombuffer(f.read(8), np.uint32)
        dt = np.dtype({"names": ["t_ns", "q_cmd", "q_meas", "tool", "speed", "mode", "monitor"],
                       "formats": ["<u8", ("<f4", 8), ("<f4", 8), ("<f4", 7), "<f4", "<u2", "<u2"], "itemsize": int(sz)})
        a = np.frombuffer(f.read(n * int(sz)), dt, count=n)
    ok = a["t_ns"] > 0
    return {"t_ns": a["t_ns"][ok], "q_cmd": a["q_cmd"][ok][:, :dof].astype(np.float64),
            "q_meas": a["q_meas"][ok][:, :dof].astype(np.float64), "tool": a["tool"][ok], "mode": a["mode"][ok], "dof": int(dof)}


# ──────────────────────────────────────────────────────────────────────────────
# 4) 지표 함수 (A1~A8, B1~B4 중 로그만으로 계산되는 것)
# ──────────────────────────────────────────────────────────────────────────────
def a1_deadline_miss(d: pd.DataFrame, period_ns: int = PERIOD_NS) -> dict:
    """A1 제어주기: 깨어남 지연이 주기(1ms)를 넘은 횟수. 0 이어야 한다."""
    lat_ns = d["t_wake_ns"] - d["t_expected_ns"]
    miss = d.index[lat_ns > period_ns]
    gaps = np.diff(d["t_expected_ns"].to_numpy())
    skipped = int(((gaps > period_ns * 1.5)).sum()) if len(gaps) else 0   # 예정 시각 자체가 건너뛴 틱
    return {"n": int(len(d)), "miss": int(len(miss)), "miss_ratio": len(miss) / max(len(d), 1),
            "miss_iters": [int(d["iter"].iloc[i]) for i in miss[:20]], "skipped_ticks": skipped,
            "pass": len(miss) == 0 and skipped == 0}


def a2_jitter(d: pd.DataFrame, threshold=JITTER_LIMIT_US) -> dict:
    """A2 지터: 깨어남 지연 분포. max ≤ 100μs 이어야 한다."""
    s = stats(d["latency_us"], threshold); s["pass"] = s.get("max", float("inf")) <= threshold
    return s


def loop_exec(d: pd.DataFrame) -> dict:
    """루프 실행시간(명령 송출 − 깨어남) 분포 + (pace 포맷이면) 단계별 최대."""
    out = {"exec": stats(d["exec_us"], threshold=None)}
    stages = {s: stats(d[f"st_{s}_us"], None) for s in PACE_STAGES[1:] if f"st_{s}_us" in d}
    if stages:
        out["stages_max_us"] = {k: round(v["max"], 1) for k, v in stages.items() if v.get("n")}
    return out


def a5_reflect_latency(d: pd.DataFrame) -> dict:
    """A5 제어 반영 지연: AI 결과(ai_seq)가 바뀐 주기에서 t_cmd − ai_t_recv.
    현재 pace 포맷엔 ai_t_recv 가 없어 t_cmd − ai_t_gen(생성 시각) 으로 근사한다. 이 값은 '공급자 지연 + 반영 지연' 이므로
    README 의 한계 항목에 적힌 대로 해석해야 한다."""
    seq = d["ai_seq"].to_numpy()
    change = np.nonzero((seq[1:] != seq[:-1]) & (seq[1:] > 0))[0] + 1
    if len(change) == 0:
        return {"n": 0, "basis": "none"}
    rows = d.iloc[change]
    if rows["ai_t_recv_ns"].notna().any():
        vals = (rows["t_cmd_ns"] - rows["ai_t_recv_ns"]) / 1e3; basis = "t_cmd − ai_t_recv (약속 포맷, 정확한 A5)"
    elif rows["ai_t_gen_ns"].notna().any():
        vals = (rows["t_cmd_ns"] - rows["ai_t_gen_ns"]) / 1e3; basis = "t_cmd − chunk_t_gen (pace 포맷 근사: 공급자 지연 포함)"
    else:
        return {"n": 0, "basis": "none"}
    s = stats(vals, threshold=None); s["basis"] = basis; s["n_changes"] = int(len(change))
    return s


def a6_e2e(d: pd.DataFrame) -> dict:
    """A6 End-to-End: t_cmd − ai_t_capture (처음 반영된 주기). 캡처 시각 열이 있어야만 가능."""
    seq = d["ai_seq"].to_numpy()
    change = np.nonzero((seq[1:] != seq[:-1]) & (seq[1:] > 0))[0] + 1
    rows = d.iloc[change]
    if len(rows) == 0 or not rows["ai_t_capture_ns"].notna().any():
        return {"n": 0, "basis": "ai_t_capture_ns 없음 → 측정 불가 (플랫폼 로그에 캡처 시각 필요)"}
    s = stats((rows["t_cmd_ns"] - rows["ai_t_capture_ns"]) / 1e3, None); s["basis"] = "t_cmd − ai_t_capture"
    return s


def b1_reject(d: pd.DataFrame, n_ai_msgs: int | None = None) -> dict:
    """B1 검증 거부: ai_state == reject 인 주기 수, 사유별 개수. 분모(도착한 AI 결과 수)는 AI 로그/summary 에서 받는다."""
    rej = d[d["ai_state"] == "reject"]
    reasons = rej["reject_reason"].astype(str).value_counts().to_dict() if len(rej) else {}
    groups: dict[str, int] = {}
    for k, v in reasons.items():
        g = REJECT_GROUP.get(k, k.lower() if k else "unknown"); groups[g] = groups.get(g, 0) + int(v)
    out = {"reject_ticks": int(len(rej)), "reasons": reasons, "by_group": groups, "expired_used": 0,
           "expired_used_note": "유효기간 지난 결과 사용 횟수. 현재 포맷은 valid_until 이 로그에 없어 검증기 EXPIRED 거부 수로 대신 본다"}
    if n_ai_msgs:
        out["n_ai_msgs"] = int(n_ai_msgs); out["reject_ratio"] = len(rej) / n_ai_msgs
    return out


def state_segments(d: pd.DataFrame) -> list[dict]:
    """ai_state 가 바뀌는 구간 목록 [{state, t0_s, t1_s, dur_ms, iter0}] (A8 상태 띠, B3 전이 시각의 재료)."""
    st = d["ai_state"].to_numpy(); t = d["t_s"].to_numpy(); it = d["iter"].to_numpy()
    cuts = np.nonzero(st[1:] != st[:-1])[0] + 1
    starts = np.concatenate([[0], cuts]); ends = np.concatenate([cuts, [len(st)]])
    return [{"state": str(st[a]), "t0_s": float(t[a]), "t1_s": float(t[b - 1]), "dur_ms": float((t[b - 1] - t[a]) * 1e3 + 1.0), "iter0": int(it[a])}
            for a, b in zip(starts, ends)]


def b3_recovery(d: pd.DataFrame, fault_t0_s: float | None = None) -> dict:
    """B3 장애 복구 시간: 상태 전이 시각으로 감지/감속/정지/복귀 시간을 잰다.
    fault_t0_s 를 주면 '장애 시작 → 첫 비정상 상태' 가 감지 시간. 없으면 전이 목록만 돌려준다.
    또 각 비정상 구간 안의 A1 미스 수를 센다 (복구 중에도 박자를 지켰는가)."""
    segs = state_segments(d)
    abnormal = [s for s in segs if s["state"] not in ("fresh", "init")]
    lat_ns = (d["t_wake_ns"] - d["t_expected_ns"]).to_numpy(); t = d["t_s"].to_numpy()
    out = {"segments": segs, "n_abnormal_segments": len(abnormal), "a1_miss_during_abnormal": 0}
    for s in abnormal:
        m = (t >= s["t0_s"]) & (t <= s["t1_s"])
        out["a1_miss_during_abnormal"] += int((lat_ns[m] > PERIOD_NS).sum())
    if fault_t0_s is not None:
        first = next((s for s in abnormal if s["t0_s"] >= fault_t0_s), None)
        out["fault_t0_s"] = fault_t0_s
        out["detect_ms"] = (first["t0_s"] - fault_t0_s) * 1e3 if first else None
        back = next((s for s in segs if s["state"] == "fresh" and first and s["t0_s"] > first["t0_s"]), None)
        out["back_to_fresh_ms"] = (back["t0_s"] - fault_t0_s) * 1e3 if back else None
    return out


def b2_smoothness(tr: dict, dt_s: float = 1e-3, windows: list[tuple[float, float]] | None = None) -> dict:
    """B2 안전 동작: 명령 위치 q_cmd 의 3차 차분 = 저크 [rad/s³], 추종 오차 |q_cmd − q_meas| [rad].
    windows=[(t0,t1),...] 를 주면 구간별(장애 전/중/후) 최대 저크를 따로 낸다. 측정 노이즈를 피하기 위해 실측이 아닌 명령값을 미분한다
    (PDF 4절 B2: '어느 쪽을 했는지 리포트에 적는다' → 명령 미분)."""
    q = tr["q_cmd"]; t = (tr["t_ns"] - tr["t_ns"][0]) / 1e9
    jerk = np.diff(q, n=3, axis=0) / dt_s ** 3
    jmag = np.abs(jerk).max(axis=1)                         # 틱별 최대 관절 저크
    err = np.abs(tr["q_cmd"] - tr["q_meas"]).max(axis=1)
    out = {"basis": "q_cmd 3차 차분 (명령 미분)", "jerk_rad_s3": stats(jmag, None, unit="rad/s³"), "track_err_rad": stats(err, None, unit="rad")}
    if windows:
        tj = t[3:]
        out["windows"] = []
        for (a, b) in windows:
            m = (tj >= a) & (tj < b)
            out["windows"].append({"t0_s": a, "t1_s": b, "jerk_max": float(jmag[m].max()) if m.any() else None,
                                   "jerk_p99": float(np.percentile(jmag[m], 99)) if m.any() else None})
    return out


def a7_table(rows: list[dict]) -> pd.DataFrame:
    """A7 부하 비교표: [{"label":..., "stats":{...}, "a1":{...}}] → Jiao Table IV 모양의 표."""
    recs = []
    for r in rows:
        s = r["stats"]
        r1 = lambda k: (round(s[k], 1) if isinstance(s.get(k), (int, float)) and s[k] != float("inf") else s.get(k, "-"))
        recs.append({"조건": r["label"], "n": s.get("n"), "avg": r1("avg"), "p99": r1("p99"),
                     "p99.9": r1("p999"), "max": r1("max"), ">100μs": s.get("over"),
                     "주기 미스": (r.get("a1") or {}).get("miss", "-"), "판정": "합격" if s.get("max", 1e9) <= JITTER_LIMIT_US else "불합격"})
    return pd.DataFrame(recs)


# ──────────────────────────────────────────────────────────────────────────────
# 5) 저장 도우미
# ──────────────────────────────────────────────────────────────────────────────
def save_json(obj, path):
    def conv(o):
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, np.ndarray): return o.tolist()
        if isinstance(o, pd.DataFrame): return o.to_dict(orient="records")
        return str(o)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=conv))


def df_to_md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v) for v in r.tolist()) + " |")
    return "\n".join(lines)
