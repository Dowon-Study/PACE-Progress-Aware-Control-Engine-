#!/usr/bin/env bash
# 10단계 통합 실행: 시뮬(에피소드 장면, weld_home 키프레임 = 용접선 시작) + 1kHz 루프 + 실제 AI 공급자(ACT급) [+ 로컬 블록] → CSV/trace/그래프
# 사용: [LOCAL=1] [CFG=...] [DUR=40] bash pace_py/tools/run_ai.sh <episode> <name> [ai_act 추가 인자...]
set -euo pipefail
EP=$1; NAME=$2; shift 2
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
OUT=docs/benchmarks/runs; mkdir -p $OUT
if [[ -f /opt/ros/jazzy/setup.bash ]]; then set +u; source /opt/ros/jazzy/setup.bash; set -u; fi
SCENE=$(printf "pace/models/ur5e/_gen_ep%04d.xml" "$EP"); DUR=${DUR:-40}
Q0=$(.venv/bin/python -c "import numpy as np,sys; print(' '.join(f'{v:.5f}' for v in np.load(f'data/gt/ep_{$EP:04d}.npz')['q'][0]))")   # 시작 자세 = 에피소드 리드인 자세 (모델이 학습한 시작 분포)
pkill -INT pace_sim 2>/dev/null || true; pkill -TERM -f 'pace_py\.local\.local_bloc[k]' 2>/dev/null || true; pkill -TERM -f 'pace_py\.supplier\.ai_ac[t]' 2>/dev/null || true; sleep 0.2
pace/build/pace_sim --model "$SCENE" --cpu 12 --init-q "$Q0" ${SIM_ARGS:-} 2> $OUT/$NAME.sim.log & SIM=$!; sleep 1
pace/build/pace_control --cpu 4 --prio 99 --duration $DUR --traj hold --policy ${POLICY:-progress} --trace $OUT/$NAME.trace.bin ${CFG:+--config $CFG} > $OUT/$NAME.summary.json 2> $OUT/$NAME.ctl.log & CTL=$!; sleep 1.0
if [[ "${LOCAL:-0}" == "1" ]]; then taskset -c 8-11 .venv/bin/python -m pace_py.local.local_block ${LOCAL_ARGS:-} > $OUT/$NAME.local.log 2>&1 & LOCALP=$!; fi
taskset -c 14-15 .venv/bin/python -m pace_py.supplier.ai_act --model "$SCENE" --duration $((DUR-2)) --ai-csv $OUT/$NAME.ai.csv "$@" > $OUT/$NAME.ai.log 2>&1 || true
wait $CTL || true
[[ -n "${LOCALP:-}" ]] && { kill -TERM $LOCALP 2>/dev/null || true; wait $LOCALP 2>/dev/null || true; }
kill -INT $SIM 2>/dev/null || true; wait $SIM 2>/dev/null || true
.venv/bin/python -m pace_py.tools.metrics_dump --shm /pace --out $OUT/$NAME.csv | tail -n +2 | head -2
.venv/bin/python -m pace_py.tools.plot_run --csv $OUT/$NAME.csv --trace $OUT/$NAME.trace.bin --out $OUT/$NAME.png --title "$NAME"
grep -E 'done|Traceback|Error' $OUT/$NAME.ai.log | tail -3
