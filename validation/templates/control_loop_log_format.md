# 제어루프 · AI 계층 로그 포맷 약속 (플랫폼 담당자와의 인터페이스)

성능측정이 가능하려면 플랫폼 코드가 아래 타임스탬프를 남겨야 한다.
모든 시각은 **같은 시계** `CLOCK_MONOTONIC`, 단위 **ns**, 정수.
루프 안에서는 파일에 쓰지 말고 메모리 링버퍼에 쌓았다가 종료 시(또는 저우선순위 스레드가) CSV로 내보낸다.

## 1. 제어루프 로그 `*_ctrl.csv` (매 주기 1행, 1kHz면 초당 1000행)

| 열 | 타입 | 뜻 |
|---|---|---|
| `iter` | int | 반복 번호 (0부터) |
| `t_expected_ns` | int | 이번 주기에 깨어났어야 할 절대 시각 |
| `t_wake_ns` | int | 실제 깨어난 시각 → **지연 = t_wake − t_expected** |
| `t_cmd_ns` | int | 제어 명령을 HAL/시뮬레이터로 보낸 시각 → 루프 실행시간 = t_cmd − t_wake |
| `ai_seq` | int | 이번 주기에 사용 중인 AI 결과의 일련번호 (없으면 -1) |
| `ai_t_capture_ns` | int | 그 AI 결과의 센서 캡처 시각 (없으면 0) |
| `ai_t_recv_ns` | int | 그 AI 결과를 제어루프가 처음 받은 시각 (없으면 0) |
| `ai_state` | str | `fresh` / `hold` / `decel` / `stop` / `reject` 중 하나 (예외처리 상태) |
| `q_ref` | float | 기준 위치 (단일 축이면 1열, 다축이면 `q_ref_0..n`) |
| `q_act` | float | 실측 위치 |
| `v_cmd` | float | 명령 속도 |

E2E 지연 = `t_cmd_ns(처음 반영된 주기) − ai_t_capture_ns`
반영 지연 = `t_cmd_ns(처음 반영된 주기) − ai_t_recv_ns`

## 2. AI 계층 로그 `*_ai.csv` (추론 1회당 1행)

| 열 | 타입 | 뜻 |
|---|---|---|
| `seq` | int | 결과 일련번호 (제어루프의 `ai_seq` 와 매칭) |
| `t_capture_ns` | int | 센서/이미지 캡처 시각 |
| `t_infer_start_ns` | int | 추론 시작 |
| `t_infer_end_ns` | int | 추론 끝 → 추론시간 = end − start |
| `t_publish_ns` | int | 공유메모리/ROS 2 로 내보낸 시각 |
| `valid_until_ns` | int | 유효기간 만료 시각 |
| `confidence` | float | 신뢰도 |

추론 주기 = 연속된 `t_publish_ns` 의 차이

## 3. 장애 주입 로그 `*_fault.csv` (이벤트 1건당 1행)

| 열 | 뜻 |
|---|---|
| `t_ns` | 주입 시각 |
| `kind` | `delay` / `drop` / `outlier` / `disconnect` / `recover` |
| `param` | 지연이면 ms, 이상값이면 값 등 |

## 4. 파일 헤더

CSV 첫 줄들은 `#` 로 시작하는 메타데이터:
```
# version=<플랫폼 git hash 또는 버전>
# kernel=<uname -r>
# cmdline=<cat /proc/cmdline>
# governor=performance
# load=idle|stress|ai-gpu|full
# cmd=<실행 명령>
# start=<ISO 날짜시각>
```
