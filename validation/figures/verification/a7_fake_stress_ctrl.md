# 제어루프 검증 — a7_fake_stress

원본: `docs/benchmarks/runs/s11_load_fake_stress.csv` (포맷 pace)

- A1 주기 미스: **0 / 20000** (합격)
- A2 지터: n=20000  min 4.3 / avg 7.4 / p50 7.3 / p99 11.3 / p99.9 18.5 / max 29.5 us  | >100us: 0 (0.0000%) (합격)
- 루프 실행시간: n=20000  min 1.1 / avg 1.3 / p50 1.3 / p99 2.3 / p99.9 4.4 / max 11.9 us
- A5 반영 지연: n=151  min 430.4 / avg 102847.5 / p50 122876.2 / p99 150783.0 / p99.9 151218.8 / max 151276.0 us — t_cmd − chunk_t_gen (pace 포맷 근사: 공급자 지연 포함)
- A6 E2E: ai_t_capture_ns 없음 → 측정 불가 (플랫폼 로그에 캡처 시각 필요)
- B1 거부 틱: 0 {}
- B3 비정상 구간 2개, 그동안 A1 미스 0
- B2 저크 p99 / max: 6804 / 20027 rad/s³, 추종 오차 max 0.0053 rad

## 상태 전이 (앞 40개)

| state | t0_s | t1_s | dur_ms | iter0 |
|---|---|---|---|---|
| stop | 0.0 | 1.506 | 1507.0 | 0 |
| recover | 1.507 | 2.005 | 499.0 | 1507 |
| fresh | 2.006 | 19.999 | 17994.0 | 2006 |

그림: `a7_fake_stress_A2_ctrl_hist.png`, `a7_fake_stress_A8_timeline.png`