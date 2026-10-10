# 제어루프 검증 — s8_ros2_eye

원본: `docs/benchmarks/runs/s8_hal_ros2_eye_ep1.csv` (포맷 pace)

- A1 주기 미스: **0 / 35000** (합격)
- A2 지터: n=35000  min 5.0 / avg 6.4 / p50 6.3 / p99 7.9 / p99.9 9.0 / max 14.2 us  | >100us: 0 (0.0000%) (합격)
- 루프 실행시간: n=35000  min 6.5 / avg 14.2 / p50 14.7 / p99 16.9 / p99.9 18.7 / max 67.2 us
- A5 반영 지연: 계산 불가 — none
- A6 E2E: ai_t_capture_ns 없음 → 측정 불가 (플랫폼 로그에 캡처 시각 필요)
- B1 거부 틱: 0 {}
- B3 비정상 구간 2개, 그동안 A1 미스 0
- B2 저크 p99 / max: 30580 / 40054 rad/s³, 추종 오차 max 0.0047 rad

## 상태 전이 (앞 40개)

| state | t0_s | t1_s | dur_ms | iter0 |
|---|---|---|---|---|
| recover | 0.0 | 2.999 | 3000.0 | 0 |
| fresh | 3.0 | 22.79 | 19791.0 | 3000 |
| hold | 22.791 | 34.999 | 12209.000000000002 | 22791 |

그림: `s8_ros2_eye_A2_ctrl_hist.png`, `s8_ros2_eye_A8_timeline.png`