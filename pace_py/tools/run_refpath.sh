#!/usr/bin/env bash
# 7단계 통합 실행: 시뮬(에피소드 장면) + 1kHz 루프(기준 경로 모드) + 작은 눈 → CSV/trace/그래프
# 사용: [ROBOT=panda] [DUR=35] [SIM_ARGS=...] [CTL_ARGS=...] bash pace_py/tools/run_refpath.sh <episode> <name> [eye|noeye] [seam_eye 추가 인자...]
set -euo pipefail
EP=$1; NAME=$2; EYE=${3:-eye}; shift 3 || shift $#
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
OUT=docs/benchmarks/runs; mkdir -p $OUT
if [[ -f /opt/ros/jazzy/setup.bash ]]; then set +u; source /opt/ros/jazzy/setup.bash; set -u; fi   # pace_control 이 ros2_control 라이브러리를 링크함 (setup.bash 는 nounset 비호환)
export AMENT_PREFIX_PATH="$ROOT/pace/build/ros2_prefix:/opt/ros/jazzy${AMENT_PREFIX_PATH:+:$AMENT_PREFIX_PATH}"   # --hal ros2 일 때 pluginlib 가 플러그인을 찾는 경로
ROBOT=${ROBOT:-ur5e}                                   # ur5e | panda | iiwa14 | xarm7 (같은 교시 경로·눈·제어기, 장면·운동학만 다름)
if [[ "$ROBOT" == "panda" ]]; then SCENE=$(printf "pace/models/panda/_gen_ep%04d_panda.xml" "$EP"); [[ -f $SCENE ]] || .venv/bin/python -m pace_py.tools.make_panda_scene --episode $EP >/dev/null; SIM_ARGS="${SIM_ARGS:---ff-tau 0.1}"
elif [[ "$ROBOT" == "iiwa14" || "$ROBOT" == "xarm7" ]]; then SCENE=$(printf "pace/models/%s/_gen_ep%04d_%s.xml" "$ROBOT" "$EP" "$ROBOT"); [[ -f $SCENE ]] || .venv/bin/python -m pace_py.tools.make_robot_scene --robot $ROBOT --episode $EP >/dev/null; SIM_ARGS="${SIM_ARGS:---ff-tau 0.1}"
else SCENE=$(printf "pace/models/ur5e/_gen_ep%04d.xml" "$EP"); fi
REF=$(printf "data/refpath/ep_%04d_teach.bin" "$EP")
[[ -n "${SCENE_OVERRIDE:-}" ]] && SCENE="$SCENE_OVERRIDE"                       # 예: 접촉력 시연 장면 (_gen_ep0001_bump.xml)
[[ -f $REF ]] || .venv/bin/python -m pace_py.tools.make_refpath --episode $EP >/dev/null
DUR=${DUR:-45}
LANE=${LANE:-a}   # 병렬 레인: b 이면 공유메모리 이름·코어 분리 (RT 루프 CPU 5, 시뮬 13, 눈 16-19)
if [[ "$LANE" == "a" ]]; then SHM=/pace; SIMLINK=/pace_sim; CTL_CPU=4; SIM_CPU=12; EYE_CPUS=8-11; else SHM=/pace_$LANE; SIMLINK=/pace_sim_$LANE; CTL_CPU=5; SIM_CPU=13; EYE_CPUS=16-19; fi
if [[ "$LANE" == "a" ]]; then pkill -INT -f 'pace_si[m] --model [^ ]* --cpu 12' 2>/dev/null || true; pkill -INT -f 'seam_ey[e] --model [^ ]* --refpath' 2>/dev/null || true; else pkill -INT -f "pace_si[m] .*--simlink $SIMLINK" 2>/dev/null || true; fi; sleep 0.2
pace/build/pace_sim --model "$SCENE" --cpu $SIM_CPU --simlink $SIMLINK ${SIM_ARGS:-} 2> $OUT/$NAME.sim.log &
SIM=$!; sleep 1
pace/build/pace_control --shm $SHM --simlink $SIMLINK --cpu $CTL_CPU --prio 99 --duration $DUR --refpath $REF --kin-model "$SCENE" --trace $OUT/$NAME.trace.bin ${CFG:+--config $CFG} ${CTL_ARGS:-} > $OUT/$NAME.summary.json 2> $OUT/$NAME.ctl.log &
CTL=$!; sleep 1.0
if [[ "$EYE" == "eye" ]]; then
  taskset -c $EYE_CPUS .venv/bin/python -m pace_py.eye.seam_eye --model "$SCENE" --refpath $REF --shm $SHM "$@" > $OUT/$NAME.eye.log 2>&1 &
  EYEP=$!
fi
wait $CTL || true
[[ -n "${EYEP:-}" ]] && { kill -INT $EYEP 2>/dev/null || true; sleep 0.3; kill -TERM $EYEP 2>/dev/null || true; }
kill -INT $SIM 2>/dev/null || true; wait $SIM 2>/dev/null || true
.venv/bin/python -m pace_py.tools.metrics_dump --shm $SHM --out $OUT/$NAME.csv | tail -n +2 | head -2
grep -E 'refpath' $OUT/$NAME.ctl.log | head -2
