"""A8 조건별 동작 시각화 — 예시 그림 (합성 데이터).

실제 측정이 나오면 make_synthetic() 대신 raw/*_ctrl.csv, *_ai.csv, *_fault.csv 를
읽어 같은 draw() 로 그리면 된다. 시나리오: 누락(drop) — AI 결과가 0.4초 동안 끊김.

실행:  source .venv/bin/activate && python validation/scripts/plot_a8_example.py
출력:  validation/figures/example_A8_drop.png
"""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# ---- 팔레트 (dataviz 참조 팔레트, 라이트) ----
C_REF, C_ACT = "#2a78d6", "#eb6834"          # 시리즈 1·2
C_V = "#4a3aa7"                              # 시리즈 7 (속도)
STATE_COLOR = {"fresh": "#0ca30c", "hold": "#fab219", "decel": "#ec835a",
               "stop": "#d03b3b", "reject": "#9a9994"}
C_FAULT = "#f0efec"
TXT, TXT2 = "#0b0b0b", "#52514e"
plt.rcParams["font.family"] = ["Noto Sans CJK KR", "Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def make_synthetic():
    """1 kHz 제어루프 3초, AI 30 ms 주기, t=1.0~1.4 s 누락. 유효기간 60 ms, hold 100 ms 후 감속."""
    dt = 0.001
    t = np.arange(0, 3.0, dt)
    n = len(t)
    # AI 도착 시각 (30 ms 주기, 누락 구간 제외)
    ai_t = np.arange(0.0, 3.0, 0.030)
    fault_start, fault_end = 1.0, 1.4
    ai_t = ai_t[(ai_t < fault_start) | (ai_t >= fault_end)]
    # 기준 경로: 천천히 오르는 S-커브 (AI가 주는 목표)
    q_ref = 10 + 0.3 * (1 - np.cos(np.pi * t / 3.0))
    # 상태 전이
    state = np.array(["fresh"] * n, dtype=object)
    last_ai = ai_t[ai_t < fault_start].max()           # 0.99
    t_hold = last_ai + 0.060                           # 유효기간 만료 → hold
    t_decel = t_hold + 0.100                           # hold 타임아웃 → decel
    t_stop = t_decel + 0.150                           # 감속 완료 → stop
    t_recv = ai_t[ai_t >= fault_end].min()             # 1.41 새 결과 도착
    t_fresh = t_recv + 0.040                           # 블렌딩 후 fresh
    state[(t >= t_hold) & (t < t_decel)] = "hold"
    state[(t >= t_decel) & (t < t_stop)] = "decel"
    state[(t >= t_stop) & (t < t_fresh)] = "stop"
    # 명령 속도: 정상 추종 속도, decel 구간 저크 제한 감속, stop 0, 복귀 시 블렌딩
    v_nominal = np.gradient(q_ref, dt)
    v_cmd = v_nominal.copy()
    v_cmd[(t >= t_hold) & (t < t_decel)] = v_nominal[t >= t_hold][0]       # hold: 직전 속도 유지
    m = (t >= t_decel) & (t < t_stop)
    s = (t[m] - t_decel) / (t_stop - t_decel)
    v_cmd[m] = v_nominal[t >= t_hold][0] * (1 - (3 * s**2 - 2 * s**3))      # 부드러운 감속
    v_cmd[(t >= t_stop) & (t < t_recv)] = 0.0
    m2 = (t >= t_recv) & (t < t_fresh)
    s2 = (t[m2] - t_recv) / (t_fresh - t_recv)
    v_cmd[m2] = v_nominal[m2] * (3 * s2**2 - 2 * s2**3)                       # 블렌딩 복귀
    # 실측 위치: 명령 속도 적분 + 작은 추종 지연·노이즈
    q_act = 10 + np.cumsum(v_cmd) * dt
    q_act = np.roll(q_act, 8); q_act[:8] = 10
    q_act += np.random.default_rng(0).normal(0, 0.0015, n)
    times = dict(t0=fault_start, t1=t_hold, t2=t_decel, t3=t_stop, t4=t_recv, t5=t_fresh)
    return t, ai_t, (fault_start, fault_end), state, q_ref, q_act, v_cmd, times


def draw(t, ai_t, fault, state, q_ref, q_act, v_cmd, times, out):
    fig, axes = plt.subplots(4, 1, figsize=(11, 8.2), sharex=True,
                             gridspec_kw=dict(height_ratios=[0.9, 0.6, 2.2, 1.6], hspace=0.12))
    ax_ai, ax_st, ax_q, ax_v = axes
    for ax in axes:
        ax.axvspan(*fault, color=C_FAULT, zorder=0)
        ax.set_facecolor("#fcfcfb")
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.spines["left"].set_color("#c3c2b7"); ax.spines["bottom"].set_color("#c3c2b7")
        ax.tick_params(colors=TXT2, labelsize=9)
        ax.grid(axis="y", color="#e9e8e4", lw=0.8, zorder=0)

    # (1) AI 결과 도착
    ax_ai.scatter(ai_t, np.ones_like(ai_t), s=18, color=C_REF, zorder=3)
    ax_ai.set_yticks([]); ax_ai.set_ylim(0.5, 1.5)
    ax_ai.set_ylabel("AI 결과\n도착", color=TXT2, fontsize=9, rotation=0, ha="right", va="center")
    ax_ai.text(fault[0] + 0.02, 1.3, "장애 주입: 누락(drop) 0.4 s", color=TXT2, fontsize=9)

    # (2) 상태 띠
    cur = state[0]; start = t[0]
    for i in range(1, len(t)):
        if state[i] != cur:
            ax_st.axvspan(start, t[i], color=STATE_COLOR[cur], zorder=2)
            cur, start = state[i], t[i]
    ax_st.axvspan(start, t[-1], color=STATE_COLOR[cur], zorder=2)
    ax_st.set_yticks([]); ax_st.set_ylim(0, 1)
    ax_st.set_ylabel("ai_state", color=TXT2, fontsize=9, rotation=0, ha="right", va="center")
    ax_st.legend(handles=[Patch(color=c, label=k) for k, c in STATE_COLOR.items() if k != "reject"],
                 ncol=4, loc="upper right", fontsize=8, frameon=False, bbox_to_anchor=(1.0, 1.9))

    # (3) 위치
    ax_q.plot(t, q_ref, color=C_REF, lw=2, label="q_ref (AI가 준 목표)", zorder=3)
    ax_q.plot(t, q_act, color=C_ACT, lw=2, label="q_act (실측)", zorder=3)
    ax_q.set_ylabel("위치 (deg)", color=TXT2, fontsize=9)
    ax_q.legend(loc="upper left", fontsize=9, frameon=False)
    err = np.abs(q_ref - q_act)
    i_max = int(np.argmax(err))
    ax_q.annotate(f"최대 추종 오차 {err[i_max]:.3f}° (B2)", xy=(t[i_max], q_act[i_max]),
                  xytext=(t[i_max] + 0.25, q_act[i_max] - 0.08), fontsize=9, color=TXT,
                  arrowprops=dict(arrowstyle="-", color=TXT2, lw=0.8))

    # (4) 명령 속도
    ax_v.plot(t, v_cmd, color=C_V, lw=2, zorder=3)
    ax_v.set_ylabel("v_cmd (deg/s)", color=TXT2, fontsize=9)
    ax_v.set_xlabel("시간 (s)", color=TXT2, fontsize=9)
    a = np.gradient(v_cmd, 0.001); j = np.gradient(a, 0.001)
    i_j = int(np.argmax(np.abs(j)))
    ax_v.annotate(f"최대 |저크| {abs(j[i_j]):.0f} deg/s³ (B2)", xy=(t[i_j], v_cmd[i_j]),
                  xytext=(t[i_j] + 0.3, v_cmd[i_j] + 0.12), fontsize=9, color=TXT,
                  arrowprops=dict(arrowstyle="-", color=TXT2, lw=0.8))

    # B3 타임라인 표시 (t0~t5)
    labels = {"t0": "장애 시작", "t1": "감지→hold", "t2": "decel", "t3": "stop", "t4": "새 결과 도착", "t5": "fresh 복귀"}
    for k, tv in times.items():
        for ax in (ax_st, ax_q, ax_v):
            ax.axvline(tv, color=TXT2, lw=0.7, ls=":", zorder=1)
        ax_v.text(tv, ax_v.get_ylim()[0], f" {k}", fontsize=8, color=TXT2, va="bottom")
    b3 = (f"B3  감지 {1000*(times['t1']-times['t0']):.0f} ms · "
          f"감속 {1000*(times['t3']-times['t2']):.0f} ms · "
          f"복귀 {1000*(times['t5']-times['t4']):.0f} ms · 주기 미스 0")
    fig.text(0.125, 0.905, b3, fontsize=9.5, color=TXT)
    fig.suptitle("A8 예시 — 조건: 누락(drop)   |   1 kHz 제어루프, AI 30 ms 주기, 유효기간 60 ms",
                 x=0.125, ha="left", fontsize=11.5, color=TXT, y=0.955)
    ax_v.set_xlim(0, 3.0)
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="#fcfcfb")
    print("saved", out)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    out = root / "figures" / "example_A8_drop.png"
    draw(*make_synthetic(), out=out)
