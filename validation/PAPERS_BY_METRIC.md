# 지표별 논문 읽기 가이드 — 실제 본문 내용 포함

작성일 2026-10-09. `METRICS.md`(A1~A8, B1~B4)와 `METRICS_EXPLAINED.md`(비전공자 설명)의 짝.
여기서는 각 지표마다 **① 읽을 논문 ② 정확히 어느 절·그림·표를 볼지 ③ 거기 실제로 뭐라고 쓰여 있는지(인용·숫자) ④ 우리 측정에 어떻게 옮길지**를 적는다.

본문을 직접 열어 확인한 논문: Cerqueira & Brandenburg 2013, Ye 2023, Teper 2022, Hofer 2020, Jiao 2026, RTC 2025, Ruan 2026, faultjector·ros2-resilience README.
본문을 열지 못한 것: Reghenzani 2019 서베이(사이트 봇 검증에 막힘 → 초록만), Puck & Keller 2021(IEEE 유료), 그 외 IEEE 논문.

---

## A1 제어주기 유지 (데드라인 미스) · A2 지터

### 논문 1. Cerqueira & Brandenburg, "A Comparison of Scheduling Latency in Linux, PREEMPT_RT, and LITMUS^RT" (OSPERT 2013)
PDF: https://people.mpi-sws.org/~bbb/papers/pdf/ospert13.pdf

**볼 곳**: §1(정의) → §2.1(cyclictest 동작) → §3 도입부(실험 설정) → §3.1~3.3(유휴/CPU/I-O 부하) → Fig. 3·4·5(히스토그램) → §4(cyclictest의 한계)

**실제 내용**
- **지연의 정의 (§1)**: 타이머나 장치 인터럽트가 발생한 뒤 ① 인터럽트 핸들러 진입 ② 깨울 태스크 식별 ③ 스케줄러 호출 ④ 문맥 교환의 네 단계를 거치므로 "even for the highest-priority task, there is always a delay between the activating event and the instant when the task starts executing. This delay, called scheduling latency, …" → **우리 A2의 정의와 같다.**
- **cyclictest 동작 (§2.1)**: 스레드마다 주기 타이머를 걸고 "resuming, measuring latency, and suspending"을 반복. 측정 끝에 히스토그램을 디스크에 쓴다.
- **실험 설정 (§3)**: 16코어 Intel Xeon X7550, 하이퍼스레딩·주파수 스케일링·딥 슬립 전부 비활성화, 트레이싱/디버그 커널 옵션 비활성화, cron 등 백그라운드 서비스 종료. cyclictest는 코어당 1스레드, SCHED_FIFO 99, 주기 1000μs부터 500μs씩 증가, `-m`(mlockall). **구성당 약 585만 샘플.**
- **부하 3종 (§3.1~3.3)**: (i) 유휴 (ii) CPU-bound: 코어마다 20 MiB 작업집합(L2 18 MiB보다 크게)에 무작위 메모리 접근하는 루프 → 캐시 미스 유발 (iii) I/O-bound: hackbench + bonnie++(direct I/O) + wget(1 Gb 네트워크 포화).
- **보고 형식**: 그림마다 1μs 간격 히스토그램, **y축 로그**, 그림 위에 `min / max / avg / median / stdev / samples total` 한 줄. 표 대신 히스토그램 6장을 나란히.
- **숫자 (Linux 3.8.13 + PREEMPT_RT)**: 유휴 max 11.20μs(avg 2.74) · CPU 부하 max 17.42μs(avg 3.40) · I/O 부하 max 44.16μs(avg 4.12). 같은 조건에서 PREEMPT_RT 없는 3.8.13은 I/O 부하에서 **max 5464μs**. bonnie++를 코어마다 띄우자 비RT 커널은 80~200 **ms** 스파이크, "the maximum observed scheduling latency under PREEMPT RT remained below 50µs even in this case."
- **cyclictest의 한계 (§4)**: "it treats the kernel and the underlying hardware as a black box and reports the actual cumulative impact of system overheads" — 최고 우선순위 태스크 하나의 지연만 보여주고 **원인은 알려주지 않는다.** 우선순위가 낮은 태스크나 IPI 같은 요소는 못 잡는다.

**우리에게 적용**
- 히스토그램 + 통계 한 줄 형식을 그대로 쓴다. `docs/benchmarks` 베이스라인 그림을 이 형식으로 다시 그린다.
- 부하 3종(유휴 / 캐시 압박 CPU / 인터럽트 폭주 I-O)은 A7 조건 설계의 원형. 우리는 여기에 **실제 GPU 추론**을 4번째로 추가.
- "cyclictest는 원인을 못 본다"는 한계가 **제어루프 로그를 따로 재야 하는 이유**다.

### 논문 2. Ye et al., "ROS2 Real-time Performance Optimization and Evaluation" (Chinese J. Mech. Eng. 2023, 오픈액세스)
https://link.springer.com/article/10.1186/s10033-023-00976-5

**볼 곳**: §2(환경, Table 1·2) → §3(최적화, Table 3) → §4.1(측정 방법, Fig. 6·7) → §4.2(네이티브 vs RT, Fig. 9·10, Table 4) → **§4.6(주기 지터 정의, 식 (3)(4), Fig. 24~27)** → §4.8(EtherCAT 1ms, Fig. 33)

**실제 내용**
- **환경 (§2)**: Ubuntu 22.04, 커널 5.15.55 + patch-5.15.55-rt48, ROS 2 Humble, Fast DDS, EtherCAT 마스터 1 + 슬레이브 16.
- **타이밍 API (§3)**: "clock_gettime(CLOCK_MONOTONIC, &ts_now)" 로 시각, "clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, …)" 로 절대시각 대기. 실시간 노드는 SCHED_FIFO, 비핵심 노드는 CFS. **우리 로그 포맷(CLOCK_MONOTONIC)과 동일.**
- **cyclictest가 재는 것 (§4.1, Fig. 6)**: "interrupt delay … between the occurrence of an interrupt and the start of the ISR, and scheduling latency … the time it takes for a task to obtain actual CPU usage after being awakened." 둘의 합.
- **네이티브 vs PREEMPT_RT (§4.2, Table 4)**: 부하는 `stress-ng -c 4 --cpu-method fft --timerfd-freq 1000000 -t 24h`. 네이티브: 242초 측정에 max **6243μs**, avg 3μs. PREEMPT_RT: 1000~3000Hz 스레드 5개, **25.7시간** 측정에 max **82μs**, avg 2μs. 본문은 "the timing jitter for a control cycle of 1 ms is usually required to be less than 200 µs"라고 관행 기준을 언급.
- **주기 지터의 두 가지 정의 (§4.6, Fig. 24)** — 이 논문의 가장 쓸모 있는 부분:
  - 절대 위치 오차 d_k = t_k − kT  (k번째 깨어난 시각 − 이상적 시각) → **우리 A2의 "지연"**
  - 주기 지터 P_k = t_{k+1} − t_k − T = d_{k+1} − d_k  (연속 두 주기의 간격 − T) → **"주기 흔들림"**
  - 10000주기, CPU 만부하. 네이티브 max 지터 >400μs(Fig. 25), PREEMPT_RT는 25~5000Hz 전부 max <60μs(Fig. 26), 히스토그램은 ±10μs 중심 정규분포 비슷(Fig. 27).
- **EtherCAT 1ms (§4.8, Fig. 33)**: 1613610 ms(약 27분) 동안 주기 min **982.5** / avg **999.8** / max **1022.4 μs**.

**우리에게 적용**
- A2는 d_k(지연)와 P_k(주기 지터) **둘 다** 보고한다. PDF의 "지터 ±100μs"는 P_k 기준으로도 읽힐 수 있다.
- 1ms 주기의 min/avg/max 표(§4.8 형식)를 우리 제어루프 로그로 똑같이 만든다. 비교 대상 숫자가 생긴다.
- 25.7시간 측정이 "최악값 신뢰"의 근거. 제출용 10분 외에 밤새 1회 돌린다.

### 논문 3. Hofer et al., "Industrial Control via Application Containers: Maintaining determinism in IAAS" (arXiv 2005.01890, 2020)
**볼 곳**: §4.1(실험 설계 문단) → §5.2(cyclictest + stress) → §5.2.1 Fig. 5(박스플롯과 기준선)

**실제 내용**
- "All variants … run the tests for at least one million firing loops." 그리고 "A total of ten million loops over multiple hours have been executed for each configuration."
- **합격선의 근거**: "Ideally, the maximum firing delay of the threads should stay below 1/10 of the cycle time" → Fig. 5에 100ms 주기용 10ms 선과 **1ms 주기용 100μs 선**을 그어 둠. **PDF의 ±100μs가 어디서 오는지 설명할 때 인용.**
- 통계: 모든 데이터에 min/max/avg/stdev, 성능 테스트에는 median·skew 추가. 10M 중 96회(0.00096%) 초과 같은 식으로 **초과 횟수와 비율**을 보고.
- 커널 파라미터(scheduler tick, scheduler isolation, RCU back-off CPUs)를 재부팅하며 바꿔 "A stable median, low average and standard deviation indicate ideal kernel configurations."

**우리에게 적용**: 최소 100만 회(1kHz로 17분), 제출용은 1000만 회(2.8시간)를 목표. "100μs = 주기의 1/10" 문장을 리포트 기준 설명에 넣는다.

### 논문 4. Reghenzani, Massari, Fornaciari, "The Real-Time Linux Kernel: A Survey on PREEMPT_RT" (ACM Computing Surveys 2019)
https://re.public.polimi.it/handle/11311/1076057 (오픈액세스. 이번에 사이트 봇 검증 때문에 본문 확인 못 함)
**볼 곳**: 초록 기준으로 — PREEMPT_RT가 커널에서 무엇을 바꾸는지, 지연 원인 분류, 측정 관행 절. 1단계 학습용 교과서로 읽되, 인용은 본문을 직접 확인한 뒤에.

---

## A3 AI 추론시간 · A4 추론 주기

전용 논문은 없고, 아래 두 논문의 "지연을 어떻게 정의하고 재는가" 부분을 쓴다.

### RTC — Black, Galliker, Levine, "Real-Time Execution of Action Chunking Flow Policies" (NeurIPS 2025, arXiv 2506.07339)
**볼 곳**: §2(지연 d의 정의) → §3.3 Algorithm 1(지연 예측) → §4.2(실제 지연 측정값) → Appendix A.3 Latency Measurements

**실제 내용**
- "d := ⌊δ/Δt⌋" — δ는 한 청크 생성 시간, Δt는 제어 주기. **추론시간을 제어 주기 단위로 환산**한 것이 "inference delay". 우리로 치면 A3 ÷ 1ms.
- Algorithm 1: 과거 관측된 지연 버퍼의 **최댓값**으로 다음 지연을 예측 → 우리 유효기간 설정의 근거(평균이 아니라 max).
- §4.2: π0.5, H=50, Δt=20ms, LAN 원격 추론이 10~20ms 추가, RTC 97ms vs 베이스라인 76ms.

### Ruan et al., "A Latency-Aware Framework for Visuomotor Policy Learning on Industrial Robots" (arXiv 2602.14255, 2026)
**볼 곳**: §3.1.1(지연 원인 세 가지) → §3.3.1·3.3.3(지연 측정 방법) → §4.3(지연 값)

**실제 내용**
- 지연을 **observation / inference / execution** 세 가지로 분해. "observation–execution gap"은 추론에 쓴 관측의 로봇 상태와 실행 시점 로봇 상태의 시간 불일치.
- 관측 지연 **82ms**는 카메라 앞에 QR코드 타임스탬프를 보여주고 찍힌 시각과 비교해 측정(§3.3.3). 실행 지연 **225ms**는 등속 궤적 명령 vs 추종 결과에 선형 모델을 맞춰 추정(§3.3.1). 로봇 피드백 83Hz.
- 추론 지연은 재지 않고 **100 / 300 / 500ms 고정 지연을 주입**(§4.3).

**우리에게 적용**: A3는 분포(avg/p99/max)로, A4는 발행 간격으로 보고하되, 추가로 **RTC처럼 제어 주기 단위 d**로도 환산해 적는다("추론 1회 = 제어 주기 8~15개"). 지연 주입 실험(A8 지연 조건)의 값은 Ruan처럼 **실측 A3의 1배/3배/5배** 정도로 잡는다.

---

## A5 제어 반영 지연 · A6 End-to-End 지연

### 논문 1. Teper et al., "End-To-End Timing Analysis in ROS2" (RTSS 2022)
PDF: https://daes.cs.tu-dortmund.de/storages/daes-cs/r/publications/teper_rtss_2022.pdf
**볼 곳**: **§III-C End-To-End Latencies(정의, Fig. 2·3)** → §VII Online End-To-End Analysis(측정 방법) → §VIII·IX(사례, Fig. 6·7). §VI 상한 증명은 건너뛴다.

**실제 내용**
- "In ROS2, each cause-effect chain … starts with a sensor node and ends with an actuator node."
- **Maximum reaction time**: "the maximum latency for an external signal to be processed by the actuator. For example, it is the largest interval between a user pressing a button to lock the car's doors and them actually being locked."
- **Maximum data age**: "the maximum duration between a sensor sampling and an output being based on that sample. For example, it is the maximum length between the current camera image sampling and the latest time at which the steering controls are based on that camera sample."
- **측정 방법 (§VII)**: 메시지 안에 "reaction time origin date"와 "data age origin date"라는 **타임스탬프 두 개를 실어 보내고**, 체인 끝(액추에이터)에서 현재 시각과의 차이를 구한다. "reaction time is updated before a send operation, while data age is updated before receive and send operations." 센서 타이머가 처음 실행될 때 두 origin을 현재 시각으로 찍는다.
- **결과 (§IX, Fig. 7)**: 카메라 수를 늘려 가며 under-utilized(합 WCET < 주기)와 over-utilized를 비교. "the under-utilized system performs much better than the over-utilized system … it is important that this state is never reached."

**우리에게 적용**
- **A6 = data age.** 우리 로그의 `ai_t_capture`가 Teper의 "data age origin date"다. 우리 `templates/control_loop_log_format.md`의 설계가 §VII의 방법과 같다는 것을 리포트에 적는다.
- A5는 그 체인의 **마지막 홉**(제어루프 수신 → 송출)만 떼어낸 것. Teper 용어로는 액추에이터 콜백의 response time.
- "over-utilized 상태에 절대 들어가면 안 된다"는 결론이 우리 1ms 루프의 **실행시간(t_cmd − t_wake) < 1ms** 를 별도 보고해야 하는 근거.

### 논문 2. Ye 2023 §4.3·§4.5 (위와 같은 논문)
**볼 곳**: §4.3(퍼블리셔→서브스크라이버 E2E, Fig. 11~19) → §4.5(프로세스 간 vs 공유메모리, Fig. 22·23)
- 측정 지점: "from the timing publish function of a single publishing node to the callback function of another subscribing node on the same computer." 10Hz, 크기별 120회, **중앙값** 보고.
- SCHED_FIFO + mlockall 적용. 네이티브 ROS 2는 64바이트에서도 800μs 넘게 튐(Fig. 17), PREEMPT_RT 후 최대 지연 대폭 감소(Fig. 18·19).
- **공유메모리(intra-process, zero-copy) vs DDS**: 작은 데이터는 비슷, 커질수록 공유메모리가 유리(Fig. 23). "DDS requires at least two message translations."
- 1KB 고정, 주파수별 120회: max <150μs(Fig. 31·32).

**우리에게 적용**: A6의 "전달" 구간(추론 끝 → 제어루프 수신)을 이 형식(크기별·주파수별 중앙값+최대)으로 잰다. 팀이 락프리 공유메모리를 택한 근거로 Fig. 23을 인용.

### 논문 3. Günzel et al., "On the Equivalence of Maximum Reaction Time and Maximum Data Age" (ECRTS 2023) — 결론만
초기 워밍업 뒤에는 두 값이 같다. 리포트에 둘 다 쓸 필요 없이 **data age 하나**로 보고해도 되는 근거.

### (못 연) Puck & Keller, IEEE CASE 2021
비실시간 객체 인식 → 실시간 제어(ROS 2 + EtherCAT) 구조에서 PTP 동기화와 오실로스코프로 외부 검증. 학교 IEEE 접근권으로 받아 보면 **측정 지점 설계의 본보기**. DBLP: CASE 2021 pp. 1670-1676.

---

## A7 AI 부하 유무 비교

### 논문 1. Jiao — Yen et al., "Bridging Isolation and Customization in Mixed Criticality Robotics" (arXiv 2605.03641, 2026)
**볼 곳**: §I(왜 PREEMPT_RT만으론 부족한가) → **§V-A(지표 정의)** → §V-B Table IV(수치) → Fig. 6(CCDF)·Fig. 7(초당 excursion)

**실제 내용**
- **지표 정의 (§V-A)**: EtherCAT 프레임 타임스탬프에서 Δt₂ = t[n] − t[n−2] (두 칸 차이로 주기 안/밖 간격 섞임 방지). 공칭 주기 = median(Δt₂). **signed jitter = Δt₂ − median.** 보고: σ, p99 |jitter|, p99.9, max, **"large excursion" = |jitter| > 50μs 횟수**, **missed cycle = Δt₂ > 2ms**. 10분 윈도우, 약 120만 프레임.
- **Table IV (baseline → Jailhouse 격리)**: σ 12.58 → 1.95μs · p99 69.0 → 7.8 · p99.9 101.0 → 13.2 · max 321.5 → 32.8 · >50μs 2.04%(24,442회) → 0.00% · missed 0 → 0. Fig. 2: ±10μs 안 비율 91.8% → 99.7%.
- **주장 (§I)**: "PREEMPT_RT makes Linux fully preemptible but provides no spatial isolation." "These mechanisms improve temporal scheduling but cannot prevent interference when perception and control contend for cache capacity, memory bandwidth, and thermal headroom."
- **주의**: 격리 수단은 Jailhouse 하이퍼바이저이고, PREEMPT_RT/Xenomai를 실험으로 비교하진 않았다. 캐시·대역폭 주장은 논증이지 측정이 아니다. 하드웨어는 ARM Cortex-A55.

**우리에게 적용**
- A7 표의 열을 Table IV와 똑같이 만든다: σ / p99 / p99.9 / max / >50μs(또는 >100μs) 횟수·비율 / missed. **"excursion 횟수"와 "비율" 둘 다.**
- 그림은 Fig. 6(CCDF, 로그 y)과 Fig. 7(초당 excursion 시계열)을 그대로 따라 한다. 특히 Fig. 7 형식은 "부하를 켠 시점"을 표시하기 좋다.
- 팀 README의 "CCX 통째 격리(L3 공유 안 함)"가 바로 이 논문의 cache capacity 논점에 대한 우리 답이다. 격리 단계별(없음/isolcpus/CCX) 비교가 **이 논문이 못 한 측정**이 된다.

### 논문 2. Cerqueira & Brandenburg §3.2 (위)
CPU-bound 부하를 "L2보다 큰 작업집합에 무작위 접근"으로 만든 이유: "cache misses and contention in the memory hierarchy." stress-ng 기본 옵션보다 **캐시를 때리는 부하**를 써야 한다는 근거. stress-ng라면 `--vm` 계열이나 `--cache`.

### 참고. MCIB (GitHub leizhou-ca/physical-ai-mixed-criticality)
벤치마크 사양. README 요점: 기존 도구(ros2_tracing, CARET)는 "어디서 시간이 갔나"를 보여주고, MCIB는 "왜 하드웨어가 느려졌나(캐시 축출/스케줄러/버스 포화)"를 판정하려 함. "P99.9 is not a safe WCET bound." **아직 데이터셋 미공개**, Raspberry Pi 4B 데모 수준. 방법론 참고만.

---

## A8 조건별 동작 시각화 · B3 장애 복구 시간

### 도구 1. ros2-resilience (hnaboulsi, ROS 2 Jazzy)
https://github.com/hnaboulsi/ros2-resilience
**볼 곳**: README "What It Does", "Results", `scenarios/dropout_burst.yaml`

**실제 내용**
- 시나리오: **dropout / latency / stale-hold / healthy-control**. YAML 계약에 "expected degradation, watchdog reason, recovery command, observed robot state, and deadlines"를 적고, 실행 결과를 JSON 증거로 남긴다.
- 핵심 철학: "Fault injection alone is not validation." 컴포넌트의 자기 보고가 아니라 **독립 스트림**(`/cmd_vel` 실제 관측)으로 복구를 확인. 가짜 복구 보고를 잡는 mutation test 포함.
- **결과 예시**: 20개 중 17개 드롭 → watchdog이 `loss_fraction_exceeded` 감지까지 **0.552 s**, 복구 명령 관측까지 **0.0070 s**, 로봇 정지 상태까지 **0.597 s**.

**우리에게 적용**: B3의 보고 형식이 이것이다. "감지 시간 / 복구 명령 시간 / 안전 상태 도달 시간" 세 숫자 + 그 사이 A1 미스 횟수. 시나리오를 YAML로 적고 결과를 JSON으로 남기는 구조를 `validation/configs`·`raw`에 그대로 쓴다.

### 도구 2. faultjector (roozyfx)
https://github.com/roozyfx/faultjector
**볼 곳**: README "Scenarios", "Faults" 표, "Limitations"
- 토픽 사이에 끼어들어 **delay(mean, jitter, distribution) / drop(probability 또는 every_nth) / duplicate / reorder / clock_skew** 주입. 시드 고정으로 결정적. `sweep` 명령으로 "navigation degrades past 125 ms of odometry delay"처럼 **허용 한계를 자동으로 찾음**.
- **주의**: README에 "Status: in development. Not yet usable." 그리고 "Message transport only. CPU starvation, thermal throttling … out of scope." 또 generic pub/sub라 zero-copy가 깨진다.
- 우리에게는 **설계 참고**(장애 종류 분류, YAML 시나리오 형식, sweep 개념)로만. 공유메모리 경로에는 못 쓰므로 자체 주입기가 필요.

### 논문. Ruan 2026 §3.4 (fallback) · RTC §4.2 (보호 정지)
- Ruan: 미래 액션이 없으면 "the system issues a safe fallback command by holding the previously commanded pose." → 우리 `hold` 상태의 선례.
- RTC §4.2: temporal ensembling 베이스라인은 +100/+200ms 지연에서 "protective stop"이 걸려 실행 자체가 실패. → **"장애 시 로봇이 보호정지에 걸렸는가"** 도 A8의 결과 항목으로 기록.

---

## B1 AI 출력 검증 거부율

전용 논문 없음. 아래에서 빌린다.
- **RTC Algorithm 1**: 지연 예측을 과거 지연의 max로. → 우리 유효기간(valid_until)을 A3의 max 기준으로 잡으면 "시간 검증" 거부가 정상 조건에서 0에 가까워야 한다는 기대치.
- **Ruan §3.4**: "Actions whose times have already passed are discarded." → **만료 결과 폐기**가 표준 관행. 폐기 횟수를 세는 것이 B1.
- **ros2-resilience "stale-hold" 시나리오**: 오래된 값을 붙잡고 있는 상황 자체를 장애로 정의. → B1의 "만료 결과 사용 0회" 검증은 이 시나리오로.
- ROS-RVFT 가이드라인 MTA1(https://ros-rvft.github.io/guidelines/guideline-mta1): "노이즈·장애 주입으로 강건성 향상" 권고.

---

## B2 안전 동작 (저크·추종 오차)

### Ruan 2026 — §4.4 Evaluation metrics, Table 1, Fig. 12~15
**실제 내용 (§4.4 정의)**
- Task duration: 동작 시작~완료.
- Idle ratio: TCP 속도 1 mm/s 미만인 시간 비율.
- Contact force: 힘 크기가 5 N 넘는 구간의 RMS.
- Force smoothness: 힘 크기 시간미분의 RMS.
- **Motion smoothness: "RMS of Cartesian jerk, penalizing start–stop behavior and abrupt velocity changes."**
- 조건: 지연 100/300/500ms × 전략 BE(블로킹)/NAE(단순 비동기)/LAE(지연 인지) × 20회.

**Table 1 중앙값 (일부, 원문 PDF로 재확인 권장)**
| 지표 | 기준 시연 | 100ms BE / NAE / LAE | 500ms BE / NAE / LAE |
|---|---|---|---|
| 접촉력 (N) | 73.98 | 231.71 / **319.71** / 37.99 | 42.72 / **329.32** / 45.28 |
| 힘 smoothness (N/s) | 136.06 | 807.67 / **1229.10** / 41.58 | 33.15 / **1153.26** / 33.03 |
| 모션 smoothness (m/s³) | 0.47 | 0.85 / 0.61 / **0.47** | 0.70 / 0.66 / **0.46** |

단순 비동기(NAE)는 접촉력이 기준의 4배, 힘 변화율이 9배. 지연 인지(LAE)는 저크가 시연과 같은 0.47.

**우리에게 적용**
- B2 지표를 "RMS 저크"와 "최대 저크" 둘 다로. Ruan은 RMS, 우리는 안전 관점이라 max도 필요.
- 비교 구조도 빌린다: 반영 정책 3종(도착 즉시 / 시간 인덱스 / 진행도 추적) × 지연 3단계 × N회. Ruan의 BE/NAE/LAE 표가 우리 정책 비교표의 원형.
- RTC Appendix A.2는 "maximum acceleration"을 jerkiness 대용으로 씀. 미분 세 번이 노이즈로 불안하면 **최대 가속도**로 대체 가능하다는 선례.

---

## B4 HAL 교체 비용

이번에 본문을 연 논문 없음. 후보:
- "ros2 fanuc interface" (arXiv 2506.14487, 오픈): ros2_control hardware interface를 실제 로봇에 붙여 평가. 어떤 항목을 평가했는지 §Evaluation을 볼 것.
- Ye 2023 §4.8: EtherCAT 마스터 주기 min/avg/max 표 → HAL 아래 계층의 지연 보고 형식.

---

## 지표 → 논문 → 볼 곳 한눈표

| 지표 | 1순위 | 볼 곳 | 2순위 | 볼 곳 |
|---|---|---|---|---|
| A1 | Ye 2023 | §4.6 식(3)(4), §4.8 Fig.33 | Jiao | §V-A "missed cycle" |
| A2 | Cerqueira&Brandenburg | §3, Fig.3-5, §4 | Ye 2023 / Hofer | §4.2 Table 4 / §5.2 "1/10 of cycle" |
| A3 | RTC | §2 d 정의, Alg.1 | Ruan | §3.1.1, §3.3 |
| A4 | RTC | §4.2 | — | |
| A5 | Teper 2022 | §III-C, §VII | Ye 2023 | §4.3, §4.5 Fig.23 |
| A6 | Teper 2022 | §III-C data age, §VII | Günzel 2023 | 결론 |
| A7 | Jiao | §V-A, Table IV, Fig.6-7 | Cerqueira&Brandenburg | §3.2 CPU-bound 설계 |
| A8 | ros2-resilience | README Results, scenarios/ | faultjector | Faults 표, Limitations |
| B1 | Ruan | §3.4 discard/hold | ros2-resilience | stale-hold |
| B2 | Ruan | §4.4, Table 1, Fig.12-15 | RTC | App. A.2 |
| B3 | ros2-resilience | Results 3개 숫자 | Jiao | missed cycle 동시 보고 |
| B4 | ros2 fanuc interface | Evaluation | Ye 2023 | §4.8 |

## 읽을 때 쓸 메모 양식 (논문당 1파일, `reports/paper_notes/`)
```
- 제목 / 저자 / 연도 / 링크
- 우리 지표 번호:
- 그들이 잰 것 (지표 이름, 정의식):
- 어떻게 잰 것 (도구, 타임스탬프 위치, 반복 횟수, 지속시간, 부하):
- 어떻게 보고한 것 (표 열, 그래프 종류, 축 스케일):
- 숫자 (우리와 비교할 것):
- 가져올 것 / 다르게 할 것:
- 주의할 점 (측정 안 한 주장, 다른 하드웨어 등):
```
