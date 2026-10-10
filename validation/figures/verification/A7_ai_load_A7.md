# A7 부하 비교 — A7_ai_load

| 조건 | n | avg | p99 | p99.9 | max | >100μs | 주기 미스 | 판정 |
|---|---|---|---|---|---|---|---|---|
| fake | 20000 | 6.2 | 7.3 | 8.5 | 12.4 | 0 | 0 | 합격 |
| fake_stress | 20000 | 7.4 | 11.3 | 18.5 | 29.5 | 0 | 0 | 합격 |
| ai_gpu | 20000 | 6.4 | 7.5 | 8.4 | 13.1 | 0 | 0 | 합격 |
| ai_cpu | 20000 | 6.4 | 7.4 | 8.1 | 10.3 | 0 | 0 | 합격 |
| ai_gpu_stress | 20000 | 7.1 | 10.2 | 16.1 | 96.0 | 0 | 0 | 합격 |

- fake: `docs/benchmarks/runs/s11_load_fake.csv`
- fake_stress: `docs/benchmarks/runs/s11_load_fake_stress.csv`
- ai_gpu: `docs/benchmarks/runs/s11_load_ai_gpu.csv`
- ai_cpu: `docs/benchmarks/runs/s11_load_ai_cpu.csv`
- ai_gpu_stress: `docs/benchmarks/runs/s11_load_ai_gpu_stress.csv`

그림: `A7_ai_load_A7_hist_overlay.png`
