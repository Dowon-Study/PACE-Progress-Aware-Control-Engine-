# 성능측정 연동 요청서 — 플랫폼·모델 개발자용

작성: 성능평가 담당 · 2026-10-09 · 대상: 플랫폼(제어루프·HAL)·AI 모델 담당자
한 줄 요약: **과제 4의 채점은 "숫자"로 되고, 그 숫자는 플랫폼이 남기는 로그에서만 나온다. 아래 로그와 훅 6가지를 코드에 넣어 주면 나머지(측정·분석·그림·리포트)는 내가 한다.**

---

## 0. 왜 이 요청이 필요한가 (1분)

출제 PDF "제안 한마디": *AI 정확도보다 추론 결과가 제어에 반영되는 과정의 실시간성·안정성·확장성을 중점 평가.*
산출물 3개 중 하나가 "정량 벤치마크 결과"이고, 나머지 둘(설계서·시연)도 숫자로 뒷받침돼야 한다.
PDF가 직접 요구하는 숫자: 제어주기 1ms · 지터 ±100μs · AI 추론시간 · 추론 주기 · **제어 반영 지연** · End-to-End 지연 · AI 부하 유무 비교 · 정상/지연/통신단절 조건별 동작 시각화.
이 숫자들은 전부 **타임스탬프 뺄셈**이다. 타임스탬프가 코드에 없으면 측정 자체가 불가능하다. 나중에 넣으면 제어루프를 다시 손대야 하므로 **처음 짤 때** 넣어 달라는 요청이다.

---

## 1. 요청 사항 (체크리스트)

| # | 요청 | 왜 | 우선순위 |
|---|---|---|---|
| R1 | 제어루프 매 주기 로그 (§2.1 열) | A1 주기 미스, A2 지터, A5 반영 지연, A6 E2E, B2 저크 | **필수, 최우선** |
| R2 | AI 계층 추론 1회당 로그 (§2.2 열) | A3 추론시간, A4 추론 주기, A6 구간 분해 | **필수** |
| R3 | `ai_state` 상태 이름 고정: `fresh / hold / decel / stop / reject` + reject 사유 열 `reject_reason ∈ {range, time, validity}` | A8 상태 띠, B1 거부율, B3 복구 시간 | **필수** |
| R4 | 장애 주입 훅: AI 결과가 공유메모리에 쓰이기 **직전**에 끼울 수 있는 함수 자리 1개 + 주입 이벤트 로그 (§2.3) | A8 5조건, B1~B3 | 필수 (데모 요구사항이기도 함) |
| R5 | HAL 변환 함수 진입·탈출 타임스탬프 2개 | B4 HAL 변환 지연 | 권장 |
| R6 | 실행 방법 1줄 + 버전 식별자(git hash)를 로그 헤더에 | 재현성 | 권장 |

### 지켜야 할 제약 (측정이 측정을 망치지 않도록)
- 모든 시각은 **`clock_gettime(CLOCK_MONOTONIC)`**, 단위 **ns, 정수**. AI 프로세스와 제어 프로세스가 같은 시계를 써야 뺄셈이 성립한다.
- 제어루프 안에서 **파일 I/O 금지, 동적 할당 금지, printf 금지.** 메모리 **링버퍼**에 숫자만 쌓고, 종료 시 또는 별도 저우선순위 스레드가 CSV로 내보낸다. (Cerqueira & Brandenburg 2013 §2.4, Ye 2023 §3 관행)
- 제어루프 스레드: `SCHED_FIFO` 우선순위 99, `mlockall`, CPU 4 고정, `clock_nanosleep(TIMER_ABSTIME)`로 절대시각 대기. 상대 대기(`nanosleep(1ms)`)는 오차가 누적되므로 쓰지 않는다.
- 로그 CSV 첫 줄들은 `#` 메타데이터: `version, kernel, cmdline, governor, load, cmd, start`.

---

## 2. 로그 포맷 약속 (열 이름을 그대로 써 주면 내 스크립트가 바로 돈다)

### 2.1 제어루프 로그 `*_ctrl.csv` — 매 주기 1행 (1kHz면 초당 1000행)

| 열 | 타입 | 찍는 위치 | 쓰는 지표 |
|---|---|---|---|
| `iter` | int | 반복 번호 | A1 |
| `t_expected_ns` | int | 이번 주기에 깨어났어야 할 절대 시각 (= 직전 + 1,000,000) | A1 A2 |
| `t_wake_ns` | int | `clock_nanosleep` 복귀 직후 | A1 A2 |
| `t_cmd_ns` | int | HAL/시뮬레이터로 명령 송출 직후 | A5 A6, 실행시간 |
| `ai_seq` | int | 이번 주기에 **사용 중인** AI 결과 일련번호 (없으면 -1) | A5 A6 |
| `ai_t_capture_ns` | int | 그 결과의 센서 캡처 시각 (AI 로그에서 그대로 전달) | A6 |
| `ai_t_recv_ns` | int | 그 결과를 제어루프가 **처음 읽은** 시각 | A5 |
| `ai_state` | str | `fresh/hold/decel/stop/reject` | A8 B1 B3 |
| `reject_reason` | str | `range/time/validity`, 거부 아닐 땐 빈칸 | B1 |
| `q_ref` | float | 기준 위치 (다축이면 `q_ref_0..n`) | B2 |
| `q_act` | float | 실측 위치 | B2 |
| `v_cmd` | float | 명령 속도 | B2 |

### 2.2 AI 계층 로그 `*_ai.csv` — 추론 1회당 1행

| 열 | 찍는 위치 |
|---|---|
| `seq` | 결과 일련번호 (ctrl의 `ai_seq`와 매칭) |
| `t_capture_ns` | 센서/이미지 캡처 시각 (카메라 드라이버 타임스탬프 또는 읽은 직후) |
| `t_infer_start_ns` | 모델 forward 직전 |
| `t_infer_end_ns` | forward 직후 (GPU면 동기화 후) |
| `t_publish_ns` | 공유메모리/토픽에 쓴 직후 |
| `valid_until_ns` | 유효기간 만료 시각 |
| `confidence` | 신뢰도 |

### 2.3 장애 주입 로그 `*_fault.csv` — 이벤트 1건당 1행
`t_ns, kind ∈ {delay, drop, outlier, disconnect, recover}, param`
주입기는 내가 만들 수 있다. 필요한 건 **R4의 훅 자리**와, `disconnect`를 흉내 낼 방법(heartbeat 갱신 중단 등) 합의.

### 2.4 HAL 로그 (R5) `*_hal.csv`
`iter, t_hal_in_ns, t_hal_out_ns`

전체 정의와 E2E 계산식: `validation/templates/control_loop_log_format.md`

---

## 3. 이 로그로 무엇이 계산되나 (지표 12개 요약)

| # | 지표 | 계산 | 합격 기준 |
|---|---|---|---|
| A1 | 제어주기 미스 | `t_wake − t_expected > 1ms` 횟수 | 0회 |
| A2 | 지터 | `t_wake − t_expected`의 max, p99.9, 100μs 초과 횟수 (cyclictest와 나란히) | max ≤ 100μs |
| A3 | 추론시간 | `t_infer_end − t_infer_start` 분포 | 보고 |
| A4 | 추론 주기 | 연속 `t_publish` 간격 | 보고 |
| A5 | 제어 반영 지연 | `ai_seq`가 바뀐 주기의 `t_cmd − ai_t_recv` | 보고 (PDF 3회 언급, 핵심) |
| A6 | E2E | 같은 주기의 `t_cmd − ai_t_capture`, 4구간 분해 | 보고 + 설계값 비교 |
| A7 | 부하 비교 | A1·A2를 idle/stress/ai-gpu/full 조건에서 반복 | 부하 있어도 A1·A2 유지 |
| A8 | 조건별 시각화 | 정상/지연/누락/이상값/통신단절 5조건 시계열 | 급격한 동작 없음 |
| B1 | 검증 거부율 | `ai_state==reject` 횟수·사유별, 만료 결과 사용 횟수 | 만료 사용 0회 |
| B2 | 안전 동작 | 장애 전·중·후 최대 저크, 추종 오차 | 저크 한계 이내 |
| B3 | 복구 시간 | 장애 주입 → hold → decel → stop → fresh 각 구간 | 그 사이 미스 0 |
| B4 | HAL 교체 비용 | 로봇 교체 시 변경 줄 수, `t_hal_out − t_hal_in` | 보고 |

상세 정의·근거 문구: `validation/METRICS.md` / 비전공자 설명: `validation/METRICS_EXPLAINED.md`

---

## 4. 역할 분담과 측정 사이클

```
[개발자]  실행 가능한 빌드 + 로그 3종 + 버전 식별자 전달
   ▼
[성능]    configs/ 조건 기록 → 체크리스트 → 측정 → raw/ 저장 → scripts/ 분석 → figures/ → reports/
   ▼
[팀]      리포트 리뷰 → 설계 수정 → 다음 사이클
```

- 모델이 나오기 전에 성능 쪽이 먼저 하는 것: cyclictest + stress-ng로 A2·A7(idle/stress) 베이스라인, 공용 통계·그림 스크립트.
- 개발자에게서 로그가 오는 순간: A1, A3~A6는 같은 스크립트로 즉시 산출. A8·B1~B3는 R4 훅이 있어야 가능.
- 측정 환경(이미 적용됨): PREEMPT_RT 6.8.1-realtime, CCX 격리 CPU 4-7/20-23, 제어루프는 CPU 4. 부하·AI·MuJoCo·ROS 2는 CPU 8-15/24-31. 상세: `docs/ENVIRONMENT.md`

---

## 5. 결과물 예시

A8(누락 조건) 그림 예시: `validation/figures/example_A8_drop.png` (합성 데이터, 생성 코드 `validation/scripts/plot_a8_example.py`)
4단 구성: ① AI 결과 도착 점 + 장애 구간 음영 ② `ai_state` 색 띠 ③ `q_ref` vs `q_act` ④ `v_cmd`. 여기서 B2(추종 오차·저크)와 B3(t0~t5 구간 시간)를 읽는다.
**이 그림이 그려지려면 §2.1의 `ai_state`, `q_ref`, `q_act`, `v_cmd`와 §2.3 장애 로그가 있어야 한다.**

A7 결과표 형식 (Jiao 2026 Table IV 방식):
`조건 | 격리 | avg | p99 | p99.9 | max | 100μs 초과 | 미스` — 조건 4 × 격리 3 × 3회.

---

## 6. 합의가 필요한 것 (답 주세요)

1. `ai_state` 다섯 이름과 전이 규칙(유효기간 만료 → hold, hold 타임아웃 → decel, 새 유효 결과 → 블렌딩 복귀)이 설계와 맞는가? 추가 상태가 있나?
2. 검증 3단계(범위 → 시간 → 유효성)의 순서와 각 단계 기준값(관절 한계, 유효기간 ms, 신뢰도 임계)은?
3. R4 훅 위치: AI 프로세스 쪽(발행 직전)인지 제어 프로세스 쪽(읽기 직후)인지. `disconnect` 흉내 방법.
4. 다축이면 `q_ref_0..n` 열 수. 단일 축 데모면 1열.
5. 유효기간 `valid_until` 설계값. (내가 잰 A3 max와 비교해 적정성 보고)
6. 로그 내보내기 방식: 종료 시 일괄 vs 별도 스레드 주기적. 10분 측정이면 60만 행 × 12열이라 링버퍼 크기 합의.

---

## 7. 참고 (근거가 필요할 때)
- 지연 정의·보고 형식: Cerqueira & Brandenburg, OSPERT 2013 §1, §2.1, Fig. 3-5
- 1ms 주기 지터 정의(d_k, P_k)와 EtherCAT 1ms 실측: Ye et al., CJME 2023 §4.6, §4.8
- 반영 지연·E2E 정의(reaction time / data age), 메시지 내 타임스탬프 측정법: Teper et al., RTSS 2022 §III-C, §VII
- AI 부하 간섭 지표(σ, p99, excursion, missed cycle): Yen et al. "Jiao", arXiv 2605.03641 §V-A, Table IV
- 저크·접촉력 평가 지표: Ruan et al., arXiv 2602.14255 §4.4
- 장애 주입·복구 검증 하네스: ros2-resilience (ROS 2 Jazzy)
- 논문별 상세: `validation/PAPERS_BY_METRIC.md`
