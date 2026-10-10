#!/usr/bin/env bash
# 통합 실행: 시뮬(에피소드 장면) + 1kHz 루프 + 가짜 공급자 → 계측 CSV + trace + 그래프
# 사용: [LOCAL=1] [LOCAL_ARGS=...] [ONLINE=1] [ONLINE_ARGS=...] [CFG=...] bash pace_py/tools/run_episode.sh <episode> <name> [fake_ai 추가 인자...]
# ONLINE=1: 보조 궤적 생성기 온라인 학습 (online_train, 비격리 코어) + local_block 가중치 교체. 산출물 $OUT/<name>.online/, <name>.online.jsonl
set -euo pipefail
EP=$1; NAME=$2; shift 2
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
OUT=docs/benchmarks/runs; mkdir -p $OUT
SCENE=$(printf "pace/models/ur5e/_gen_ep%04d.xml" "$EP")
DUR=${DUR:-40}
# 레인: 병렬 실행용 (LANE=b 이면 공유메모리 이름과 코어를 분리). RT 루프는 격리 코어 4 또는 5, 시뮬 12/13, 로컬 8-11/16-19, 공급자 14-15/2-3
LANE=${LANE:-a}
if [[ "$LANE" == "a" ]]; then SHM=/pace; SIMLINK=/pace_sim; CTL_CPU=4; SIM_CPU=12; LOCAL_CPUS=8-11; FAKE_CPUS=14-15; TRAIN_CPUS=0-3
else SHM=/pace_$LANE; SIMLINK=/pace_sim_$LANE; CTL_CPU=5; SIM_CPU=13; LOCAL_CPUS=16-19; FAKE_CPUS=2-3; TRAIN_CPUS=0-1; fi
if [[ "$LANE" == "a" ]]; then pkill -INT -f 'pace_si[m] --model [^ ]* --cpu 12' 2>/dev/null || true; else pkill -INT -f "pace_si[m] .*--simlink $SIMLINK" 2>/dev/null || true; fi; sleep 0.2
pace/build/pace_sim --model "$SCENE" --cpu $SIM_CPU --simlink $SIMLINK ${SIM_ARGS:-} 2> $OUT/$NAME.sim.log &
SIM=$!; sleep 1
pace/build/pace_control --shm $SHM --simlink $SIMLINK --cpu $CTL_CPU --prio 99 --duration $DUR --traj hold --policy ${POLICY:-progress} --trace $OUT/$NAME.trace.bin ${CFG:+--config $CFG} > $OUT/$NAME.summary.json 2> $OUT/$NAME.ctl.log &
CTL=$!; sleep 1.5
if [[ "${PROC:-0}" == "1" ]]; then taskset -c $LOCAL_CPUS .venv/bin/python -m pace_py.supplier.process_monitor --shm $SHM --duration $((DUR-2)) ${PROC_ARGS:-} > $OUT/$NAME.proc.log 2>&1 & PROCP=$!; fi   # 11단계: 공정 상태 추론기(규칙)
if [[ "${ONLINE:-0}" == "1" ]]; then ONDIR=$OUT/$NAME.online; mkdir -p $ONDIR; rm -f $OUT/$NAME.online.jsonl   # 보조 궤적 생성기 온라인 학습 (격리 코어 밖)
  taskset -c $TRAIN_CPUS .venv/bin/python -m pace_py.local.online_train --shm $SHM --deploy $ONDIR/current.pt --log $OUT/$NAME.online.jsonl ${ONLINE_ARGS:-} > $OUT/$NAME.online.log 2>&1 & ONLINEP=$!
  LOCAL_ARGS="${LOCAL_ARGS:-} --online-ckpt $ONDIR/current.pt"; sleep 1.0; fi
if [[ "${LOCAL:-0}" == "1" ]]; then taskset -c $LOCAL_CPUS .venv/bin/python -m pace_py.local.local_block --shm $SHM ${LOCAL_ARGS:-} > $OUT/$NAME.local.log 2>&1 & LOCALP=$!; fi   # 9단계: 로컬 감독 블록
taskset -c $FAKE_CPUS .venv/bin/python -m pace_py.supplier.fake_ai --episode $EP --shm $SHM "$@" > $OUT/$NAME.fake.log 2>&1 || true
wait $CTL || true
[[ -n "${LOCALP:-}" ]] && { kill -TERM $LOCALP 2>/dev/null || true; wait $LOCALP 2>/dev/null || true; }
[[ -n "${PROCP:-}" ]] && { kill -TERM $PROCP 2>/dev/null || true; wait $PROCP 2>/dev/null || true; }
[[ -n "${ONLINEP:-}" ]] && { kill -TERM $ONLINEP 2>/dev/null || true; wait $ONLINEP 2>/dev/null || true; }
kill -INT $SIM 2>/dev/null || true; wait $SIM 2>/dev/null || true
.venv/bin/python -m pace_py.tools.metrics_dump --shm $SHM --out $OUT/$NAME.csv | tail -n +2 | head -3
.venv/bin/python -m pace_py.tools.plot_run --csv $OUT/$NAME.csv --trace $OUT/$NAME.trace.bin --out $OUT/$NAME.png --title "$NAME"
grep -E 'done|SKIP|\[fake\] t=' $OUT/$NAME.fake.log | tail -5
