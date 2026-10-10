# PACE 개발 환경 구성

대상 머신: `kw-gpu-ws` · Ubuntu 24.04.5 · Threadripper PRO 3955WX (16C/32T) · RTX PRO 5000 72GB · 128GB RAM

## 설치 순서

| 단계 | 스크립트 | sudo | 재부팅 | 내용 |
|---|---|---|---|---|
| 0 | (완료) | ✗ | ✗ | `.venv` Python 환경, MuJoCo 3.15.0 C 라이브러리 (`third_party/`) |
| 1 | `scripts/01_system_packages.sh` | ✓ | 재로그인 | 빌드 도구, rt-tests(cyclictest), trace-cmd, cpupower, GLFW/EGL, `realtime` 그룹 + rtprio/memlock 한도 |
| 2 | `scripts/02_ros2_jazzy.sh` | ✓ | ✗ | ROS 2 Jazzy desktop, ros2_control, ros2_controllers, realtime_tools, colcon/rosdep |
| 2b | `scripts/02b_mujoco_ros2_control_src.sh` | ✗ | ✗ | apt에 `ros-jazzy-mujoco-ros2-control` 이 없을 때만 소스 빌드 (`ros2_ws/`) |
| 3 | `scripts/03_rt_kernel.sh pro <TOKEN>` 또는 `build` | ✓ | ✓ | PREEMPT_RT 커널 |
| 4 | `scripts/04_grub_isolcpus.sh` | ✓ | ✓ | 코어 격리 커널 파라미터 |
| 4b | `scripts/04b_grub_default_rt.sh` | ✓ | ✓ | GRUB 기본 부팅을 RT 커널로 고정, 부팅 메뉴 5초 표시 |
| 5 | `scripts/05_verify_env.sh` | ✗ | ✗ | 전체 검증 + 10초 cyclictest |

```bash
sudo bash scripts/01_system_packages.sh
sudo bash scripts/02_ros2_jazzy.sh
sudo bash scripts/03_rt_kernel.sh pro <UBUNTU_PRO_TOKEN>   # 권장
sudo bash scripts/04_grub_isolcpus.sh
sudo apt-get install -y nvidia-dkms-595-open                 # RT 커널용 NVIDIA 모듈 (아래 참조)
sudo env IGNORE_PREEMPT_RT_PRESENCE=1 dkms install nvidia/595.99.02 -k 6.8.1-1061-realtime --force
sudo bash scripts/04b_grub_default_rt.sh
sudo reboot
bash scripts/05_verify_env.sh
```

## PREEMPT_RT 커널 선택

- **권장: Ubuntu Pro realtime-kernel.** 서명된 공식 커널, 보안 업데이트 유지. 개인 계정은 무료로 5대까지 (https://ubuntu.com/pro). 토큰 발급 후 3단계 `pro` 모드.
- **대안: 직접 빌드.** 메인라인 6.12+ 는 x86_64 에서 PREEMPT_RT 가 내장되어 패치 불필요. 3단계 `build` 모드가 LTS 6.18 소스에 현재 Ubuntu config 를 입혀 `CONFIG_PREEMPT_RT=y` 로 빌드. 32코어 기준 약 20~40분.
- **NVIDIA 드라이버 (실제 적용 결과, 2026-10-09).** Ubuntu 의 사전 빌드 모듈(`linux-modules-nvidia-595-open-*`)은 generic 커널 전용이라 RT 커널에는 없음. `nvidia-dkms-595-open` 을 설치하면 드라이버가 595.99.02 로 통일되지만 DKMS 가 RT 커널 빌드를 자동으로 시도하지 않으며, 수동 빌드도 NVIDIA 의 PREEMPT_RT 검사에서 1차 거부됨. `IGNORE_PREEMPT_RT_PRESENCE=1` 로 재시도하면 빌드·서명·설치 성공 (`/lib/modules/6.8.1-1061-realtime/updates/dkms/nvidia*.ko.zst`). 커널 업데이트 시 같은 절차 반복 필요. GPU 는 AI 추론 계층에만 쓰이므로 만약 RT 커널에서 GPU 가 안 잡히면 AI 추론은 CPU/ONNX 로 대체 가능.
- **Pro 가 추가한 GRUB 설정**: `/etc/default/grub.d/99-realtime.cfg` 의 `GRUB_FLAVOUR_ORDER="realtime"` 이 RT 커널을 최상위 기본 항목으로 올림. 4b 는 여기에 더해 부팅 메뉴를 5초 표시해 문제 시 generic 커널 선택을 가능하게 함.

## 코어 할당 (4단계)

SMT 쌍은 CPU N 과 N+16 이다. L3 캐시(16MB)는 4코어 CCX 단위로 공유되므로, 제어 전용 CCX 를 통째로 격리해 AI 추론과 L3 를 공유하지 않게 한다 (공유 메모리 경합에 의한 잔여 지연 완화).

| CCX | CPU | 용도 | 격리 |
|---|---|---|---|
| 0 | 0-3, 16-19 | OS, IRQ, 하우스키핑 | ✗ |
| 1 | 4, 20 | 1kHz 실시간 제어 루프 (SCHED_FIFO 99) | ✓ |
| 1 | 5, 21 | 경량 모델 / 반영 정책 비동기 작업 | ✓ |
| 1 | 6-7, 22-23 | 예비 격리 코어 (격리 단계별 비교 실험용) | ✓ |
| 2-3 | 8-15, 24-31 | AI 추론(GPU 스레드), MuJoCo, ROS 2, 일반 작업 | ✗ |

커널 파라미터: `isolcpus=managed_irq,domain,4-7,20-23 nohz_full=... rcu_nocbs=... irqaffinity=0-3,8-19,24-31 skew_tick=1 nmi_watchdog=0 nosoftlockup processor.max_cstate=1 amd_pstate=passive` (백업: `/etc/default/grub.pace.bak`)

실행 시 주파수 고정: `sudo cpupower frequency-set -g performance`

## 프로세스 배치 (확정 설계 기준, docs/IDEA_FIXED.md)

새 계층(로컬 감독 블록)은 **환경 변경 없이** 일반 코어의 프로세스로 추가된다. 코어 배치만 고정한다.

| 프로세스 | 코어 | 주기 | 비고 |
|---|---|---|---|
| 1kHz 제어 루프 | CPU 4 (CCX1, 격리) | 1ms | SCHED_FIFO 99, 모델 없음 |
| 예비 / 규칙 외삽 보조 | CPU 5-7 (CCX1, 격리) | - | 필요 시 |
| 로컬 감독 블록 (연속 정책, 감속 조언기, 작은 눈) | CPU 8-11 (CCX2) + GPU 일부 | 30~60Hz | `taskset -c 8-11`, 비실시간 |
| MuJoCo 시뮬 프로세스 (C API, 1ms 락스텝) + 렌더 스레드 | CPU 12-13 (CCX3) | 1ms / 30Hz | 제어기 PC 시계 기준 |
| AI 추론 프로세스 (큰 모델) | CPU 14-15, 28-31 (CCX3) + GPU | 수 Hz~수십 Hz | 두 PC 구성 시 원격으로 이동 |
| 장애 주입기, 측정·시각화, ROS 2 비실시간 노드 | CPU 24-27 (CCX2 SMT) | 비주기 | |
| OS, IRQ | CPU 0-3, 16-19 (CCX0) | - | irqaffinity 고정 |

추가 패키지 (sudo 불필요, requirements.txt 반영): `opencv-python-headless` (작은 눈 고전 검출), `ruckig` (저크 제한 재겨냥, 7축 update 32μs 실측).

두 PC 구성으로 갈 때만 추가 설치: `linuxptp` (PTP 시계 동기화), 전송 계층을 공유메모리 → UDP/DDS 로 교체. 현재 단일 PC 구성에서는 불필요.

## Python 환경 (0단계, 검증 완료)

| 패키지 | 버전 | 확인 |
|---|---|---|
| mujoco | 3.15.0 | mj_step 25 µs/step (humanoid), EGL 오프스크린 렌더 OK |
| torch / torchvision | 2.14.1+cu130 / 0.29.1 | CUDA 13.0, Blackwell sm_120 matmul OK |
| onnx / onnxruntime | 1.23.2 / 1.30.0 | CPU provider |
| numpy / scipy / pandas / matplotlib | 2.5.3 / 1.18.1 / 3.0.6 / 3.11.2 | |
| pytest / jupyter | 9.1.1 / - | |

```bash
source .venv/bin/activate
export MUJOCO_GL=egl        # 헤드리스 렌더
```

MuJoCo C 라이브러리: `third_party/mujoco-3.15.0/` (lib, include, bin/simulate, bin/testspeed, model/). testspeed humanoid 30 µs/step.

## 검증 기준 (5단계)

- `uname -v` 에 `PREEMPT_RT`
- `/proc/cmdline` 에 `isolcpus`
- `ulimit -r` = 99, `id` 에 `realtime`
- cyclictest 10초 (CPU4, FIFO 99, 1ms 주기) 최대 지연 < 100 µs
