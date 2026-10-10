# 성능지표별 참고 논문 목록 (1차, 2026-10-09)

`METRICS.md` 의 지표 번호(A1~A8, B1~B4)에 대응. ★ = 먼저 읽을 것, ○ = 여유 있을 때.
난이도: 하(개념·수치 위주) / 중(수식 일부) / 상(스케줄링 이론).
각 논문에서 "무엇을 뽑아 올지"를 적어 두었으니 그 부분만 찾아 읽어도 된다.

---

## 그룹 1. 제어주기·지터 측정 방법론 (A1, A2, A7)

| | 논문 | 연도·출처 | 난이도 | 왜 읽나 / 뽑아 올 것 |
|---|---|---|---|---|
| ★ | Reghenzani, Massari, Fornaciari, **"The Real-Time Linux Kernel: A Survey on PREEMPT_RT"** | ACM Computing Surveys 52(1), 2019. 오픈액세스: https://re.public.polimi.it/handle/11311/1076057 | 중 | PREEMPT_RT가 무엇을 바꾸는지, 지연의 원인 분류, 측정 관행. 1단계 학습의 교과서. 1~3장과 측정 관련 절만 |
| ★ | Cerqueira, Brandenburg, **"A Comparison of Scheduling Latency in Linux, PREEMPT_RT, and LITMUS^RT"** | OSPERT 2013. https://people.mpi-sws.org/~bbb/papers/pdf/ospert13.pdf | 중 | cyclictest로 지연을 재고 **결과를 어떻게 표·그래프로 제시하는지**의 학술 표준. 부하 조건 설계(유휴/CPU/메모리/IO)와 히스토그램·최대값 보고 방식을 그대로 따라 하면 된다 |
| ★ | Ye et al., **"ROS2 Real-time Performance Optimization and Evaluation"** | Chinese J. Mech. Eng. 2023. https://cjme.springeropen.com/articles/10.1186/s10033-023-00976-5 | 하~중 | 우리와 가장 비슷한 구성(PREEMPT_RT + ROS 2 + EtherCAT 1ms). 1000μs 주기에서 min 982.5 / avg 999.8 / max 1022.4 μs 보고. **"주기 자체의 분포"를 보고하는 형식**과 QoS·DDS가 지터에 미치는 영향 |
| ○ | Hofer et al. (arXiv 2005.01890), **"Industrial Control via Application Containers: Maintaining determinism in IAAS"** | 2020. https://arxiv.org/pdf/2005.01890 | 중 | 일반 Ubuntu / Xenomai / PREEMPT_RT 비교. "최소 100만 회 반복" 같은 측정 길이 기준의 근거 |
| ○ | Linux Foundation RT wiki, cyclictest 문서 | https://wiki.linuxfoundation.org/realtime/documentation/howto/tools/cyclictest/start | 하 | 논문은 아니지만 옵션 의미와 결과 해석의 1차 출처 |

**이 그룹에서 정할 것**: 측정 길이(반복 횟수), 부하 조건 목록, 보고 통계량(min/avg/p99/p99.9/max + 히스토그램), "주기"를 보고할지 "지연"을 보고할지(둘 다).

---

## 그룹 2. 반영 지연·End-to-End 지연 정의 (A5, A6)

| | 논문 | 연도·출처 | 난이도 | 왜 읽나 / 뽑아 올 것 |
|---|---|---|---|---|
| ★ | Teper et al., **"End-To-End Timing Analysis in ROS2"** | RTSS 2022. https://daes.cs.tu-dortmund.de/storages/daes-cs/r/publications/teper_rtss_2022.pdf | 상 (정의 부분만 중) | E2E 지연의 두 가지 공식 정의: **reaction time**(외부 신호 → 액추에이터 반영까지 최대 시간)과 **data age**(센서 샘플 → 그 샘플에 기반한 액추에이션까지 최대 시간). 우리 A6는 data age, A5는 그 마지막 구간. 정의 절(2~3장)만 읽고 증명은 건너뜀 |
| ★ | Puck, Keller, **"Performance Evaluation of Real-Time ROS2 Robotic Control in a Time-Synchronized Distributed Network"** | IEEE CASE 2021. https://ieeexplore.ieee.org/document/9551447/ | 하~중 | **비실시간 객체 인식 → 실시간 제어(ROS 2 + EtherCAT)** 라는 우리와 같은 구조에서 E2E를 잰 실험 논문. 오실로스코프로 외부 검증한 방법, PTP 시각 동기화. 측정 지점 설계의 본보기 |
| ○ | Günzel et al., **"On the Equivalence of Maximum Reaction Time and Maximum Data Age for Cause-Effect Chains"** | ECRTS 2023. https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.ECRTS.2023.10 | 상 | 두 정의가 결국 같다는 증명. 결론만 알면 됨 (리포트에 둘 중 하나만 보고해도 되는 근거) |
| ○ | Teper et al., **"End-To-End Timing Analysis and Optimization of Multi-Executor ROS 2 Systems"** | RTAS 2024. https://daes.cs.tu-dortmund.de/storages/daes-cs/r/Bilder/Beschaeftigte/Harun_Teper/preprint_rtas_2024_teper.pdf | 상 | executor 여러 개일 때. 우리 플랫폼이 ROS 2 executor를 쓰면 참고 |
| ○ | **"A Survey of Real-Time Support, Analysis, and Advancements in ROS 2"** | LITES / arXiv 2601.10722, 2026. https://arxiv.org/html/2601.10722v1 | 중 | ROS 2 실시간 관련 문헌 지도. 더 찾을 때 출발점 |
| ○ | **"Uncovering Underexplored Runtime Behaviors in ROS2-Based Autonomous Systems"** | ACM 2025. https://dl.acm.org/doi/pdf/10.1145/3772083 | 중 | ros2_tracing 으로 cause-effect chain 을 **실측**하는 방법. 도구 선택 참고 |

**이 그룹에서 정할 것**: A5·A6의 정확한 정의(어느 타임스탬프에서 어느 타임스탬프를 빼는가)를 Teper 용어로 표현, 측정 지점이 Puck & Keller 와 대응되는지 확인.

---

## 그룹 3. AI 추론과 실시간 제어의 간섭·격리 (A3, A4, A7)

| | 논문 | 연도·출처 | 난이도 | 왜 읽나 / 뽑아 올 것 |
|---|---|---|---|---|
| ★ | Yen et al., **"Jiao: Bridging Isolation and Customization in Mixed Criticality Robotics"** | arXiv 2605.03641, 2026 (Infocom'26 워크숍). https://arxiv.org/abs/2605.03641 | 중 | 인식 워크로드와 1kHz 제어 루프를 같은 칩에서 돌릴 때의 간섭 실측. **보고 지표가 우리와 거의 같다**: cycle-period jitter, p99 \|jitter\| (69.0 → 7.8μs), 50μs 초과 excursion 횟수. PREEMPT_RT만으로는 캐시·메모리 대역 경합을 못 막는다는 주장 → 팀 README의 "CCX 격리" 근거 |
| ★ | Zhou, **MCIB: Mixed-Criticality Interference Benchmark** (오픈소스 벤치마크 사양) | GitHub, 2026. https://github.com/leizhou-ca/physical-ai-mixed-criticality | 중 | AI 추론 vs 실시간 제어 간섭을 재는 **벤치마크 설계 사양**. 간섭 채널 분류(캐시/버스/스케줄러), 결과 스키마, "p99.9는 안전한 WCET 상한이 아니다" 같은 교훈. 주의: 아직 데이터셋 미공개, 방법론 참고용 |
| ○ | **"Survey on safe robot control via learning"** | arXiv 2501.01432, 2025. https://arxiv.org/pdf/2501.01432 | 중 | 자원 경합, WCET 추정, 하이퍼바이저/메모리 격리(Jailhouse, MemGuard) 개관 |
| ○ | Seeed Jetson Orin PREEMPT_RT 테스트 (벤더 자료) | https://wiki.seeedstudio.com/deploy_preempt_rt_kernel_with_prebuilt_deb_package_on_recomputer_jetson/ | 하 | 논문 아님. 일반 커널 max 1909μs vs RT 커널 비교, 1kHz EtherCAT 루프 + CPU 부하. 우리 베이스라인(592/1325μs)과 비슷한 패턴의 참고 수치 |

**이 그룹에서 정할 것**: 부하 조건을 "stress-ng" 로 끝내지 말고 **실제 GPU 추론**을 돌리며 재야 하는 이유, excursion 임계값(50μs? 100μs?) 선택.

---

## 그룹 4. 비주기 AI 결과를 주기 제어에 반영하는 방식 (A5, B2 — 팀 PACE 핵심과 직결)

| | 논문 | 연도·출처 | 난이도 | 왜 읽나 / 뽑아 올 것 |
|---|---|---|---|---|
| ★ | Black, Galliker, Levine, **"Real-Time Execution of Action Chunking Flow Policies"** (RTC) | NeurIPS 2025 / arXiv 2506.07339. https://arxiv.org/abs/2506.07339 | 중 | 추론 지연 동안 실행될 액션은 고정하고 나머지만 새로 채우는 방식. 팀의 "진행도 추적 반영 정책"과 비교 대상. **지연을 인위적으로 늘려 가며 성능 저하를 재는 실험 설계** 를 참고 |
| ★ | **"A latency-aware framework for visuomotor policy learning on industrial robots"** | ScienceDirect 2026. https://www.sciencedirect.com/science/article/pii/S1474034626009006 | 중 | 산업용 로봇에서 100~500ms 추론 지연 하에서 부드러움·접촉력 유지. "naive asynchronous execution 은 접촉력 오버슈트" → **B2(저크·오버슈트) 지표의 근거** |
| ○ | **RT-HCP** "Dealing with Inference Delays and Sample Efficiency…" | arXiv 2509.06714. https://arxiv.org/html/2509.06714 | 중 | "마지막 액션 유지(hold-last-action)" 베이스라인의 한계 서술 → 우리 예외처리(hold → decel)와 비교 |
| ○ | **REMAC** "Real-Time Robot Execution with Masked Action Chunking" | arXiv 2601.20130. https://arxiv.org/html/2601.20130 | 중 | 추론 지연을 정책 입력으로 넣는 방식. 반영 정책 비교 실험의 후보 |

**이 그룹에서 정할 것**: 반영 정책 비교 실험(도착 즉시 / 시간 인덱스 / 진행도 추적)의 평가 지표를 RTC 논문의 지표(추종 오차, 성공률, 지연 스윕)와 맞출지.

---

## 그룹 5. 장애 주입·안전 동작·복구 (A8, B1, B2, B3)

| | 논문·도구 | 연도·출처 | 난이도 | 왜 읽나 / 뽑아 올 것 |
|---|---|---|---|---|
| ★ | **faultjector** (ROS 2 메시지 스트림 장애 주입기) | GitHub. https://github.com/roozyfx/faultjector | 하 | 지연·드롭·중복·순서 바꿈을 토픽 사이에 끼워 넣는 도구. **A8 장애 주입 구현의 출발점** |
| ★ | **ros2-resilience** (ROS 2 Jazzy 회복력 테스트 하네스) | GitHub. https://github.com/hnaboulsi/ros2-resilience | 하 | dropout / latency / stale-hold 시나리오 + 감지·복구·안전상태 **독립 검증** 구조. 우리 ROS 2 Jazzy 와 버전 일치 |
| ○ | **ros2_fault_injection** (C++) | GitHub. https://github.com/reeceholland/ros2_fault_injection | 하 | joint state 등에 drop/delay/bias/noise 주입 + 시나리오 assertion |
| ○ | **"Failing Gracefully: Mitigating Impact of Inevitable Robot Failures"** | arXiv 2608.05313, 2026. https://arxiv.org/pdf/2608.05313 | 중 | 장애 "예방"이 아니라 장애 "후 완만한 저하" 관점. B3 복구 지표의 논리 |
| ○ | **"Fault-tolerant control strategies for industrial robots: state of the art…"** | Artificial Intelligence Review 2025. https://link.springer.com/article/10.1007/s10462-025-11327-2 | 중 | 산업용 로봇 내고장 제어 개관. 리포트 관련연구 절용 |
| ○ | **"Runtime Verification and Field Testing for ROS-Based Robotic Systems"** / ROS-RVFT 가이드라인 MTA1 | arXiv 2404.11498. https://ros-rvft.github.io/guidelines/guideline-mta1 | 하 | "노이즈·장애 주입으로 강건성 검증" 가이드라인. B1 검증 지표 설계 근거 |
| ○ | Hu, **"Permissive Safety Through Trusted Inference…"** | arXiv 2606.02562, 2026. https://arxiv.org/abs/2606.02562 | 상 | "지연되거나 틀린 추론이 안전 실패로 이어진다"는 문제 정의. 서론만 |

**이 그룹에서 정할 것**: 5개 장애 조건 각각의 주입 방법(도구 vs 자체 구현), B2 저크 한계값, B3 복구 시간 측정 시작·끝 기준.

---

## 그룹 6. HAL·ros2_control·EtherCAT (B4)

| | 논문 | 연도·출처 | 난이도 | 왜 읽나 / 뽑아 올 것 |
|---|---|---|---|---|
| ○ | **"A Real-Time Software Framework for Multi-axis Robotic Systems Using ROS 2 and EtherCAT"** | IEEE 2025. https://ieeexplore.ieee.org/document/10895565/ | 중 | PREEMPT_RT 위 ROS 2 + EtherCAT 프레임워크와 실시간 실험. HAL 계층 설계·측정 참고 |
| ○ | **"ros2 fanuc interface: Design and Evaluation of a Fanuc CRX Hardware Interface in ROS2"** | arXiv 2506.14487. https://arxiv.org/pdf/2506.14487 | 하 | ros2_control hardware interface 를 실제 로봇에 붙이고 **평가한** 사례. B4 "교체 비용" 서술 방식 |
| ○ | **"Develop Real-Time Robot Control Architecture Using ROS and EtherCAT"** | MDPI Actuators 2017. https://www.mdpi.com/2076-0825/10/7/141 | 하 | 고해상도 타이머로 주기·실행시간을 재는 고전적 방법. 250μs 주기 달성 |

---

## 추천 읽기 순서 (성능평가 담당, 4주)

| 주 | 읽을 것 | 로드맵 단계 | 산출물 |
|---|---|---|---|
| 1 | Reghenzani 1~3장 → Cerqueira&Brandenburg 전체 → Ye 2023 결과 절 | 1~2단계 | "지터 측정·보고 방법" 1쪽 요약, 측정 길이·부하 조건 결정 |
| 2 | Teper RTSS 2022 정의 절 → Puck&Keller 전체 → ROS 2 실시간 서베이 훑기 | 3단계 | A5·A6 정의 확정, 타임스탬프 지점 확정 (templates/control_loop_log_format.md 갱신) |
| 3 | Jiao 전체 → MCIB README·spec → RTC 실험 절 → latency-aware visuomotor 결과 절 | 3~4단계 | A7 부하 조건 설계, B2 저크 지표 정의, 반영 정책 비교 실험 지표 |
| 4 | faultjector·ros2-resilience README → Failing Gracefully 서론 → RVFT MTA1 | 4~5단계 | 5개 장애 조건 주입 계획, B1·B3 측정 기준 |

## 읽으면서 채울 양식 (논문 1편당)

```
- 제목 / 저자 / 연도 / 링크
- 우리 지표 번호:
- 그들이 잰 것 (지표 이름, 단위):
- 어떻게 잰 것 (도구, 타임스탬프 위치, 반복 횟수, 지속시간):
- 어떻게 보고한 것 (표 형식, 그래프 종류, 통계량):
- 숫자 (비교용):
- 우리가 가져올 것 / 다르게 할 것:
```
→ 이 양식으로 쓴 메모는 `validation/reports/paper_notes/` 에 논문당 1파일.

## 검색 중 확인된 공백

- "AI 추론 + 1kHz 제어 + PREEMPT_RT" 를 한 번에 평가한 동료심사 논문은 못 찾음. Jiao(2026)와 MCIB가 가장 가깝고 둘 다 매우 최근. 우리 결과가 이 공백을 채우는 데이터가 될 수 있다는 점을 리포트에 쓸 수 있음.
- ROS 2 장애 주입은 도구는 많으나 "지연·드롭·이상값을 함께 평가한 지표 체계" 논문은 없음. 우리가 정의해야 함.
- 용접 용융풀 적응제어 쪽 논문은 아직 검색 안 함 (도메인 배경, 2차 조사 대상).
