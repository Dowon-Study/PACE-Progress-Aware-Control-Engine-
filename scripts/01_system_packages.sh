#!/usr/bin/env bash
# PAC 2026 PACE — 1단계: 시스템 패키지 + 실시간 권한 설정
# 실행: sudo bash scripts/01_system_packages.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요"; exit 1; }
TARGET_USER="${SUDO_USER:-kwuser}"

echo "== [1/4] apt 업데이트"
apt-get update -y

echo "== [2/4] 빌드 도구 / RT 측정 도구 / 그래픽 라이브러리 설치"
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  build-essential cmake ninja-build git curl pkg-config gdb \
  python3-dev python3-venv python3-pip \
  rt-tests stress-ng trace-cmd numactl hwloc util-linux \
  linux-tools-common "linux-tools-$(uname -r)" \
  libglfw3-dev libgl1-mesa-dev libegl1-mesa-dev libx11-dev libxinerama-dev libxcursor-dev libxi-dev libxrandr-dev \
  libeigen3-dev libboost-dev \
  htop tmux jq

echo "== [3/4] 실시간 권한 (realtime 그룹, rtprio/memlock 한도)"
getent group realtime >/dev/null || groupadd realtime
usermod -aG realtime "$TARGET_USER"
cat > /etc/security/limits.d/99-pace-realtime.conf <<'LIM'
@realtime   -   rtprio    99
@realtime   -   memlock   unlimited
@realtime   -   nice      -20
LIM

echo "== [4/4] 완료. 그룹 반영을 위해 재로그인(또는 재부팅)이 필요합니다."
echo "   확인: id $TARGET_USER | grep realtime"
