# 제어루프 검증 — a7_fake

원본: `docs/benchmarks/runs/s11_load_fake.csv` (포맷 pace)

- A1 주기 미스: **0 / 20000** (합격)
- A2 지터: n=20000  min 5.2 / avg 6.2 / p50 6.2 / p99 7.3 / p99.9 8.5 / max 12.4 us  | >100us: 0 (0.0000%) (합격)
- 루프 실행시간: n=20000  min 1.2 / avg 5.9 / p50 5.9 / p99 7.8 / p99.9 9.8 / max 14.9 us
- A5 반영 지연: n=150  min 413.7 / avg 102575.7 / p50 122783.1 / p99 150174.9 / p99.9 150862.0 / max 150952.0 us — t_cmd − chunk_t_gen (pace 포맷 근사: 공급자 지연 포함)
- A6 E2E: ai_t_capture_ns 없음 → 측정 불가 (플랫폼 로그에 캡처 시각 필요)
- B1 거부 틱: 0 {}
- B3 비정상 구간 2개, 그동안 A1 미스 0
- B2 저크 p99 / max: 14782 / 30041 rad/s³, 추종 오차 max 0.0093 rad

## 상태 전이 (앞 40개)

| state | t0_s | t1_s | dur_ms | iter0 |
|---|---|---|---|---|
| stop | 0.0 | 1.549 | 1550.0 | 0 |
| recover | 1.55 | 2.048 | 499.0 | 1550 |
| fresh | 2.049 | 19.999 | 17951.0 | 2049 |

그림: `a7_fake_A2_ctrl_hist.png`, `a7_fake_A8_timeline.png`