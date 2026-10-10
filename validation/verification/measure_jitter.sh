#!/usr/bin/env bash
# A2·A7 측정 실행기: cyclictest 로 "빈 손" 지터를 조건별로 재서 validation/raw/ 에 규칙대로 저장한다.
# (reference/성능지표_정리.pdf "a7 더 자세히 설명" 절의 터미널 두 개 절차를 한 스크립트로 묶은 것)
#
# 사용:  bash validation/verification/measure_jitter.sh <idle|stress> [초, 기본 600] [회차, 기본 1]
#   예)  bash validation/verification/measure_jitter.sh idle 600 1
#        bash validation/verification/measure_jitter.sh stress 600 1
#
# 하는 일
#   1) 커널/격리/governor 를 확인해 파일 머리말(# key=value)에 남긴다
#   2) stress 조건이면 비격리 코어(8-15,24-31)에 stress-ng 를 띄우고 30초 안정화
#   3) CPU4 에 cyclictest 1kHz FIFO99 를 <초> 동안 돌려 raw/<날짜>_<커널>_<격리>_<부하>_<초>s_r<회차>.txt 에 저장
#   4) 끝나면 verify.py cyclictest 로 바로 요약을 찍는다
# 필요: cyclictest, stress-ng (설치됨), realtime 그룹 권한 (sudo 불필요). ai-gpu / full 조건은 모델이 나오면 README 절차대로.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RAW="$ROOT/validation/raw"; CFG="$ROOT/validation/configs"; mkdir -p "$RAW" "$CFG"
LOAD="${1:?idle 또는 stress 를 지정}"; DUR="${2:-600}"; REP="${3:-1}"; CPU=4
LOAD_CPUS="8-15,24-31"

KERNEL=$(uname -r | grep -q realtime && echo rt || echo generic)
ISOL_RAW=$(cat /sys/devices/system/cpu/isolated 2>/dev/null); ISOL=none
[[ -n "$ISOL_RAW" ]] && ISOL=isol
grep -q "4-7,20-23" <<<"$ISOL_RAW" && ISOL=ccx
GOV=$(cat /sys/devices/system/cpu/cpu$CPU/cpufreq/scaling_governor 2>/dev/null || echo unknown)
STAMP=$(date +%Y%m%d); NAME="${STAMP}_${KERNEL}_${ISOL}_${LOAD}_${DUR}s_r${REP}"
OUTF="$RAW/$NAME.txt"
CT="cyclictest -m -S -p 99 -i 1000 -h 400 -q -a $CPU -t 1 -D $DUR"

echo "== 커널 $(uname -r) | 격리 '$ISOL_RAW' ($ISOL) | governor $GOV | 조건 $LOAD | ${DUR}s | r$REP"
echo "== 저장: $OUTF"
if [[ -e "$OUTF" ]]; then echo "!! 이미 있음. 회차를 올려서 다시 실행"; exit 1; fi

{
  echo "# version=$(cd "$ROOT" && git rev-parse --short HEAD 2>/dev/null || echo no-git)"
  echo "# kernel=$(uname -r)"
  echo "# cmdline=$(cat /proc/cmdline)"
  echo "# governor=$GOV"
  echo "# isolation=$ISOL ($ISOL_RAW)"
  echo "# load=$LOAD"
  echo "# cmd=$CT"
  echo "# start=$(date -Iseconds)"
} > "$OUTF"

SPID=""
if [[ "$LOAD" == "stress" ]]; then
  STRESS="taskset -c $LOAD_CPUS stress-ng --vm 8 --vm-bytes 2G --cache 4 --timeout $((DUR+45))s"
  echo "# load_cmd=$STRESS" >> "$OUTF"
  echo "== 부하 시작 (비격리 코어 $LOAD_CPUS), 30초 안정화"
  $STRESS >/dev/null 2>&1 & SPID=$!
  sleep 30
elif [[ "$LOAD" != "idle" ]]; then
  echo "!! 이 스크립트는 idle / stress 만 지원. ai-gpu, full 은 README 의 절차 참고"; exit 1
fi

echo "== 측정 ${DUR}s 시작 $(date +%T)  (측정 중 브라우저·IDE 등 다른 프로그램을 켜지 마세요)"
$CT >> "$OUTF"
RC=$?
echo "# end=$(date -Iseconds)" >> "$OUTF"
[[ -n "$SPID" ]] && { kill "$SPID" 2>/dev/null; wait "$SPID" 2>/dev/null; }
if [[ $RC -ne 0 ]]; then echo "!! cyclictest 종료 코드 $RC (권한? realtime 그룹 / ulimit -r 확인)"; exit $RC; fi

# 측정 기록 양식도 같은 이름으로 만들어 둔다 (빈칸은 손으로 채움)
CFGF="$CFG/$NAME.md"
if [[ ! -e "$CFGF" ]]; then
  sed -e "s|^- 날짜/시각:.*|- 날짜/시각: $(date -Iseconds)|" \
      -e "s|^- 커널: .*|- 커널: \`uname -r\` → $(uname -r)|" \
      -e "s|^- governor: .*|- governor: $GOV|" \
      -e "s|^- 격리 조건: .*|- 격리 조건: $ISOL|" \
      -e "s|^- 부하 조건: .*|- 부하 조건: $LOAD|" \
      -e "s|^- 지속시간:.*|- 지속시간: ${DUR}s|" \
      -e "s|^- 회차:.*|- 회차: r$REP|" \
      -e "s|^- 측정 명령 .*|- 측정 명령: \`$CT\`|" \
      -e "s|^- 결과 파일: raw/.*|- 결과 파일: raw/$NAME.txt|" \
      "$ROOT/validation/templates/measurement_log.md" > "$CFGF"
fi
echo "== 완료. 요약:"
"$ROOT/.venv/bin/python" "$ROOT/validation/verification/verify.py" --out "$ROOT/validation/figures/verification" cyclictest "$OUTF" --label "$NAME"
echo "== 기록 양식: $CFGF (부하 명령·특이사항을 채워 주세요)"
