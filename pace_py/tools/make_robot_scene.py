"""로봇 확장(HAL 비종속 시연): Menagerie 팔에 같은 토치·카메라를 붙인 로봇 파일을 만들고, UR5e 에피소드 장면의 작업물·용접선 위에 그 로봇을 세워
IK 로 weld_home 키프레임을 넣은 장면을 생성한다. 제어기·눈·평가기는 그대로 쓴다.
사용: python -m pace_py.tools.make_robot_scene --robot iiwa14|xarm7 --episode 1  →  pace/models/<robot>/_gen_ep0001_<robot>.xml"""
import argparse, re, struct, sys
from pathlib import Path
import numpy as np, mujoco
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pace_py.datagen.trajectory import SeamIK, tool_rotation   # noqa: E402
ROOT = Path(__file__).resolve().parents[2]
TORCH = '''<body name="torch" pos="{pos}">
                      <geom name="torch_body" type="cylinder" fromto="0 0 0 0 0 0.10" size="0.012" rgba="0.2 0.2 0.25 1" mass="0.3" contype="0" conaffinity="0"/>
                      <geom name="torch_tip" type="cylinder" fromto="0 0 0.10 0 0 0.14" size="0.004" rgba="0.8 0.5 0.2 1" mass="0.02" contype="1" conaffinity="1"/>
                      <site name="tip_touch" pos="0 0 0.14" size="0.006" type="sphere" rgba="0 0 0 0"/>
                      <site name="tool" pos="0 0 0.145" size="0.003" rgba="1 0 0 1"/>
                      <camera name="cam_tool" pos="0 -0.07 0.05" xyaxes="1 0 0 0 -0.82 0.57" fovy="50"/>
                    </body>'''
ROBOTS = {
    "iiwa14": dict(src="third_party/mujoco_menagerie/kuka_iiwa_14/iiwa14.xml", base_body="base", base_pos="0.05 0 0", attach_pos="0 0 0.045",
                   home=[0, 0.7854, 0, -1.5708, 0, 0, 0], limits=("1.48 1.48 1.74 1.31 2.27 2.36 2.36", "10 10 10 10 12 12 12", "400 400 400 400 400 400 400")),
    "xarm7": dict(src="third_party/mujoco_menagerie/ufactory_xarm7/xarm7_nohand.xml", base_body="link_base", base_pos="0.30 0.38 0.12", attach_pos="0 0 0",
                  home=[0, -0.247, 0, 0.909, 0, 1.156, 0], limits=("2.0 2.0 2.0 2.0 2.5 2.5 2.5", "10 10 10 10 12 12 12", "400 400 400 400 400 400 400")),
}
WORKSPACE = "0.25 -0.45 0.25  1.0 0.40 0.90"


def prepare_robot(name, spec):
    """Menagerie 로봇 파일 → pace/models/<name>/<name>_torch.xml (토치 부착, 베이스 위치, keyframe/option 제거)"""
    src = (ROOT / spec["src"]).read_text(encoding="utf-8")
    out = re.sub(r"\s*<keyframe>.*?</keyframe>", "", src, flags=re.S); out = re.sub(r"\s*<option[^>]*/>", "", out)
    out = re.sub(r'(<site[^>]*name="attachment_site"[^>]*/>)', r"\1\n                    " + TORCH.format(pos=spec["attach_pos"]), out, count=1)
    m_ = re.search(rf'<body name="{spec["base_body"]}"[^>]*>', out); tag = m_.group(0)
    tag2 = re.sub(r'\spos="[^"]*"', "", tag).replace(f'<body name="{spec["base_body"]}"', f'<body name="{spec["base_body"]}" pos="{spec["base_pos"]}"', 1)   # 기존 pos 는 지우고 우리 값으로
    out = out.replace(tag, tag2, 1)
    out = out.replace("<mujoco model=", f"<!-- Menagerie {Path(spec['src']).name} + 용접 토치(UR5e 와 동일 기하) · 베이스 {spec['base_pos']} · 접촉 센서 -->\n<mujoco model=", 1)
    out = out.replace("</mujoco>", '  <sensor>\n    <touch name="tip_touch" site="tip_touch"/>\n  </sensor>\n</mujoco>')
    p = ROOT / f"pace/models/{name}/{name}_torch.xml"; p.write_text(out, encoding="utf-8"); return p


def load_rpth(path):
    b = open(path, "rb").read(); magic, n, sdot, standoff, travel, _ = struct.unpack_from("<II4f", b, 0); assert magic == 0x48545052
    a = np.frombuffer(b, np.float32, count=7 * n, offset=24).reshape(n, 7).astype(np.float64); return a[:, 1:4], a[:, 4:7], standoff, travel


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--robot", required=True, choices=list(ROBOTS)); ap.add_argument("--episode", type=int, required=True); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(); spec = ROBOTS[a.robot]; prepare_robot(a.robot, spec)
    src = ROOT / f"pace/models/ur5e/_gen_ep{a.episode:04d}.xml"; out = ROOT / f"pace/models/{a.robot}/_gen_ep{a.episode:04d}_{a.robot}.xml"
    xml = src.read_text(encoding="utf-8").replace('<include file="ur5e_torch.xml"/>', f'<include file="{a.robot}_torch.xml"/>').replace('model="weld_ur5e_gen"', f'model="weld_{a.robot}_gen"')
    xml = re.sub(r'file="textures/', 'file="../ur5e/textures/', xml)
    qd, qdd, jk = spec["limits"]
    xml = re.sub(r"  <custom>.*?</custom>", f'  <custom>\n    <numeric name="qd_max" data="{qd}"/>\n    <numeric name="qdd_max" data="{qdd}"/>\n    <numeric name="jerk_max" data="{jk}"/>\n    <numeric name="workspace" data="{WORKSPACE}"/>\n  </custom>', xml, flags=re.S)
    xml = re.sub(r"\s*<keyframe>.*?</keyframe>", "", xml, flags=re.S); out.write_text(xml, encoding="utf-8")
    m = mujoco.MjModel.from_xml_path(str(out)); d = mujoco.MjData(m)
    ref = ROOT / f"data/refpath/ep_{a.episode:04d}_teach.bin"
    if not ref.exists():
        import subprocess; subprocess.run([sys.executable, "-m", "pace_py.tools.make_refpath", "--episode", str(a.episode)], check=True, stdout=subprocess.DEVNULL)
    pos, tan, standoff, travel = load_rpth(ref); p0 = pos[0] + np.array([0, 0, standoff]); R0 = tool_rotation(tan[0], travel)
    ik = SeamIK(m, "tool"); rng = np.random.default_rng(a.seed); home = np.array(spec["home"], float); floor = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "floor")
    names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i) or "" for i in range(m.nbody)]
    links = [i for i, n in enumerate(names) if n.startswith("link") and n not in ("link0", "link_base", "link1", "link2")]   # 원위 링크만 (베이스 쪽 링크는 원래 낮다)
    best = None; nq = m.nq
    for k in range(600):
        q_init = np.clip(home + (rng.normal(0, 0.7, nq) if k else 0), m.jnt_range[:, 0] + 0.1, m.jnt_range[:, 1] - 0.1)
        q, ep, er = ik.solve(p0, R0, q_init, iters=200)
        if ep > 1e-4 or er > 1e-3: continue
        d.qpos[:] = q; mujoco.mj_forward(m, d)
        if any(floor not in (c.geom1, c.geom2) for c in d.contact[:d.ncon]): continue
        margin = float(np.min(np.minimum(q - m.jnt_range[:, 0], m.jnt_range[:, 1] - q))); zmin = float(np.min(d.xpos[links, 2])) if links else 1.0
        if zmin < 0.33: continue
        score = margin + 2.0 * zmin
        if best is None or score > best[0]: best = (score, q.copy(), ep, er, margin, zmin)
    if best is None: print(f"{a.robot}: IK failed (base {spec['base_pos']})"); sys.exit(1)
    _, q, ep, er, margin, zmin = best
    key = f'<key name="weld_home" qpos="{" ".join(f"{v:.4f}" for v in q)}" ctrl="{" ".join(f"{v:.4f}" for v in q)}"/>'
    out.write_text(xml.replace("</mujoco>", f"  <keyframe>\n    {key}\n  </keyframe>\n</mujoco>"), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} nq={nq} weld_home={np.round(q,3).tolist()} pos_err={ep*1e3:.3f}mm rot_err={er:.4f} margin={margin:.2f}rad min link z={zmin:.3f}")


if __name__ == "__main__":
    main()
