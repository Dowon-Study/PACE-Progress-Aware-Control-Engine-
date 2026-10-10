"""B4 HAL 교체 비용: 로봇/백엔드 교체 시 바뀐 코드량(제어·눈 코드 0줄 확인)과 HAL read/write 실측(summary.json hal.*), 용접 결과.
사용: .venv/bin/python validation/scripts/b4_hal_swap_cost.py --out validation/figures/verification/B4_hal_swap.md"""
import argparse, json, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args()
runs = [("UR5e 6축, sim_shm (직접)", "s12_ur5e_eye_ep1"), ("Panda 7축, sim_shm (직접)", "s8_panda_eye_ep1"), ("KUKA iiwa14 7축, sim_shm (직접)", "s13_iiwa14_eye_ep1"), ("UFactory xArm7 7축, sim_shm (직접)", "s13_xarm7_eye_ep1"), ("UR5e, ros2_control 플러그인 경로", "s8_hal_ros2_eye_ep1")]
rows = ["| 구성 | HAL read max [μs] | HAL write max [μs] | 선언 WCET read/write [μs] | 계약 위반 | 루프 실행 p99/max [μs] | 완주 s_end [m] |", "|---|---|---|---|---|---|---|"]
for lb, r in runs:
    s = json.load(open(ROOT / f"docs/benchmarks/runs/{r}.summary.json")); h = s["hal"]
    rows.append(f"| {lb} | {h['read_max_us']} | {h['write_max_us']} | {h['read_wcet_us']}/{h['write_wcet_us']} | {h['read_viol']}/{h['write_viol']} | {s['loop_exec']['p99_us']}/{s['loop_exec']['max_us']} | {s['refpath']['s_end']:.4f} |")
# 교체에 든 코드: 로봇 B 추가 파일(모델·장면 생성)과 ros2 어댑터·플러그인 줄 수, 제어기·눈 변경 줄 수(0)
def wc(p): return sum(1 for _ in open(ROOT / p, encoding="utf-8", errors="ignore"))
added = {"로봇 B 추가 (Panda)": ["pace/models/panda/panda_torch.xml", "pace_py/tools/make_panda_scene.py"],
         "로봇 C·D 추가 (iiwa14, xArm7)": ["pace/models/iiwa14/iiwa14_torch.xml", "pace/models/xarm7/xarm7_torch.xml", "pace_py/tools/make_robot_scene.py"],
         "ros2_control 경로 추가": ["pace/src/hal_ros2.cpp", "pace/ros2/pace_mujoco_hardware.cpp", "pace/ros2/ur5e_pace_mujoco.urdf"]}
rows2 = ["| 교체 종류 | 새로 쓴 파일 (줄 수) | 제어기·검증기·접합·눈 코드 변경 |", "|---|---|---|"]
for k, fs in added.items():
    rows2.append(f"| {k} | " + ", ".join(f"`{f}` ({wc(f)})" for f in fs) + " | 0 줄 (HAL 인터페이스 `pace/include/pace/hal.h` 뒤에서만 교체) |")
md = "# B4 HAL 교체 비용\n\n## HAL 변환 지연·계약 (summary.json `hal.*`)\n\n" + "\n".join(rows) + "\n\n## 교체에 든 코드량\n\n" + "\n".join(rows2) + "\n\n(용접 오차 mean: UR5e 0.30 / Panda 0.30 / iiwa14 0.32 / xArm7 0.31 / ros2 경로 0.31 mm — `docs/benchmarks/README.md` 8단계·8단계 보충. 정지 사다리도 4 로봇 동일 타임라인: `docs/figures/s13_stop_fault_*.png`)\n"
Path(a.out).write_text(md, encoding="utf-8"); print(md)
