"""발표 PPT 생성 (python-pptx) + PIL 미리보기. 템플릿(pace_template.pdf) 스타일: 흰→연파랑 그라데이션, 알약 태그, 남색 제목, 흰 카드, 남색 강조 박스.
사용: .venv/bin/python -m pace_py.tools.make_deck  → docs/slides/PACE_발표.pptx, docs/slides/preview/*.png"""
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from PIL import Image, ImageDraw, ImageFont
import copy
ROOT = Path(__file__).resolve().parents[2]; A = ROOT / "docs/slides/assets"; F = ROOT / "docs/figures"; OUT = ROOT / "docs/slides"; PV = OUT / "preview"; PV.mkdir(parents=True, exist_ok=True)
NAVY, DARK, BLUE, LBLUE, PILL, GRAY, LGRAY, WHITE, RED, GREEN, ORANGE, TEAL = "0B1437", "0B1230", "4A90D9", "DCEEFC", "3B82C4", "7A8699", "EEF3F8", "FFFFFF", "D64545", "2E9E5B", "EF8A17", "00897B"
FONT = "맑은 고딕"; W, H = 13.333, 7.5
prs = Presentation(); prs.slide_width = Inches(W); prs.slide_height = Inches(H); BLANK = prs.slide_layouts[6]
PILF = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 20); PILB = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 20)
OPS = []  # 미리보기용 기록
VF = ROOT / "validation/figures/verification"



def rgb(h): return RGBColor.from_string(h)


COUNT = [0]

class S:
    def __init__(self, idx=None):
        COUNT[0] += 1; idx = COUNT[0]
        self.s = prs.slides.add_slide(BLANK); self.ops = []; OPS.append(self.ops); self.idx = idx
        bg = self.s.background.fill; bg.gradient(); bg.gradient_angle = 90; st = bg.gradient_stops; st[0].color.rgb = rgb("FFFFFF"); st[0].position = 0.0; st[1].color.rgb = rgb("CFE4F7"); st[1].position = 1.0
        self.ops.append(("bg",))
        self.text(W - 1.2, H - 0.42, 1.0, 0.3, f"{idx}", 9, color=GRAY, align="r")

    def rect(self, x, y, w, h, fill=WHITE, line=None, radius=0.0, shadow=False, lw=0.75):
        shp = self.s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        if radius: shp.adjustments[0] = min(0.5, radius / min(w, h))
        if fill is None: shp.fill.background()
        else: shp.fill.solid(); shp.fill.fore_color.rgb = rgb(fill)
        if line: shp.line.color.rgb = rgb(line); shp.line.width = Pt(lw)
        else: shp.line.fill.background()
        if not shadow: shp.shadow.inherit = False
        shp.text_frame.text = ""; self.ops.append(("rect", x, y, w, h, fill, line, radius)); return shp

    def text(self, x, y, w, h, s, size=14, bold=False, color=NAVY, align="l", valign="t", italic=False, lsp=1.1, font=FONT):
        tb = self.s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); tf = tb.text_frame; tf.word_wrap = True; tf.margin_left = tf.margin_right = Inches(0.05); tf.margin_top = tf.margin_bottom = Inches(0.03)
        tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[valign]
        for i, line in enumerate(s.split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph(); p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]; p.line_spacing = lsp
            r = p.add_run(); r.text = line; r.font.size = Pt(size); r.font.bold = bold; r.font.italic = italic; r.font.color.rgb = rgb(color); r.font.name = font
            rPr = r._r.get_or_add_rPr(); ea = rPr.find(qn("a:ea"))
            if ea is None: ea = rPr.makeelement(qn("a:ea"), {}); rPr.append(ea)
            ea.set("typeface", font)
        self.ops.append(("text", x, y, w, h, s, size, bold, color, align, valign)); return tb

    def img(self, path, x, y, w=None, h=None):
        path = str(path); im = Image.open(path); ar = im.width / im.height
        if w and not h: h = w / ar
        if h and not w: w = h * ar
        if w and h and abs(w / h - ar) > 1e-3:  # 비율 유지: 박스 안에 맞춤
            if w / h > ar: w2 = h * ar; x += (w - w2) / 2; w = w2
            else: h2 = w / ar; y += (h - h2) / 2; h = h2
        self.s.shapes.add_picture(path, Inches(x), Inches(y), Inches(w), Inches(h)); self.ops.append(("img", path, x, y, w, h)); return (x, y, w, h)

    def pill(self, x, y, s, w=None):
        w = w or (0.16 * len(s) + 0.5); self.rect(x, y, w, 0.36, fill=LBLUE, radius=0.18); self.text(x, y, w, 0.36, s, 10.5, bold=True, color=PILL, align="c", valign="m"); return w

    def header(self, tag, title, sub=None, center=False):
        if center:
            self.pill(W / 2 - 1.2, 0.45, tag, 2.4); self.text(1, 0.85, W - 2, 0.8, title, 30, bold=True, align="c")
            if sub: self.text(1, 1.6, W - 2, 0.4, sub, 13, color=GRAY, align="c")
        else:
            self.pill(0.7, 0.45, tag); self.text(0.62, 0.85, W - 2, 0.8, title, 28, bold=True)
            if sub: self.text(0.7, 1.55, W - 2, 0.4, sub, 12.5, color=GRAY)

    def arrow(self, x1, y1, x2, y2, color=BLUE, lw=2.0, head=True):
        c = self.s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2)); c.line.color.rgb = rgb(color); c.line.width = Pt(lw)
        if head:
            ln = c.line._get_or_add_ln(); te = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}); ln.append(te)
        self.ops.append(("arrow", x1, y1, x2, y2, color)); return c

    def circle(self, x, y, d, s, fill=BLUE, color=WHITE, size=12):
        shp = self.s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d)); shp.fill.solid(); shp.fill.fore_color.rgb = rgb(fill); shp.line.fill.background(); shp.shadow.inherit = False
        self.ops.append(("circ", x, y, d, fill)); self.text(x, y, d, d, s, size, bold=True, color=color, align="c", valign="m")

    def card(self, x, y, w, h, title, body, num=None, icon=None, dark=False, tsize=14, bsize=11.5):
        self.rect(x, y, w, h, fill=DARK if dark else WHITE, radius=0.08, shadow=not dark); tc, bc = (WHITE, "C9D3E3") if dark else (NAVY, "4A5568"); ox = 0.25
        if num: self.circle(x + 0.22, y + 0.22, 0.42, num, size=11); ox = 0.8
        self.text(x + ox, y + 0.16, w - ox - 0.2, 0.5, title, tsize, bold=True, color=tc)
        if body: self.text(x + ox, y + 0.62, w - ox - 0.2, h - 0.7, body, bsize, color=bc, lsp=1.15)


def arch(sl, x, y, w, h, hi=None, note=None):
    """4계층 아키텍처 블록 다이어그램. hi: 강조할 블록 키 (ai, eye, mlp, val, splice, pace, mon, hal)."""
    rows = [("ai", "AI 추론 계층", "비실시간 · GPU · 10 Hz", [("ai", "AI 모델 (ACT/VLA 등, 교체 가능) → 액션 청크 PATH")]),
            ("local", "로컬 감독 계층", "일반 코어 · 30~100 Hz", [("eye", "작은 눈(CV)\n용접선 → CORRECTION"), ("mlp", "MLP 보조 궤적\nLOCAL 청크 100 ms 마다"), ("proc", "공정 상태 추론\n→ PARAM / EVENT")]),
            ("rt", "실시간 제어 계층", "격리 코어 · 1 kHz · 학습 모델 없음", [("val", "3단계 검증기\n범위·시간·유효성"), ("splice", "진행도 접합\n실측 위치에서 잇기"), ("pace", "공백 사다리\n페이싱→LOCAL→외삽→정지"), ("mon", "상태 감시기\n정지 결정(규칙)")]),
            ("hal", "HAL 계층", "함수 5개 · 정지 3단계 · WCET 계약", [("hal", "MuJoCo 락스텝 · ros2_control · 4 로봇 (UR5e·Panda·iiwa14·xArm7)")])]
    rh = (h - 0.3 * 3) / 4; yy = y
    for key, title, sub, blocks in rows:
        sl.rect(x, yy, w, rh, fill="F6F9FC", line="D5DEE9", radius=0.08); sl.text(x + 0.15, yy + 0.05, 2.6, 0.3, title, 11, bold=True); sl.text(x + 0.15, yy + 0.32, 3.2, 0.3, sub, 8.5, color=GRAY)
        bw = (w - 0.3 - 0.12 * (len(blocks) - 1)) / len(blocks); bx = x + 0.15
        for bk, bt in blocks:
            on = (hi == bk) if hi else True; fill = ("FFF1E0" if hi else "E3F4F1"); line = (ORANGE if (hi and on) else ("B8E0D8" if not hi else "D5DEE9")); fill = fill if (not hi or on) else "FFFFFF"
            sl.rect(bx, yy + 0.62, bw, rh - 0.72, fill=fill, line=line, radius=0.06, lw=2.0 if (hi and on) else 0.75); sl.text(bx + 0.06, yy + 0.64, bw - 0.12, rh - 0.76, bt, 9 if len(blocks) > 1 else 10, bold=bool(hi and on), color=NAVY if (not hi or on) else "9AA5B5", align="c", valign="m"); bx += bw + 0.12
        if key != "hal": sl.arrow(x + w / 2, yy + rh, x + w / 2, yy + rh + 0.3, color="9AA5B5", lw=1.5)
        yy += rh + 0.3
    if note: sl.text(x, y + h + 0.05, w, 0.3, note, 9, color=GRAY, align="c")


def build():
    # 1 표지
    s = S(); s.pill(W / 2 - 1.9, 0.9, "PAC 2026 · HD현대로보틱스 과제 4", 3.8)
    s.text(1, 1.4, W - 2, 1.0, "피지컬100 실시간 제어 OS", 40, bold=True, align="c"); s.text(1, 2.3, W - 2, 0.5, "AI 추론·실시간 제어 통합형 RTOS 기반 로봇 상위제어 플랫폼 — 진행도 기반 접합 (PACE)", 14, color=GRAY, align="c")
    s.text(1, 2.85, W - 2, 0.4, "윤도원 · 권희재", 16, bold=True, align="c", color=PILL)
    s.img(F / "compare_gap6_t16s.png", 0.7, 3.45, w=W - 1.4, h=3.9)
    # 2 서론
    s = S(); s.header("문제의 정합성 · 배경과 문제 정의", "AI는 '언제' 판단했고, 로봇은 '지금' 어디에 있는가")
    s.img(A / "fail_baseline.gif", 0.7, 1.75, w=5.2); s.text(0.7, 6.45, 5.8, 0.6, "▲ 일반 추론 재생: AI 응답이 6 s 늦자 유지 → 정지 → 용접 불량 (시뮬레이션, 실측 로그)", 10, color=GRAY)
    s.card(6.7, 1.75, 6.0, 0.95, "AI 판단과 1 kHz 제어기가 함께 돌아야 한다", "용접: AI 가 영상으로 용접선·용융풀 판단 → 제어기가 토치 위치·속도·조건 조정", num="01")
    s.card(6.7, 2.85, 6.0, 0.95, "두 작업의 시간 특성이 다르다", "AI 추론시간은 입력·부하에 따라 흔들리고, 제어 주기는 일정해야 한다 → 지연·지터 → 추종 오차 (Smeds·Lu 2012)", num="02")
    s.card(6.7, 3.95, 6.0, 0.95, "주기를 지켜도 '적용 시점'이 어긋난다", "늦게 온 판단은 이미 지나간 구간의 것 → 그대로 적용하면 틀린 보정 (de Graaf 등 2010)", num="03")
    s.card(6.7, 5.05, 6.0, 1.35, "문제 정의", "AI 결과의 관측 시점·도착 시점이 제어 주기와 어긋나도, 1 ms 주기를 지키면서 작업을 멈추지 않고 올바르게 반영하는 상위 제어 구조", dark=True, bsize=12)
    # 3 원인
    s = S(); s.header("문제의 정합성 · 발생 원인", "AI 결과가 '준비되는 시점' ≠ 제어 명령을 '갱신해야 하는 시점'")
    y0 = 2.0; s.text(0.7, y0, 2.0, 0.4, "제어 주기 (1 ms)", 12, bold=True); 
    for i in range(40): s.rect(2.8 + i * 0.24, y0 + 0.05, 0.12, 0.3, fill=BLUE)
    s.text(0.7, y0 + 0.9, 2.0, 0.4, "AI 결과 도착", 12, bold=True)
    for xi in (2.8, 3.95, 5.6, 6.1, 8.3, 9.0, 11.4): s.arrow(xi, y0 + 1.5, xi, y0 + 1.0, color=ORANGE, lw=2.5)
    s.text(2.8, y0 + 1.55, 9.6, 0.35, "도착 간격이 불규칙 → 어떤 주기는 새 결과 없이, 어떤 주기는 이미 지난 결과로 갱신", 11, color=GRAY)
    s.card(0.7, 4.3, 6.0, 1.9, "모델 연산량 → 기본 추론 지연", "모델·입력이 클수록 계산 시간이 길다\nAI 결과 생성 주기(수십~수백 ms) > 제어 주기(1 ms)", num="01", bsize=12)
    s.card(6.9, 4.3, 5.8, 1.9, "공유 CPU·GPU 의 자원 대기와 간섭", "같은 모델·같은 입력이라도 다른 작업이 자원·메모리 대역폭을 쓰면 완료 시각이 달라진다\n전처리·후처리의 CPU 스케줄링과 전송도 지연에 더해진다", num="02", bsize=12)
    s.rect(0.7, 6.4, 12.0, 0.6, fill=DARK, radius=0.06); s.text(0.7, 6.4, 12.0, 0.6, "연산량이 일정해도 도착 시각은 일정하지 않다 → 제어기는 '늦고·끊기고·틀린' 결과를 전제로 설계해야 한다", 13, bold=True, color=WHITE, align="c", valign="m")
    # 4 아키텍처
    s = S(); s.header("기술 성숙도 · 아키텍처", "4계층: AI 는 늦어도 되고, 1 kHz 제어기는 멈추지 않는다")
    arch(s, 0.7, 1.75, 7.6, 5.2)
    s.card(8.6, 1.75, 4.1, 1.45, "분리", "AI·로컬은 비실시간 코어, 제어는 격리 코어 1 kHz\n락프리 공유메모리로만 연결 (루프 안 락·할당·ROS 없음)", num="01")
    s.card(8.6, 3.35, 4.1, 1.45, "진행도 접합", "AI 청크를 '시간'이 아니라 '진행도'로 잇는다\n→ 늦게 와도 현재 위치에서 자연스럽게 연결", num="02")
    s.card(8.6, 4.95, 4.1, 1.45, "공백 사다리", "AI 가 끊기면 페이싱 → MLP 보조 궤적 → 외삽 → 정지\n정지는 규칙(감시기)만 결정, 학습 모델은 교체 가능 부품", num="03")
    # 5~8 스토리
    story = [(5, "① AI 응답이 끊겼다", "ai", A / "pace_1_no_ai.gif", "AI 청크가 오지 않음 → 검증기가 '남은 참조'를 보고 늦을 조짐 감지 → 0.2배까지 감속(페이싱). 멈추지 않는다.", "AI 추론 계층: ✕ 응답 없음  →  실시간 제어: PACING"),
             (6, "② MLP 가 보조 궤적을 그린다", "mlp", A / "pace_2_local.gif", "로컬 MLP 가 최근 300 ms 관절 이력으로 1 s 보조 궤적(LOCAL 청크)을 100 ms 마다 생성 → 제어기가 채택, 용접 계속.", "로컬 감독 계층: MLP 보조 궤적  →  실시간 제어: LOCAL"),
             (7, "③ 이미지로 궤적을 계속 보정한다", "eye", F / "s7_eye_frames_ep1.png", "토치 카메라 → 용접선 검출 → CORRECTION. 보조 궤적을 따라가는 동안에도 용접선에서 벗어나지 않게 1 kHz 로 보정 (가로 오차 0.3 mm).", "로컬 감독 계층: 작은 눈  →  실시간 제어: 보정 반영"),
             (8, "④ AI 가 돌아오면 '진행도'로 이어 붙인다", "splice", A / "pace_3_splice.gif", "새 AI 청크가 오면 현재 관절값을 청크에 투영해 가장 가까운 점(진행도)을 찾고 거기서부터 잇는다. 시간으로 맞추지 않으므로 늦게 와도 점프가 없다 (점프 비례 블렌딩).", "AI 추론 계층: 청크 복귀  →  실시간 제어: 진행도 접합")]
    for idx, title, hi, media, cap, flow in story:
        s = S(idx); s.header("기술 성숙도 · 동작 흐름", title)
        arch(s, 0.6, 1.75, 5.6, 4.6, hi=hi); s.text(0.6, 6.45, 5.6, 0.4, flow, 10.5, bold=True, color=ORANGE, align="c")
        if idx == 8:
            s.img(media, 6.5, 1.75, w=6.2, h=3.45); s.rect(6.5, 5.3, 6.2, 0.5, fill=WHITE, line="D5DEE9", radius=0.06); s.text(6.55, 5.3, 6.1, 0.5, "시간 기준 접합 → 점프 ✕      진행도 기준 접합 → 연속 ○ (점프 비례 블렌딩)", 11, bold=True, color=NAVY, align="c", valign="m")
        else: s.img(media, 6.5, 1.75, w=6.2, h=4.0)
        s.rect(6.5, 5.95, 6.2, 1.0, fill=DARK, radius=0.06); s.text(6.6, 5.95, 6.0, 1.0, cap, 12, color=WHITE, valign="m")
    # 진행도 접합 비교 (5단계)
    s = S(); s.header("기술 성숙도 · 접합 정책 비교", "같은 AI, 같은 지연 — 반영 정책만 바꾸면 결과가 갈린다")
    s.img(A / "policy_compare.png", 0.7, 1.8, w=8.3)
    s.card(9.3, 1.8, 3.4, 1.55, "시간 인덱스 (기준선)", "벽시계를 따라잡으려 2.4배속 → 5.2 mm, 저크 21,100\n운영자 속도 지령 무시 (1.00×)", num="01", bsize=10.5)
    s.card(9.3, 3.5, 3.4, 1.55, "진행도 접합 (PACE)", "멈춘 자리에서 1.07배로 이어가 0.26 mm\n지령 0.5× 를 0.53× 로 정확히 실행", num="02", bsize=10.5)
    s.card(9.3, 5.2, 3.4, 1.55, "관측시각 청크(미래 겨냥 없는 AI)", "저크 p99: 진행도 2,685 < 즉시 3,457 < 시간 인덱스 8,821\n투영이 뒤로 점프하지 않기 때문", num="03", bsize=10.5)
    s.rect(0.7, 5.05, 8.3, 1.0, fill=DARK, radius=0.06); s.text(0.8, 5.05, 8.1, 1.0, "8개 시나리오 × 3 정책 (지연 100±50 ms). 외란은 세 정책 동일(서보 영역) → 접합 정책의 차이는 '중단 뒤 복귀' 와 '속도 조절' 에서 난다", 11.5, bold=True, color=WHITE, align="c", valign="m")
    s.text(0.7, 6.2, 8.3, 0.5, "출처: docs/benchmarks/README.md 5단계 (compare_policies, ep0)", 9, color=GRAY)
    # 비전 보정 (7단계)
    s = S(); s.header("현장 적용 가능성 · 비전 AI 기반 목표 위치 보정", "고정구 오차를 토치 카메라의 작은 눈이 보정")
    s.img(F / "s7_ep1_lateral.png", 0.7, 1.8, w=6.0); s.text(0.7, 5.35, 6.0, 0.4, "▲ ep1 직선 용접선: 교시 경로만 / 눈 보정 / 눈 10~14 s 끊김", 10, color=GRAY)
    s.img(F / "s7_ep5_lateral.png", 6.9, 1.8, w=5.8); s.text(6.9, 5.35, 5.8, 0.4, "▲ ep5 원호 용접선: 고정구 오차 −9 ~ +6 mm 를 수렴 후 0.6 mm 로", 10, color=GRAY)
    s.card(0.7, 5.8, 3.9, 1.15, "직선 ep1", "1.47 → 0.29 mm (max 0.49), 보정 957건 거부 0", num="01", bsize=10.5)
    s.card(4.75, 5.8, 3.9, 1.15, "눈 끊김 4 s", "0.30 mm 유지, 2 s 뒤 0.5× 감속, 정지 0회", num="02", bsize=10.5)
    s.card(8.8, 5.8, 3.9, 1.15, "원호 ep5", "5.05 → 1.27 mm (수렴 후 0.6), 루프 지연 변화 없음", num="03", bsize=10.5)
    # 9 하위 계층 대비
    s = S(); s.header("기술 성숙도 · 보조 궤적도 없을 때", "하위 계층의 자체 대비: 규칙만으로 멈추고, 규칙만으로 돌아온다")
    steps = [("페이싱", "늦을 조짐 → 0.2배 감속", BLUE), ("LOCAL", "MLP 보조 궤적 채택", BLUE), ("규칙 외삽", "등속 400 ms, 0.2배", TEAL), ("유지 HOLD", "진입 위치 잠금 1 s", TEAL), ("감속·정지", "아크 OFF, 0.4 s 램프", ORANGE), ("비상정지", "2 s 지속 시 브레이크 체결", RED), ("복귀", "실측 위치에 재고정 후 재개", GREEN)]
    sw = (W - 1.4 - 0.15 * 6) / 7; x = 0.7
    for i, (t, d, c) in enumerate(steps):
        s.rect(x, 2.0, sw, 1.5, fill=WHITE, line=c, radius=0.08, lw=2); s.rect(x, 2.0, sw, 0.5, fill=c, radius=0.08); s.text(x, 2.0, sw, 0.5, t, 12, bold=True, color=WHITE, align="c", valign="m"); s.text(x + 0.05, 2.55, sw - 0.1, 0.9, d, 9.5, color="4A5568", align="c", valign="m")
        if i < 6: s.arrow(x + sw, 2.75, x + sw + 0.15, 2.75, color="9AA5B5", lw=1.5, head=False)
        x += sw + 0.15
    s.card(0.7, 3.85, 3.9, 1.6, "3단계 검증기", "범위 → 시간(유효기간·순서) → 유효성(이탈도·신뢰도)\n주입 이상값 3/3 거부 · 만료 결과 사용 0", num="01", bsize=11)
    s.card(4.75, 3.85, 3.9, 1.6, "물리 기준 상태 감시기", "추종 오차·속도·작업 공간·접촉력·HAL 폴트 → 정지 결정\n감지 1~40 ms, 정지 결정에 학습 모델 없음", num="02", bsize=11)
    s.card(8.8, 3.85, 3.9, 1.6, "HAL 정지 3단계", "DECEL(램프) → HOLD(위치 잠금) → ESTOP(브레이크·폴트 비트)\n네 로봇 동일 타임라인", num="03", bsize=11)
    s.rect(0.7, 5.75, 12.0, 1.1, fill=DARK, radius=0.06); s.text(0.8, 5.75, 11.8, 1.1, "HAL 폴트 5 s 실측: 판정 틱에 아크 OFF → 0.37 s 감속 → HOLD → 2 s 뒤 ESTOP 체결 · 네 로봇 동일 타임라인\n비정상 구간에서도 1 ms 주기 미스 0 · 감지 1~40 ms · 1 s 폴트는 1.56 s 만에 자동 복귀", 12.5, bold=True, color=WHITE, align="c", valign="m")
    # 검증기 거부 · 장애 복구 (B1·B3)
    s = S(); s.header("기술 성숙도 · 검증기와 복구", "틀린 것·늦은 것은 막고, 장애는 스스로 돌아온다")
    s.img(F / "paper/fig4_validator_and_recovery.png", 0.7, 1.8, w=12.0)
    s.card(0.7, 5.95, 3.9, 1.0, "(a) 검증기 거부", "주입 3종 전부 거부 · 실제 AI 잡음 58/230 거부 · 만료 사용 0", num="01", bsize=10)
    s.card(4.75, 5.95, 3.9, 1.0, "(b) HAL 폴트 1 s", "아크 OFF 즉시 → 0.4 s 감속 → HOLD → 1.56 s 뒤 자동 복귀", num="02", bsize=10)
    s.card(8.8, 5.95, 3.9, 1.0, "(c) 감지·복귀", "접촉 1 ms · 단절 11 ms · 폴트 40 ms, 비정상 구간 주기 미스 0", num="03", bsize=10)
    # 접촉력 조정 (11단계)
    s = S(); s.header("현장 적용 가능성 · 센서 기반 접촉력·이동속도 조정", "돌출부 접촉 → 감속·회피 → 복귀 (규칙 감시기)")
    s.img(F / "s11_contact_ep1.png", 0.7, 1.8, h=5.1)
    s.card(7.4, 1.8, 5.3, 1.2, "센서 → HAL 상태", "토치 팁 접촉 센서 → tool_force [N] (실 로봇: F/T 센서·전류 추정치 같은 자리)", num="01", bsize=10.5)
    s.card(7.4, 3.1, 5.3, 1.2, "규칙", "> 2 N → SLOW 0.5×   > 30 N → STOP\n접촉 중 스탠드오프 +12 mm 상승(200 ms 램프), 해제 1 s 뒤 복귀", num="02", bsize=10.5)
    s.card(7.4, 4.4, 5.3, 1.2, "결과 (9 mm 돌출부)", "접촉 최대 53 N · SLOW 3.08 s · STOP 0.04 s 뒤 즉시 복귀\n스탠드오프 +25.8 mm 로 넘어가 완주, 오차 mean 0.40 mm", num="03", bsize=10.5)
    s.rect(7.4, 5.75, 5.3, 1.15, fill=DARK, radius=0.06); s.text(7.5, 5.75, 5.1, 1.15, "감지 1 ms · 정지 결정은 규칙만 · 복귀 0.09 s", 13, bold=True, color=WHITE, align="c", valign="m")
    # 공정 상태 추론 (11단계)
    s = S(); s.header("현장 적용 가능성 · 공정 상태 추론 기반 파라미터 변경", "속도에 맞춰 아크 출력 조정 — 입열 일정 유지 (PARAM)")
    s.img(F / "s11_process_gap_ep0.png", 0.7, 1.8, w=7.3)
    s.card(8.3, 1.8, 4.4, 1.35, "공정 상태 추론기 (규칙 대리 모델)", "20 Hz 로 제어기 계약(속도 배율)을 읽어 입열 지수 H = 아크출력 / 속도 유지\n실제 추론 모델(용융풀 영상)이 같은 메시지 자리에 들어감", num="01", bsize=10)
    s.card(8.3, 3.3, 4.4, 1.35, "결과", "3 s 공급 중단 페이싱 구간: 속도 0.20× → 아크 100 → 30 %\n입열 지수 평균 1.14, 최대 1.74 (제어 없으면 5.0)", num="02", bsize=10)
    s.card(8.3, 4.8, 4.4, 1.35, "결함 위험 → EVENT", "속도 0.15 미만 2 s 지속 시 DEFECT 이벤트로 정지 사다리 진입\nPARAM 은 감시기 한계 안에서만 반영(상한)", num="03", bsize=10)
    s.text(0.7, 5.7, 7.3, 1.0, "▲ 위: 속도 배율과 아크 출력, 아래: 입열 지수 — 페이싱으로 느려진 구간에서 입열이 치솟지 않는다", 10.5, color="4A5568")
    # 10 범용성
    s = S(); s.header("현장 적용 가능성 · 범용성", "로봇이 바뀌어도 상위 제어는 그대로 — HAL 뒤에서만 교체")
    s.img(A / "robots4.gif", 0.7, 1.75, h=5.1)
    s.card(7.0, 1.75, 5.7, 1.3, "4 로봇 · 2 백엔드, 핵심 코드 변경 0 줄", "UR5e 6축 · Panda 7축 · KUKA iiwa14 7축 · UFactory xArm7 7축\n직접 공유메모리 + ros2_control 플러그인 경로", num="01", bsize=11)
    s.card(7.0, 3.2, 5.7, 1.3, "같은 눈 · 같은 제어기 · 같은 교시 경로", "고정구 오차 1.47 mm → 눈 보정 0.30 ~ 0.32 mm (네 로봇 모두)\n루프 실행 max 16 ~ 22 μs", num="02", bsize=11)
    s.card(7.0, 4.65, 5.7, 1.3, "추가에 든 것", "로봇 모델 XML + 장면 생성기 (IK 홈 자세)\n실 로봇: HAL 함수 5개 + 정지 3단계 매핑(STO/SS1/SS2)", num="03", bsize=11)
    s.text(7.0, 6.1, 5.7, 0.6, "▲ 4분할 영상: 각 로봇이 같은 용접선을 완주 (비드 진행률 100 %)", 10, color=GRAY)
    # ros2_control 경로 (8단계)
    s = S(); s.header("기업 도입 의향 · 기존 ROS 2 자산 재사용", "ros2_control 플러그인으로도 같은 제어기가 돈다")
    s.img(F / "s8_hal_paths_ep1.png", 0.7, 1.8, w=6.6)
    s.card(7.6, 1.8, 5.1, 1.35, "HAL 2경로", "직접 공유메모리 락스텝  /  ros2_control ResourceManager → SystemInterface 플러그인\nURDF <limit> 이 HAL 공통 한계값으로", num="01", bsize=10.5)
    s.card(7.6, 3.3, 5.1, 1.35, "같은 결과", "용접 오차 직접 0.29 / ros2 경로 0.31 mm\n루프 실행 p99 11 → 16 μs, HAL read max 1.6 → 39.5 μs (모두 기준 안)", num="02", bsize=10.5)
    s.card(7.6, 4.8, 5.1, 1.35, "도입 비용", "현장 로봇의 기존 ros2_control 드라이버를 그대로 HAL 로 사용\n실 로봇 연결 = 플러그인 1개 + 정지 3단계 매핑", num="03", bsize=10.5)
    s.text(0.7, 5.9, 6.6, 1.0, "▲ 같은 UR5e 용접 시연 ep1 을 두 HAL 경로로 실행 — mock_components/GenericSystem 호환성도 확인", 10.5, color="4A5568")
    # 11 검증 환경 + A1/A2
    s = S(); s.header("기술 성숙도 · 검증 ① 제어 주기와 지터", "환경값 고정 후 측정: 제어 주기 1 ms · 지터 ±100 μs")
    env = [("커널", "Ubuntu 24.04 · 6.8.1-realtime (PREEMPT_RT)"), ("코어 격리", "isolcpus CCX 4-7, 20-23 · nohz_full · rcu_nocbs · irqaffinity 제외"), ("제어 루프", "CPU 4 고정 · SCHED_FIFO 99 · mlockall · cpu_dma_latency 0"), ("governor", "performance (전 코어)"), ("시뮬레이터", "MuJoCo 락스텝, 별도 비실시간 프로세스 (CPU 12)"), ("AI·로컬", "GPU 추론 / CPU 8-11, 14-15 — 격리 코어 밖"), ("시계", "모든 지표는 제어기 PC CLOCK_MONOTONIC 으로 측정")]
    s.rect(0.7, 1.95, 5.3, 4.9, fill=WHITE, radius=0.08)
    for i, (k, v) in enumerate(env):
        s.text(0.85, 2.05 + i * 0.68, 1.3, 0.6, k, 11, bold=True, color=PILL, valign="m"); s.text(2.1, 2.05 + i * 0.68, 3.8, 0.6, v, 10.5, color="4A5568", valign="m")
    s.img(F / "paper/fig3_jitter_under_load.png", 6.2, 1.95, w=6.5)
    s.rect(6.2, 4.45, 3.15, 1.1, fill=DARK, radius=0.06); s.text(6.2, 4.45, 3.15, 1.1, "주기 미스  0 / 532,000 틱\n12개 실행 · 장애 주입 포함", 13, bold=True, color=WHITE, align="c", valign="m")
    s.rect(9.55, 4.45, 3.15, 1.1, fill=DARK, radius=0.06); s.text(9.55, 4.45, 3.15, 1.1, "깨어남 지연 max 17 μs\nGPU 추론 중 13 μs · 부하 중 96 μs", 13, bold=True, color=WHITE, align="c", valign="m")
    s.rect(6.2, 5.7, 6.5, 1.15, fill=WHITE, radius=0.06); s.text(6.35, 5.7, 6.3, 1.15, "환경 설정의 효과 (cyclictest 60 s): 일반 커널·격리 없음 max 592 μs(유휴) / 1,325 μs(부하) → RT 커널 + CCX 격리 76 / 20 μs\n위 그래프는 실제 1 kHz 제어 루프에서 측정 — 5조건 모두 100 μs 초과 0회", 10.5, color="4A5568", valign="m")
    # 12 다른 검증
    s = S(); s.header("기술 성숙도 · 검증 ② AI 지연과 부하", "AI 추론시간 · 반영 지연 · 부하 유무 성능")
    s.img(A / "e2e_decomp.png", 0.7, 1.85, w=6.1); s.text(0.7, 4.0, 6.1, 0.4, "▲ 실제 AI 모델(ACT급, GPU): 캡처 → 반영 평균 10.3 ms, 추론 주기 100 ms", 10, color=GRAY)
    s.img(A / "ai_load.png", 7.0, 1.85, w=5.7); s.text(7.0, 4.35, 5.7, 0.4, "▲ AI 가 돌아도 제어 루프는 그대로: 5조건 주기 미스 0", 10, color=GRAY)
    s.card(0.7, 4.7, 3.9, 2.2, "추론시간 (A3)", "avg 6.5 ms · max 7.0 ms (GPU)\n추론 주기 avg 100.0 · max 106.9 ms", num="01", bsize=11.5)
    s.card(4.75, 4.7, 3.9, 2.2, "제어 반영 지연 (A5·A6)", "발행 → 첫 반영 0.49 ms\n캡처 → 반영 avg 10.3 / p99 15.2 / max 20.7 ms", num="02", bsize=11.5)
    s.card(8.8, 4.7, 3.9, 2.2, "부하 비교 (A7)", "AI 없음 12 μs → GPU 추론 13 μs → GPU+CPU 부하 96 μs\n모두 기준 안, 주기 미스 0", num="03", bsize=11.5)
    # 조건별 동작 시각화 (A8)
    s = S(); s.header("기술 성숙도 · 정상·지연·단절 조건별 동작", "조건만 바꿔도 모드 전이는 규칙대로, 급격한 동작 없음")
    s.img(VF / "favorable/A8_conditions_overview.png", 0.7, 1.8, h=5.1)
    s.card(7.3, 1.8, 5.4, 1.0, "정상 · 지연 200 ms", "모드 NORMAL 유지, 정지 0, 이탈도 ≤ 0.4 mrad", num="01", bsize=10.5)
    s.card(7.3, 2.95, 5.4, 1.0, "이상값 주입 3종", "거부만 되고 동작 변화 없음, 19 s AI ESTOP 이벤트는 의도된 정지 → 복귀", num="02", bsize=10.5)
    s.card(7.3, 4.1, 5.4, 1.0, "누락 (dropout 1 s 반복)", "페이싱 → 1.1 s 정지 → 복귀, 완주", num="03", bsize=10.5)
    s.card(7.3, 5.25, 5.4, 1.0, "통신 단절 6 s", "페이싱 → LOCAL 4.1 s → 복귀 접합, 정지 0, 완주", num="04", bsize=10.5)
    s.text(7.3, 6.4, 5.4, 0.5, "모든 조건 1 ms 주기 미스 0 (용접 구간)", 11, bold=True, color=PILL)
    # 안전 동작 (B2)
    s = S(); s.header("기술 성숙도 · 안전 동작 여유", "추종 오차는 한계의 1/9, 깨어남 지연은 기준의 1/6")
    s.img(F / "paper/fig6_safety_margins.png", 0.7, 1.8, w=12.0)
    s.rect(0.7, 6.0, 12.0, 0.9, fill=DARK, radius=0.06); s.text(0.8, 6.0, 11.8, 0.9, "8조건 276,000 틱: 추종 오차 max ≤ 10.6 mrad (한계 100) · 깨어남 지연 max ≤ 16 μs (기준 100) · 주기 미스 합계 0", 13, bold=True, color=WHITE, align="c", valign="m")
    # 13 절제 실험
    s = S(); s.header("기술 성숙도 · 검증 ③ 절제 실험", "생성 모델이라서 버티는가? — 로컬 블록만 바꿔 같은 사다리에서 비교")
    s.img(A / "ablation.png", 0.7, 1.8, w=7.9)
    s.card(8.9, 1.8, 3.8, 1.5, "같은 조건", "입력(관절 이력 300 ms) · 출력(1 s 청크) · 크기 · 증강 동일\n청크 51점 · 100 ms 재접합 · 두 레인 병렬 측정", num="01", bsize=10.5)
    s.card(8.9, 3.45, 3.8, 1.5, "결과", "오프라인 오차는 flow matching 이 낫지만(1.9 vs 3.3 mrad),\n폐루프 10 s 중단은 회귀 MLP 0.59 mm vs FM 17.2 mm", num="02", bsize=10.5)
    s.card(8.9, 5.1, 3.8, 1.5, "원인과 보완", "FM 은 손목 회전·높이로 드리프트 → 복귀 접합 과도 응답\n점프 비례 블렌딩으로 17 → 2.3 mm, 복귀 증강은 MLP 만 개선", num="03", bsize=10.5)
    s.rect(0.7, 5.35, 7.9, 1.25, fill=DARK, radius=0.06); s.text(0.8, 5.35, 7.7, 1.25, "킥은 로컬 모델의 종류가 아니라 진행도 접합과 공백 사다리다\n로컬 블록은 교체 가능한 부품 — 현재 기본값은 복귀 증강 회귀 MLP", 13, bold=True, color=WHITE, align="c", valign="m")
    # 실제 AI 모델 연결 (10단계) — 한계 포함
    s = S(); s.header("기술 성숙도 · 실제 AI 모델 연결", "플랫폼 통합은 검증, 모델의 폐루프 안정성은 과제")
    s.img(F / "s10_ai_ep0_timeline.png", 0.7, 1.8, h=5.1)
    s.card(6.4, 1.8, 6.3, 1.2, "모델", "경량 ACT 6.4M: 카메라 2장 + 관절 300 ms 이력 → 1 s 관절 청크\nGT 112 에피소드 + 복귀 증강 69k 프레임, GPU 추론 6.4 ms", num="01", bsize=10.5)
    s.card(6.4, 3.1, 6.3, 1.2, "플랫폼 통합: 성공", "청크 수락 237/277 (잡음 40건 거부), 추론 중 깨어남 max 11 μs, 실행 p99 7 μs\n공급자 프로토콜·검증·접합·E2E 측정 모두 실제 모델로 확인", num="02", bsize=10.5)
    s.card(6.4, 4.4, 6.3, 1.2, "모델: 폐루프 발산", "손목 회전이 카메라와 함께 도는 자기 피드백 → 2~4 s 뒤 용접선 이탈\n검증기 거부·감시기 정지가 작동해 '급격한 동작' 은 없음", num="03", bsize=10.5)
    s.rect(6.4, 5.75, 6.3, 1.15, fill=DARK, radius=0.06); s.text(6.5, 5.75, 6.1, 1.15, "AI 가 틀려도 플랫폼이 막는다 — 다음: 툴 공간 청크 출력, 폐루프 데이터(DAgger)", 12.5, bold=True, color=WHITE, align="c", valign="m")
    # 14 시뮬레이션 영상
    s = S(); s.header("현장 적용 가능성 · 실제 구동 환경 시뮬레이션", "같은 6 s AI 단절 — 좌: 일반 추론 재생 / 우: PACE")
    s.img(A / "compare_full.gif", 0.7, 1.8, w=W - 1.4, h=4.95)
    s.text(0.7, 6.85, W - 1.4, 0.4, "좌: 정지 → 비드 33 % 에서 용접 불량  /  우: 완주 100 %   (MuJoCo 락스텝 1 kHz, 실측 로그 렌더)", 10, color=GRAY, align="c")
    # 15 마무리
    s = S(); s.header("마무리", "AI 는 늦어도 되고, 로봇은 멈추지 않는다", center=True)
    items = [("문제의 정합성", "AI 결과의 시점 불일치를 문제로 정의하고\n실측(정지·불량)으로 보인 뒤 해결"), ("기술 성숙도", "1 ms 주기 미스 0 · 지터 max 17 μs\n6 s 단절 완주 · 12개 지표 전수 검증"), ("현장 적용 가능성", "4 로봇 · ros2_control · 규칙 기반 정지\n실 로봇은 HAL 5개 함수만 구현"), ("사업화·실증 연계", "RTOS 상위 제어 미들웨어로 독립 상품화\nAI 모델은 교체 가능 부품"), ("기업 도입 의향", "AI 지연·단절에도 용접 불량 0 (시뮬)\n기존 ros2_control 자산 재사용")]
    cw = (W - 1.4 - 0.2 * 4) / 5; x = 0.7
    for i, (t, d) in enumerate(items):
        s.rect(x, 2.4, cw, 2.9, fill=WHITE, radius=0.08); s.circle(x + cw / 2 - 0.3, 2.6, 0.6, f"0{i+1}", size=14); s.text(x + 0.1, 3.35, cw - 0.2, 0.5, t, 13, bold=True, align="c"); s.text(x + 0.12, 3.9, cw - 0.24, 1.3, d, 10, color="4A5568", align="c"); x += cw + 0.2
    s.rect(0.7, 5.6, W - 1.4, 1.1, fill=DARK, radius=0.06); s.text(0.7, 5.6, W - 1.4, 1.1, "진행도 기반 접합 + 공백 사다리 + 규칙 기반 정지\n= 어떤 AI 모델이든, 어떤 로봇이든, 1 kHz 제어기는 흔들리지 않는다", 15, bold=True, color=WHITE, align="c", valign="m")
    prs.save(OUT / "PACE_발표.pptx"); print("saved", OUT / "PACE_발표.pptx", len(prs.slides.__iter__.__self__._sldIdLst))


def preview(scale=100):
    """PIL 로 같은 레이아웃을 그려 겹침·넘침 점검 (글꼴·줄바꿈은 근사)."""
    def font(size, bold):
        return ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", max(8, int(size * scale / 72 * 1.0)))
    def wrap(dr, text, fnt, maxw):
        out = []
        for line in text.split("\n"):
            cur = ""
            for ch in line:
                if dr.textlength(cur + ch, font=fnt) > maxw and cur: out.append(cur); cur = ch
                else: cur += ch
            out.append(cur)
        return out
    for i, ops in enumerate(OPS, 1):
        im = Image.new("RGB", (int(W * scale), int(H * scale)), "white"); dr = ImageDraw.Draw(im)
        for yy in range(im.height): dr.line([(0, yy), (im.width, yy)], fill=(255 - int(48 * yy / im.height), 255 - int(27 * yy / im.height), 255 - int(8 * yy / im.height)))
        for op in ops:
            k = op[0]
            if k == "rect":
                _, x, y, w, h, fill, line, r = op; box = [x * scale, y * scale, (x + w) * scale, (y + h) * scale]
                dr.rounded_rectangle(box, radius=r * scale, fill=("#" + fill) if fill else None, outline=("#" + line) if line else None, width=2)
            elif k == "circ":
                _, x, y, d, fill = op; dr.ellipse([x * scale, y * scale, (x + d) * scale, (y + d) * scale], fill="#" + fill)
            elif k == "img":
                _, p, x, y, w, h = op; pic = Image.open(p).convert("RGB").resize((max(1, int(w * scale)), max(1, int(h * scale)))); im.paste(pic, (int(x * scale), int(y * scale)))
            elif k == "arrow":
                _, x1, y1, x2, y2, c = op; dr.line([x1 * scale, y1 * scale, x2 * scale, y2 * scale], fill="#" + c, width=3)
            elif k == "text":
                _, x, y, w, h, s, size, bold, color, align, valign = op; fnt = font(size, bold); lines = wrap(dr, s, fnt, (w - 0.1) * scale); lh = fnt.size * 1.25; th = lh * len(lines)
                ty = y * scale + 0.03 * scale + ({"t": 0, "m": (h * scale - th) / 2, "b": h * scale - th}[valign])
                for ln in lines:
                    tw = dr.textlength(ln, font=fnt); tx = x * scale + 0.05 * scale + ({"l": 0, "c": (w * scale - 0.1 * scale - tw) / 2, "r": w * scale - 0.1 * scale - tw}[align])
                    dr.text((tx, ty), ln, font=fnt, fill="#" + color); ty += lh
        im.save(PV / f"s{i:02d}.png")
    print("preview", len(OPS))


if __name__ == "__main__":
    build(); preview()
