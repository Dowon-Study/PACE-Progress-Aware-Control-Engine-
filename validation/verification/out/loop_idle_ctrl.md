# 제어루프 검증 — loop_idle

원본: `/home/kwuser/바탕화면/PAC_PhysicalAI/docs/benchmarks/loop_rt_ccx_idle_20s.csv` (포맷 pace)

- A1 주기 미스: **0 / 20000** (합격)
- A2 지터: n=20000  min 5.3 / avg 6.5 / p50 6.4 / p99 7.8 / p99.9 8.6 / max 16.7 us  | >100us: 0 (0.0000%) (합격)
- 루프 실행시간: n=20000  min 1.0 / avg 5.8 / p50 5.8 / p99 6.7 / p99.9 7.3 / max 14.9 us
- A5 반영 지연: 계산 불가 — none
- A6 E2E: ai_t_capture_ns 없음 → 측정 불가 (플랫폼 로그에 캡처 시각 필요)
- B1 거부 틱: 0 {}
- B3 비정상 구간 0개, 그동안 A1 미스 0

## 상태 전이 (앞 40개)

| state | t0_s | t1_s | dur_ms | iter0 |
|---|---|---|---|---|
| fresh | 0.0 | 19.999 | 20000.0 | 0 |

그림: `loop_idle_A2_ctrl_hist.png`, `loop_idle_A8_timeline.png`