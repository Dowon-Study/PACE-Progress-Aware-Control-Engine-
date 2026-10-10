# B4 HAL 교체 비용

## HAL 변환 지연·계약 (summary.json `hal.*`)

| 구성 | HAL read max [μs] | HAL write max [μs] | 선언 WCET read/write [μs] | 계약 위반 | 루프 실행 p99/max [μs] | 완주 s_end [m] |
|---|---|---|---|---|---|---|
| UR5e 6축, sim_shm (직접) | 1.6 | 13.6 | 20.0/20.0 | 0/0 | 10/18.2 | 0.2719 |
| Panda 7축, sim_shm (직접) | 1.6 | 12.9 | 20.0/20.0 | 0/0 | 11/21.4 | 0.2719 |
| KUKA iiwa14 7축, sim_shm (직접) | 1.2 | 10.5 | 20.0/20.0 | 0/0 | 11/17.6 | 0.2719 |
| UFactory xArm7 7축, sim_shm (직접) | 1.7 | 12.8 | 20.0/20.0 | 0/0 | 10/21.8 | 0.2719 |
| UR5e, ros2_control 플러그인 경로 | 39.5 | 25.8 | 30.0/30.0 | 1/0 | 16/68.4 | 0.2719 |

## 교체에 든 코드량

| 교체 종류 | 새로 쓴 파일 (줄 수) | 제어기·검증기·접합·눈 코드 변경 |
|---|---|---|
| 로봇 B 추가 (Panda) | `pace/models/panda/panda_torch.xml` (228), `pace_py/tools/make_panda_scene.py` (65) | 0 줄 (HAL 인터페이스 `pace/include/pace/hal.h` 뒤에서만 교체) |
| 로봇 C·D 추가 (iiwa14, xArm7) | `pace/models/iiwa14/iiwa14_torch.xml` (179), `pace/models/xarm7/xarm7_torch.xml` (111), `pace_py/tools/make_robot_scene.py` (80) | 0 줄 (HAL 인터페이스 `pace/include/pace/hal.h` 뒤에서만 교체) |
| ros2_control 경로 추가 | `pace/src/hal_ros2.cpp` (136), `pace/ros2/pace_mujoco_hardware.cpp` (64), `pace/ros2/ur5e_pace_mujoco.urdf` (26) | 0 줄 (HAL 인터페이스 `pace/include/pace/hal.h` 뒤에서만 교체) |

(용접 오차 mean: UR5e 0.30 / Panda 0.30 / iiwa14 0.32 / xArm7 0.31 / ros2 경로 0.31 mm — `docs/benchmarks/README.md` 8단계·8단계 보충. 정지 사다리도 4 로봇 동일 타임라인: `docs/figures/s13_stop_fault_*.png`)
