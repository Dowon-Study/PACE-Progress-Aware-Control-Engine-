#!/usr/bin/env bash
# PAC 2026 PACE — RT 커널 + CCX 격리 지터 측정 (sudo 불필요, realtime 그룹 필요)
# 격리 코어 CPU4 에 1kHz SCHED_FIFO 99 스레드를 고정하고, (1) 유휴 (2) CPU/메모리 + GPU 부하 조건에서 측정
# 실행: bash scripts/06_rt_jitter_bench.sh [초, 기본 60]
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; OUT="$ROOT/docs/benchmarks"; mkdir -p "$OUT"
DUR="${1:-60}"; CPU=4
TAG="rt_$(uname -r | grep -q realtime && echo ccx || echo generic)"
CT="cyclictest -m -p 99 -i 1000 -h 400 -q -a $CPU -t 1 -D $DUR"

echo "== 커널 $(uname -r) | 격리 $(cat /sys/devices/system/cpu/isolated) | governor $(cat /sys/devices/system/cpu/cpu$CPU/cpufreq/scaling_governor)"
echo "== [1/2] 유휴 ${DUR}s (CPU$CPU, FIFO 99, 1ms)"
$CT > "$OUT/${TAG}_idle.txt"; grep -E '^# (Min|Avg|Max)' "$OUT/${TAG}_idle.txt"

echo "== [2/2] 부하 ${DUR}s: stress-ng CPU 24 + VM 4x2GB (비격리 코어) + GPU matmul 루프"
stress-ng --cpu 24 --vm 4 --vm-bytes 2G --timeout $((DUR+5))s >/dev/null 2>&1 &
SPID=$!
"$ROOT/.venv/bin/python" - "$((DUR+5))" <<'PY' >/dev/null 2>&1 &
import sys, time, torch
t_end=time.time()+float(sys.argv[1]); x=torch.randn(8192,8192,device="cuda")
while time.time()<t_end: y=x@x; torch.cuda.synchronize()
PY
GPID=$!
sleep 3
$CT > "$OUT/${TAG}_stress.txt"; grep -E '^# (Min|Avg|Max)' "$OUT/${TAG}_stress.txt"
wait $SPID $GPID 2>/dev/null
echo "== 저장: $OUT/${TAG}_idle.txt, $OUT/${TAG}_stress.txt"
