# validation — PACE 성능측정·지표 산출 작업 공간

담당: 성능평가 (측정 · 지표 · 시각화 · 리포트)
역할: 다른 팀원이 만든 모델/플랫폼을 받아 **과제가 요구하는 정량 벤치마크 전부**를 뽑아 팀에 전달한다.

## 폴더 구조

```
validation/
├── README.md        # 이 문서: 역할, 작업 흐름, 전달물 정의
├── configs/         # 측정 조건 정의 파일 (어떤 커널/격리/부하/시간으로 쟀는지)
├── raw/             # 원본 측정 데이터. 절대 수정하지 않음 (cyclictest 출력, 제어루프 로그 CSV)
├── scripts/         # 파싱 · 분석 · 그래프 스크립트
├── figures/         # 생성된 그림 (스크립트가 만든다. 손으로 넣지 않음)
├── reports/         # 팀에 전달하는 리포트 (조건별 표 + 그림 + 해석)
└── templates/       # 측정 로그 양식, 제어루프 로그 포맷 약속, 리포트 양식
```

## 작업 흐름 (한 번의 측정 사이클)

```
[입력]  모델/플랫폼 담당자가 실행 가능한 산출물을 넘김
   │     - 실행 방법 (명령 한 줄)
   │     - 제어루프 로그 CSV (templates/control_loop_log_format.md 형식)
   │     - 바뀐 점 요약 (어떤 버전인지)
   ▼
[1] configs/ 에 측정 조건 기록 (커널, 격리, 부하, 지속시간, 반복 횟수, 버전)
[2] 측정 전 체크리스트 통과 (아래)
[3] 측정 실행 → raw/ 에 저장 (파일명 규칙 준수, 메타데이터 헤더 포함)
[4] scripts/ 로 raw/ 를 분석 → figures/ 그림 + 통계표
[5] reports/ 에 리포트 작성 → 팀 전달
```

## 과제가 요구하는 측정 항목 (전달물의 최소 범위)

PDF에 문구로 명시된 정량 지표 (A) 와, "필수 고려사항"을 증명하기 위해 우리가 정한 파생 지표 (B).

| # | 항목 | 데이터 출처 | 통계량 | 합격 기준 |
|---|---|---|---|---|
| A1 | 제어주기 (데드라인 미스) | 제어루프 로그 t_wake | 주기 미스(>1ms) 횟수 | 0회 |
| A2 | 지터 | cyclictest (환경) + 제어루프 로그 (실제) | min / avg / p50 / p99 / p99.9 / max, 100μs 초과 횟수 | max ≤ 100μs |
| A3 | AI 추론시간 | AI 로그 t_infer_start → t_infer_end | 분포, max | 보고 |
| A4 | AI 추론 주기 | AI 로그 연속 t_publish 차이 | 분포 | 보고 |
| A5 | 제어 반영 지연 | ai_t_recv → 처음 반영된 주기의 t_cmd | 분포, max | 보고 (PDF가 3회 언급, 핵심) |
| A6 | End-to-End 지연 | ai_t_capture → 처음 반영된 주기의 t_cmd | 분포, max, 구간별 분해 | 보고 + 설계값 비교 |
| A7 | AI 부하 유무 비교 | A1·A2 를 부하 조건별 반복 | 조건별 나란히 | 부하 있어도 A1·A2 유지 |
| A8 | 조건별 동작 시각화 | 정상 / 지연 / 누락(중단) / 이상값 / 통신단절 5조건 시계열 | 그래프 | 급격한 동작 없음 |
| B1 | 검증 거부율 | ai_state == reject 횟수 / 전체 결과 수, 단계별(범위·시간·유효성) | 횟수, 비율 | 유효기간 만료 결과 사용 0회 |
| B2 | 안전 동작 | q_act, v_cmd 시계열에서 최대 저크·가속도·추종 오차 | 장애 전후 비교 | 저크 한계 이내 |
| B3 | 장애 복구 시간 | 장애 주입 → decel → hold → 복귀까지 | 시간, 그 사이 주기 미스 | 미스 0회 |
| B4 | HAL 교체 비용 | 로봇 모델 교체 시 변경 코드량, HAL 변환 지연 | 줄 수, μs | 보고 |

## 실험 매트릭스

| 축 | 값 |
|---|---|
| 커널 | generic (베이스라인, docs/benchmarks) / **realtime 6.8.1-1061** |
| 격리 | 없음 / isolcpus / CCX 통째 격리 (현재 적용: CPU 4-7, 20-23) |
| 부하 | 유휴 / stress-ng / 실제 AI 추론 (GPU) / AI + MuJoCo + ROS 2 전부 |
| 지속시간 | 30초 (확인용) / 10분 (제출용) / 1시간+ (최악값 신뢰도용) |
| 반복 | 조건당 최소 3회 |

## 파일명 규칙

```
raw/<날짜>_<커널>_<격리>_<부하>_<지속>_r<회차>.<확장자>
예) raw/20261009_rt_ccx_idle_30s_r1.txt
    raw/20261009_rt_ccx_stress_600s_r2.txt
    raw/20261012_rt_ccx_ai-gpu_600s_r1_ctrl.csv
```

약어: 커널 `generic|rt` · 격리 `none|isol|ccx` · 부하 `idle|stress|ai-gpu|full`

모든 raw 파일 첫머리에 메타데이터 헤더를 남긴다 (templates/measurement_log.md 참고).

## 측정 전 체크리스트

- [ ] `uname -v` 에 PREEMPT_RT
- [ ] `cat /proc/cmdline` 에 isolcpus (격리 조건일 때)
- [ ] governor performance (`cat /sys/devices/system/cpu/cpu4/cpufreq/scaling_governor`)
- [ ] 브라우저, IDE, 다른 측정 프로그램 종료
- [ ] 다른 팀원이 같은 PC에서 GPU/CPU 쓰는 중이 아닌지 확인
- [ ] 측정 명령과 조건을 configs/ 에 먼저 적음

## 기존 자료

- RT 커널 적용 전 베이스라인: `../docs/benchmarks/` (유휴 최대 592μs, 부하 1325μs)
- 환경 구성: `../docs/ENVIRONMENT.md`
- 학습 로드맵: `../docs/LEARNING_ROADMAP_PERF.md`
