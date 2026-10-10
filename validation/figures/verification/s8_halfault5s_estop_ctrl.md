# 제어루프 검증 — s8_halfault5s_estop

원본: `docs/benchmarks/runs/s8_stop_fault_ur5e.csv` (포맷 pace)

- A1 주기 미스: **0 / 30000** (합격)
- A2 지터: n=30000  min 5.0 / avg 6.4 / p50 6.3 / p99 7.9 / p99.9 8.7 / max 12.7 us  | >100us: 0 (0.0000%) (합격)
- 루프 실행시간: n=30000  min 1.0 / avg 7.9 / p50 7.6 / p99 10.6 / p99.9 11.6 / max 69.4 us
- A5 반영 지연: 계산 불가 — none
- A6 E2E: ai_t_capture_ns 없음 → 측정 불가 (플랫폼 로그에 캡처 시각 필요)
- B1 거부 틱: 0 {}
- B3 비정상 구간 3개, 그동안 A1 미스 0
- B2 저크 p99 / max: 22769 / 30041 rad/s³, 추종 오차 max 0.0078 rad

## 상태 전이 (앞 40개)

| state | t0_s | t1_s | dur_ms | iter0 |
|---|---|---|---|---|
| recover | 0.0 | 2.999 | 3000.0 | 0 |
| fresh | 3.0 | 10.066 | 7067.000000000001 | 3000 |
| hold | 10.067 | 10.44 | 373.9999999999993 | 10067 |
| stop | 10.441 | 29.999 | 19559.0 | 10441 |

그림: `s8_halfault5s_estop_A2_ctrl_hist.png`, `s8_halfault5s_estop_A8_timeline.png`