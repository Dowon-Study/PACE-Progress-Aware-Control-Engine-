# verification — 성능지표 검증 프로세스

기준 문서: [reference/성능지표_정리.pdf](reference/성능지표_정리.pdf) (12개 지표의 정의·근거·구현법).
이 폴더는 그 PDF 4절("일기장 3권 → 빼기 → 그림")을 **실제로 돌릴 수 있는 절차와 코드**로 옮긴 것이다.
플랫폼 코드(`pace/`, `pace_py/`)는 건드리지 않는다. 로그 파일을 받아서 읽기만 한다.

```
verification/
├── README.md            # 이 문서: 검증 절차 (0~5단계), 지표별 계산 위치, 지금 가능한 것/막힌 것
├── CHECKLIST.md         # 측정 전·후 체크리스트 (한 번의 측정마다 복사해서 체크)
├── metrics_core.py      # "계산기" stats() + cyclictest 파서 + 제어루프 로그 로더(두 포맷) + 지표 함수 A1~B3
├── verify.py            # 실행기: cyclictest / ctrl / compare / demo
├── measure_jitter.sh    # A2·A7 측정 실행기 (idle / stress, 10분, raw/ 규칙 이름으로 저장)
├── reference/           # 기준 PDF
└── out/                 # demo 결과 (스크립트 동작 확인용 그림·표). 제출용 그림은 validation/figures/ 로
```

---

## 0. 한눈에: 지표 → 재료 → 계산 함수

| 지표 | 재료 (일기장) | 계산 | 함수 (`metrics_core.py`) | 합격 기준 | 지금 상태 |
|---|---|---|---|---|---|
| A1 제어주기 | ctrl.csv `t_wake − t_expected` | 1ms 넘은 주기 수 | `a1_deadline_miss` | 0회 | ✅ 계산됨 |
| A2 지터 | ctrl.csv (실제) + cyclictest (빈 손) | min/avg/p50/p99/p99.9/max, 100μs 초과 | `a2_jitter`, `cyclictest_stats` | max ≤ 100μs | ✅ 계산됨 |
| A3 추론시간 | ai.csv `t_infer_end − t_infer_start` | 분포 | (ai.csv 오면 `stats`) | 보고 | ⛔ AI 로그 없음 |
| A4 추론 주기 | ai.csv 연속 `t_publish` 차 | 분포 | (ai.csv 오면 `stats`) | 보고 | ⛔ AI 로그 없음 |
| A5 반영 지연 | ctrl.csv `t_cmd − ai_t_recv` (ai_seq 바뀐 주기) | 분포 | `a5_reflect_latency` | 보고 | ⚠ 근사 (아래 §4) |
| A6 E2E | ctrl.csv `t_cmd − ai_t_capture` | 분포 + 구간 분해 | `a6_e2e` | 보고 | ⛔ 캡처 시각 없음 |
| A7 부하 비교 | A1·A2 를 조건별 반복 | 표 1장 + 겹친 히스토그램 | `a7_table`, `verify.py compare` | 전 조건 max ≤ 100μs | ⚠ idle/stress 만 |
| A8 조건별 시각화 | ctrl.csv + fault 이벤트 | 시간축 그림 (지연·상태 띠·속도) | `verify.py ctrl` → `*_A8_timeline.png` | 급격한 동작 없음 | ✅ 그림 나옴 |
| B1 거부율 | ctrl.csv `ai_state == reject` + 사유 | 횟수·비율·사유별 | `b1_reject` | 유효기간 만료 사용 0 | ✅ (분모는 summary.json) |
| B2 저크·추종오차 | trace.bin `q_cmd`, `q_meas` | 3차 차분 max/p99, \|q_cmd − q_meas\| | `b2_smoothness` | 장애 중 ≈ 정상 | ✅ trace 있으면 |
| B3 복구 시간 | ctrl.csv 상태 전이 시각 | 감지/감속/정지/복귀 ms, 그 사이 A1 미스 | `b3_recovery` | 미스 0 | ✅ (장애 시각은 손으로 입력) |
| B4 HAL 교체 비용 | `git diff --stat` + HAL read/write 시간 | 줄 수, μs | summary.json `hal.*` 읽기 | 보고 | ⚠ 수동 |

범례: ✅ 지금 데이터로 계산됨 · ⚠ 계산되지만 해석에 조건 붙음 · ⛔ 플랫폼 로그에 열이 없어 불가

---

## 1. 검증 절차 (한 사이클)

### 0단계. 입력 받기
플랫폼 담당자(또는 docs/benchmarks/runs/)에서 받는 것:
- 제어루프 로그 CSV 1개 이상 (`*.csv`, 아래 §3 두 포맷 중 하나)
- 있으면 같은 이름의 `*.trace.bin` (관절 명령·실측 1kHz → B2), `*.summary.json` (거부·HAL·정지 사다리 요약 → B1 분모, B4)
- 장애 주입 시각 (fake.log 의 `t_ep=` 줄, 또는 실행 명령의 `--fault-at`)
- 실행 조건: 커널, 격리, 부하, 지속시간, 버전

### 1단계. 조건 기록
`configs/<raw 와 같은 이름>.md` 를 `templates/measurement_log.md` 로 만들어 채운다. `measure_jitter.sh` 는 자동으로 만들어 준다.

### 2단계. 측정 (또는 파일 복사)
- 지금 당장 가능한 것: `measure_jitter.sh idle 600 1`, `measure_jitter.sh stress 600 1` (각 3회). → `raw/`
- 플랫폼 실행 결과는 `docs/benchmarks/runs/<이름>.csv` 를 `raw/` 로 **복사** (원본은 건드리지 않는다).

### 3단계. 계산 (verify.py)
프로젝트 루트에서:
```bash
.venv/bin/python validation/verification/verify.py cyclictest validation/raw/20261010_rt_ccx_idle_600s_r1.txt
```
```bash
.venv/bin/python validation/verification/verify.py ctrl docs/benchmarks/runs/s4_faultsA_ep4.csv --label s4_faultsA --fault-t0 13.0
```
```bash
.venv/bin/python validation/verification/verify.py compare idle=validation/raw/..._idle_600s_r1.txt stress=validation/raw/..._stress_600s_r1.txt --name rt_ccx_600s
```
결과: `--out` 폴더(기본 `out/`)에 `<label>_*.json`(숫자), `<label>_*.md`(표), `<label>_*.png`(그림).

### 4단계. 그림·표 확인
- `*_A2_*_hist.png`: 세로축 로그, 빨간 선(100μs) 오른쪽에 아무것도 없어야 한다.
- `*_A8_timeline.png`: 위 칸 지연이 빨간 선 아래, 가운데 상태 띠가 설계 순서(fresh → pacing/hold → stop → recover → fresh), 아래 칸 속도 배율이 수직으로 떨어지지 않아야 한다.
- `*_A7_hist_overlay.png`: 조건별 산이 겹쳐 보여야 한다. 한 조건만 오른쪽으로 꼬리가 길면 그 조건의 간섭 경로가 뚫린 것.

### 5단계. 리포트
`templates/report_template.md` 로 `reports/` 에 작성. 표는 `out/*.md` 를 붙여 넣고, 그림은 `validation/figures/` 로 옮긴 뒤 링크한다.
리포트에 반드시 적을 것: 포맷(§3), A5 근사 여부(§4), 반복 횟수, 지속시간, 제외한 구간(예열 등).

---

## 2. 지금 폴더 데이터로 바로 해 보기 (demo)

```bash
.venv/bin/python validation/verification/verify.py demo
```
`docs/benchmarks` 의 cyclictest 4개(일반 커널 유휴/부하, RT+격리 유휴/부하), 1kHz 루프 로그 2개(유휴 20s / 부하 60s), 장애 주입 실행 1개(s4_faultsA)를 돌려 `out/` 에 저장한다.
2026-10-10 실행 결과 요약 (이 숫자들이 PDF 의 "before/after" 그대로다):

| 조건 | avg | p99 | p99.9 | max | >100μs | 판정 |
|---|---|---|---|---|---|---|
| 일반 커널 유휴 (cyclictest, 32코어 최악) | 5.2 | 215 | 399 | 592 | 563 | 불합격 |
| 일반 커널 stress (cyclictest, 최악 코어) | 11.2 | 56 | 399 | 1325 | 203 | 불합격 (25/32 코어 초과) |
| RT+CCX 유휴 (cyclictest CPU4) | 6.1 | 9 | 29 | 76 | 0 | 합격 |
| RT+CCX stress+GPU (cyclictest) | 6.4 | 8 | 11 | 20 | 0 | 합격 |
| RT+CCX 유휴 (실제 1kHz 루프 20s) | 6.5 | 7.8 | 8.6 | 16.7 | 0 | 합격, A1 미스 0 |
| RT+CCX stress+GPU (실제 루프 60s) | 7.7 | 18.6 | 27.1 | 41.8 | 0 | 합격, A1 미스 0 |

장애 주입 실행(s4_faultsA, 34s): A1 미스 0, A2 max 11.7μs, 거부 3건(RANGE_VEL·SEQ_ORDER·CONFIDENCE 각 1 = 주입한 3종과 일치), 비정상 구간 11개 동안 A1 미스 0, 저크 p99 8647 rad/s³, 추종 오차 max 0.0034 rad.

---

## 3. 로그 포맷 두 가지 (중요)

`validation/templates/control_loop_log_format.md` 의 **약속 포맷**과, 현재 플랫폼이 **실제로 내보내는 포맷**이 다르다. `metrics_core.load_ctrl()` 이 자동으로 구분해 공통 열로 바꾼다.

| 약속 포맷 (contract) | 현재 pace 포맷 | 변환 |
|---|---|---|
| `iter` | `tick` | 그대로 |
| `t_expected_ns` | `t_sched_ns` | 그대로 |
| `t_wake_ns` | `t_wake_ns` | 그대로 (`st_wake_ns` = 지연 ns) |
| `t_cmd_ns` | 없음 | `t_wake + Σ st_read..st_write` 로 복원 |
| `ai_seq` | `chunk_seq` | 그대로 |
| `ai_t_recv_ns` | **없음** | A5 를 `chunk_t_gen_ns` 기준으로 근사 (§4) |
| `ai_t_capture_ns` | **없음** | A6 불가 |
| `ai_state` (fresh/hold/decel/stop/reject) | `mode` 0~7 (INIT/NORMAL/PACING/LOCAL/EXTRAP/HOLD/STOPPED/RECOVER) + `reject` | NORMAL→fresh, STOPPED→stop, reject≠0→reject, 나머지는 이름 그대로 |
| `reject_reason` (range/time/validity) | `reject` 1~11 (RANGE_POS, EXPIRED, SEQ_ORDER, CONFIDENCE …) | 이름으로 바꾸고 range/time/validity 로 묶음 |
| `q_ref`, `q_act`, `v_cmd` | CSV 에 없음, `*.trace.bin` 에 `q_cmd`, `q_meas` | trace 를 읽어 B2 |
| AI 로그 `*_ai.csv` | **없음** (가짜 공급자 fake.log 만) | A3·A4 불가 |
| 장애 로그 `*_fault.csv` | fake.log 의 `t_ep=` 줄, `--fault-at` 인자 | `--fault-t0` 로 손 입력 |

→ 플랫폼 담당자에게 요청할 최소 2가지 (HANDOFF_PLATFORM_DEV.md R1·R2 와 같음):
1. 틱 레코드에 **`chunk_t_recv_ns`** (청크를 처음 읽은 시각) 추가 → A5 가 정확해진다.
2. 실제 AI 공급자(10단계)가 나오면 **`*_ai.csv`** (seq, t_capture, t_infer_start/end, t_publish, valid_until) → A3·A4·A6.

---

## 4. 해석할 때 주의 (리포트에 그대로 옮길 문장)

- **A5 근사**: 현재 로그의 `chunk_t_gen_ns` 는 공급자가 청크를 만든 시각이라, `t_cmd − chunk_t_gen` 은 "공급자→제어기 전달 지연 + 제어기 반영 지연"의 합이다. 가짜 공급자가 60ms 미래를 겨냥하므로 정상 구간 값 ≈ 60ms 가 나오며, 이는 설계값이지 반영 지연이 아니다. 순수 반영 지연(수 μs~1ms)은 `chunk_t_recv_ns` 가 생겨야 잰다.
- **A7**: 지금의 "stress" 는 stress-ng + PyTorch 행렬곱이지 실제 AI 모델이 아니다. 조건 이름을 `stress` 로 쓰고, 모델이 나오면 `ai-gpu`, `full` 을 추가한다. 또한 실제 루프 측정은 3단계 뼈대(검증기·눈 없이)에서 한 것이라, 최종 숫자는 **전체 시스템(full) 조건에서 10분 이상** 다시 재야 한다.
- **B2**: 저크는 실측이 아닌 **명령 위치의 3차 차분**이다 (측정 노이즈 회피). 단위 rad/s³. 장애 전/중/후 창을 나눠 비교하려면 `b2_smoothness(tr, windows=[(t0,t1),...])`.
- **B3**: 감지 시간은 "장애 시작 → 첫 비정상 상태" 인데, 참조 버퍼가 1.0s 분량이라 공급 중단은 버퍼가 바닥난 뒤에야 보인다 (s4_faultsA: 13.0s 중단 → 13.6s pacing). 이는 설계대로이며, 유효기간·버퍼 길이 설정값과 함께 적는다.
- **cyclictest 32코어 파일**: 일반 커널 베이스라인은 `-S`(전 코어)라 열이 32개다. 표에는 "최악 코어" 값을 쓰고 몇 코어에서 초과가 났는지도 적는다. 히스토그램 범위(400μs)를 넘친 샘플은 꼬리의 `# Max Latencies` 로 최대값을 잡는다.

---

## 5. 다음 할 일 (우선순위)

1. `measure_jitter.sh idle 600 r1~r3`, `stress 600 r1~r3` → 과제 핵심 숫자 "RT+격리, 10분, 부하 중 max" 확보. (지금 가능)
2. 9단계 결과(`docs/benchmarks/runs/s9*_ep0.csv`)를 `verify.py ctrl` 로 돌려 A8 시간축 그림 5조건(정상/지연/누락/이상값/단절)을 `validation/figures/` 에 모은다. (지금 가능: s4_normal, s5_*_d100~300, s5_dropout, s4_faultsB(이상값), s6_gap)
3. 플랫폼에 `chunk_t_recv_ns` 요청 → A5 정확화.
4. 10단계 실제 AI 모델 → `*_ai.csv` → A3·A4·A6, A7 의 ai-gpu/full 조건.
5. B4: UR5e→Panda 전환 시 바뀐 파일 목록(HAL 밖 0줄 확인) + summary.json `hal.read_max_us/write_max_us` 표.
