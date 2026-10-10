#!/usr/bin/env bash
# PAC 2026 PACE — 4b단계: GRUB 기본 부팅 항목을 RT 커널로 고정 + 부팅 메뉴 5초 표시 (문제 시 generic 으로 복귀 가능)
# 실행: sudo bash scripts/04b_grub_default_rt.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요"; exit 1; }
RT_KVER=$(ls /boot/vmlinuz-*-realtime | sed 's|/boot/vmlinuz-||' | sort -V | tail -1)
[[ -n "$RT_KVER" ]] || { echo "realtime 커널이 /boot 에 없습니다"; exit 1; }
ENTRY="Advanced options for Ubuntu>Ubuntu, with Linux ${RT_KVER}"
grep -q "^menuentry 'Ubuntu, with Linux ${RT_KVER}'" /boot/grub/grub.cfg || grep -q "Ubuntu, with Linux ${RT_KVER}'" /boot/grub/grub.cfg || { echo "grub.cfg 에 ${RT_KVER} 항목이 없습니다"; exit 1; }
sed -i "s|^GRUB_DEFAULT=.*|GRUB_DEFAULT=\"${ENTRY}\"|" /etc/default/grub
sed -i 's|^GRUB_TIMEOUT_STYLE=.*|GRUB_TIMEOUT_STYLE=menu|' /etc/default/grub
sed -i 's|^GRUB_TIMEOUT=.*|GRUB_TIMEOUT=5|' /etc/default/grub
update-grub
echo "== 기본 부팅: ${ENTRY}"
echo "== 재부팅 후 'uname -r' 이 ${RT_KVER} 인지 확인. 문제 시 부팅 메뉴(5초)에서 generic 커널 선택 가능"
