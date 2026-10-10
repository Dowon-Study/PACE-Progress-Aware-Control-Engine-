"""보조 궤적 생성기의 입력·정답을 만드는 공통 함수. 추론(local_block)과 온라인 학습(online_train)이 반드시 같은 방식을 쓰도록 한 곳에 둔다.

입력 x (186) = 최근 300 ms 관절 이력 (10 ms 간격 30점, 현재 q 기준 차분) + 현재 q (절대)
정답 y (300) = 앞으로 1 s 관절 궤적 (20 ms 간격 50점, 현재 q 기준 차분)
시각은 모두 CLOCK_MONOTONIC ns (time.monotonic_ns, 제어기 t_wake 와 같은 시계)."""
import numpy as np
from pace_py.local.data import CTX_N, CTX_DT, HOR_N, HOR_DT

CTX_OFFS_NS = (CTX_DT * 1_000_000 * np.arange(CTX_N, 0, -1)).astype(np.int64)      # 300, 290, ..., 10 ms 전
HOR_OFFS_NS = (HOR_DT * 1_000_000 * np.arange(1, HOR_N + 1)).astype(np.int64)      # 20, 40, ..., 1000 ms 뒤


def nearest(ts: np.ndarray, want: np.ndarray) -> np.ndarray:
    """정렬된 ts 에서 want 각각에 가장 가까운 인덱스."""
    i = np.clip(np.searchsorted(ts, want), 1, len(ts) - 1)
    return np.where(np.abs(ts[i - 1] - want) <= np.abs(ts[i] - want), i - 1, i)


def context(ts: np.ndarray, qs: np.ndarray, i_now: int):
    """i_now 시점의 입력 벡터. 반환 (x [186] float32, ctx [30, dof], 최대 시각 오차 ns)."""
    t_now = ts[i_now]; q_now = qs[i_now]
    want = t_now - CTX_OFFS_NS; idx = nearest(ts[: i_now + 1], want)
    ctx = qs[idx] - q_now
    return np.concatenate([ctx.reshape(-1), q_now]).astype(np.float32), ctx, int(np.abs(ts[idx] - want).max())


def target(ts: np.ndarray, qs: np.ndarray, i_now: int):
    """i_now 시점부터 앞 1 s 실제 궤적 (정답). 반환 (y [300] float32, 최대 시각 오차 ns)."""
    t_now = ts[i_now]; want = t_now + HOR_OFFS_NS; idx = nearest(ts, want)
    return (qs[idx] - qs[i_now]).reshape(-1).astype(np.float32), int(np.abs(ts[idx] - want).max())
