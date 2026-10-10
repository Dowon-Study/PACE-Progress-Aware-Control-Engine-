#!/usr/bin/env bash
# PAC 2026 PACE — 3단계: PREEMPT_RT 커널
# 실행: sudo bash scripts/03_rt_kernel.sh pro <UBUNTU_PRO_TOKEN>   (권장: 서명된 공식 RT 커널, 개인 무료 5대)
#       sudo bash scripts/03_rt_kernel.sh build                     (대안: 메인라인 커널 CONFIG_PREEMPT_RT=y 직접 빌드)
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요"; exit 1; }
MODE="${1:-}"

case "$MODE" in
  pro)
    TOKEN="${2:-}"; [[ -n "$TOKEN" ]] || { echo "토큰 필요: https://ubuntu.com/pro 에서 발급"; exit 1; }
    pro attach "$TOKEN"
    pro enable realtime-kernel --assume-yes
    echo "== 설치 완료. 재부팅 후 'uname -v | grep PREEMPT_RT' 로 확인"
    ;;
  build)
    # 메인라인 6.12+ 는 PREEMPT_RT 가 내장되어 있어 패치 불필요 (x86_64)
    apt-get install -y build-essential libncurses-dev bison flex libssl-dev libelf-dev bc dwarves zstd fakeroot debhelper rsync
    KVER="${2:-6.18.55}"   # LTS (PREEMPT_RT 내장). 필요 시 두 번째 인자로 버전 지정
    MAJOR="${KVER%%.*}"
    WORK=/usr/local/src/pace-rt-kernel; mkdir -p "$WORK"; cd "$WORK"
    [[ -f "linux-$KVER.tar.xz" ]] || wget -q --show-progress "https://cdn.kernel.org/pub/linux/kernel/v${MAJOR}.x/linux-$KVER.tar.xz"
    [[ -d "linux-$KVER" ]] || tar -xf "linux-$KVER.tar.xz"
    cd "linux-$KVER"
    cp "/boot/config-$(uname -r)" .config
    scripts/config --disable PREEMPT_NONE --disable PREEMPT_VOLUNTARY --disable PREEMPT \
                   --disable PREEMPT_DYNAMIC --enable PREEMPT_RT --enable EXPERT \
                   --disable DEBUG_INFO --disable DEBUG_INFO_BTF --disable DEBUG_INFO_DWARF5 \
                   --set-str SYSTEM_TRUSTED_KEYS "" --set-str SYSTEM_REVOCATION_KEYS "" \
                   --disable MODULE_SIG --set-str CONFIG_LOCALVERSION "-pace-rt"
    make olddefconfig
    grep -q 'CONFIG_PREEMPT_RT=y' .config || { echo "CONFIG_PREEMPT_RT 설정 실패"; exit 1; }
    make -j"$(nproc)" bindeb-pkg
    dpkg -i ../linux-image-*pace-rt*.deb ../linux-headers-*pace-rt*.deb
    echo "== 설치 완료. 재부팅 후 GRUB에서 *-pace-rt 커널 선택, 'uname -v | grep PREEMPT_RT' 로 확인"
    echo "   주의: NVIDIA DKMS 모듈이 RT 커널에서 빌드되는지 'dkms status' 로 확인"
    ;;
  *)
    echo "사용법: $0 pro <TOKEN> | $0 build [커널버전]"; exit 1 ;;
esac
