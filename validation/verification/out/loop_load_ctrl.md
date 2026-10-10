# 제어루프 검증 — loop_load

원본: `/home/kwuser/바탕화면/PAC_PhysicalAI/docs/benchmarks/loop_rt_ccx_load_60s.csv` (포맷 pace)

- A1 주기 미스: **0 / 60000** (합격)
- A2 지터: n=60000  min 5.3 / avg 7.7 / p50 7.0 / p99 18.6 / p99.9 27.1 / max 41.8 us  | >100us: 0 (0.0000%) (합격)
- 루프 실행시간: n=60000  min 1.0 / avg 6.4 / p50 6.2 / p99 10.4 / p99.9 12.6 / max 17.9 us
- A5 반영 지연: 계산 불가 — none
- A6 E2E: ai_t_capture_ns 없음 → 측정 불가 (플랫폼 로그에 캡처 시각 필요)
- B1 거부 틱: 0 {}
- B3 비정상 구간 0개, 그동안 A1 미스 0

## 상태 전이 (앞 40개)

| state | t0_s | t1_s | dur_ms | iter0 |
|---|---|---|---|---|
| fresh | 0.0 | 59.999 | 60000.0 | 0 |

그림: `loop_load_A2_ctrl_hist.png`, `loop_load_A8_timeline.png`