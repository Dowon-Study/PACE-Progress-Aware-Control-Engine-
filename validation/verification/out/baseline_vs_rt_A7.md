# A7 부하 비교 — baseline_vs_rt

| 조건 | n | avg | p99 | p99.9 | max | >100μs | 주기 미스 | 판정 |
|---|---|---|---|---|---|---|---|---|
| generic_idle | 29947 | 5.2 | 215.0 | 399.0 | 592.0 | 563 | - | 불합격 |
| generic_stress | 29965 | 11.2 | 56.0 | 399.0 | 1325.0 | 203 | - | 불합격 |
| rt_idle(cyclictest) | 60000 | 6.1 | 9.0 | 29.0 | 76.0 | 0 | - | 합격 |
| rt_stress(cyclictest) | 60000 | 6.4 | 8.0 | 11.0 | 20.0 | 0 | - | 합격 |
| rt_idle(제어루프) | 20000 | 6.5 | 7.8 | 8.6 | 16.7 | 0 | 0 | 합격 |
| rt_stress(제어루프) | 60000 | 7.7 | 18.6 | 27.1 | 41.8 | 0 | 0 | 합격 |

- generic_idle: `/home/kwuser/바탕화면/PAC_PhysicalAI/docs/benchmarks/baseline_generic_idle.txt`
- generic_stress: `/home/kwuser/바탕화면/PAC_PhysicalAI/docs/benchmarks/baseline_generic_stress.txt`
- rt_idle(cyclictest): `/home/kwuser/바탕화면/PAC_PhysicalAI/docs/benchmarks/rt_ccx_idle.txt`
- rt_stress(cyclictest): `/home/kwuser/바탕화면/PAC_PhysicalAI/docs/benchmarks/rt_ccx_stress.txt`
- rt_idle(제어루프): `/home/kwuser/바탕화면/PAC_PhysicalAI/docs/benchmarks/loop_rt_ccx_idle_20s.csv`
- rt_stress(제어루프): `/home/kwuser/바탕화면/PAC_PhysicalAI/docs/benchmarks/loop_rt_ccx_load_60s.csv`

그림: `baseline_vs_rt_A7_hist_overlay.png`
