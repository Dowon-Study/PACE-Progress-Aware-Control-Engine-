"""접촉력 시연 장면: 에피소드 장면의 용접선 중간에 돌출부(스패터/탭 가정, 기본 9mm 높이)를 올린다. 토치 끝(판 위 7mm)이 부딪혀 접촉력이 생긴다.
사용: python -m pace_py.tools.make_bump_scene --episode 1 [--height 0.009] → pace/models/ur5e/_gen_ep0001_bump.xml"""
import argparse, math, struct
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--episode", type=int, required=True); ap.add_argument("--height", type=float, default=0.009); ap.add_argument("--at", type=float, default=0.5, help="용접선 호길이 비율 위치")
    a = ap.parse_args(); src = ROOT / f"pace/models/ur5e/_gen_ep{a.episode:04d}.xml"
    b = open(ROOT / f"data/refpath/ep_{a.episode:04d}_real.bin", "rb").read(); n = struct.unpack_from("<II", b, 0)[1]; arr = np.frombuffer(b, np.float32, count=7 * n, offset=24).reshape(n, 7)
    i = int(a.at * (n - 1)); p, t = arr[i, 1:4], arr[i, 4:7]; yaw = math.atan2(t[1], t[0]); qw, qz = math.cos(yaw / 2), math.sin(yaw / 2)
    bump = f'    <body name="bump" pos="{p[0]:.4f} {p[1]:.4f} {0.31 + a.height/2:.4f}" quat="{qw:.6f} 0 0 {qz:.6f}"><geom name="bump" type="box" size="0.010 0.015 {a.height/2:.4f}" rgba="0.6 0.3 0.1 1"/></body>\n'
    xml = src.read_text(encoding="utf-8").replace('    <body name="seam" pos="0 0 0">', bump + '    <body name="seam" pos="0 0 0">', 1)
    out = ROOT / f"pace/models/ur5e/_gen_ep{a.episode:04d}_bump.xml"; out.write_text(xml, encoding="utf-8"); print("wrote", out.relative_to(ROOT), "bump at", np.round(p, 4), "height", a.height)


if __name__ == "__main__":
    main()
