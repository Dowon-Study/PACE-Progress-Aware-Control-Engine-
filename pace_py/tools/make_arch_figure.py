"""검증된 아키텍처 그림 생성 (SVG+PNG → docs/figures/pace_arch_validated.*). 사용: python -m pace_py.tools.make_arch_figure"""
import re, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
fills = {"c-teal": ("#D7F3EE", "#0B5E52", "#13796A"), "c-coral": ("#FBE1DB", "#8A2C1D", "#B23A26"), "c-gray": ("#EEEEEE", "#222222", "#555555")}
def box(cls, x, y, w, h, title, sub=None, sub2=None, op=1.0):
    f, t1, t2 = fills[cls]; s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{f}" fill-opacity="{op}" stroke="{t2}" stroke-opacity="0.35"/>'
    s += f'<text x="{x+10}" y="{y+22}" font-size="14" font-weight="500" fill="{t1}">{title}</text>'
    if sub: s += f'<text x="{x+10}" y="{y+42}" font-size="12" fill="{t2}">{sub}</text>'
    if sub2: s += f'<text x="{x+10}" y="{y+62}" font-size="12" fill="{t2}">{sub2}</text>'
    return s
def layer(y, h, title): return f'<rect x="40" y="{y}" width="600" height="{h}" rx="12" fill="#F4F4F4" stroke="#CCCCCC"/><text x="52" y="{y+20}" font-size="14" font-weight="500" fill="#222">{title}</text>'
def arrow(x1, y1, x2, y2, label=None, lx=None, ly=None):
    s = f'<path d="M{x1} {y1} L{x2} {y2}" stroke="#7a7a7a" stroke-width="1.5" marker-end="url(#a)"/>'
    if label: s += f'<text x="{lx}" y="{ly}" font-size="12" fill="#555">{label}</text>'
    return s
P = ['<svg xmlns="http://www.w3.org/2000/svg" width="1360" height="1560" viewBox="0 0 680 780" font-family="Noto Sans CJK KR, sans-serif"><rect width="680" height="780" fill="white"/><defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#7a7a7a"/></marker></defs>']
P.append(layer(40, 110, "AI 추론 계층 · GPU / 원격 · 수 Hz~수십 Hz"))
P.append(box("c-teal", 56, 72, 570, 62, "AI 모델 자리 (ACT / VLA 등, 교체 가능) → 영상·상태 → 액션 청크", "검증: GT 경로 공급자(지연·중단·이상값 주입) + 실제 모델 연결(추론 6.4ms, 청크 수락, 지터 불변)"))
P.append(arrow(340, 160, 340, 186, "PATH / PATH_S 청크 (타임스탬프·유효기간·신뢰도·시퀀스)", 350, 178))
P.append(layer(192, 128, "로컬 감독 계층 · 일반 코어 · 30~100 Hz · 켜고 끌 수 있는 블록"))
P.append(box("c-teal", 56, 224, 184, 80, "작은 눈 (고전 CV)", "용접선 검출 → CORRECTION", "고정구 오차 1.47→0.29mm"))
P.append(box("c-teal", 250, 224, 184, 80, "연속 정책 (flow matching)", "AI 끊기면 LOCAL 청크로 잇기", "정지 0회 4s → 10s"))
P.append(box("c-teal", 444, 224, 182, 80, "공정 상태 추론기 (규칙)", "입열 지수 유지 → PARAM", "결함 위험 → EVENT"))
P.append(arrow(340, 322, 340, 346))
P.append(f'<rect x="40" y="350" width="600" height="34" rx="6" fill="#E4E4E4"/><text x="340" y="372" font-size="14" font-weight="500" fill="#222" text-anchor="middle">락프리 공유메모리 /pace · 큐 4 + 상태 + 계약 + 프레임 · 루프 안 락·할당·ROS 없음</text>')
P.append(arrow(340, 386, 340, 410))
P.append(layer(414, 160, "실시간 제어 계층 · 격리 CCX · 1 kHz · 모델 없음 · 깨어남 max 16.7 μs"))
for x, t, s in [(52, "3단계 검증기", "범위·시간·유효성"), (172, "진행도 접합", "실측 위치에서 잇기"), (292, "페이싱", "늦을 조짐 → 감속"), (412, "명령 생성", "툴 공간 IK ≤15μs"), (532, "상태 감시기", "정지 결정 (규칙)")]:
    P.append(box("c-teal", x, 446, 96 if x == 532 else 104, 52, t, s))
for x in [158, 278, 398, 518]: P.append(arrow(x, 472, x + 12, 472))
P.append(box("c-gray", 52, 510, 576, 52, "공백 사다리", "페이싱 → LOCAL 청크 → 규칙 외삽 → 유지 → 감속·정지(아크 OFF)·비상정지 → 실측 위치에서 복귀"))
P.append(arrow(340, 576, 340, 600, "HAL read/write · 정지 3단계 · WCET 계약", 350, 594))
P.append(layer(604, 96, "HAL 계층 · 함수 포인터 5개 + 공통 데이터 구조 (한계값·폴트·접촉력·정지 3단계)"))
P.append(box("c-teal", 56, 636, 200, 52, "MuJoCo 락스텝 백엔드", "UR5e 6축 · Panda 7축 · 0.29~0.30mm"))
P.append(box("c-teal", 268, 636, 200, 52, "ros2_control 플러그인", "hardware_interface · 0.31mm"))
P.append(box("c-gray", 480, 636, 146, 52, "EtherCAT (확장)", "같은 인터페이스"))
for x, cls, lb in [(40, "c-teal", "실측 검증됨"), (150, "c-gray", "구조 / 확장 자리")]:
    pass
for x, cls, lb in [(40, "c-teal", "실측 검증됨"), (150, "c-gray", "구조 / 확장 자리")]:
    P.append(f'<rect x="{x}" y="716" width="14" height="14" rx="4" fill="{fills[cls][0]}" stroke="{fills[cls][2]}"/><text x="{x+20}" y="728" font-size="12" fill="#555">{lb}</text>')
P.append('<text x="40" y="752" font-size="12" fill="#555">각주: 자체 학습 ACT급 모델은 폐루프 발산으로 미채택, 감속 조언기는 무효로 제외 (향후 과제)</text>')
P.append("</svg>")
out = ROOT / "docs/figures/pace_arch_validated.svg"; out.write_text("\n".join(P), encoding="utf-8")
html = ROOT / "docs/figures/_arch.html"; html.write_text(f'<html><body style="margin:0">{out.read_text(encoding="utf-8")}</body></html>', encoding="utf-8")
subprocess.run(["google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox", "--window-size=1360,1560", f"--screenshot={ROOT/'docs/figures/pace_arch_validated.png'}", f"file://{html}"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
html.unlink(); print("saved svg+png")
