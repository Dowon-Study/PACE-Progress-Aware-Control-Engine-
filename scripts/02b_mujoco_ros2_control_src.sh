#!/usr/bin/env bash
# PAC 2026 PACE — 2b단계: mujoco_ros2_control 소스 빌드 (apt 패키지가 없을 때만)
# 실행: bash scripts/02b_mujoco_ros2_control_src.sh   (sudo 불필요)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WS="$ROOT/ros2_ws"
MUJOCO_DIR="$ROOT/third_party/mujoco-3.15.0"
source /opt/ros/jazzy/setup.bash
mkdir -p "$WS/src"
cd "$WS/src"
[[ -d mujoco_ros2_control ]] || git clone --depth 1 https://github.com/moveit/mujoco_ros2_control.git
cd "$WS"
rosdep update || true
rosdep install --from-paths src --ignore-src -r -y || true
export MUJOCO_DIR
colcon build --symlink-install --cmake-args -DMUJOCO_DIR="$MUJOCO_DIR" -DCMAKE_BUILD_TYPE=Release
echo "== 완료. 사용 시: source $WS/install/setup.bash"
