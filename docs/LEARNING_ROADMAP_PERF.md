# 성능평가 담당자 학습 로드맵 (비전공자용)

> 대상: PACE 팀에서 **정량 벤치마크(제어주기·지터·지연 측정, 시각화, 리포트)** 를 맡는 팀원
> 전제: 로봇/RTOS 전공지식 없음. 터미널과 파이썬은 따라 하며 배운다.
> 작성일: 2026-10-09

## 왜 이 파트가 중요한가

과제 문서의 "제안 한마디"는 **AI 정확도가 아니라 추론 결과가 제어에 반영되는 과정의 실시간성·안정성을 중점 평가**한다고 명시한다.
산출물 3개(설계서 · 시연 · **정량 벤치마크**) 중 하나가 통째로 이 파트이고, 나머지 둘도 결국 숫자로 뒷받침되어야 한다.
심사위원이 가장 먼저 볼 숫자는 아래 세 개다.

| 지표 | 과제 기준 | 우리 팀 현재 상태 (RT 커널 전) |
|---|---|---|
| 제어주기 | 1ms (1kHz) | 측정 중 |
| 지터 (최대 지연) | ±100μs 이내 | 유휴 146μs, 부하 1325μs (CPU4 기준, 미달) |
| AI 부하 유무 비교 | 부하가 있어도 위 기준 유지 | 부하 시 1ms 초과 → 주기 자체를 놓침 |

즉 "RT 커널 + 코어 격리 적용 후 이 숫자가 100μs 아래로 내려갔다"를 **재현 가능하게 증명**하는 것이 당신의 첫 번째 임무다.

---

## 전체 구조 (약 3주, 하루 2~3시간 기준)

```
0단계 전제지식 (1~2일)
  └ 1단계 실시간 개념 (3일)
      └ 2단계 측정 도구 (3~4일)   ← 첫 실습: 기존 baseline 파일 그래프화
          └ 3단계 지표 정의·실험 설계 (3일)   ← 팀 제안서의 "벤치마크 계획" 담당
              └ 4단계 측정 코드 이해 (3~4일)
                  └ 5단계 시각화·리포트 (2~3일)
                      └ 6단계 심화 (여유 시)
```

각 단계는 **목표 → 배울 것 → 자료 → 실습(이 프로젝트 안에서) → 자가 점검 질문** 순서다.
자가 점검 질문에 말로 답할 수 있으면 다음 단계로 넘어간다.

---

## 0단계. 전제 지식 (1~2일)

**목표**: 이후 단계의 용어와 숫자를 읽을 수 있게 된다.

**배울 것**
- 리눅스 터미널 기본: `cd`, `ls`, `cat`, `grep`, `sudo`, 파이프(`|`), 리다이렉션(`>`)
- 프로세스와 스레드, CPU 코어, 우선순위라는 개념
- 시간 단위 감각: 1s = 1,000ms = 1,000,000μs = 1,000,000,000ns. **1ms 주기 = 1초에 1000번**, 100μs = 1ms의 1/10
- 통계 기초: 평균, 최소/최대, 백분위(p50, p99, p99.9), 히스토그램, 누적분포(CDF)
- 파이썬 기초: 리스트, 파일 읽기, `pandas.DataFrame`, `matplotlib`로 선 그래프·히스토그램

**자료**
- 리눅스 명령어: 아무 입문서나 1장 분량. `man <명령>` 읽는 법만 익히면 충분
- 통계/백분위: "p99 latency" 로 검색해서 나오는 블로그 글 2~3개 (실시간 시스템에서 왜 평균이 아니라 최악값을 보는지 감 잡기)
- 파이썬/matplotlib: 공식 튜토리얼 "Pyplot tutorial" (https://matplotlib.org/stable/tutorials/pyplot.html)

**실습**
- `source .venv/bin/activate` 후 `python -c "import mujoco, matplotlib; print('ok')"` 가 되는지 확인
- `docs/ENVIRONMENT.md` 를 읽고 모르는 단어를 전부 적어 둔다 (1~2단계에서 하나씩 지운다)

**자가 점검**
- "p99.9가 80μs" 라는 문장을 설명할 수 있는가?
- 1kHz 제어 루프가 10분 돌면 반복 횟수는 몇 번인가? (60만 번)

---

## 1단계. 실시간 시스템 개념 (3일)

**목표**: 과제 문서의 요구사항과 팀 README의 설계를 전문용어로 이해한다.

**배울 것**
- **실시간(real-time)의 정의**: "빠르다"가 아니라 "**정해진 시간 안에 반드시**". 하드 리얼타임 vs 소프트 리얼타임
- **주기(period) / 지연(latency) / 지터(jitter) / 데드라인 / WCET(최악 실행시간)** 의 차이
  - 지연: 깨어나야 할 시각과 실제 깨어난 시각의 차이 (cyclictest가 재는 것)
  - 지터: 그 지연의 흔들림. 과제의 "±100μs"는 사실상 최대 지연 100μs 이하를 뜻한다
- **스케줄링**: `SCHED_OTHER`(일반) vs `SCHED_FIFO`/`SCHED_RR`(실시간), 우선순위 1~99, 왜 제어 루프에 FIFO 99를 주는지
- **선점(preemption)**: 일반 커널은 커널 안에서 실행 중이면 더 급한 일이 와도 못 끊음. **PREEMPT_RT** 는 거의 모든 지점을 끊을 수 있게 바꾼 커널
- **지연을 만드는 범인들** (이걸 알아야 "왜 격리했는지"를 설명할 수 있다)
  - CPU 절전 상태(C-state) 진입/복귀 → `processor.max_cstate=1`
  - CPU 주파수 변동 → governor `performance` 고정
  - 인터럽트(IRQ)가 제어 코어에 떨어짐 → `irqaffinity`, `isolcpus=managed_irq`
  - 타이머 틱 → `nohz_full`
  - 다른 프로세스가 같은 코어 사용 → `isolcpus=domain`
  - 캐시 경합(L3 공유) → 팀 README의 "CCX 통째로 격리"
  - 페이지 폴트 → `mlockall`
  - SMI(펌웨어 인터럽트, OS가 못 막음) → `hwlatdetect` 로 확인만 가능
- **Xenomai vs PREEMPT_RT** 차이 (개념만): PREEMPT_RT는 리눅스 자체를 고친 것, Xenomai는 리눅스 옆에 작은 실시간 커널을 붙인 것. 우리 팀은 PREEMPT_RT 선택

**자료**
- Linux Foundation Real-Time wiki 시작 페이지: https://wiki.linuxfoundation.org/realtime/start
- 같은 wiki의 "Real-time application HOWTO" (application_base): https://wiki.linuxfoundation.org/realtime/documentation/howto/applications/application_base
- Ubuntu Real-time kernel 소개: https://ubuntu.com/real-time
- Red Hat "RHEL for Real Time" 튜닝 가이드 (지연 원인 설명이 가장 친절함. 검색: "RHEL for Real Time Optimizing latency")
- `man 7 sched` (스케줄링 정책 설명, 터미널에서 바로)

**실습**
- 팀 README의 "실시간 제어 계층" 문단을 읽고, 각 문장이 위의 어느 "범인"을 막는 조치인지 옆에 적어 본다
- `cat /proc/cmdline` 으로 현재 커널 파라미터를 보고 `docs/ENVIRONMENT.md` 의 목표 파라미터와 비교

**자가 점검**
- "평균 지연 3μs인데 최대 592μs" 인 시스템이 왜 실시간 제어에 부적합한지 설명할 수 있는가?
- `isolcpus` 와 `SCHED_FIFO` 는 각각 어떤 범인을 막는가?

---

## 2단계. 측정 도구 손에 익히기 (3~4일)

**목표**: 팀이 이미 만든 baseline 파일을 읽고, 직접 같은 측정을 재현하고, 그래프로 그린다.

**배울 것**
- **cyclictest** (실시간 지연 측정의 표준 도구). 팀이 쓴 옵션을 하나씩 해석:
  ```
  cyclictest -m -S -p 99 -i 1000 -D 30 -h 400
  ```
  | 옵션 | 뜻 |
  |---|---|
  | `-m` | 메모리 잠금(mlockall). 페이지 폴트 지연 제거 |
  | `-S` | 모든 CPU에 스레드 하나씩 |
  | `-p 99` | SCHED_FIFO 우선순위 99 |
  | `-i 1000` | 주기 1000μs = 1ms (과제 기준) |
  | `-D 30` | 30초 동안 |
  | `-h 400` | 0~400μs 히스토그램 출력 |
  | `-a 4 -t 1` | CPU 4번에 스레드 1개 (제어 전용 코어만 측정) |
  | `-q` | 조용히, 끝에 요약만 |
  - 출력 해석: `Min / Act / Avg / Max` 와 히스토그램 (행 = μs, 열 = CPU, 값 = 횟수)
- **stress-ng**: 일부러 부하 걸기. `--cpu N`, `--vm N --vm-bytes 2G`, `--timeout`. "AI 부하 있을 때" 흉내
- **코어/우선순위 제어**: `taskset -c 4 <명령>` (코어 고정), `chrt -f 99 <명령>` (FIFO 99로 실행), `cpupower frequency-set -g performance`
- **상태 확인**: `uname -v` (PREEMPT_RT 여부), `cat /proc/cmdline`, `cat /sys/devices/system/cpu/cpu4/cpufreq/scaling_governor`, `ulimit -r`
- **hwlatdetect**: SMI 등 하드웨어 지연 유무 확인 (rt-tests에 포함)
- **trace-cmd / ftrace** (맛보기): 지연이 튄 순간 커널 안에서 무슨 일이 있었는지 추적. 6단계에서 본격

**자료**
- cyclictest 공식 문서: https://wiki.linuxfoundation.org/realtime/documentation/howto/tools/cyclictest/start
- rt-tests 소스/README: https://git.kernel.org/pub/scm/utils/rt-tests/rt-tests.git
- `man stress-ng`, `man chrt`, `man taskset`
- 팀 자료: `docs/benchmarks/README.md`, `scripts/05_verify_env.sh` (cyclictest 호출 부분)

**실습 (이 단계의 핵심 과제)**
1. `docs/benchmarks/baseline_generic_idle.txt` 의 히스토그램을 파이썬으로 파싱해서
   - CPU4 열의 히스토그램 (y축 로그 스케일)
   - 전체 CPU의 CDF
   - p50 / p99 / p99.9 / max 표
   를 만든다. `baseline_generic_stress.txt` 도 같은 그림에 겹쳐 그린다
   → 이것이 **팀의 첫 번째 공식 벤치마크 그림**이 된다
2. 직접 30초 측정을 재현: `cyclictest -m -S -p 99 -i 1000 -D 30 -h 400 -q > my_idle.txt`
   (주의: `realtime` 그룹 반영 안 되어 있으면 `-p 99` 실패. `id` 로 확인)
3. 다른 터미널에서 `stress-ng --cpu 24 --vm 4 --vm-bytes 2G --timeout 60` 걸고 2번 반복
4. 팀 README 수치와 비슷하게 나오는지 비교. 다르면 **왜 다른지**(governor, 다른 프로그램 실행 중 등) 메모

**자가 점검**
- cyclictest 히스토그램 파일에서 "146μs" 라는 숫자를 직접 찾아낼 수 있는가?
- `-i 1000` 을 `-i 500` 으로 바꾸면 무엇을 재는 것인가?

---

## 3단계. 과제 지표 정의와 실험 설계 (3일)

**목표**: 심사 기준을 만족하는 **벤치마크 계획서**를 쓴다. 팀 제안서/설계서의 벤치마크 절은 이 단계 산출물이다.

**배울 것 — 과제가 요구하는 5가지 측정**

| # | 측정 항목 | 측정 지점 | 통계량 | 합격 기준 |
|---|---|---|---|---|
| 1 | 제어주기 & 지터 | 1kHz 루프 매 반복 시작 시각 | 주기 차이의 min/avg/p99/p99.9/max, 100μs 초과 횟수, 주기 미스(>1ms) 횟수 | max ≤ 100μs, 미스 0 |
| 2 | AI 추론시간 & 주기 | 추론 시작/끝 시각 | 추론시간 분포, 결과 도착 간격 분포 | 기준 없음(보고) |
| 3 | End-to-End 지연 | 센서 데이터 타임스탬프 → 제어 명령 반영 시각 | 분포, max | 보고 + 설계값과 비교 |
| 4 | AI 부하 유무 비교 | 1번을 부하 조건별 반복 | 조건별 1번 통계 나란히 | 부하 있어도 1번 유지 |
| 5 | 장애 조건별 동작 | 정상/지연/중단/이상값/통신단절 시 로봇 상태 시계열 | 추종 오차, 최대 저크, 거부율(팀 README 지표) | 급격한 동작 없음 |

**실험 매트릭스 설계** (바꿀 변수 × 고정 변수)
- 커널: generic (이미 있음) vs PREEMPT_RT
- 격리: 없음 → `isolcpus` 만 → CCX 통째 격리 (팀 README "격리 단계별 비교")
- 부하: 유휴 → stress-ng → **실제 AI 추론 (GPU)** → AI + MuJoCo + ROS 2 전부
- 지속시간: 30초(빠른 확인) → 10분(제출용) → 1시간 이상(최악값 신뢰도용, 밤새 돌리기)
- 반복: 같은 조건 최소 3회. 최악값은 1회 측정으로 믿으면 안 된다

**재현성 규칙 (중요)**
- 모든 측정 파일에 메타데이터 기록: 날짜, `uname -r`, `/proc/cmdline`, governor, 실행 명령, 동시에 돌던 프로그램
- 파일명 규칙 예: `docs/benchmarks/<커널>_<격리>_<부하>_<지속>_<회차>.txt`
- 측정 전 체크리스트: governor performance? 브라우저·IDE 꺼짐? 다른 팀원이 GPU 쓰는 중?

**자료**
- 과제 PDF "성능 측정 및 시각화" 항목 (About/ 폴더)
- 팀 README "측정 항목", "반영 정책 비교 실험"
- ROS 2 Real-Time 문서 (실시간 측정 관점의 용어 통일): https://docs.ros.org/en/jazzy/Tutorials/Demos/Real-Time-Programming.html

**실습**
- 위 표와 매트릭스를 바탕으로 `docs/BENCHMARK_PLAN.md` 초안 작성. 팀원 리뷰 받기
- 측정 결과 파일명 규칙과 메타데이터 양식을 팀에 제안

**자가 점검**
- "AI 부하가 제어 성능에 영향을 주지 않았다"를 증명하려면 **최소 몇 가지 조건**의 결과가 필요한가?
- 10분 측정에서 최대 지연 80μs가 나왔다. 1시간 측정에서도 그럴 거라고 말할 수 있는가? (없다. 그래서 장시간 측정이 필요)

---

## 4단계. 측정 코드 이해 (3~4일)

**목표**: cyclictest가 아니라 **우리 팀 제어 루프 자체**에서 지표 1~3을 뽑는 코드를 읽고, 필요하면 작은 수정을 할 수 있다.
직접 다 짜라는 뜻이 아니다. 제어 루프를 짜는 팀원이 "여기에 타임스탬프 찍어 달라"는 요청을 정확히 할 수 있으면 된다.

**배울 것**
- **1kHz 실시간 루프의 표준 패턴** (C/C++)
  1. `mlockall(MCL_CURRENT|MCL_FUTURE)` 메모리 잠금
  2. `sched_setscheduler` 로 SCHED_FIFO 99, `pthread_setaffinity_np` 로 CPU 4 고정
  3. `clock_gettime(CLOCK_MONOTONIC)` 으로 현재 시각
  4. `clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, next)` 로 **절대시각** 기준 대기 (상대 대기를 쓰면 오차가 누적됨)
  5. 매 반복: 깨어난 시각 기록 → 제어 계산 → `next += 1ms`
- **측정 오버헤드 없이 기록하기**: 루프 안에서 파일에 쓰면 안 됨 (파일 I/O가 지연을 만듦). 메모리 링버퍼에 숫자만 쌓고, 끝난 뒤 또는 별도 저우선순위 스레드가 파일로 내보냄
- **E2E 지연 측정 원리**: AI 쪽이 메시지에 "센서 캡처 시각 t0, 추론 완료 시각 t1" 을 담아 보내고, 제어 루프가 "반영 시각 t2" 를 기록. 같은 `CLOCK_MONOTONIC` 시계를 쓰므로 같은 PC 안에서는 그냥 빼면 됨
- **ros2_control 의 주기 통계**: controller_manager 가 자체적으로 주기 측정값을 제공. 우리 측정과 교차 검증에 사용
- **공유메모리 / 락프리** (개념만): 두 프로세스가 같은 메모리를 보되 서로 기다리지 않는 구조. 왜 뮤텍스를 안 쓰는지 (우선순위 역전 방지)

**자료**
- RT wiki application HOWTO (1단계와 같은 문서, 이번엔 코드 예제 중심으로 재독)
- `man 2 clock_nanosleep`, `man 2 mlockall`, `man 2 sched_setscheduler`
- ros2_control 문서: https://control.ros.org/jazzy/
- cyclictest 소스 `src/cyclictest/cyclictest.c` 의 메인 루프 (측정 코드의 교과서. 전부 읽을 필요 없고 `clock_nanosleep` 주변 50줄)

**실습**
- 파이썬으로 "가짜 1kHz 루프" 를 만들어 `time.perf_counter_ns()` 로 주기를 재 본다. 파이썬은 실시간이 아니라서 지터가 크게 나온다. **그 자체가 "왜 C++와 RT 커널이 필요한가"의 데모**가 된다
- 팀 제어 루프 코드가 나오면 타임스탬프 기록 위치 3곳(깨어남, AI 결과 수신, 명령 송출)을 함께 정한다

**자가 점검**
- 상대 시간 대기(`nanosleep(1ms)`)와 절대 시각 대기의 차이를 설명할 수 있는가?
- 제어 루프 안에서 `printf` 를 하면 안 되는 이유는?

---

## 5단계. 시각화와 리포트 (2~3일)

**목표**: 심사위원이 10초 안에 "기준 통과"를 읽을 수 있는 그림과 표를 만든다.

**필수 그림 세트**
1. **지연 히스토그램** (y축 로그): 조건별(generic/RT, 유휴/부하) 겹쳐 그리기, 100μs 선 표시
2. **CDF**: "99.99%의 반복이 X μs 이내" 를 한눈에
3. **시계열 지터 플롯**: x=시간, y=지연. 부하를 켠 시점에 세로선. "부하를 켜도 튀지 않는다"가 보여야 함
4. **조건별 박스플롯/표**: 커널 × 격리 × 부하 매트릭스를 한 장에
5. **E2E 지연 분해 막대**: 센서→추론 / 추론→전달 / 전달→반영 구간별
6. **장애 주입 타임라인**: 위 = AI 결과 도착 여부, 아래 = 로봇 속도/위치. 지연 발생 → 감속 → 유지 → 복귀 가 보이게

**리포트 구조 (docs/benchmarks/REPORT.md 또는 설계서의 한 절)**
1. 측정 환경 (하드웨어, 커널, 파라미터, 도구 버전)
2. 측정 방법 (무엇을, 어디서, 어떻게, 몇 번)
3. 결과 표 (조건별 min/avg/p99/p99.9/max/초과횟수)
4. 그림
5. 해석: 기준 통과 여부, 남은 잔여 지연의 원인 추정, 한계

**자료**
- matplotlib 갤러리에서 `hist`(log scale), `ecdf`, `boxplot` 예제
- `dataviz` 스킬 (이 세션에 있음): 색·축·범례 규칙 참고 가능

**실습**
- 2단계 실습 그림을 위 1·2·4 형식으로 다듬어 `docs/figures/` 에 저장
- RT 커널 적용 후 첫 측정이 나오면 generic 과 나란히 놓은 "before/after" 한 장 만들기

**자가 점검**
- 그림 한 장만 보여줄 수 있다면 어느 것을 고르겠는가, 왜?

---

## 6단계. 심화 (여유 있을 때)

- **ftrace / trace-cmd** 로 지연이 튄 순간 추적: `trace-cmd record -p function_graph` 또는 cyclictest `-b <μs>` (breaktrace) 옵션으로 "100μs 넘는 순간 추적 중단" 후 원인 찾기
- **hwlatdetect** 로 SMI 지연 확인 (OS로 못 막는 지연이 있으면 리포트의 "한계"에 적는다)
- **perf** 로 제어 루프의 캐시 미스 확인 (L3 격리 효과 증명용)
- **ROS 2 실시간 가이드** 정독: 메모리 할당 금지, 콜백 실행기(executor) 우선순위
- **Xenomai** 와의 차이를 설계서 "대안 검토" 절에 한 문단으로

---

## 바로 시작할 것 (오늘)

1. 0단계 자가 점검 두 문항에 답해 본다
2. `docs/benchmarks/baseline_generic_idle.txt` 를 열어 구조를 눈으로 본다 (첫 줄 주석, 그 다음 히스토그램, 행=μs, 열=CPU)
3. 2단계 실습 1번(히스토그램 파싱·그래프)을 첫 목표로 잡는다. 파이썬 파싱 스크립트가 필요하면 요청

## 용어 빠른 참조

| 용어 | 한 줄 설명 |
|---|---|
| RTOS | 정해진 시간 안의 응답을 보장하는 운영체제 |
| PREEMPT_RT | 리눅스를 RTOS 수준으로 만드는 커널 설정/패치 |
| Xenomai | 리눅스 옆에 붙는 별도 실시간 커널 (우리 팀 미사용) |
| 제어주기 | 제어 명령을 내는 간격. 과제 1ms |
| 지연(latency) | 깨어나야 할 시각 대비 실제 깨어난 시각의 차 |
| 지터 | 지연의 변동 폭. 과제 ±100μs |
| WCET | 최악 실행시간 |
| SCHED_FIFO | 실시간 스케줄링 정책. 우선순위 높은 게 끝날 때까지 양보 안 함 |
| isolcpus | 특정 코어를 일반 작업에서 떼어내는 커널 파라미터 |
| CCX | AMD CPU에서 L3 캐시를 공유하는 4코어 묶음 |
| cyclictest | 실시간 지연 측정 표준 도구 |
| stress-ng | 인위적 부하 생성 도구 |
| E2E 지연 | 센서 입력부터 로봇 명령 반영까지 총 시간 |
| HAL | 로봇별 차이를 흡수하는 추상화 계층 |
| ros2_control | ROS 2의 제어기/하드웨어 인터페이스 프레임워크 |
| EtherCAT | 산업용 실시간 통신 규격 (모터 드라이버와 연결) |
| MuJoCo | 물리 시뮬레이터. 우리 팀의 "가짜 로봇" |
