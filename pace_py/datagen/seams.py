"""용접선 형상 생성 + 작업물 텍스처 + 장면 MJCF 작성.

좌표계: 판 로컬 (u, v) ∈ [-0.18, 0.18] × [-0.16, 0.16] (m), 판 중심이 원점. 월드 변환은 판 포즈(x, y, z_top, yaw)로.
GT: 호 길이 s 로 매개화된 밀집 점열 (약 1mm 간격), 접선, 그리고 사이트 seam_### (약 4mm 간격).
"""
from __future__ import annotations
import json
import math
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

PLATE_HALF = np.array([0.18, 0.16])     # 판 반폭 (m)
PLATE_THICK = 0.01
TABLE_TOP = 0.30
PLATE_TOP = TABLE_TOP + PLATE_THICK      # 0.31
SEAM_Z = PLATE_TOP + 0.0002
MARGIN = 0.03                            # 용접선이 판 가장자리에서 떨어질 최소 거리
MODEL_DIR = Path(__file__).resolve().parents[2] / "pace" / "models" / "ur5e"
FAMILIES = ("line", "polyline", "arc", "s_curve", "sine", "spline")


@dataclass
class PlatePose:
    x: float = 0.60
    y: float = -0.03
    yaw: float = 0.0          # rad


@dataclass
class SeamSpec:
    family: str
    params: dict
    plate: PlatePose = field(default_factory=PlatePose)
    seed: int = 0

    def to_json(self):
        d = asdict(self); return d


def _resample(pts: np.ndarray, step: float) -> tuple[np.ndarray, np.ndarray]:
    """폴리라인을 호 길이 기준 등간격으로 재샘플. 반환 (points[N,2], s[N])."""
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    L = s[-1]
    n = max(2, int(L / step) + 1)
    ss = np.linspace(0, L, n)
    out = np.stack([np.interp(ss, s, pts[:, 0]), np.interp(ss, s, pts[:, 1])], axis=1)
    return out, ss


def _inside(pts: np.ndarray) -> bool:
    return bool(np.all(np.abs(pts) <= PLATE_HALF - MARGIN))


def seam_local(spec: SeamSpec, step: float = 0.001) -> tuple[np.ndarray, np.ndarray]:
    """판 로컬 좌표의 밀집 점열 (u,v) 와 호 길이 s."""
    p = spec.params; f = spec.family
    if f == "line":
        a = np.array(p["start"]); b = np.array(p["end"]); raw = np.stack([a, b])
    elif f == "polyline":
        raw = np.array(p["points"])
    elif f == "arc":
        c = np.array(p["center"]); r = p["radius"]; a0, a1 = p["a0"], p["a1"]
        ang = np.linspace(a0, a1, 400); raw = c + r * np.stack([np.cos(ang), np.sin(ang)], axis=1)
    elif f == "s_curve":
        # 두 원호를 접선 연속으로 이음: 시작점, 방향, 반지름 r, 각 각도 ±phi
        start = np.array(p["start"]); th = p["heading"]; r = p["radius"]; phi = p["phi"]; L0 = p["lead"]
        pts = [start]; h = th; cur = start.copy()
        cur2 = cur + L0 * np.array([math.cos(h), math.sin(h)]); pts.append(cur2); cur = cur2
        for sgn in (+1, -1):
            c = cur + r * np.array([-math.sin(h), math.cos(h)]) * sgn
            a_start = math.atan2(cur[1] - c[1], cur[0] - c[0])
            ang = a_start + sgn * np.linspace(0, phi, 200)[1:]
            arc = c + r * np.stack([np.cos(ang), np.sin(ang)], axis=1); pts.extend(arc.tolist())
            cur = arc[-1]; h = h + sgn * phi
        cur2 = cur + L0 * np.array([math.cos(h), math.sin(h)]); pts.append(cur2)
        raw = np.array(pts)
    elif f == "sine":
        start = np.array(p["start"]); th = p["heading"]; L = p["length"]; A = p["amp"]; k = p["waves"]
        t = np.linspace(0, L, 600); loc = np.stack([t, A * np.sin(2 * math.pi * k * t / L)], axis=1)
        R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]]); raw = start + loc @ R.T
    elif f == "spline":
        ctrl = np.array(p["ctrl"]); n = len(ctrl)
        # Catmull-Rom
        pts = []
        P = np.vstack([ctrl[0], ctrl, ctrl[-1]])
        for i in range(1, n):
            p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
            for t in np.linspace(0, 1, 60, endpoint=(i == n - 1)):
                t2, t3 = t * t, t * t * t
                pts.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
        raw = np.array(pts)
    else:
        raise ValueError(f)
    return _resample(raw, step)


def random_spec(rng: np.random.Generator, family: str | None = None, perturb_plate: bool = True) -> SeamSpec:
    """판 안에 들어오는 형상이 나올 때까지 샘플링."""
    for _ in range(500):
        fam = family or rng.choice(FAMILIES)
        H = PLATE_HALF - MARGIN
        if fam == "line":
            a = rng.uniform(-H, H); ang = rng.uniform(0, 2 * math.pi); L = rng.uniform(0.18, 0.30)
            b = a + L * np.array([math.cos(ang), math.sin(ang)]); params = {"start": a.tolist(), "end": b.tolist()}
        elif fam == "polyline":
            n = int(rng.integers(3, 5)); a = rng.uniform(-H, H); ang = rng.uniform(0, 2 * math.pi); pts = [a]
            for _ in range(n - 1):
                ang += rng.uniform(-1.2, 1.2); L = rng.uniform(0.06, 0.14); a = a + L * np.array([math.cos(ang), math.sin(ang)]); pts.append(a)
            params = {"points": [q.tolist() for q in pts]}
        elif fam == "arc":
            r = rng.uniform(0.06, 0.14); c = rng.uniform(-H + r, H - r) if np.all(H > r) else np.zeros(2)
            a0 = rng.uniform(0, 2 * math.pi); a1 = a0 + rng.choice([-1, 1]) * rng.uniform(1.0, 2.6)
            params = {"center": c.tolist(), "radius": float(r), "a0": float(a0), "a1": float(a1)}
        elif fam == "s_curve":
            params = {"start": rng.uniform(-H, H).tolist(), "heading": float(rng.uniform(0, 2 * math.pi)), "radius": float(rng.uniform(0.04, 0.09)), "phi": float(rng.uniform(0.6, 1.4)), "lead": float(rng.uniform(0.03, 0.07))}
        elif fam == "sine":
            params = {"start": rng.uniform(-H, H).tolist(), "heading": float(rng.uniform(0, 2 * math.pi)), "length": float(rng.uniform(0.16, 0.28)), "amp": float(rng.uniform(0.01, 0.03)), "waves": float(rng.uniform(1.0, 2.5))}
        else:
            n = int(rng.integers(4, 7)); a = rng.uniform(-H, H); ang = rng.uniform(0, 2 * math.pi); pts = [a]
            for _ in range(n - 1):
                ang += rng.uniform(-0.9, 0.9); a = a + rng.uniform(0.04, 0.09) * np.array([math.cos(ang), math.sin(ang)]); pts.append(a)
            params = {"ctrl": [q.tolist() for q in pts]}
        plate = PlatePose(0.60 + (rng.uniform(-0.03, 0.03) if perturb_plate else 0), -0.03 + (rng.uniform(-0.03, 0.03) if perturb_plate else 0), rng.uniform(-0.25, 0.25) if perturb_plate else 0.0)
        spec = SeamSpec(fam, params, plate, int(rng.integers(1 << 31)))
        try:
            pts, s = seam_local(spec)
        except Exception:
            continue
        if _inside(pts) and 0.15 <= s[-1] <= 0.6:
            return spec
    raise RuntimeError("no valid seam")


def local_to_world(pts_uv: np.ndarray, plate: PlatePose) -> np.ndarray:
    c, s_ = math.cos(plate.yaw), math.sin(plate.yaw)
    R = np.array([[c, -s_], [s_, c]])
    xy = pts_uv @ R.T + np.array([plate.x, plate.y])
    return np.concatenate([xy, np.full((len(xy), 1), SEAM_Z)], axis=1)


def seam_world(spec: SeamSpec, step: float = 0.001):
    """월드 좌표 밀집 점열 [N,3], 호 길이 s[N], 단위 접선 [N,3]."""
    uv, s = seam_local(spec, step)
    w = local_to_world(uv, spec.plate)
    tang = np.gradient(w, s, axis=0); tang /= np.linalg.norm(tang, axis=1, keepdims=True) + 1e-12
    return w, s, tang


def render_texture(spec: SeamSpec, path: Path, px_per_m: float = 5000, width_m: float = 0.0015, rng: np.random.Generator | None = None):
    """판 상면 텍스처: 금속 질감 + 용접선(진한 홈). 이미지 u→가로(+x 로컬), v→세로(+y 로컬, 위쪽이 +v)."""
    import cv2
    W, Hh = int(2 * PLATE_HALF[0] * px_per_m), int(2 * PLATE_HALF[1] * px_per_m)
    rng = rng or np.random.default_rng(spec.seed)
    base = np.full((Hh, W, 3), 150, np.uint8)
    noise = rng.normal(0, 6, (Hh, W, 1)).astype(np.int16); base = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    # 미세 브러시 결
    for _ in range(60):
        y = int(rng.integers(0, Hh)); cv2.line(base, (0, y), (W, y), (int(rng.integers(135, 165)),) * 3, 1)
    uv, _ = seam_local(spec, 0.0005)
    px = np.stack([(uv[:, 0] + PLATE_HALF[0]) * px_per_m, (PLATE_HALF[1] - uv[:, 1]) * px_per_m], axis=1).astype(np.int32)
    cv2.polylines(base, [px.reshape(-1, 1, 2)], False, (70, 70, 72), max(2, int(width_m * px_per_m * 1.8)), cv2.LINE_AA)   # 모따기(groove) 음영
    cv2.polylines(base, [px.reshape(-1, 1, 2)], False, (35, 35, 38), max(1, int(width_m * px_per_m)), cv2.LINE_AA)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), base)
    return path


def write_scene(spec: SeamSpec, name: str, texture_rel: str, show_sites: bool = False, site_step: float = 0.004) -> Path:
    """weld_ur5e.xml 과 같은 장면이되 판 포즈·텍스처·용접선 사이트가 spec 을 따른다. MODEL_DIR 에 쓴다 (include/asset 경로 때문)."""
    w, s, _ = seam_world(spec, 0.001)
    idx = np.arange(0, len(w), max(1, int(site_step / 0.001)))
    if idx[-1] != len(w) - 1: idx = np.append(idx, len(w) - 1)
    sites = "\n".join(f'      <site name="seam_{i:03d}" pos="{w[k,0]:.4f} {w[k,1]:.4f} {w[k,2]:.4f}" size="0.0015" rgba="0 1 0 {1 if show_sites else 0}"/>' for i, k in enumerate(idx))
    pl = spec.plate; qw, qz = math.cos(pl.yaw / 2), math.sin(pl.yaw / 2)
    xml = f'''<mujoco model="weld_ur5e_gen">
  <include file="ur5e_torch.xml"/>
  <option timestep="0.001" integrator="implicitfast"/>
  <statistic center="0.5 0 0.3" extent="1.2"/>
  <visual><headlight diffuse="0.6 0.6 0.6" ambient="0.3 0.3 0.3" specular="0 0 0"/><global azimuth="150" elevation="-25" offwidth="1280" offheight="960"/></visual>
  <asset>
    <texture type="skybox" builtin="gradient" rgb1="0.3 0.5 0.7" rgb2="0 0 0" width="512" height="3072"/>
    <texture type="2d" name="groundplane" builtin="checker" mark="edge" rgb1="0.2 0.3 0.4" rgb2="0.1 0.2 0.3" markrgb="0.8 0.8 0.8" width="300" height="300"/>
    <material name="groundplane" texture="groundplane" texuniform="true" texrepeat="5 5" reflectance="0.1"/>
    <texture type="2d" name="plate_tex" file="{texture_rel}"/>
    <material name="plate_mat" texture="plate_tex" texuniform="false" texrepeat="1 1" specular="0.4" shininess="0.5"/>
  </asset>
  <custom>
    <numeric name="qd_max" data="2.0 2.0 2.5 3.0 3.0 3.0"/>
    <numeric name="qdd_max" data="8 8 10 15 15 15"/>
    <numeric name="jerk_max" data="200 200 250 400 400 400"/>
    <numeric name="workspace" data="0.25 -0.45 0.25  1.0 0.40 0.90"/>
  </custom>
  <worldbody>
    <light pos="0.5 -0.5 1.5" dir="0 0.3 -1" directional="true"/>
    <geom name="floor" size="0 0 0.05" type="plane" material="groundplane"/>
    <camera name="cam_scene" pos="1.35 -1.0 1.0" xyaxes="0.67 0.74 0 -0.30 0.27 0.92" fovy="45"/>
    <body name="table" pos="0.60 -0.03 {TABLE_TOP/2-0.005:.3f}"><geom name="table_top" type="box" size="0.26 0.22 {TABLE_TOP/2-0.005:.3f}" rgba="0.35 0.35 0.38 1"/></body>
    <body name="workpiece" pos="{pl.x:.4f} {pl.y:.4f} {TABLE_TOP:.2f}" quat="{qw:.6f} 0 0 {qz:.6f}">
      <geom name="plate" type="box" size="{PLATE_HALF[0]} {PLATE_HALF[1]} {PLATE_THICK}" material="plate_mat"/>
    </body>
    <body name="seam" pos="0 0 0">
{sites}
    </body>
  </worldbody>
</mujoco>
'''
    key = re.search(r'<key name="weld_home"[^>]*/>', (MODEL_DIR / "weld_ur5e.xml").read_text(encoding="utf-8"))
    if key: xml = xml.replace("</mujoco>", f"  <keyframe>\n    {key.group(0)}\n  </keyframe>\n</mujoco>")
    out = MODEL_DIR / f"{name}.xml"; out.write_text(xml, encoding="utf-8")
    return out


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    for fam in FAMILIES:
        sp = random_spec(rng, fam); w, s, _ = seam_world(sp); print(fam, "length=%.3f m" % s[-1], json.dumps(sp.to_json())[:80])
