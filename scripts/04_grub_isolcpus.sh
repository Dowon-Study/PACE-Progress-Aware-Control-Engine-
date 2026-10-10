#!/usr/bin/env bash
# PAC 2026 PACE — 4단계: 코어 격리 커널 파라미터 (GRUB)
# 실행: sudo bash scripts/04_grub_isolcpus.sh
#
# Threadripper PRO 3955WX (16C/32T, SMT 쌍 = N 과 N+16, L3 16MB 를 4코어 CCX 단위로 공유)
#   CCX0  CPU 0-3,16-19  : OS / IRQ / 하우스키핑
#   CCX1  CPU 4-7,20-23  : 실시간 제어 전용 ← CCX 통째로 격리 (AI 와 L3 캐시를 공유하지 않음)
#           CPU 4  : 1kHz 제어 루프 (SCHED_FIFO 99)
#           CPU 5  : 경량 모델 / 반영 정책 비동기 작업
#           CPU 6-7: 예비 (격리 단계별 비교 실험용)
#   CCX2-3 CPU 8-15,24-31: AI 추론(GPU 드라이버 스레드), MuJoCo, ROS 2, 일반 작업
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요"; exit 1; }
ISOL="4-7,20-23"
PARAMS="isolcpus=managed_irq,domain,${ISOL} nohz_full=${ISOL} rcu_nocbs=${ISOL} irqaffinity=0-3,8-19,24-31 \
rcu_nocb_poll skew_tick=1 nmi_watchdog=0 nosoftlockup tsc=reliable transparent_hugepage=never \
processor.max_cstate=1 amd_pstate=passive"
cp -n /etc/default/grub /etc/default/grub.pace.bak
sed -i "s|^GRUB_CMDLINE_LINUX_DEFAULT=.*|GRUB_CMDLINE_LINUX_DEFAULT=\"quiet splash ${PARAMS}\"|" /etc/default/grub
update-grub
echo "== 적용 완료 (백업: /etc/default/grub.pace.bak). 재부팅 후 'cat /proc/cmdline' 로 확인"
