# 과제 4 성능지표 총괄표 (출제 PDF 기준, 1차 정리)

출처: `About/pac2026_hd-hyundai-robotics_mission__4.pdf` 만을 근거로 함. 논문 조사 전 기준표.
A = PDF가 지표 이름을 직접 쓴 것 / B = PDF가 "증명하라"고 요구하지만 지표 이름은 안 준 것 (우리가 정의)

| # | 지표 | PDF 근거 문구 (위치) | 정의 (무엇을 어디서 뺀 값인가) | 측정 방법 | 통계량 | 합격 기준 | 논문 검색 키워드 |
|---|---|---|---|---|---|---|---|
| A1 | 제어주기 유지 (데드라인 미스) | "목표 제어주기 1ms(1kHz)" (개발목표) · "제어주기 유지 여부 검증" (기술요구) · "제어주기…실제 측정값으로 제시" (필수고려) | 실제 깨어난 시각 − 깨어났어야 할 시각 > 1ms 인 반복 | 제어루프 매 주기 타임스탬프 (t_expected, t_wake) | 미스 횟수, 미스율 | 0회 | deadline miss, periodic task, control loop timing |
| A2 | 지터 | "목표 지터 ±100μs 이내" (개발목표) · "제어주기와 지터 측정" (기술요구) · "지터…실제 측정값" (필수고려) | 깨어난 시각 − 깨어났어야 할 시각 (주기 내 흔들림) | ① cyclictest (환경 수준) ② 제어루프 로그 (실제 루프) | min / avg / p50 / p99 / p99.9 / max, 100μs 초과 횟수, 히스토그램 | max ≤ 100μs | PREEMPT_RT latency, cyclictest, scheduling latency, jitter measurement |
| A3 | AI 추론시간 | "AI 추론시간" (개발목표) · "AI 추론시간…측정" (기술요구) | 추론 끝 − 추론 시작 | AI 계층 로그 (t_infer_start, t_infer_end) | 분포, avg, p99, max (WCET) | 보고 | inference latency, execution time variability, WCET |
| A4 | AI 추론 주기 | "AI 추론시간 및 추론 주기 측정" (기술요구) | 연속된 결과 발행 시각의 차이 | AI 계층 로그 (t_publish) | 분포, avg, max | 보고 | inference rate, aperiodic task, sampling period |
| A5 | 제어 반영 지연 | "제어 반영 지연시간" (개발목표) · "추론 결과의 제어 반영 지연을 실제 측정값으로 제시" (필수고려) · "반영 시점과 유효기간을 관리하는 동기화 구조" (기술요구) | 추론 결과를 제어루프가 받은 시각 → 그 결과가 처음 명령에 반영된 주기의 송출 시각 | 제어루프 로그 (ai_t_recv, t_cmd, ai_seq 변화 시점) | 분포, max | 보고 (PDF 3회 언급, 핵심) | asynchronous to periodic, sample-and-hold, actuation latency, data freshness |
| A6 | End-to-End 지연 | "End-to-End 지연시간 측정" (기술요구) | 센서 캡처 시각 → 그 데이터 기반 명령이 처음 송출된 시각 | AI 로그 t_capture + 제어루프 로그 t_cmd | 분포, max, 구간별 분해 (캡처→추론→전달→반영) | 보고 + 설계값 비교 | end-to-end latency ROS 2, cause-effect chain, reaction time, data age |
| A7 | AI 부하 유무 비교 | "AI 연산 부하 유무에 따른 실시간 성능 비교" (개발목표) · "AI 연산 부하 변화에 따른 실시간 제어 성능 비교" (기술요구) · "AI 추론 작업 동시 수행 환경에서 제어주기 유지 여부 검증" (기술요구) | A1·A2 를 부하 조건별(유휴 / 인위 부하 / 실제 AI / 전체)로 반복 | 같은 측정을 조건만 바꿔 반복 | 조건별 A1·A2 통계 나란히 | 부하 있어도 A1·A2 유지 | interference, CPU isolation, mixed-criticality, temporal isolation |
| A8 | 조건별 동작 시각화 | "정상·지연·통신 단절 조건별 시스템 동작 결과 시각화" (기술요구) · 예외처리 대상 "추론 지연, 데이터 누락 및 비정상 출력" (기술요구) · "통신 이상 시" (기술요구) | 정상 / 지연 / 누락(중단) / 이상값 / 통신단절 5조건에서 로봇 상태(위치·속도)와 AI 결과 도착의 시계열 | 장애 주입 로그 + 제어루프 로그 | 시계열 그래프 | 급격한 동작 없음 | fault injection, graceful degradation, fail-safe control |
| B1 | AI 출력 검증 거부율 | "값의 범위, 유효성 및 시간 정보를 검증해야 함" (필수고려) · "AI 추론 결과 유효성 검증" (기술요구) | 검증 단계(범위·시간·유효성)별 거부 횟수 / 전체 결과 수. 유효기간 지난 결과가 명령에 쓰인 횟수 | 제어루프 로그 ai_state == reject | 횟수, 비율, 단계별 분해 | 만료 결과 사용 0회 | runtime verification, safety monitor, input validation |
| B2 | 안전 동작 (급격함) | "급격하거나 불안정하게 동작하지 않도록 안전한 제어방식" (필수고려) | 장애 전후 로봇 위치·속도 시계열의 최대 저크, 최대 가속도, 추종 오차 | 제어루프 로그 q_act, v_cmd 미분 | 장애 전/중/후 비교 | 저크·가속도 한계 이내 | jerk-limited, smooth trajectory, safe stop, degradation mode |
| B3 | 장애 복구 시간 | "추론 지연·통신 이상 시 안전한 기존 제어값 유지" (기술요구) · "지연 또는 비정상 추론 발생 시 예외처리 시연" (개발목표) | 장애 주입 → 감속 → 유지 → 새 유효 결과로 복귀까지 시간. 그 사이 주기 미스 | 장애 주입 로그 + ai_state 전이 시각 | 각 전이 시간, 미스 횟수 | 미스 0회 | recovery time, fault tolerance, hold-last-value |
| B4 | HAL 교체 비용 | "서로 다른 로봇을 동일한 상위 명령으로 제어하는 HAL 기능 시연" (기술요구) · "상위 명령과 로봇별 인터페이스를 분리한 HAL 구조" (필수고려) | 로봇 모델 교체 시 변경된 코드량, 상위 명령 → 로봇 명령 변환 지연 | 코드 diff, HAL 계층 전후 타임스탬프 | 줄 수, μs | 보고 (정성 시연 보조) | hardware abstraction layer robot, ros2_control, portability |

## 채점 축과의 대응 ("제안 한마디": 실시간성 · 안정성 · 확장성)

| 채점 축 | 지표 |
|---|---|
| 실시간성 | A1 A2 A3 A4 A5 A6 A7 |
| 안정성 | A8 B1 B2 B3 |
| 확장성 | B4 (+ 설계서) |

## 지표 간 관계 (시간축 위에서)

```
센서 캡처 ──(A3 추론시간)──▶ 추론 완료 ──(전달)──▶ 제어루프 수신 ──(A5 반영 지연)──▶ 명령 송출
│◀────────────────────────────── A6 End-to-End ──────────────────────────────────▶│
                                                   ▲ 이 루프가 매 1ms 깨어남: A1 미스, A2 지터
```
