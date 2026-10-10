#!/usr/bin/env bash
# PAC 2026 PACE — 2단계: ROS 2 Jazzy + ros2_control + MuJoCo 연동 패키지
# 실행: sudo bash scripts/02_ros2_jazzy.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요"; exit 1; }

echo "== [1/4] 로케일 / 저장소 준비"
apt-get install -y software-properties-common locales
locale-gen en_US en_US.UTF-8 >/dev/null
add-apt-repository -y universe

echo "== [2/4] ROS 2 apt 소스 등록 (ros2-apt-source)"
VER=$(wget -qO- https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F tag_name | awk -F'"' '{print $4}')
CODENAME=$(. /etc/os-release && echo "$UBUNTU_CODENAME")
TMP=$(mktemp -d)
wget -qO "$TMP/ros2-apt-source.deb" \
  "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${VER}/ros2-apt-source_${VER}.${CODENAME}_all.deb"
dpkg -i "$TMP/ros2-apt-source.deb"
rm -rf "$TMP"
apt-get update -y

echo "== [3/4] ROS 2 Jazzy 설치"
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ros-jazzy-desktop ros-dev-tools \
  ros-jazzy-ros2-control ros-jazzy-ros2-controllers ros-jazzy-controller-manager \
  ros-jazzy-hardware-interface ros-jazzy-realtime-tools \
  ros-jazzy-xacro ros-jazzy-robot-state-publisher ros-jazzy-joint-state-publisher-gui \
  ros-jazzy-rmw-cyclonedds-cpp \
  python3-colcon-common-extensions python3-rosdep python3-vcstool

echo "== [4/4] mujoco_ros2_control (apt에 있으면 설치, 없으면 안내)"
if apt-cache show ros-jazzy-mujoco-ros2-control >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y ros-jazzy-mujoco-ros2-control
else
  echo "   apt 패키지 없음 → scripts/02b_mujoco_ros2_control_src.sh 로 소스 빌드하세요 (sudo 불필요)"
fi

[[ -f /etc/ros/rosdep/sources.list.d/20-default.list ]] || rosdep init
echo "== 완료. 사용자 셸에서: rosdep update && source /opt/ros/jazzy/setup.bash"
