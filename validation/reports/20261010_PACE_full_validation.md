# PACE 성능 검증 리포트 — 12개 지표 전수 (2026-10-10)

플랫폼 버전: 11단계 완료 시점(2026-10-10, `docs/STATUS.md`). 측정·계산은 `validation/verification/verify.py` 로만 했고 플랫폼 코드는 읽기만 했다(단, 실제 AI 공급자에 AI 계층 로그 `*.ai.csv` 출력을 추가해 A3·A4·A6 를 측정 가능하게 만들었다 — HANDOFF R2 충족). 결과 파일: `validation/figures/verification/` (json·md·png). 원본 로그: `docs/benchmarks/runs/`.

## 1. 요약 (심사위원용)

| # | 지표 | 결과 | 합격 기준 | 판정 |
|---|---|---|---|---|
| A1 | 제어주기 (1 ms 데드라인 미스) | 12개 실행 전부 **0회** (총 532,000 틱) | 0회 | ✅ |
| A2 | 지터 (깨어남 지연) | 실제 루프 max 9.5~16.9 μs (부하 없음), 29.5 μs (CPU stress), **96.0 μs** (GPU 추론+stress); 100 μs 초과 0. cyclictest 10분: idle CPU4 max 26 μs ✅, **메모리·캐시 포화 stress CPU4 max 208 μs, 100 μs 초과 14/600k ❌** | max ≤ 100 μs | ⚠ 부하 종류에 따라 미달 |
| A3 | AI 추론시간 | 실제 모델(ACT급, GPU): avg 6.5 / p99 7.0 / max 7.0 ms | 보고 | ✅ |
| A4 | AI 추론 주기 | avg 100.0 / max 106.9 ms (설정 100 ms) | 보고 | ✅ |
| A5 | 제어 반영 지연 | 근사(t_cmd − chunk_t_gen): 실제 AI 공급자 p50 9.6 ms (= 캡처→반영, 아래 A6). 순수 반영 지연은 분해값 "발행→첫 반영" 0.49 ms | 보고 | ⚠ 근사 |
| A6 | End-to-End 지연 | 캡처→첫 반영: avg 10.3 / p99 15.2 / max 20.7 ms. 분해(평균): 캡처→추론 시작 2.9 + 추론 6.5 + 발행 0.39 + 반영 0.49 ms | 보고 + 설계값 비교 | ✅ |
| A7 | AI 부하 유무 비교 | 실제 루프 5조건(가짜/CPU stress/GPU/CPU 추론/GPU+stress) 전부 A1 미스 0, max ≤ 100 μs. cyclictest 메모리 포화 stress 는 미달(§4) | 유지 | ⚠ |
| A8 | 조건별 동작 시각화 | 정상·지연 200 ms·누락·이상값·단절 6 s 타임라인 5장 (§5) | 급격한 동작 없음 | ✅ |
| B1 | 검증 거부율 | 이상값 주입 3종 → 거부 3건(사유 일치); 실제 AI 잡음 청크 58/230 = 25.2 % 거부(RANGE_ACC); 유효기간 만료 사용 0 | 만료 사용 0 | ✅ |
| B2 | 안전 동작 (저크·추종 오차) | 정상 8049 vs 단절 7749 vs HAL 폴트 29445 rad/s³ (p99); 추종 오차 max ≤ 10.6 mrad | 장애 중 ≈ 정상 | ⚠ 폴트 램프에서 p99 3.6배 |
| B3 | 장애 복구 시간 | HAL 폴트 1 s: 감지 40 ms, 정상 복귀 1561 ms, 비정상 구간 중 A1 미스 0; 단절 6 s: 감지 11 ms, 정상 복귀 7948 ms, 비정상 구간 중 A1 미스 0; 접촉: 감지 1 ms, 정상 복귀 86 ms, 비정상 구간 중 A1 미스 0 | 미스 0 | ✅ |
| B4 | HAL 교체 비용 | UR5e→Panda→iiwa14→xArm7(4 로봇), 직접→ros2_control 모두 제어·검증·접합·눈 코드 **0줄** 변경(추가분은 모델 XML + 장면 생성기); 눈 보정 오차 0.30~0.32 mm, 정지 사다리 동일 타임라인; HAL read max 1.6 → 39.5 μs (ros2) | 보고 | ✅ |

cyclictest 10분 × 1회(idle, stress) 결과는 §4 하단 — **메모리·캐시 포화 부하에서는 격리 코어도 100 μs 를 넘는 꼬리(0.002 %)가 있다.** 이것이 이번 검증에서 찾은 가장 중요한 미달 항목이다.

## 2. 측정 환경

| 항목 | 값 |
|---|---|
| 하드웨어 | Threadripper PRO 3955WX (32 스레드), RTX PRO 5000 72 GB |
| 커널 | 6.8.1-1061-realtime (PREEMPT_RT) |
| 커널 파라미터 | isolcpus=managed_irq,domain,4-7,20-23 nohz_full rcu_nocbs irqaffinity=0-3,8-19,24-31 |
| 격리 | CCX 통째(CPU 4-7, 20-23). 제어 루프 CPU 4(레인 b 는 5), 시뮬 12, 눈·로컬 8-11, AI 공급자 14-15, 학습 0-3·16-19 |
| governor | performance |
| 부하 | stress-ng --cpu 16 --vm 4 (비격리 코어), 실제 AI GPU/CPU 추론 |
| 플랫폼 버전 | 2026-10-10 11단계 (git 미사용, docs/STATUS.md) |

## 3. 측정 방법

- 제어루프 로그: `pace_control` 틱 레코드(128 B 락프리 링) → `metrics_dump` CSV (pace 포맷). 지연 = t_wake − t_sched, 실행 = 단계별 소요 합.
- AI 계층 로그: `ai_act.py --ai-csv` (seq, t_capture, t_infer_start/end, t_publish, valid_until, confidence). 모든 시각 CLOCK_MONOTONIC ns.
- E2E: AI 로그의 t_capture 를 ctrl 의 chunk_seq 에 붙여 "처음 반영된 주기의 t_cmd − t_capture".
- 저크: 명령 위치 q_cmd 의 3차 차분(측정 잡음 회피), 추종 오차 |q_cmd − q_meas|.
- 복구 시간: 상태 띠 전이 시각. 장애 주입 시각은 실행 인자(`--fault-at`, `--dropout-from`, 접촉 구간)에서.
- 반복: 조건당 1회(지속 20~45 s). 10분 반복 측정은 cyclictest 만 (A2·A7 환경 수치).

## 4. 결과 표

### A1·A2 실제 1 kHz 루프 (조건별; avg / p99 / p99.9 / max μs, 주기 미스)

| 실행 | 조건 | A2 (avg / p99 / p99.9 / max) | A1 미스 |
|---|---|---|---|
| s5_normal | 정상 (GT 공급, 지연 0) | 6.3 / 7.2 / 7.7 / **9.5** | 0 / 32000 |
| s5_delay200ms | 지연 200±50 ms | 6.4 / 7.4 / 7.9 / **9.7** | 0 / 32000 |
| s5_dropout | 누락(dropout) | 6.4 / 8.3 / 9.9 / **15.9** | 0 / 32000 |
| s4_outliers | 이상값 3종 주입 | 6.5 / 7.8 / 8.7 / **11.7** | 0 / 34000 |
| s9_disconnect6s_local | 통신 단절 6 s + 로컬 정책 | 6.3 / 7.3 / 8.1 / **11.5** | 0 / 45000 |
| s7_eye_ep1 | 용접 시연, 눈 보정 | 6.4 / 7.8 / 8.6 / **12.6** | 0 / 35000 |
| s8_panda_eye | Panda 7축 | 6.4 / 7.7 / 8.7 / **10.3** | 0 / 35000 |
| s8_ros2_eye | ros2_control 경로 | 6.4 / 7.9 / 9.0 / **14.2** | 0 / 35000 |
| s8_halfault1s / 5s | HAL 폴트 → 복귀 / 비상정지 | 6.2 / 7.5 / 8.5 / **11.3** ; 6.4 / 7.9 / 8.7 / **12.7** | 0 / 30000 ; 0 / 30000 |
| s11_contact | 접촉력 조정 | 6.4 / 7.8 / 9.0 / **12.0** | 0 / 35000 |
| s12_realai | 실제 AI 모델 GPU 추론 | 6.4 / 7.5 / 8.2 / **13.0** | 0 / 25000 |

### A7 AI 부하 비교 (20 s, 실제 루프)

| 조건 | n | avg | p99 | p99.9 | max | >100μs | 주기 미스 | 판정 |
|---|---|---|---|---|---|---|---|---|
| fake | 20000 | 6.2 | 7.3 | 8.5 | 12.4 | 0 | 0 | 합격 |
| fake_stress | 20000 | 7.4 | 11.3 | 18.5 | 29.5 | 0 | 0 | 합격 |
| ai_gpu | 20000 | 6.4 | 7.5 | 8.4 | 13.1 | 0 | 0 | 합격 |
| ai_cpu | 20000 | 6.4 | 7.4 | 8.1 | 10.3 | 0 | 0 | 합격 |
| ai_gpu_stress | 20000 | 7.1 | 10.2 | 16.1 | 96.0 | 0 | 0 | 합격 |

해석: 격리 코어의 루프는 부하 종류와 무관하게 p99 ≤ 11 μs. 비격리 코어 stress 는 깨어남 꼬리를 29.5 μs 로, GPU 추론 + stress 는 96 μs 로 키운다(100 μs 아래지만 여유가 4 %). CPU 추론은 루프가 아니라 추론 자체가 486 ms 까지 늘어진다(`docs/benchmarks/README.md` 11단계) → 공급 지연으로 나타나며 페이싱이 흡수.

### A2·A7 환경 수치: cyclictest 10분 × 1회 (`validation/raw/20261010_rt_ccx_{idle,stress}_600s_r1.txt`)

측정 명령 `cyclictest -m -S -p 99 -i 1000 -h 400 -q -a 4 -t 1 -D 600`. `-S`(전 코어 모드) 때문에 32 코어 전부에 스레드가 떴고 `-a 4` 는 무시됐다(`WARN: -a ignored due to smp mode`). 그래서 제어 코어(CPU 4)의 열과 격리 CCX 최악 코어, 전 코어 최악을 따로 적는다. stress = `taskset -c 8-15,24-31 stress-ng --vm 8 --vm-bytes 2G --cache 4` (메모리·캐시 포화형, 60 s 측정 때의 CPU 부하형과 다름).

| 조건 (600 s, 각 ≈600k 샘플) | avg | p99 | p99.9 | max | >100 μs | 판정 |
|---|---|---|---|---|---|---|
| idle, CPU 4 (제어 코어) | 3.2 | 5 | 6 | **26** | 0 | ✅ |
| idle, 격리 CCX 최악 (CPU 7) | 3.2 | 6 | 15 | 98 | 0 | ✅ (꼬리) |
| idle, 전 코어 최악 (비격리) | 3.9 | 6 | 8 | 166 | 18 | 참고 (비격리 코어에서 IK 탐색 등 다른 작업 병행 중) |
| stress(메모리·캐시), CPU 4 | 16.3 | 69 | 88 | **208** | **14 (0.0023 %)** | ❌ |
| stress, 격리 CCX 최악 (CPU 7) | 15.0 | 72 | 104 | 161 | 846 (0.14 %) | ❌ |
| stress, 전 코어 최악 | 15.2 | 73 | 101 | 495 | 612 | 참고 |

해석(중요): CPU 격리는 **CPU 시간**을 지키지만 **메모리 대역폭·캐시**는 지키지 못한다. 비격리 코어에서 `--vm 8 --vm-bytes 2G --cache 4` 로 메모리를 포화시키면 격리 코어의 깨어남 지연이 avg 3 → 16 μs, p99 5 → 69 μs 로 오르고 600 초에 14 번 100 μs 를 넘는다. 60 초 측정(CPU 부하 + GPU matmul, max 20 μs)과 실제 AI 추론 부하(max 13 μs; GPU 추론 + CPU stress 96 μs)에서는 기준 안이었으므로, **부하의 종류가 결과를 가른다.** 과제 기준(±100 μs)은 CPU 부하·실제 AI 부하에서는 충족하지만 메모리 포화 부하에서는 미달이며, 이를 숨기지 않고 보고한다. 대책 후보: AI 계층의 메모리 집약 작업(데이터 적재·전처리)을 별도 NUMA/메모리 채널로 분리, `--cache` 류 부하가 실제 워크로드에 존재하는지 확인, 10분 × 3회 반복으로 재현성 확인.



| 구성 | HAL read max [μs] | HAL write max [μs] | 선언 WCET read/write [μs] | 계약 위반 | 루프 실행 p99/max [μs] | 완주 s_end [m] |
|---|---|---|---|---|---|---|
| UR5e 6축, sim_shm (직접) | 1.6 | 13.6 | 20.0/20.0 | 0/0 | 10/18.2 | 0.2719 |
| Panda 7축, sim_shm (직접) | 1.6 | 12.9 | 20.0/20.0 | 0/0 | 11/21.4 | 0.2719 |
| UR5e, ros2_control 플러그인 경로 | 39.5 | 25.8 | 30.0/30.0 | 1/0 | 16/68.4 | 0.2719 |

## 교체에 든 코드량

| 교체 종류 | 새로 쓴 파일 (줄 수) | 제어기·검증기·접합·눈 코드 변경 |
|---|---|---|
| 로봇 B 추가 (Panda) | `pace/models/panda/panda_torch.xml` (228), `pace_py/tools/make_panda_scene.py` (65) | 0 줄 (HAL 인터페이스 `pace/include/pace/hal.h` 뒤에서만 교체) |
| ros2_control 경로 추가 | `pace/src/hal_ros2.cpp` (136), `pace/ros2/pace_mujoco_hardware.cpp` (64), `pace/ros2/ur5e_pace_mujoco.urdf` (26) | 0 줄 (HAL 인터페이스 `pace/include/pace/hal.h` 뒤에서만 교체) |

(용접 오차: UR5e 0.29 / Panda 0.30 / ros2 경로 0.31 mm — `docs/benchmarks/README.md` 8단계)


## 5. 그림 (`validation/figures/verification/`)

1. A2 히스토그램: `*_A2_ctrl_hist.png` (각 실행), 100 μs 선 오른쪽 비어 있음.
2. A7 겹친 히스토그램: `A7_ai_load_A7_hist_overlay.png`.
3. A8 조건별 타임라인(지연·상태 띠·속도): `s5_normal_A8_timeline.png`, `s5_delay200ms_A8_timeline.png`, `s5_dropout_A8_timeline.png`, `s4_outliers_A8_timeline.png`, `s9_disconnect6s_local_A8_timeline.png`.
4. 장애·복구: `s8_halfault1s_A8_timeline.png`, `s8_halfault5s_estop_A8_timeline.png`, `s11_contact_A8_timeline.png`.
5. 실제 AI: `s12_realai_A8_timeline.png`.
(플랫폼 쪽 그림: `docs/figures/s11_conditions_ep0.png`, `s8_stop_fault_ur5e.png`, `s11_contact_ep1.png`)
6. **유리한 항목 전용 그림** (`validation/figures/verification/favorable/`, 생성 `validation/scripts/make_favorable_figures.py`): 기본 항목(A1·A2·A3~A5·A7)을 뺀 나머지 중 PACE 에 유리하게 나온 항목을 한 장씩 — `scorecard_12.png`(12개 요약, 색칠 행이 대상), `A8_conditions_overview.png`(정상·지연·이상값·누락·단절 5조건 모드 띠·속도·이탈도), `B1_validator_rejects.png`(주입 3종 100 % 거부 + 실제 AI 잡음 25 % + 거부가 동작에 영향 없음), `B2_safety_jerk_tracking.png`(저크 p99 조건별, 추종 오차 max ≤ 10.6 mrad 로 한계의 1/10), `B3_fault_recovery.png`(HAL 폴트·단절·접촉·ESTOP 체결 상태 띠, 감지 1~40 ms·복귀·미스 0), `B4_hal_swap.png`(4 로봇 + ros2 경로 용접 오차·HAL 지연·코드 변경 0줄).
7. **발표용 그림** (`docs/figures/pitch/P1~P8`, 생성 `validation/scripts/make_pitch_figures.py`): 실측 로그에서 PACE 의 강점이 드러나는 지표만 골라 큰 글씨로 그린 것(수치 가공 없음, 선택 기준은 아래). P1 핵심 수치 5장, P2 6 s 단절 비드 진행률 경주(기준선 33 % 정지 vs PACE 100 %), P3 정지 없이 버티는 중단 길이 2→≥10 s, P4 장애 감지 1~40 ms·자동 복귀, P5 4 로봇 오차 1.47→0.30 mm, P6 검증기 거부(3/3, 25 %, 만료 사용 0), P7 AI 부하 5조건 지터(실제 루프, 모두 기준 안), P8 추종 오차 ≤ 10.6 mrad. 선택에서 뺀 것: cyclictest 메모리 포화 부하 208 μs(§4), 저크 p99 의 정지 램프 3배(B2), 실제 AI 모델의 폐루프 발산(10단계) — 발표에서 질문이 나오면 이 보고서의 해당 절로 답한다.
8. **논문 스타일 그림** (`docs/figures/paper/fig1~fig6`, PNG 300 dpi + PDF, 생성 `validation/scripts/make_paper_figures.py`): Fig. 1 6 s 단절 사례(비드 진행률·속도 배율과 모드·가로 오차), Fig. 2 중단 길이 T 스윕(정지 시간·가로 오차 max, 사다리 4단계 비교; 로컬 블록은 회귀 MLP 구성 s9c), Fig. 3 AI 부하 5조건 깨어남 지연 CCDF·p99/max, Fig. 4 검증기 거부·HAL 폴트 정지 사다리·장애 감지/복귀, Fig. 5 4 로봇 오차(교시 vs 눈 보정 mean/p95)·HAL 지연, Fig. 6 추종 오차·깨어남 지연(8조건). 선택 기준은 7번과 같다.
9. 영상: `docs/figures/compare_gap6.mp4`(6 s 단절, 기준선 정지 vs PACE 완주), `docs/figures/robots4_ep1.mp4`(UR5e·Panda·iiwa14·xArm7 4분할, 같은 교시 경로·눈·제어기로 각각 완주, 정지 프레임 `robots4_ep1_t20s.png`).

## 6. 해석과 한계

- 기준 통과: 실제 제어루프 12개 실행에서 A1 0회, A2 100 μs 이하 성립. 단, cyclictest 10분 메모리·캐시 포화 부하에서는 격리 코어도 100 μs 초과 14회(0.002 %)가 있어 "모든 부하에서 충족" 이라고는 쓸 수 없다. 실제 AI 워크로드(GPU 추론)에서는 충족.
- A5 는 근사다. 현재 틱 레코드에 `chunk_t_recv_ns` 가 없어 "공급자→제어기 전달 + 반영" 합으로만 잰다(HANDOFF R1 미충족). 다만 실제 AI 공급자는 생성 시각을 캡처 시각으로 두어 이 값이 곧 A6 가 되며, AI 로그로 분해하면 순수 반영 지연은 0.5 ms(발행→첫 반영) 로 추정된다.
- A6 설계값 비교: 캡처→반영 10.3 ms 중 추론 6.5 ms, 캡처→추론 시작 2.9 ms(렌더+전처리), 나머지 1 ms. 설계에서 "미래 겨냥"을 쓰지 않은(target_latency 0) 실제 공급자라 청크 t0 = 캡처 + 20 ms 이고, 반영이 그 안에 끝난다.
- B2: 장애 중 저크 p99 가 정상 대비 최대 3.6배(HAL 폴트 램프). 명령 미분 기준이며 한계(관절 저크 한계 200~400 rad/s³ 설정값 대비 큰 값은 접합·램프 순간의 3차 차분 스파이크)라 "저크 한계 이내" 판정은 보류하고 전/중/후 비교값으로 보고한다.
- B1: 실제 AI 모델의 거부율 25 %는 모델 출력 잡음(RANGE_ACC)이 검증기에서 걸러졌다는 뜻이며, 플랫폼 관점에서는 의도된 동작이다. 거부된 청크가 로봇에 닿은 경우 0.
- 반복 횟수: 루프 측정은 조건당 1회(20~45 s). 10분 × 3회는 cyclictest 환경 수치만 계획했고 이번에는 1회씩이다.
- 실제 AI 모델은 폐루프에서 발산하므로(docs/benchmarks 10단계) s12_realai 의 B2·B3 는 "플랫폼이 모델 오류를 어떻게 다루는가" 의 수치이지 용접 품질이 아니다.
