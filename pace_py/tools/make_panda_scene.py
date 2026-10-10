"""로봇 B(Franka Panda, 7축) 용접 장면 생성: UR5e 에피소드 장면(_gen_epXXXX.xml)의 작업물·용접선·텍스처는 그대로, 로봇만 Panda 로 바꾼다.
weld_home 키프레임은 교시 경로 시작 포즈(standoff·진행각 포함)로 IK 를 풀어 넣는다 (다중 시작, 충돌 0, 관절 여유).
사용: python -m pace_py.tools.make_panda_scene --episode 1  →  pace/models/panda/_gen_ep0001_panda.xml"""
import argparse, re, struct, sys
from pathlib import Path
import numpy as np, mujoco
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.datagen.trajectory import SeamIK, tool_rotation   # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PANDA_LIMITS = """  <custom>
    <numeric name="qd_max" data="2.17 2.17 2.17 2.17 2.6 2.6 2.6"/>
    <numeric name="qdd_max" data="15 7.5 10 12.5 15 20 20"/>
    <numeric name="jerk_max" data="400 400 400 400 400 400 400"/>
    <numeric name="workspace" data="0.25 -0.45 0.25  1.0 0.40 0.90"/>
  </custom>"""


def load_rpth(path):
    b = open(path, "rb").read(); magic, n, sdot, standoff, travel, _ = struct.unpack_from("<II4f", b, 0); assert magic == 0x48545052
    a = np.frombuffer(b, np.float32, count=7 * n, offset=24).reshape(n, 7).astype(np.float64); return a[:, 1:4], a[:, 4:7], standoff, travel


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--episode", type=int, required=True); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    src = ROOT / f"pace/models/ur5e/_gen_ep{a.episode:04d}.xml"; out = ROOT / f"pace/models/panda/_gen_ep{a.episode:04d}_panda.xml"
    xml = src.read_text(encoding="utf-8")
    xml = xml.replace('<include file="ur5e_torch.xml"/>', '<include file="panda_torch.xml"/>').replace('model="weld_ur5e_gen"', 'model="weld_panda_gen"')
    xml = re.sub(r'file="textures/', 'file="../ur5e/textures/', xml)
    xml = re.sub(r"  <custom>.*?</custom>", PANDA_LIMITS, xml, flags=re.S)
    xml = re.sub(r"\s*<keyframe>.*?</keyframe>", "", xml, flags=re.S)
    out.write_text(xml, encoding="utf-8")
    m = mujoco.MjModel.from_xml_path(str(out)); d = mujoco.MjData(m)
    ref = ROOT / f"data/refpath/ep_{a.episode:04d}_teach.bin"
    if not ref.exists():
        import subprocess; subprocess.run([sys.executable, "-m", "pace_py.tools.make_refpath", "--episode", str(a.episode)], check=True, stdout=subprocess.DEVNULL)
    pos, tan, standoff, travel = load_rpth(ref)
    p0 = pos[0] + np.array([0, 0, standoff]); R0 = tool_rotation(tan[0], travel)
    ik = SeamIK(m, "tool"); rng = np.random.default_rng(a.seed)
    home = np.array([0, 0, 0, -1.57079, 0, 1.57079, -0.7853]); floor = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "floor")
    best = None
    links = [i for i in range(m.nbody) if (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i) or "").startswith("link") and mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i) != "link0"]
    for k in range(400):
        q_init = home + (rng.normal(0, 0.6, 7) if k else 0)
        q_init = np.clip(q_init, m.jnt_range[:, 0] + 0.1, m.jnt_range[:, 1] - 0.1)
        q, ep, er = ik.solve(p0, R0, q_init, iters=200)
        if ep > 1e-4 or er > 1e-3: continue
        d.qpos[:] = q; mujoco.mj_forward(m, d)
        ncon = sum(1 for c in d.contact[:d.ncon] if floor not in (c.geom1, c.geom2))
        if ncon: continue
        margin = float(np.min(np.minimum(q - m.jnt_range[:, 0], m.jnt_range[:, 1] - q)))
        # 선호: 팔꿈치 위(joint4 음수 큰 쪽), 손목이 작업물 위에 서 있는 자세(toolz 위 링크들이 판보다 높게), 관절 여유
        zmin = float(np.min(d.xpos[links, 2])); score = margin - 0.5 * abs(q[6]) + 2.0 * zmin
        if zmin < 0.33: continue                                  # 로봇 링크 원점이 판 상면(0.31) 아래로 내려가면 제외
        if best is None or score > best[0]: best = (score, q.copy(), ep, er, margin, ncon, zmin)
    if best is None: print("IK failed: no collision-free solution"); sys.exit(1)
    _, q, ep, er, margin, ncon, zmin = best
    key = f'<key name="weld_home" qpos="{" ".join(f"{v:.4f}" for v in q)}" ctrl="{" ".join(f"{v:.4f}" for v in q)}"/>'
    xml = xml.replace("</mujoco>", f"  <keyframe>\n    {key}\n  </keyframe>\n</mujoco>"); out.write_text(xml, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}  weld_home q={np.round(q,4).tolist()}  pos_err={ep*1e3:.3f}mm rot_err={er:.4f}rad margin={margin:.2f}rad contacts={ncon} min link z={zmin:.3f}")


if __name__ == "__main__":
    main()
