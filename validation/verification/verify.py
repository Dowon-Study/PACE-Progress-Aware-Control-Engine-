"""성능지표 검증 실행기 (명령 한 줄 = 지표 한 묶음).

사용법 (프로젝트 루트에서):
  .venv/bin/python validation/verification/verify.py cyclictest <파일> [--thread N] [--label 이름]
      → A2 (빈 손 지터). cyclictest -h 출력 파일. 히스토그램 그림 + 요약 json/md
  .venv/bin/python validation/verification/verify.py ctrl <ctrl.csv> [--label 이름] [--fault-t0 초]
      → A1, A2, 루프 실행시간, A5, A6, B1, B3 (+ 같은 이름의 .trace.bin 이 있으면 B2). 그림 2장
  .venv/bin/python validation/verification/verify.py compare idle=<파일> stress=<파일> ...
      → A7 부하 비교표 (cyclictest 파일과 ctrl.csv 를 섞어도 됨) + 히스토그램 겹친 그림
  .venv/bin/python validation/verification/verify.py demo
      → 지금 폴더에 있는 베이스라인 자료(docs/benchmarks)로 위 전부를 한 번 돌려 out/ 에 저장 (스크립트가 잘 도는지 확인용)

출력은 전부 --out (기본 validation/verification/out/) 아래에 <label>_*.png / .json / .md 로 저장된다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metrics_core as mc  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]          # 프로젝트 루트
OUT_DEFAULT = Path(__file__).resolve().parent / "out"

plt.rcParams["font.family"] = ["Noto Sans CJK KR", "Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
STATE_COLOR = {"fresh": "#0ca30c", "pacing": "#7fbf3f", "local": "#2a78d6", "extrap": "#4a3aa7", "hold": "#fab219",
               "decel": "#ec835a", "stop": "#d03b3b", "recover": "#17a2b8", "reject": "#9a9994", "init": "#dddddd", "unknown": "#000000"}


# ──────────────────────────────────────────────────────────────────────────────
# 그림
# ──────────────────────────────────────────────────────────────────────────────
def plot_hist(series: list[tuple[str, np.ndarray, np.ndarray]], title: str, out: Path, threshold=mc.JITTER_LIMIT_US):
    """series = [(label, bins_us, counts)] 를 겹쳐 그린다. 세로축 로그, 100μs 빨간 선."""
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for label, b, c in series:
        m = c > 0
        ax.step(b[m], c[m], where="mid", label=label, lw=1.4)
    ax.axvline(threshold, color="#d03b3b", ls="--", lw=1, label=f"기준 {threshold:g}μs")
    ax.set_yscale("log"); ax.set_xlabel("깨어남 지연 [μs]"); ax.set_ylabel("샘플 수 (로그)"); ax.set_title(title)
    ax.grid(alpha=0.3, which="both"); ax.legend(fontsize=8)
    fig.tight_layout(); out.parent.mkdir(parents=True, exist_ok=True); fig.savefig(out, dpi=130); plt.close(fig)


def values_to_hist(v_us: np.ndarray, width: float = 1.0):
    """원시 지연값 → 1μs 히스토그램 (cyclictest 와 같은 모양으로 겹쳐 그리기 위해)."""
    v = np.asarray(v_us, dtype=np.float64); v = v[np.isfinite(v)]
    hi = int(np.ceil(max(v.max(), 1.0))) + 1
    counts, edges = np.histogram(v, bins=np.arange(0, hi + width, width))
    return edges[:-1], counts


def plot_ctrl_timeline(d: pd.DataFrame, title: str, out: Path, tr: dict | None = None):
    """A8 식 시간축 그림: ① 깨어남 지연 ② 상태 띠 ③ 속도 배율(+ 추종 오차)."""
    n = 3
    fig, axes = plt.subplots(n, 1, figsize=(10, 6.5), sharex=True, gridspec_kw={"height_ratios": [2, 0.7, 1.6]})
    t = d["t_s"].to_numpy()
    ax = axes[0]
    ax.plot(t, d["latency_us"], lw=0.5, color="#2a78d6")
    ax.axhline(mc.JITTER_LIMIT_US, color="#d03b3b", ls="--", lw=1)
    ax.set_ylabel("깨어남 지연 [μs]"); ax.set_title(title); ax.grid(alpha=0.3)
    ax = axes[1]
    for s in mc.state_segments(d):
        ax.axvspan(s["t0_s"], s["t1_s"] + 1e-3, color=STATE_COLOR.get(s["state"], "#000"), lw=0)
    ax.set_yticks([]); ax.set_ylabel("상태")
    present = [s for s in mc.STATE_ORDER if (d["ai_state"] == s).any()]
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=STATE_COLOR[s]) for s in present], labels=present,
              loc="upper left", bbox_to_anchor=(1.0, 1.2), fontsize=7, frameon=False)
    ax = axes[2]
    if d["speed_scale"].notna().any():
        ax.plot(t, d["speed_scale"], color="#4a3aa7", lw=1, label="속도 배율")
    if tr is not None:
        tt = (tr["t_ns"] - tr["t_ns"][0]) / 1e9
        err = np.abs(tr["q_cmd"] - tr["q_meas"]).max(axis=1)
        ax2 = ax.twinx(); ax2.plot(tt, err, color="#eb6834", lw=0.7, label="추종 오차 max [rad]"); ax2.set_ylabel("추종 오차 [rad]")
        ax2.legend(loc="upper right", fontsize=8)
    ax.set_ylabel("속도 배율"); ax.set_xlabel("시간 [s]"); ax.grid(alpha=0.3); ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout(); out.parent.mkdir(parents=True, exist_ok=True); fig.savefig(out, dpi=130); plt.close(fig)


# ──────────────────────────────────────────────────────────────────────────────
# 명령
# ──────────────────────────────────────────────────────────────────────────────
def cmd_cyclictest(path: Path, label: str, out: Path, thread: int | None):
    ct = mc.parse_cyclictest(path)
    s = mc.cyclictest_stats(ct, thread)
    print(f"[A2 cyclictest] {label}: {mc.fmt_stats(s)}   판정: {'합격' if s['max'] <= mc.JITTER_LIMIT_US else '불합격'}")
    if "over_threads" in s:
        print(f"    100μs 초과가 난 스레드(코어) 수: {s['over_threads']} / {ct['n_threads']}")
    col = thread if thread is not None else int(np.argmax(ct["counts"].max(axis=0) * 0 + [mc.cyclictest_stats(ct, i)["max"] for i in range(ct["n_threads"])]))
    plot_hist([(label, ct["bins"], ct["counts"][:, col])], f"A2 cyclictest 지연 분포 — {label}", out / f"{label}_A2_cyclictest_hist.png")
    res = {"label": label, "source": str(path), "kind": "cyclictest", "A2": s}
    mc.save_json(res, out / f"{label}_cyclictest.json")
    (out / f"{label}_cyclictest.md").write_text(f"# A2 cyclictest — {label}\n\n원본: `{path}`\n\n{mc.fmt_stats(s)}\n")
    return res


def cmd_ctrl(path: Path, label: str, out: Path, fault_t0: float | None, n_ai_msgs: int | None):
    d, meta = mc.load_ctrl(path)
    tr = mc.load_trace(path.with_suffix(".trace.bin"))
    res = {"label": label, "source": str(path), "format": meta["format"], "meta": {k: v for k, v in meta.items() if k not in ("format", "path")}}
    res["A1"] = mc.a1_deadline_miss(d)
    res["A2"] = mc.a2_jitter(d)
    res["loop_exec"] = mc.loop_exec(d)
    res["A5"] = mc.a5_reflect_latency(d)
    res["A6"] = mc.a6_e2e(d)
    res["B1"] = mc.b1_reject(d, n_ai_msgs)
    res["B3"] = mc.b3_recovery(d, fault_t0)
    if tr is not None:
        res["B2"] = mc.b2_smoothness(tr)
    res["state_ticks"] = d["ai_state"].value_counts().to_dict()

    print(f"[ctrl] {label}  포맷={meta['format']}  틱={len(d)}  길이={d['t_s'].iloc[-1]:.1f}s")
    a1 = res["A1"]; print(f"  A1 주기 미스: {a1['miss']} / {a1['n']}  (건너뛴 틱 {a1['skipped_ticks']})  → {'합격' if a1['pass'] else '불합격'}")
    print(f"  A2 지터     : {mc.fmt_stats(res['A2'])}  → {'합격' if res['A2']['pass'] else '불합격'}")
    print(f"  루프 실행   : {mc.fmt_stats(res['loop_exec']['exec'])}")
    if "stages_max_us" in res["loop_exec"]:
        print(f"    단계별 최대 μs: {res['loop_exec']['stages_max_us']}")
    a5 = res["A5"]; print(f"  A5 반영 지연: {mc.fmt_stats(a5) if a5.get('n') else '계산 불가'}   근거: {a5.get('basis')}")
    a6 = res["A6"]; print(f"  A6 E2E     : {mc.fmt_stats(a6) if a6.get('n') else a6.get('basis')}")
    print(f"  B1 거부     : 거부 틱 {res['B1']['reject_ticks']}  사유별 {res['B1']['reasons']}" + (f"  거부율 {res['B1']['reject_ratio']*100:.2f}%" if "reject_ratio" in res["B1"] else ""))
    b3 = res["B3"]
    b3txt = f"  B3 전이     : 비정상 구간 {b3['n_abnormal_segments']}개, 그동안 A1 미스 {b3['a1_miss_during_abnormal']}"
    if b3.get("detect_ms") is not None:
        b3txt += f", 장애 {b3['fault_t0_s']:.1f}s → 감지 {b3['detect_ms']:.0f}ms"
        b3txt += f", 정상 복귀 {b3['back_to_fresh_ms']:.0f}ms" if b3.get("back_to_fresh_ms") is not None else ", 정상 복귀 없음"
    print(b3txt)
    if "B2" in res:
        print(f"  B2 저크     : {mc.fmt_stats(res['B2']['jerk_rad_s3'], 0)} ;  추종 오차 max {res['B2']['track_err_rad']['max']:.4f} rad  ({res['B2']['basis']})")
    print(f"  상태별 틱   : {res['state_ticks']}")

    b, c = values_to_hist(d["latency_us"].to_numpy())
    plot_hist([(label, b, c)], f"A2 제어루프 깨어남 지연 — {label}", out / f"{label}_A2_ctrl_hist.png")
    plot_ctrl_timeline(d, f"{label} — 지연 · 상태 · 속도", out / f"{label}_A8_timeline.png", tr)
    mc.save_json(res, out / f"{label}_ctrl.json")
    segs = pd.DataFrame(res["B3"]["segments"])
    md = [f"# 제어루프 검증 — {label}", "", f"원본: `{path}` (포맷 {meta['format']})", "",
          f"- A1 주기 미스: **{a1['miss']} / {a1['n']}** ({'합격' if a1['pass'] else '불합격'})",
          f"- A2 지터: {mc.fmt_stats(res['A2'])} ({'합격' if res['A2']['pass'] else '불합격'})",
          f"- 루프 실행시간: {mc.fmt_stats(res['loop_exec']['exec'])}",
          f"- A5 반영 지연: {mc.fmt_stats(a5) if a5.get('n') else '계산 불가'} — {a5.get('basis')}",
          f"- A6 E2E: {mc.fmt_stats(a6) if a6.get('n') else a6.get('basis')}",
          f"- B1 거부 틱: {res['B1']['reject_ticks']} {res['B1']['reasons']}",
          f"- B3 비정상 구간 {b3['n_abnormal_segments']}개, 그동안 A1 미스 {b3['a1_miss_during_abnormal']}"]
    if "B2" in res:
        md.append(f"- B2 저크 p99 / max: {res['B2']['jerk_rad_s3']['p99']:.0f} / {res['B2']['jerk_rad_s3']['max']:.0f} rad/s³, 추종 오차 max {res['B2']['track_err_rad']['max']:.4f} rad")
    md += ["", "## 상태 전이 (앞 40개)", "", mc.df_to_md(segs.head(40)) if len(segs) else "없음", "",
           f"그림: `{label}_A2_ctrl_hist.png`, `{label}_A8_timeline.png`"]
    (out / f"{label}_ctrl.md").write_text("\n".join(md))
    return res


def cmd_ai(ctrl: Path, ai_csv: Path, label: str, out: Path):
    """A3 추론시간 · A4 추론 주기 (ai.csv) · A6 E2E (ai.csv 의 t_capture 를 ctrl 의 chunk_seq 에 붙여 처음 반영 주기의 t_cmd − t_capture)."""
    a, _ = mc.read_csv_with_meta(ai_csv)
    inf_ms = (a["t_infer_end_ns"] - a["t_infer_start_ns"]) / 1e6; period_ms = np.diff(a["t_publish_ns"].to_numpy()) / 1e6
    A3 = mc.stats(inf_ms, None, "ms"); A4 = mc.stats(period_ms, None, "ms")
    d, meta = mc.load_ctrl(ctrl); cap = dict(zip(a["seq"].astype(int), a["t_capture_ns"].astype("int64")))
    d["ai_t_capture_ns"] = d["ai_seq"].map(cap)
    A6 = mc.a6_e2e(d)
    # 구간 분해: 캡처→추론시작, 추론, 추론끝→발행(지연 주입 포함), 발행→첫 반영
    seq = d["ai_seq"].to_numpy(); change = np.nonzero((seq[1:] != seq[:-1]) & (seq[1:] > 0))[0] + 1; rows = d.iloc[change]
    pub = dict(zip(a["seq"].astype(int), a["t_publish_ns"].astype("int64"))); t_pub = rows["ai_seq"].map(pub)
    decomp = {"capture→infer_start_ms": float(((a["t_infer_start_ns"] - a["t_capture_ns"]) / 1e6).mean()), "infer_ms": float(inf_ms.mean()), "infer_end→publish_ms": float(((a["t_publish_ns"] - a["t_infer_end_ns"]) / 1e6).mean()),
              "publish→first_apply_ms": float(((rows["t_cmd_ns"] - t_pub) / 1e6).mean()) if t_pub.notna().any() else None}
    res = {"label": label, "ai_csv": str(ai_csv), "ctrl": str(ctrl), "n_ai_rows": int(len(a)), "A3_infer_ms": A3, "A4_period_ms": A4, "A6_e2e_us": A6, "A6_decomposition_ms": decomp}
    print(f"[ai] {label}  AI 결과 {len(a)}건"); print(f"  A3 추론시간 : {mc.fmt_stats(A3)}"); print(f"  A4 추론 주기: {mc.fmt_stats(A4)}"); print(f"  A6 E2E     : {mc.fmt_stats(A6) if A6.get('n') else A6.get('basis')}"); print(f"  A6 분해(ms): {decomp}")
    mc.save_json(res, out / f"{label}_ai.json")
    (out / f"{label}_ai.md").write_text(f"# AI 계층 검증 — {label}\n\n원본: `{ai_csv}` + `{ctrl}`\n\n- A3 추론시간: {mc.fmt_stats(A3)}\n- A4 추론 주기: {mc.fmt_stats(A4)}\n- A6 E2E (t_cmd − t_capture, 처음 반영 주기): {mc.fmt_stats(A6) if A6.get('n') else A6.get('basis')}\n- A6 구간 분해 (평균 ms): {decomp}\n")
    return res


def cmd_compare(items: list[tuple[str, Path]], out: Path, name: str):
    rows, series = [], []
    for label, p in items:
        if p.suffix == ".csv":
            d, _ = mc.load_ctrl(p)
            s = mc.a2_jitter(d); a1 = mc.a1_deadline_miss(d)
            b, c = values_to_hist(d["latency_us"].to_numpy())
        else:
            ct = mc.parse_cyclictest(p); s = mc.cyclictest_stats(ct); a1 = None
            col = int(np.argmax([mc.cyclictest_stats(ct, i)["max"] for i in range(ct["n_threads"])]))
            b, c = ct["bins"], ct["counts"][:, col]
        rows.append({"label": label, "stats": s, "a1": a1, "source": str(p)}); series.append((label, b, c))
    table = mc.a7_table(rows)
    print(f"[A7 비교표] {name}\n{mc.df_to_md(table)}")
    plot_hist(series, f"A7 조건별 지연 분포 — {name}", out / f"{name}_A7_hist_overlay.png")
    mc.save_json(rows, out / f"{name}_A7.json")
    (out / f"{name}_A7.md").write_text(f"# A7 부하 비교 — {name}\n\n{mc.df_to_md(table)}\n\n" + "\n".join(f"- {r['label']}: `{r['source']}`" for r in rows) + f"\n\n그림: `{name}_A7_hist_overlay.png`\n")
    return table


def cmd_demo(out: Path):
    """지금 폴더에 있는 자료로 전체 흐름을 한 번 돌린다 (스크립트 동작 확인 + 첫 그림)."""
    bm = ROOT / "docs" / "benchmarks"
    print("=== 1. cyclictest 베이스라인 (일반 커널 → RT+격리) ===")
    for f, lab in [("baseline_generic_idle.txt", "generic_idle"), ("baseline_generic_stress.txt", "generic_stress"),
                   ("rt_ccx_idle.txt", "rt_idle"), ("rt_ccx_stress.txt", "rt_stress")]:
        if (bm / f).exists():
            cmd_cyclictest(bm / f, lab, out, None)
    print("\n=== 2. 실제 1kHz 제어루프 (3단계 뼈대, pace 포맷) ===")
    for f, lab in [("loop_rt_ccx_idle_20s.csv", "loop_idle"), ("loop_rt_ccx_load_60s.csv", "loop_load")]:
        if (bm / f).exists():
            cmd_ctrl(bm / f, lab, out, None, None)
    print("\n=== 3. 장애 주입 실행 (4단계 faultsA: 점프@5s 역순@7s 저신뢰@9s 버스트지연@11s 중단13~15.5s ESTOP@19s) ===")
    fa = bm / "runs" / "s4_faultsA_ep4.csv"
    if fa.exists():
        cmd_ctrl(fa, "s4_faultsA", out, 13.0, None)
    print("\n=== 4. A7 부하 비교표 ===")
    items = [(lab, bm / f) for lab, f in [("generic_idle", "baseline_generic_idle.txt"), ("generic_stress", "baseline_generic_stress.txt"),
                                          ("rt_idle(cyclictest)", "rt_ccx_idle.txt"), ("rt_stress(cyclictest)", "rt_ccx_stress.txt"),
                                          ("rt_idle(제어루프)", "loop_rt_ccx_idle_20s.csv"), ("rt_stress(제어루프)", "loop_rt_ccx_load_60s.csv")] if (bm / f).exists()]
    cmd_compare(items, out, "baseline_vs_rt")
    print(f"\n저장 위치: {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT, help="결과 저장 폴더 (기본 validation/verification/out)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("cyclictest"); p.add_argument("file", type=Path); p.add_argument("--label"); p.add_argument("--thread", type=int)
    p = sub.add_parser("ctrl"); p.add_argument("file", type=Path); p.add_argument("--label"); p.add_argument("--fault-t0", type=float, help="장애 주입 시작 시각 [s] (B3 감지 시간용)"); p.add_argument("--n-ai-msgs", type=int, help="도착한 AI 결과 수 (B1 분모)")
    p = sub.add_parser("compare"); p.add_argument("items", nargs="+", help="라벨=파일 ..."); p.add_argument("--name", default="compare")
    p = sub.add_parser("ai"); p.add_argument("ctrl", type=Path); p.add_argument("ai_csv", type=Path); p.add_argument("--label")
    sub.add_parser("demo")
    a = ap.parse_args(); a.out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "cyclictest":
        cmd_cyclictest(a.file, a.label or a.file.stem, a.out, a.thread)
    elif a.cmd == "ctrl":
        cmd_ctrl(a.file, a.label or a.file.stem, a.out, a.fault_t0, a.n_ai_msgs)
    elif a.cmd == "compare":
        items = []
        for it in a.items:
            lab, _, f = it.partition("=")
            items.append((lab if f else Path(lab).stem, Path(f or lab)))
        cmd_compare(items, a.out, a.name)
    elif a.cmd == "ai":
        cmd_ai(a.ctrl, a.ai_csv, a.label or a.ai_csv.stem, a.out)
    elif a.cmd == "demo":
        cmd_demo(a.out)


if __name__ == "__main__":
    main()
