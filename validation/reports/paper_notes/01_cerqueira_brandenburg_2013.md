# 논문 노트 01 — Cerqueira & Brandenburg, "A Comparison of Scheduling Latency in Linux, PREEMPT_RT, and LITMUS^RT" (OSPERT 2013)

- 링크: https://people.mpi-sws.org/~bbb/papers/pdf/ospert13.pdf
- 우리 지표: **A2 지터(정의·보고 형식)**, A7 부하 조건 설계, A1 간접
- 읽은 절: §1, §2.1, §2.4, §3 도입부, §3.1~3.3, Fig. 3~5, §4 앞부분. (§2.2~2.3, §3.4~3.5, §5는 LITMUS^RT 전용이라 생략)

---

## 1. 지연이란 무엇인가 (§1)

타이머나 장치 인터럽트가 발생한 뒤 태스크가 실제로 실행을 시작하기까지 커널은 반드시 네 단계를 거친다.

| 단계 | 논문 문구 | 뜻 | 어디서 늦어질 수 있나 |
|---|---|---|---|
| 1 | processor transfers control to an interrupt handler | CPU가 하던 일을 멈추고 인터럽트 핸들러로 진입 | 누군가 인터럽트를 꺼 둔 상태(`local_irq_disable`)면 끝날 때까지 못 들어감 |
| 2 | interrupt handler identifies the task waiting for the event and resumes it | 어느 태스크를 깨울지 찾아 준비 큐에 넣음 | |
| 3 | scheduler is invoked to check whether the resumed task has higher priority | 지금 실행 중인 것보다 급한지 판단 | 누군가 선점을 꺼 둔 상태(`preempt_disable`)면 끝날 때까지 못 판단 |
| 4 | if higher priority, context switch (dispatch) | 실제로 CPU를 넘김 | TLB 플러시 등 하드웨어 비용 |

"even for the highest-priority task, there is always a delay between the activating event and the instant when the task starts executing. This delay, called scheduling latency, … imposes a lower bound on the deadlines that can be supported by the system."

→ 지연은 0이 될 수 없고, 그 **최댓값**이 시스템이 보장할 수 있는 가장 짧은 데드라인을 정한다.
→ **PREEMPT_RT가 하는 일**(§1): "reengineers core parts of the kernel to avoid delaying Steps 1 and 3." 즉 인터럽트 금지 구간과 선점 금지 구간을 잘게 쪼개고, 인터럽트 핸들러를 스레드로 바꿔 1단계와 3단계의 대기를 없앤다.

## 2. cyclictest가 재는 것 (§2.1)

"a sample of scheduling latency is recorded as the difference between the current time and the instant when the timer should have fired."

**지연 = 실제 깨어난 시각 − 깨어났어야 할 시각.** 우리 로그의 `t_wake − t_expected`와 같다.

동작 3단계: ① 초기화(스레드 생성, 실시간 태스크로 승격, CPU 친화도 설정) ② 주기 실행(한 번씩 타이머 만료 → 깨어남 → 지연 기록 → 타이머 재설정 → 잠듦) ③ 종료(일반 태스크로 강등, 히스토그램을 디스크에 기록).
측정 루프는 표준 유저스페이스 API만 쓴다 → 같은 방식의 측정을 우리 제어 루프 안에 넣을 수 있다.

## 3. 측정 전 환경 준비 (§3 도입부)

논문이 끈 것: 하이퍼스레딩, 주파수 스케일링, 딥 슬립 상태, 트레이싱·디버그 커널 옵션, cron 등 백그라운드 서비스(sshd만 예외).
cyclictest 설정: 코어당 1스레드, SCHED_FIFO 99, 주기 1000μs부터 500μs씩 증가, `-m`(mlockall로 페이지 폴트 방지).

→ 우리 ENVIRONMENT.md의 `processor.max_cstate=1`, `amd_pstate=passive` + governor performance, `nmi_watchdog=0`, `nosoftlockup`이 이 목록에 대응된다. 측정 전 체크리스트의 근거.

## 4. 부하 3종과 설계 의도 (§3.1~3.3)

| 조건 | 만든 방법 | 노리는 간섭 |
|---|---|---|
| 유휴 | 없음 | 최선의 경우 |
| CPU-bound | 코어마다 20 MiB 작업집합(L2 18 MiB보다 크게)에 무작위 메모리 접근 루프 | 캐시 미스, 메모리 계층 경합 |
| I/O-bound | hackbench(스케줄러 스트레스) + bonnie++(direct I/O 디스크) + wget(1 Gb 네트워크 포화) | 인터럽트 폭주, 커널 안의 인터럽트 금지 구간 자주 진입 |

핵심: 부하는 "CPU를 100%로"가 아니라 **"어떤 종류의 간섭을 만들 것인가"**로 설계한다. 단순 연산 루프는 캐시 안에서 돌아 간섭을 못 만든다.

## 5. 결과와 보고 형식 (Fig. 3~5)

보고 형식: 그림마다 1μs 간격 히스토그램, **y축 로그**, 그림 위에 `min / max / avg / median / stdev / samples total` 한 줄. 구성당 샘플 약 585만 개(16스레드 합산, 약 20분 분량).

| 조건 | Linux 3.8.13 + PREEMPT_RT | Linux 3.8.13 (패치 없음) |
|---|---|---|
| 유휴 | max 11.20μs, avg 2.74 | max 19.73μs, avg 2.89 |
| CPU-bound | max 17.42μs, avg 3.40 | max 64.47μs, avg 4.02 |
| I/O-bound | max 44.16μs, avg 4.12 | **max 5464μs**, avg 6.23 |

추가 실험(§3.3): bonnie++를 코어마다 띄우자 비RT 커널은 80~200 **ms** 스파이크, PREEMPT_RT는 "remained below 50µs even in this case."
평균은 어느 조건이든 2~6μs로 비슷하다. **차이는 max에서만 난다** → 평균을 보고하면 안 되는 이유.

## 6. 측정 함정 (§2.4)

처음에 LITMUS^RT 태스크에서 일정하게 50μs가 더 나왔다. 원인은 리눅스가 `nanosleep()`에 타이머 병합(timer slack)을 적용하기 때문. 이 기능은 **SCHED_FIFO / SCHED_RR 태스크에는 적용되지 않는다**("it is circumvented for SCHED FIFO and SCHED RR tasks"). LITMUS 태스크는 그 예외에 없어서 걸린 것.
→ 교훈 두 가지: ① 제어 루프와 측정 스레드는 반드시 SCHED_FIFO로. ② 지연이 이상하게 일정하게 크면 시스템보다 **측정 방법**을 먼저 의심.

## 7. cyclictest의 한계 (§4)

"it treats the kernel and the underlying hardware as a black box and reports the actual cumulative impact of system overheads."
- 장점: 해석 쉬움, 커널 지식 불필요.
- 한계: **최고 우선순위 태스크 하나**의 총 지연만 보여준다. 원인 분리 불가. 다른 코어에서 깨우는 IPI 지연 같은 요소는 설정에 따라 안 잡힌다.
→ cyclictest = 환경의 최선. 실제 제어 루프의 지연은 제어루프 로그에서 따로 재고, 둘의 차이로 "코드 탓 / 환경 탓"을 가른다.

---

## 우리 작업으로 옮길 것

1. **A2 정의 확정**: 지연 = `t_wake − t_expected` (§2.1 방식). 환경 수준은 cyclictest, 실제는 제어루프 로그, 같은 식.
2. **보고 형식 확정**: 1μs 빈 히스토그램 + 로그 y축 + min/max/avg/median/stdev/samples 한 줄. `docs/benchmarks` 베이스라인을 이 형식으로 다시 그린다.
3. **A7 부하 축**: 유휴 / 캐시 압박 (stress-ng `--vm`·`--cache`, 작업집합을 L3보다 크게) / 인터럽트 폭주 (네트워크·디스크) / **실제 GPU 추론** (우리 추가). GPU 추론은 PCIe·드라이버 인터럽트라는 새 간섭 경로일 것이라는 가설을 리포트에 적되, 측정으로 확인.
4. **비교 기준**: RT 커널 + 격리 후 우리 max가 유휴 ~11, 캐시 부하 ~17, I/O 부하 ~44μs 근처면 논문 수준. 베이스라인(일반 커널, 유휴 146 / 부하 1325μs)은 이 논문의 "패치 없음" 열과 같은 현상.
5. **측정 길이·방법**: 구성당 수백만 샘플(1kHz 단일 스레드면 100만 회 = 17분 이상). 측정 스레드는 SCHED_FIFO + mlockall. 결과가 이상하면 측정법부터 점검.

## 대화에서 바로잡은 점

- "585만 샘플 = 약 97분"은 **1kHz 스레드 하나로 환산했을 때** 이야기. 논문은 16스레드가 서로 다른 주기로 동시에 돌아 합산 585만 개이고, 실제 실행 시간은 약 20분.
- §2.4의 50μs는 "실시간 태스크에 붙는 지연"이 아니라 **SCHED_FIFO/RR이 아닌 태스크에 붙는 지연**. SCHED_FIFO면 이미 면제된다. 그래서 교훈은 "FIFO를 꼭 써라"다.
- 우리 베이스라인이 높은 이유는 "RT 패치가 안 됐을 가능성"이 아니라 **확정적으로 일반 커널(7.0.0-generic)에서 잰 것**. 지금은 6.8.1-realtime으로 바뀌었으니 다음 측정이 바로 before/after가 된다.
