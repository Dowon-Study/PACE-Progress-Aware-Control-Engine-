# 구현 진행 상황 (docs/IDEA_FIXED.md 12절 기준)

| # | 단계 | 상태 | 산출물 |
|---|---|---|---|
| 1 | 메시지 규격 + 상태 구조체 | ✅ 2026-10-09 | `pace/include/pace/msg.h`, `state.h`, Python 미러 `pace_py/msg.py`, 레이아웃 테스트 |
| 2 | 락프리 공유메모리 | ✅ | `spsc.h`, `seqlock.h`, `shm.h/.c`, `pace_py/shm.py`, C/Python 왕복 테스트 |
| 3 | 1kHz 루프 뼈대 + 자체 MuJoCo 백엔드 | ✅ | `rt.c`, `sim_link.c`, `hal.h`, `hal_sim_shm.c`, `pace_control.c`, `pace_sim.c`, `metrics_dump.py`. 실측: 유휴 최대 16.7μs / 부하 41.8μs |
| 3b | **용접 시연 장면 (UR5e)** | ✅ | `pace/models/ur5e/weld_ur5e.xml`: Menagerie UR5e + 토치·툴 사이트·근접 카메라(`ur5e_torch.xml`), 작업물 판, 용접선(직선-원호-직선 0.43m, 참값 사이트 107개 `seam_truth.json`), 전경 카메라, 작업대(상면 0.30m) 위 작업물, IK 로 구한 `weld_home` 키프레임(툴이 용접선 시작점 2mm 위, 토치 수직, 팔꿈치 위, 베이스가 작업물 방향, 충돌 0). 시뮬에 이상적 중력 보상 추가(없으면 59mm 처짐). 락스텝 10초 유지 시 간격 2.01mm 유지 |
| 3c | **GT 데이터 생성기** | ✅ | `pace_py/datagen/`: 용접선 형상 6종 랜덤 생성(`seams.py`), 판 텍스처+장면 자동 작성, 일정 속도·진행각 궤적 IK(`trajectory.py`), 에피소드 실행·렌더·라벨(`collect.py`). ideal/nominal 모드, 보정 라벨 자동. 속도 피드포워드(ctrl = q + 0.2·qd, 서보 kv/kp)로 추종 오차 2.6→0.1mm. 에피소드별 결정적 시드, 8프로세스 병렬(80개/분). **1차 데이터셋: 240 시도 → 225 성공**(폐기 15: IK 해 갈라짐), ideal 112 / nominal 113, 형상 6종(polyline 25, 나머지 40), 총 용접 길이 49.5m, 80.9분, 프레임 147k×2, 보정 라벨 1~13mm, 7.9GiB. 포맷: `data/gt/README.md` |
| 4 | 가짜 공급자 + 3단계 검증기 + 상태 감시기 | ✅ 2026-10-09 | `config.c`(key=value 파라미터), `refbuf.c`(2슬롯 시간 인덱스 재생 = 5단계 기준선), `validator.c`(헤더→범위→시간→유효성), `monitor.c`(실측+룩어헤드, 히스테리시스, 정지 결정권), `pace_control.c` 통합, `fake_ai.py`(GT 청크 발행 + 장애 주입 7종, 상태 인지 재계획/`--open-loop`), `plot_run.py`, `run_episode.sh`. 단위 테스트 7개. 결과: docs/benchmarks/README.md 4단계 절 |
| 5 | 진행도 접합 (PATH, PATH_S) + 비교 정책 3종 + 재적합 블렌딩 | ✅ 2026-10-09 | `refbuf.c` 정책 모듈(timeidx/immediate/progress), 투영(타임스탬프 창·단조·NO_OVERLAP), 오프셋 감쇠 블렌딩, PATH_S(s 재생, sdot_nominal), 룩어헤드 평가; `pace_control --policy`; 공급자 `--msg path_s`, `--open-loop`, `--target-latency`; `eval_run.py`(선분 투영 오차·툴속도·완주·저크), `compare_policies.py`(시나리오 프리셋 8종), `plot_scenarios.py`; 시뮬 외란 `--disturb-*`. 결과: benchmarks README 5단계 절 |
| 6 | 페이싱 + 규칙 외삽 + 사다리 + 장애 주입기 → 공백 T 측정 | ✅ 2026-10-09 | 버퍼 여유 페이싱(`pace_*` 설정), 규칙 외삽(`ext_*`, refbuf), 참조 소진 기반 BLIND(유지→정지), 사다리 모드(NORMAL/PACING/EXTRAP/HOLD/STOPPED/RECOVER), `gap_sweep.py`, `plot_gap.py`, 평가기 정지·페이싱·외삽 지표. **정지 0회 한계 T: hold 2s → 페이싱+외삽 4s**. 결과: benchmarks README 6단계 절 |
| 7 | 작은 눈(고전 CV) + 기준 경로 + CORRECTION → 시나리오 ① | ✅ 2026-10-10 | `kin.c`(MuJoCo 운동학 전용 FK/DLS IK, 루프 안 ≤15μs), `refpath.c`(교시 경로 'RPTH' 파일, s 매개화), `pace_control --refpath --kin-model`(툴 공간 목표 = 교시점 + lat·n + ẑ(standoff+h), CORRECTION 검증: 범위·순서·점프 3mm, 100ms 블렌딩, 눈 끊김 → EYE_STALE SLOW), `make_refpath.py`(GT → 교시/실제 경로), `pace_py/eye/`(`seam_eye.py` 고전 CV 눈: 토치 마스크·꼭대기 자동 학습, 열별 중앙값 + 2차 곡선 Huber 적합, 절대 보정량 = FK 로 잰 적용 오프셋 + 영상 잔차, 중앙값 7·이상치 게이트 3mm·운동 게이트 10mm/s·변화율 6mm/s; `calibrate_eye.py` 데이터셋 라벨로 px→mm RANSAC 보정; `eye_frames_fig.py`), `eval_refpath.py`(실제 용접선 대비 가로 오차), `run_refpath.sh`. **결과: 고정구 오차 1.5mm → 0.29mm, 9mm → 1.3s 안에 0.6mm, 눈 4초 끊김에도 정지 없이 완주**. benchmarks README 7단계 절 |
| 8 | HAL 정식화(hardware_interface), 로봇 B → 시나리오 ④ | ✅ 2026-10-10 | **HAL 정식화**: 정지 3단계 의미 확정(DECEL=램프 위치 명령 / HOLD=진입 순간 위치 잠금 / ESTOP=브레이크 체결·이후 명령 무시·폴트 비트, `pace_sim.c`), 폴트 코드(`PACE_HALF_*`), RT 계약 측정(read/write 실측 vs 선언 WCET → `summary.hal`), 틱 레코드에 `stop_level`·`arc_on`. **ros2_control 경로**: `src/hal_ros2.cpp`(ResourceManager 로 hardware_interface 플러그인 적재, URDF `<limit>` → HAL 공통 한계값, position+velocity 명령, `--hal ros2 --urdf`), 자체 플러그인 `ros2/pace_mujoco_hardware.cpp`(pace_sim 을 ros2_control SystemInterface 로 노출, ament 인덱스는 `build/ros2_prefix`), URDF 2종(`ur5e_mock.urdf` = mock_components/GenericSystem, `ur5e_pace_mujoco.urdf`). **로봇 B**: `models/panda/panda_torch.xml`(Panda 7축 + 동일 토치·카메라), `make_panda_scene.py`(UR5e 에피소드 장면의 작업물·용접선 그대로 + IK weld_home), `run_refpath.sh ROBOT=panda`. **시나리오 ④**: `pace_sim --fault-at/--fault-dur`(드라이브 폴트 주입), 제어기 정지 사다리(STOP 판정 → DECEL → HOLD → 2s 지속 시 ESTOP 체결, 아크 OFF 즉시, 정지 중 보정 무시·목표 동결, 밀려났으면 실측 위치에 재고정 후 복귀), `plot_stop_ladder.py`. 결과: benchmarks README 8단계 절. **보충(10-10)**: 로봇 C·D(KUKA iiwa14, UFactory xArm7, `models/iiwa14`, `models/xarm7`, `make_robot_scene.py`, `ROBOT=iiwa14|xarm7`) 같은 제어기로 눈 보정 0.32 / 0.31 mm, 정지 사다리 동일 타임라인. 비교 영상 `render_compare_video.py` → `docs/figures/compare_gap6.mp4` |
| 9 | 로컬 감독 계층 블록 (연속 정책 + 감속 조언기) | ✅ 2026-10-10 (+9c 절제 실험) | `pace_py/local/`: `data.py`(GT ideal 112 에피소드 → 문맥 300ms/목표 1s 창 229k), `model.py`(조건부 flow matching 연속 정책 MLP 1.19M, 회귀 MLP 1.04M + 조언기), `train.py`(GPU 66s/300 에폭), `local_block.py`(비실시간 프로세스: 100Hz 상태 → 100ms 마다 1s PATH 청크 supplier=LOCAL, 3차 다항 평활, 정지 게이트, 추론 1.7ms CPU). 제어기: LOCAL 슬롯·사다리 ② 채택(AI 참조 소진 시, `local_max_ns` 상한, 100ms 재접합), 조언 PARAM 상한, 모드 LOCAL, `summary.local`. 설정 `gap_local.cfg`(3s), `gap_local_long.cfg`(10s). 도구 `gap_post.py`(중단 구간 내 지표), `plot_gap_local.py`. **결과: 정지 0회 한계 T 4s → 5s(3s 상한) / ≥10s(10s 상한), 용접 허용 1mm 안에서는 약 6s**. 조언기는 관절 이력만으로는 무효(기본 꺼짐). benchmarks README 9단계 절 |
| 10 | 실제 AI 모델(ACT급) + 보조 실험 | 🔶 2026-10-10 연결 완료 / 모델 폐루프 미달 | `pace_py/ai/`: `data.py`(GT ideal 프레임 2카메라 + q + 300ms 이력 → 1s 청크, GPU 상주), `model.py`(ACT급 경량 6.4M: CNN 토큰 ×2 + Transformer enc/dec, 조언기 머리), `train.py`(bf16, 20 에폭 6분), `augment.py`(흔들린 자세 재렌더 복귀 증강, 손목 회전 강조), `pace_py/supplier/ai_act.py`(실제 AI 공급자: 장면 렌더→추론→PATH supplier=AI, 3차 평활, 출력 가드, 워밍업, E2E=촬영 시각), `run_ai.sh`(`pace_sim --init-q` 리드인 자세). **연결 지표**: 청크 수락 100 %(평활 후), GPU 추론 6.4 ms p50, 추론 중 루프 지터 불변. **모델 품질**: 검증 300ms 오차 3.6 mrad(로컬 정책 1.9, 규칙 외삽 3.5) 이지만 폐루프에서 발산(손목 회전 자기 피드백, 복귀 증강으로도 미해결) → 용접 완주 실패. gym-aloha/LIBERO 보조 실험은 패키지 부재로 미수행. 교훈 절 참조 |
| 11 | 측정·시각화, 비교 실험 자동화, 설계서 | ✅ 2026-10-10 (설계서 `docs/DESIGN.md`) | 과제 평가 항목 매핑: 접촉력 센서(`tip_touch`, `tool_force`) + 감시기 SLOW/STOP + 스탠드오프 상승 규칙 + 돌출부 시연(`make_bump_scene.py`, `plot_contact.py`), 공정 상태 추론기(규칙, `process_monitor.py`: 입열 지수 유지 아크 출력 PARAM, DEFECT EVENT), 틱 레코드 `arc_power_pct`·`tool_force_cN`, AI 연산 부하 6조건 지터 비교(`ai_load_sweep.py`), 조건별(정상·지연·단절) 통합 시각화(`plot_conditions.py`). 설계서 `docs/DESIGN.md`(아키텍처 개념설계서: 원칙·계층·메시지·루프·사다리·HAL·시나리오 ①~⑧ 수치·교훈·한계·재현). 남음: 여러 에피소드 평균 |

## 실행 방법 (3단계)
```bash
cd pace && cmake -S . -B build -G Ninja && cmake --build build && (cd build && ctest)
cd build && ./pace_sim --model ../models/ur5e/weld_ur5e.xml --cpu 12 &   # 시뮬 (비실시간 코어), 용접 장면 UR5e
./pace_control --cpu 4 --prio 99 --duration 20 --traj sine            # 1kHz 루프 (격리 코어)
cd ../.. && .venv/bin/python -m pace_py.tools.metrics_dump --shm /pace --out docs/benchmarks/run.csv
```

## 모델
- 기본 시연 모델: `pace/models/ur5e/weld_ur5e.xml` (UR5e). `arm6_test.xml` 은 타이밍 뼈대 검증용 임시 모델.
- 로봇 B: `pace/models/panda/panda_torch.xml` (Menagerie panda_nohand + 토치, 베이스 x=0.10) + `_gen_epXXXX_panda.xml` (`make_panda_scene.py`). 서보 kv/kp=0.1 이라 `pace_sim --ff-tau 0.1` (run_refpath.sh 가 자동 지정).
- 토치 근접 카메라 `cam_tool`(160×120, 토치 뒤 7cm 위 5cm, 앞으로 기울임)은 7단계에서 작은 눈 입력으로 확정. 꼭대기 픽셀(76,59)·토치 마스크는 보정 때 자동 학습해 `pace_py/eye/calib.json` 에 저장.

## 자세·장면 메모
- UR5e 는 pan=0 에서 팔이 -x 방향으로 뻗는다(Menagerie 좌표). 작업물(방위각 -17°)을 향하는 pan 은 약 148°~162°이며, 148°가 정답이다 (처음 "뒤로 넘어간 자세"로 보였던 것은 베이스 방향이 아니라 작업물이 바닥 높이라 팔이 눕혀진 것). 작업대를 넣어 해결.
- IK 다중 시작 선택 기준: 위치/자세 오차, 관절 한계 여유 0.1rad, pan 이 정면 ±0.6rad, 팔꿈치 > 0.3, 어깨 -2.0~-0.5, 충돌 0.
- 테스트 스크립트에서 qpos 만 바꾸고 ctrl 을 안 바꾸면 서보가 이전 목표로 끌어당겨 팔이 튄다(1.36m 이동 소동의 원인). pace_sim 은 매 틱 ctrl 을 받으므로 해당 없음.

## 4단계에서 배운 것 (5단계 설계 입력)
- **시간 인덱스 재생은 페이싱이 불가능하다.** 재생 시각을 늦추면 벽시계로 찍힌 대기 청크의 시작 시각에 영원히 닿지 못해 교착. 기준선에서는 재생 시각=벽시계로 고정하고 SLOW 는 기록만 한다. 진행도 접합(5단계)이 이 제약을 푼다.
- **채택 즉시 교체는 1.6배속 버그를 만들었다.** 새 청크 시작 시각으로 재생 시각을 당기면 100ms 마다 60ms 씩 앞지름. 2슬롯 버퍼(현재/대기, t0 에 승격)로 해결 — 이것이 "도착 즉시 반영" 과 "시간 인덱스" 기준선의 올바른 구현.
- **유효성 검증은 "지금 벽시계 점" 이 아니라 "재생 시각 점" 과 비교**해야 로봇이 늦어도 정상 청크를 거부하지 않는다.
- **상태를 안 보는 AI(open-loop) 는 중단 후 복귀 불가**(DEVIATION 연속 거부). 상태 인지 재계획(현재 위치에서 다시 계획)이면 복귀한다. 실제 AI 는 관측을 조건으로 쓰므로 후자가 현실적이고, 전자는 최악 사례 기준선.
- 가짜 공급자의 진행 위치 추정은 관절 최근접 탐색이 아니라 **시간 장부 + 불일치 시 재동기화**여야 한다 (최근접 탐색은 느린 구간에서 모호해 청크가 어긋남).
- 시뮬에 속도 피드포워드(kv/kp=0.2s) 가 없으면 추종 오차 0.1rad 로 TRACK_ERR 가 오발.

## 5단계에서 배운 것 (6단계 설계 입력)
- 페이싱은 반드시 진행도 축(재생 인덱스/s)에서. 관절별 속도 캡은 경로를 뒤튼다.
- 시간 인덱스는 페이싱 불가·중단 후 2.4배 따라잡기 튐 → 과제의 "급격한 동작 방지" 요건을 구조적으로 못 지킨다. 이것이 진행도 접합의 존재 이유를 실측으로 보여준다.
- 상태 무시 AI 아래서는 어떤 정책도 페이싱이 안 된다. 메시지 규격에 "직전 구간 포함"(RTC 식 겹침) 또는 상태 조건부가 전제돼야 함 → 설계서 요구사항으로 명시.
- 가짜 공급자의 진행 추정: 시간 장부 예측 + 예측 근방 국소 최근접(동률은 예측 쪽) + 큰 불일치 시 광역 재탐색. 정지 구간(리드인) 동률 처리를 틀리면 공급자가 시작점에 갇힌다.
- 평가의 용접 구간은 "툴이 용접선에 닿은 시각 + 0.3s"부터. 고정 시각(4.5s)은 페이싱 시 접근 구간을 오염시킨다.
- 즉시 반영 vs 진행도: 상태 인지 AI 에서는 거의 같음. 차이는 관측시각 청크(저크)와 복귀 완주. 6단계 페이싱·연장과 결합하면 더 벌어질 것으로 예상.

## 6단계에서 배운 것
- 페이싱 시작 시점(여유 목표·최저 속도)이 "버티는 길이 T" 와 "정상 시 느려짐" 사이의 트레이드오프를 결정한다. 설정으로 빼두었고 스윕 축으로 쓴다.
- BLIND(정지) 판정은 "마지막 청크 이후 시간" 이 아니라 "참조(외삽 포함)가 바닥난 뒤 시간" 이어야 사다리와 일관된다.
- 외삽은 재생 속도의 영향을 받는다 (경로시간 400ms 를 0.2배로 재생하면 벽시계 2초). 상한은 경로시간·거리 둘 다로 건다.
- 평가의 "용접 중" 구간은 툴이 용접선 위에서 마지막으로 움직인 시각까지로 잘라야 에피소드 끝 정지가 섞이지 않는다.

## 7단계에서 배운 것
- 눈이 영상에서 재는 것은 '지금 툴 기준' 잔차다. 제어기가 받는 CORRECTION 은 '교시 경로 기준' 절대 오프셋이므로, 눈이 FK 로 잰 "이미 적용된 오프셋" 을 더해 절대량으로 바꿔 보내야 한다. 잔차를 그대로 보내면 보정이 한 번 들어간 뒤 멈춘다.
- 측정은 정지 상태에서 0.36mm(rms)인데, 툴이 가로로 빠르게 움직이면 수 mm 씩 틀린다 (IK 가 위치는 수렴하고 자세는 ~1.7° 늦게 따라와 카메라가 기운다). 이것이 그대로 피드백되면 ±10mm 발산 진동(1.7Hz)이 난다 → 눈 쪽에 "툴이 10mm/s 보다 빨리 움직이는 프레임은 안 쓴다" 는 운동 게이트와 6mm/s 변화율 제한을 두고, 제어기는 첫 보정도 0 기준으로 점프 3mm 를 제한한다. 고정구 오차는 느리게 변하는 양이므로 이 제한이 성능을 깎지 않는다.
- 160×120 렌더에서 프레임별 선 검출은 ±3px 로 튄다 (앨리어싱). 직선 Huber 적합은 원호 용접선에서 깨지므로 열별 중앙값 → 꼭대기 ±30열 2차 곡선 적합으로 바꿨다 (검출률 58% → 97%).
- 용접선 끝에 닿으면 눈이 선을 못 보는 것이 정상이다. 이때 EYE_STALE → SLOW 가 걸리는데, 경로가 끝났으므로 무해하다. 끊김 4초(10~14s) 동안은 마지막 보정을 유지하며 0.5배로 진행하고 눈이 돌아오면 바로 복귀한다 (오차 0.30mm, 정지 0회).
- 보정 상수항(3.3mm)은 카메라 꼭대기 픽셀과 TCP 의 영상 위치 차이다. 잔여 편향 −0.3~−0.6mm 는 보정 잔차(p95 0.78mm) 안이며, 에피소드별 기하(진행각·높이)에 따라 달라진다 → 10단계에서 실제 AI 모델 쪽 보정과 함께 다룬다.

## 8단계에서 배운 것
- "제조사 비종속" 의 실체는 함수 포인터 5개(read/write/stop/limits/lag)와 공통 데이터 구조(한계값·폴트 비트·정지 3단계·WCET 계약)다. ros2_control 플러그인은 그 위의 번역 층일 뿐이고, 1kHz 루프는 어느 백엔드가 꽂혔는지 모른 채 같은 용접 결과(0.29 vs 0.31mm)를 낸다.
- ros2_control 경로의 비용은 측정 가능하다: HAL read 최대 1.6 → 39.5μs, 루프 실행 p99 11 → 16μs(최대 68μs). 1kHz 예산(1ms) 안이지만 WCET 계약 위반 1회가 기록됐다. 실 로봇 드라이버는 이 계약값을 스스로 선언해야 한다.
- 플러그인이 위치 명령만 노출하면 속도 피드포워드가 사라져 전이 구간에서 추종 오차 0.1rad → 정지 판정이 반복된다. position+velocity 명령 인터페이스를 둘 다 노출하는 것이 HAL 요구사항이다.
- ros2_control 은 read() 가 ERROR 를 돌려주면 컴포넌트를 영구 비활성화한다. 락스텝 시뮬처럼 "아직 새 상태가 없다" 는 일시 상황은 OK + 지난 상태 유지로 처리해야 한다.
- HOLD 는 "진입 순간의 위치" 를 잠가야 한다. 매 틱 현재 위치로 갱신하면 서보 강성이 0 이 되어 외란에 밀린 채로 남고, 추종 오차가 안 풀려 ESTOP 까지 간다.
- 정지 중에는 목표를 동결하고(보정 무시) 로봇이 밀려났을 때만 명령을 실측 위치에 재고정한다. 그렇지 않으면 STOPPED↔HOLD 가 틱마다 토글한다.
- 외란 시연은 세기 조절이 필요하다: 250Nm 는 작업 영역 밖으로 밀어내 ESTOP(정당한 결과), 180Nm 는 추종 오차 정지 뒤 복귀. 두 경우 모두 감시기 로그에 물리적 트리거가 남는다.

## 9단계에서 배운 것
- 로컬 연속 정책의 출력은 AI 와 같은 PATH 청크(supplier=LOCAL)다. 제어기 변경은 "슬롯 하나 + AI 참조가 바닥났을 때 채택" 뿐이고 검증기·접합·페이싱은 그대로다 (사다리 ②가 ③ 외삽 앞에 끼어든다).
- 흐름 샘플은 점 단위 잡음(가속도 20 rad/s²)이 있어 검증기 RANGE_ACC 에 걸린다. 1초 지평의 용접 동작은 매끈하므로 원점을 지나는 3차 다항식으로 평활하면 검증을 통과하고 접합도 매끈하다.
- 정책의 신뢰 구간은 짧다: 300ms 오차 1.9 mrad(규칙 외삽 3.5) 이지만 1s 오차 20 mrad. 그래서 새 청크가 올 때마다(100ms) 다시 접합해 각 청크의 앞 200~300ms 만 쓴다. 그래도 6s 를 넘기면 누적 드리프트가 1mm 를 넘는다 → "멈추지 않는 한계" 와 "허용 오차 안에서 버티는 한계" 를 구분해 보고해야 한다.
- 이력에 움직임이 없으면 이어 그릴 것도 없다(정지 게이트). 없으면 작업 끝에서 정책이 밀고 나간다. 실제 시스템에서는 AI 가 완료 EVENT 를 보내야 한다.
- 감속 조언기는 관절 이력만으로는 300ms 앞 곡률 변화를 예측하지 못했다(MAE 6.2 vs 평균 예측 2.6 mrad). 관절 공간에는 앞이 보이지 않는다 → 영상·용접선 문맥이 필요하고 10단계로 넘긴다. 학습 모델의 조언은 상한으로만 작용하므로 꺼도 안전하다.
- (9c 절제, 재현 확인) 같은 입력·출력·청크 구성의 회귀 MLP 가 폐루프에서 flow matching 보다 안정적이다. flow matching 도 로컬 재생 중엔 1 mm 안이지만 손목 회전·높이로 드리프트하고(8 s 에 −166 mrad, +2.6 mm), 15 mm 오차는 AI 복귀 접합 과도 응답이다. 접합 블렌딩을 점프 비례로 바꾸니(`splice_blend_rate`) 15.7 → 2.3 mm. 오프라인 오차·편향이 낮다고 폐루프가 좋은 것이 아니며, 킥은 모델이 아니라 접합·사다리다. 로컬 블록 기본값은 복귀 증강 회귀 MLP(`local_mlp_rec.pt`, `local_block.py --kind mlp` 가 기본; flow matching 은 `--kind fm --ckpt local_block.pt`). flow matching 은 복귀 증강으로도 못 살렸다(가로 12.6 mm 이탈).
- 보조 프로세스는 SIGINT 로 안 죽을 수 있다(torch 안). SIGTERM + 시작 시 pkill 로 정리하지 않으면 생산자가 겹쳐 SPSC 큐 가정을 깬다 (첫 스윕을 그래서 다시 돌렸다. 결과는 같았다).

## 10단계에서 배운 것
- 실제 AI 모델 연결에 필요한 것은 전부 플랫폼 쪽에 있었다: 공급자 프로세스가 영상→청크를 내고 PATH(supplier=AI)로 보내면 검증·접합·사다리는 그대로 돈다. GPU 추론이 돌아도 격리 코어의 루프 지터는 변하지 않는다 (깨어남 max 13 μs, 실행 p99 7 μs).
- 회귀 출력의 점 단위 잡음은 검증기 RANGE_ACC 에 걸린다(9단계와 같음). AI 래퍼에서 3차 평활 + 변위 상한을 걸어야 한다. 검증기가 거부한 덕에 잡음 청크가 로봇에 닿지 않았다는 것 자체가 4단계 설계의 증거다.
- 영상 한 장 + 관절로는 위상·속도가 안 보여 1s 오차 60 mrad. 300ms 관절 이력을 넣으면 26 mrad(300ms 3.6 mrad)로 로컬 정책 수준이 된다.
- 그래도 폐루프에서는 발산한다. 손목 회전(5번 관절)에 카메라가 붙어 있어 작은 회전 오차가 영상을 바꾸고 다시 회전을 키운다(자기 피드백). 흔들린 자세에서 GT 로 복귀하는 증강(σ 손목 0.08 rad, 69k 프레임 재렌더)으로도 못 잡았다. 남은 처방: 청크를 툴 공간(x,y,z,진행각)으로 내고 손목 회전은 운동학이 정하게 하거나, DAgger 식 폐루프 데이터 수집, 또는 CVAE/확산 정책. 시간 제한으로 여기서 멈춘다.
- 제어기의 비상정지 카운트는 '작업 시작 전 대기(BLIND)' 를 제외해야 한다. 실제 모델은 적재에 3~4 s 가 걸려 이 규칙이 드러났다.
- 폐루프 시작 자세는 모델이 학습한 리드인 자세여야 한다(`pace_sim --init-q`). 장면 키프레임(IK 해)은 GT 시작 자세와 1.5 rad 다를 수 있다.

## 알려진 이슈
- 실제 AI 모델 폐루프 발산 (위). 10단계 보류 항목: gym-aloha/LIBERO 보조 실험(패키지 없음).
- GPU 추론 + 비격리 코어 stress 조건에서 깨어남 지연 max 96 μs (1 ms 예산 안이지만 꼬리가 큼). GPU 드라이버 인터럽트 친화성 점검 필요.
- 로컬 정책 1s 예측 오차 20 mrad(p95 70). 문맥에 영상/용접선 정보가 없고 모델이 작다. 10단계에서 AI 와 같은 입력으로 재학습 검토.
- DLS IK(틱당 반복 제한)가 빠른 가로 이동에서 자세를 1~2° 늦게 수렴시킨다. 자세 가중치 또는 반복 수 조정 필요 (7단계에서는 눈 쪽 운동 게이트로 우회).
- 눈의 초기 수렴: 9mm 고정구 오차를 6mm/s 로 따라가므로 용접 시작 후 1.3초 동안 오차가 남는다. 실제 공정에서는 리드인(용접 전 접근 구간)에서 눈을 먼저 수렴시키는 것이 맞다.
- 시뮬 프로세스가 비실시간 코어 부하와 경쟁하면 lag 최대 8틱. 시뮬 전용 코어 확보 또는 낮은 FIFO 우선순위 부여 필요.
- `/dev/cpu_dma_latency` 권한(-13). udev 규칙 미적용.
- 테스트는 `#undef NDEBUG` 로 assert 를 살림 (Release 빌드 -DNDEBUG 때문에 한 번 멈춘 적 있음).

- 2026-10-10 14단계(추가): 보조 궤적 생성기 온라인 학습 — 계약에 실행 상태 필드(72 B, 10 ms), `online_train.py`(라벨 거름망·재생 버퍼·챔피언/도전자 게이트·원자적 배포), `local_block --online-ckpt` 교체, `run_episode.sh ONLINE=1`. 실시간 영향 없음(주기 미스 0). 폐루프 이득은 미확정(보류 ep36 개선, ep20 악화) → 기본값 보수적, 자동 배포 0회. benchmarks README 14단계 절
