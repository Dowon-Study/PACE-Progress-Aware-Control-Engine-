#!/usr/bin/env bash
# 로봇 장면이 쓰는 메시(Menagerie assets)를 third_party 에서 상대 경로 심볼릭 링크로 연결한다.
# 먼저 README 의 '서드파티' 절대로 third_party/mujoco_menagerie 를 받아 둘 것.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
declare -A SRC=([ur5e]=universal_robots_ur5e [panda]=franka_emika_panda [iiwa14]=kuka_iiwa_14 [xarm7]=ufactory_xarm7)
for r in "${!SRC[@]}"; do
  tgt="third_party/mujoco_menagerie/${SRC[$r]}/assets"
  [[ -d "$tgt" ]] || { echo "없음: $tgt (Menagerie sparse-checkout 에 ${SRC[$r]} 포함 필요)"; exit 1; }
  ln -sfn "../../../$tgt" "pace/models/$r/assets"; echo "pace/models/$r/assets -> ../../../$tgt"
done
