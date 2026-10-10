# AI 계층 검증 — s12_realai

원본: `docs/benchmarks/runs/s12_ai_gpu.ai.csv` + `docs/benchmarks/runs/s12_ai_gpu.csv`

- A3 추론시간: n=230  min 6.1 / avg 6.5 / p50 6.4 / p99 7.0 / p99.9 7.0 / max 7.0 ms
- A4 추론 주기: n=229  min 90.8 / avg 100.0 / p50 100.0 / p99 106.2 / p99.9 106.8 / max 106.9 ms
- A6 E2E (t_cmd − t_capture, 처음 반영 주기): n=149  min 8631.8 / avg 10262.4 / p50 9645.6 / p99 15166.8 / p99.9 19961.1 / max 20710.7 us
- A6 구간 분해 (평균 ms): {'capture→infer_start_ms': 2.8751283304347828, 'infer_ms': 6.459625052173914, 'infer_end→publish_ms': 0.39008253478260874, 'publish→first_apply_ms': 0.4944743691275168}
