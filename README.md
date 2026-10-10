# PACE — 진행도 기반 접합 (Progress-Aware Control Engine)

**AI 추론·실시간 제어 통합형 RTOS 기반 로봇 상위제어 플랫폼** — PAC 2026 HD현대로보틱스 과제 4, 팀 피지컬100 (윤도원 · 권희재)

AI 가 늦고·끊기고·틀려도 1 kHz 제어기는 멈추지 않는다. AI 액션 청크를 **시간이 아니라 진행도(로봇이 실제로 어디까지 왔는가)** 로 이어 붙이고, AI 가 끊기면 **공백 사다리**(페이싱 → 로컬 보조 궤적 → 규칙 외삽 → 유지 → 정지)로 내려가며, 정지는 **규칙 기반 감시기**만 결정한다. 용접선 추종 시연(MuJoCo 락스텝 1 kHz)으로 12개 지표를 실측했다.

| 핵심 결과 | 값 | 출처 |
|---|---|---|
| 1 ms 제어 주기 미스 | **0 / 532,000 틱** (12개 실행, 장애 주입 포함) | `validation/reports/20261010_PACE_full_validation.md` |
| 제어 루프 깨어남 지연 | max 9.5 ~ 17 μs (GPU 추론 중 13 μs, GPU+CPU 부하 96 μs) | 같은 보고서 §4 |
| 6 s AI 단절 | 기준선(시간 인덱스 재생) 비드 33 % 에서 정지 → **PACE 100 % 완주** | `docs/figures/compare_gap6.mp4` |
| 정지 없이 버티는 단절 길이 | 유지만 2 s → 페이싱+외삽 4 s → 로컬 MLP ≥ 10 s | `docs/benchmarks/README.md` 6·9단계 |
| 비전 보정 | 고정구 오차 1.47 → 0.29 mm, 눈 4 s 끊김에도 0.30 mm | 7단계 |
| 4 로봇 · 2 백엔드 | UR5e·Panda·iiwa14·xArm7 모두 0.30~0.32 mm, 핵심 코드 변경 0 줄 | 8단계·8단계 보충 |
| 캡처 → 제어 반영 E2E | avg 10.3 / p99 15.2 ms (실제 ACT급 모델, GPU 추론 6.5 ms) | 검증 보고서 A6 |

![6 s 단절: 기준선 정지 vs PACE 완주](docs/figures/compare_gap6_t16s.png)

---

## 1. 저장소 구성

```
pace/                 C 실시간 제어기 + MuJoCo 락스텝 시뮬레이터 + HAL (ros2_control 플러그인 포함)
  src/pace_control.c    1 kHz 루프: 3단계 검증기 → 진행도 접합 → 페이싱/사다리 → 명령 생성 → 상태 감시기 → HAL
  src/pace_sim.c        MuJoCo 백엔드 (별도 프로세스, 공유메모리 락스텝, 폴트 주입)
  src/hal_ros2.cpp, ros2/   ros2_control hardware_interface 경로 + 자체 플러그인
  include/pace/         메시지(PATH·PATH_S·CORRECTION·PARAM·EVENT·CONTRACT)·상태·설정
  models/               UR5e·Panda·iiwa14·xArm7 토치 장면 (생성 장면은 스크립트가 만듦)
  config/               시나리오 설정 (gap_*.cfg 등)
pace_py/              Python: 공급자(가짜 AI·실제 ACT급 모델), 작은 눈(CV), 로컬 블록(MLP/flow matching), 공정 상태 추론기, 실행·평가·그림 도구
  tools/                run_*.sh 실행 스크립트, gap_sweep·compare_policies·eval_refpath·plot_* 평가/그림, render_*_video 영상, make_deck 발표자료
  local/ckpt/           로컬 블록 체크포인트 (local_mlp_rec.pt 기본값)
validation/           12개 지표 검증 (verify.py, metrics_core.py), 결과 json/md/png, 보고서, 원본 cyclictest 로그
docs/benchmarks/      단계별 실험 결과 README(수치 표), 스윕 결과 json, 각 실행의 summary.json
docs/figures/         모든 그림 (paper/ 논문 스타일, pitch/ 발표용), 정지 프레임
docs/slides/          발표 PPT(24장 전체판·7분용), 대본, GIF 소재
docs/DESIGN.md        설계서 · docs/STATUS.md 진행표 · docs/ENVIRONMENT.md 환경 구성 · docs/IDEA_FIXED.md 확정 아이디어
scripts/              환경 구성 스크립트 (RT 커널, 코어 격리, ROS 2, 검증, 지터 벤치)
```

이 패키지에서 뺀 것(크기 때문): 생성 데이터 `data/` (15 GB), 실행 원본 로그 `docs/benchmarks/runs/*.csv|trace.bin` (1.7 GB), 실제 AI 모델 체크포인트 (50 MB), `third_party/` (MuJoCo C 라이브러리·Menagerie), 영상 mp4. 전부 아래 절차로 다시 만들 수 있고, 각 실행의 `summary.json` 과 스윕 결과 json, 검증 결과는 포함되어 있다.

---

## 2. 환경

실측 환경: Ubuntu 24.04 · PREEMPT_RT 6.8.1-realtime · Threadripper PRO 3955WX · RTX PRO 5000 · ROS 2 Jazzy · MuJoCo 3.15.0 · PyTorch (CUDA).

```bash
# RT 커널·코어 격리·ROS 2 (sudo, 재부팅 포함) — 자세한 순서와 주의는 docs/ENVIRONMENT.md
sudo bash scripts/01_system_packages.sh
sudo bash scripts/02_ros2_jazzy.sh
sudo bash scripts/03_rt_kernel.sh pro <UBUNTU_PRO_TOKEN>      # 또는 build
sudo bash scripts/04_grub_isolcpus.sh                          # isolcpus=managed_irq,domain,4-7,20-23 nohz_full rcu_nocbs
sudo bash scripts/04b_grub_default_rt.sh && sudo reboot
bash scripts/05_verify_env.sh

# Python
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install python-pptx

# 서드파티 (third_party/)
mkdir -p third_party && cd third_party
curl -L https://github.com/google-deepmind/mujoco/releases/download/3.15.0/mujoco-3.15.0-linux-x86_64.tar.gz | tar xz
git clone --depth 1 --filter=blob:none --sparse https://github.com/google-deepmind/mujoco_menagerie
cd mujoco_menagerie && git sparse-checkout set universal_robots_ur5e franka_emika_panda kuka_iiwa_14 ufactory_xarm7 && cd ../..
bash scripts/link_menagerie_assets.sh        # 로봇 메시를 pace/models/<로봇>/assets 로 연결 (상대 경로 링크)

# C 제어기·시뮬레이터 빌드 (ros2_control 경로까지 빌드하려면 먼저 source /opt/ros/jazzy/setup.bash)
cmake -S pace -B pace/build -DCMAKE_BUILD_TYPE=Release && cmake --build pace/build -j
```

코어 배치(스크립트가 고정): 제어 루프 CPU 4 (레인 b 는 5), 시뮬 12, 눈·로컬 블록 8-11, AI 공급자 14-15, 학습·증강 0-3,16-19. **격리 코어 4-7, 20-23 에는 제어 루프 외에 아무것도 올리지 않는다.**

---

## 3. 데이터 생성

```bash
# 용접선 장면 + GT 궤적 (data/gt/ep_XXXX.npz, 토치·전경 카메라 영상 포함)
.venv/bin/python -m pace_py.datagen.collect --n 112 --mode ideal --workers 8     # 로컬 블록·AI 학습용
.venv/bin/python -m pace_py.datagen.collect --n 40  --mode nominal --start 200   # 눈 보정용
.venv/bin/python -m pace_py.tools.make_refpath --episode 1                       # 교시 경로 (data/refpath)
.venv/bin/python -m pace_py.eye.calibrate_eye                                    # px→mm 보정 (−1.117 mm/px)
```

---

## 4. 실험 재현 (단계 번호는 `docs/benchmarks/README.md` 와 같다)

모든 실행은 `docs/benchmarks/runs/<이름>.{csv,trace.bin,summary.json}` 을 남기고, 평가 도구가 그 파일을 읽는다. 실행 스크립트의 환경변수: `ROBOT=panda|iiwa14|xarm7`, `LANE=b`(병렬 레인), `CFG=`(설정), `SIM_ARGS=`, `CTL_ARGS=`, `LOCAL=1`, `PROC=1`.

| 단계 | 내용 | 명령 |
|---|---|---|
| 0 | 환경 지터 벤치 (cyclictest) | `bash scripts/06_rt_jitter_bench.sh` · 10분: `bash validation/verification/measure_jitter.sh` |
| 4 | 장애 주입 7종 + 검증기 거부 | `bash pace_py/tools/run_episode.sh 4 s4_faultsA_ep4 --faults A` |
| 5 | 접합 정책 비교 (시간 인덱스 / 즉시 / 진행도) 8 시나리오 | `.venv/bin/python -m pace_py.tools.compare_policies --episode 0 --scenario <name>` → `plot_scenarios.py` |
| 6 | 공급 중단 길이 T 스윕 (유지·페이싱·외삽) | `.venv/bin/python -m pace_py.tools.gap_sweep --episode 0 --gaps 0.5 1 1.5 2 3 4 5 --configs hold pacing pacing_ext --tag s6` |
| 7 | 작은 눈 + 교시 경로 + CORRECTION | `bash pace_py/tools/run_refpath.sh 1 s7_eye_ep1 eye` · 평가 `eval_refpath.py --episode 1 --runs s7_teach_ep1 s7_eye_ep1` |
| 8 | ros2_control 경로 | `source /opt/ros/jazzy/setup.bash; CTL_ARGS="--hal ros2 --urdf pace/ros2/ur5e_pace_mujoco.urdf" bash pace_py/tools/run_refpath.sh 1 s8_hal_ros2_eye_ep1 eye` |
| 8 | 로봇 B·C·D | `ROBOT=panda bash pace_py/tools/run_refpath.sh 1 s8_panda_eye_ep1 eye` (iiwa14, xarm7 동일) |
| 8 | 정지 사다리 (HAL 폴트) | `SIM_ARGS="--ff-tau 0.1 --fault-at 10 --fault-dur 5" bash pace_py/tools/run_refpath.sh 1 s8_stop_fault_ur5e eye` → `plot_stop_ladder.py --run s8_stop_fault_ur5e` |
| 9 | 로컬 블록 학습 + 스윕 | `.venv/bin/python -m pace_py.local.train_mlp --epochs 60 --recover-sigma 0.08` · `.venv/bin/python -m pace_py.tools.gap_sweep --episode 0 --gaps 2 3 4 5 6 8 10 --configs local_long --tag s9b` → `gap_post.py` |
| 9c | 절제 (MLP vs flow matching) | `LOCAL_ARGS="--kind fm --ckpt pace_py/local/ckpt/local_fm_rec.pt" ... --tag s9f_fm` vs `--kind mlp` → `plot_local_ablation.py` |
| 10 | 실제 AI 모델 (ACT급) | `.venv/bin/python -m pace_py.ai.augment --sigma 0.01 0.01 0.01 0.02 0.02 0.08 --stride 2` · `.venv/bin/python -m pace_py.ai.train --epochs 20` · `DUR=32 bash pace_py/tools/run_ai.sh 0 s10_ai_ep0` |
| 14 | 보조 궤적 생성기 온라인 학습 | `.venv/bin/python -m pace_py.local.export_replay --n 8000` · `ONLINE=1 LOCAL=1 ONLINE_ARGS="--replay pace_py/local/ckpt/replay_ideal.npz --state runs_online_state.pt" CFG=pace/config/gap_local_long.cfg bash pace_py/tools/run_episode.sh 3 s15_online_collect_ep3 --delay-ms 100 --delay-jitter-ms 50` → `.venv/bin/python -m pace_py.tools.eval_online --gap 6 --runs <이름:에피소드> ...` |
| 11 | 접촉력 조정 | `SCENE_OVERRIDE=pace/models/ur5e/_gen_ep0001_bump.xml bash pace_py/tools/run_refpath.sh 1 s11_contact_ep1 eye` (장면: `make_bump_scene.py`) → `plot_contact.py` |
| 11 | 공정 상태 추론 PARAM | `PROC=1 CFG=pace/config/gap_pacing_ext.cfg bash pace_py/tools/run_episode.sh 0 s11_process_gap --delay-ms 100 --delay-jitter-ms 50 --dropout-from 8 --dropout-to 11` → `plot_process.py` |
| 11 | AI 부하 6조건 지터 | `.venv/bin/python -m pace_py.tools.ai_load_sweep` |
| 11 | 조건별 통합 그림 | `.venv/bin/python -m pace_py.tools.plot_conditions --episode 0` |
| 12 | 12개 지표 검증 | `.venv/bin/python validation/verification/verify.py ctrl docs/benchmarks/runs/<run>.csv --label <name> [--fault-t0 10]` · `verify.py ai <ctrl.csv> <ai.csv>` · `verify.py cyclictest <raw> --thread 4` |
| 13 | 기준선 vs PACE 비교 영상 | `POLICY=timeidx CFG=pace/config/gap_hold.cfg bash pace_py/tools/run_episode.sh 0 s13_baseline_timeidx_gap6_ep0 ...` → `MUJOCO_GL=egl .venv/bin/python -m pace_py.tools.render_compare_video --episode 0 --left s13_baseline_timeidx_gap6_ep0 --right s9b_local_long_gap6_ep0 --gap 12.5 18.6 --out docs/figures/compare_gap6.mp4` |
| 13 | 4 로봇 4분할 영상 | `MUJOCO_GL=egl .venv/bin/python -m pace_py.tools.render_robots_video --episode 1 --out docs/figures/robots4_ep1.mp4` |
| 그림 | 논문 스타일 / 발표용 / 유리 항목 | `validation/scripts/make_paper_figures.py` · `make_pitch_figures.py` · `make_favorable_figures.py` · `make_slide_figures.py` |
| 발표 | PPT·GIF | `.venv/bin/python -m pace_py.tools.make_gifs` → `make_deck` (24장) / `make_deck_7min` (11장) |

주의: 보조 프로세스(로컬 블록·눈·공급자)는 SIGTERM 으로 끝낸다. `pkill` 패턴은 `'local_bloc[k]'` 처럼 자기 셸이 매칭되지 않게 쓴다. 학습·증강은 격리 코어 밖(`taskset -c 0-3,16-19`)에서 돌린다.

---

## 5. 결과 파일 안내

- 단계별 수치 표와 해석: `docs/benchmarks/README.md` (0~13단계, 9c 절제, 8단계 보충 4 로봇)
- 12개 지표 검증 보고서: `validation/reports/20261010_PACE_full_validation.md` — 결과 json/md/png 는 `validation/figures/verification/`, 10분 cyclictest 원본은 `validation/raw/`
- 스윕 결과: `docs/benchmarks/s5_*_compare_ep0.json`, `s6_gap_sweep_ep0*.json`, `s9*_gap_sweep_ep0*.json`, `s13_robots4_eye_ep1.json`, `s13_stop_fault_*.json`
- 각 실행 요약(지터·HAL 계약·정지 사다리·로컬 통계): `docs/benchmarks/runs/*.summary.json`
- 그림: `docs/figures/` (단계별), `docs/figures/paper/` (fig1~6, PNG+PDF), `docs/figures/pitch/` (P1~P8)
- 설계서 `docs/DESIGN.md`, 진행 보고서 `docs/PACE_진행보고서.pdf`, 발표 `docs/slides/`

온라인 학습(14단계)은 실시간 성능에 영향 없이 동작하지만, 보류 에피소드 2개에서 폐루프 이득이 갈려(ep36 개선, ep20 악화) 기본값은 보수적이며 자동 배포가 일어나지 않는다.

솔직하게 적어 둔 한계: cyclictest 10분 메모리·캐시 포화 부하에서 격리 코어도 100 μs 초과 꼬리(0.002 %)가 있다(보고서 §4). 실제 ACT급 모델은 플랫폼 통합은 성공했지만 폐루프에서 발산했다(10단계). flow matching 로컬 블록은 폐루프에서 회귀 MLP 를 이기지 못해 기본값이 MLP 다(9c).

---

## 6. 인용

Smeds K., Lu X., "Effect of Jitter on Precision Motion Control", 2012. · de Graaf M. et al., "Real-time seam tracking for robotic laser welding using trajectory-based control", Control Engineering Practice, 2010.
