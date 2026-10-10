#!/usr/bin/env bash
# PAC 2026 PACE — 환경 검증 (sudo 불필요, cyclictest 는 realtime 그룹 반영 후 RT 우선순위 사용)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ok(){ printf "  [OK]   %s\n" "$*"; }; ng(){ printf "  [FAIL] %s\n" "$*"; FAIL=1; }; FAIL=0

echo "== 커널 / 실시간"
uname -r
if uname -v | grep -q PREEMPT_RT; then ok "PREEMPT_RT 커널"; else ng "PREEMPT_RT 아님 (현재: $(uname -v | grep -oE 'PREEMPT[_A-Z]*'))"; fi
grep -q isolcpus /proc/cmdline && ok "isolcpus: $(grep -oE 'isolcpus=[^ ]+' /proc/cmdline)" || ng "isolcpus 미적용"
id | grep -q realtime && ok "realtime 그룹" || ng "realtime 그룹 아님 (재로그인 필요?)"
[[ "$(ulimit -r)" == "99" ]] && ok "rtprio 한도 99" || ng "rtprio 한도 $(ulimit -r)"
echo "   governor: $(cat /sys/devices/system/cpu/cpu4/cpufreq/scaling_governor 2>/dev/null || echo n/a)"

echo "== 도구"
for t in gcc g++ cmake ninja git cyclictest stress-ng trace-cmd numactl cpupower chrt taskset; do
  command -v "$t" >/dev/null && ok "$t" || ng "$t 없음"; done

echo "== ROS 2"
if [[ -f /opt/ros/jazzy/setup.bash ]]; then
  source /opt/ros/jazzy/setup.bash
  ok "ROS_DISTRO=$ROS_DISTRO"
  ros2 pkg list 2>/dev/null | grep -q '^controller_manager$' && ok "ros2_control" || ng "ros2_control 없음"
  ros2 pkg list 2>/dev/null | grep -q 'mujoco_ros2_control' && ok "mujoco_ros2_control" || echo "  [--]   mujoco_ros2_control 미설치 (02b 스크립트로 소스 빌드)"
else ng "ROS 2 Jazzy 없음"; fi

echo "== MuJoCo C 라이브러리"
MJ="$ROOT/third_party/mujoco-3.15.0"
[[ -f "$MJ/lib/libmujoco.so" ]] && ok "libmujoco.so" || ng "libmujoco.so 없음"
[[ -x "$MJ/bin/testspeed" ]] && ok "testspeed: $("$MJ/bin/testspeed" --nstep=2000 "$MJ/model/humanoid/humanoid.xml" 2>&1 | grep -E 'Time per step|Realtime' | tr -s ' ' | paste -sd '|')" || ng "testspeed 실행 불가"

echo "== Python venv"
PY="$ROOT/.venv/bin/python"
if [[ -x "$PY" ]]; then
  "$PY" - <<'PYV' || FAIL=1
import importlib
mods = ["mujoco","numpy","scipy","matplotlib","pandas","yaml","onnx","onnxruntime","torch","torchvision","tqdm","pytest"]
bad=[]
for m in mods:
    try:
        mod=importlib.import_module(m); print(f"  [OK]   {m} {getattr(mod,'__version__','')}")
    except Exception as e:
        print(f"  [FAIL] {m}: {e}"); bad.append(m)
import torch
print(f"  [{'OK' if torch.cuda.is_available() else 'FAIL'}]   torch.cuda {torch.cuda.is_available()} {torch.cuda.get_device_name(0) if torch.cuda.is_available() else ''}")
import mujoco, os
os.environ.setdefault("MUJOCO_GL","egl")
m=mujoco.MjModel.from_xml_string('<mujoco><worldbody><body><joint type="hinge"/><geom size="0.1"/></body></worldbody></mujoco>')
d=mujoco.MjData(m); mujoco.mj_step(m,d); print("  [OK]   mujoco mj_step")
try:
    r=mujoco.Renderer(m,64,64); r.update_scene(d); r.render(); print("  [OK]   mujoco EGL offscreen render")
except Exception as e: print(f"  [FAIL] mujoco EGL render: {e}")
raise SystemExit(1 if bad else 0)
PYV
else ng ".venv 없음"; fi

echo "== cyclictest (10초, CPU4, FIFO 99)"
if command -v cyclictest >/dev/null; then
  cyclictest -m -S -p 99 -i 1000 -D 10 -q -a 4 -t 1 2>&1 | tail -2 || true
fi
echo; [[ $FAIL -eq 0 ]] && echo "모든 항목 통과" || echo "실패 항목 있음 (위 [FAIL] 참조)"
exit $FAIL
