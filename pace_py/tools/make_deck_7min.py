"""7분 발표용 11장 덱 (v2: 용어 정리 · 절제된 디자인). 사용: .venv/bin/python -m pace_py.tools.make_deck_7min
→ docs/slides/PACE_발표_7분.pptx, 미리보기 docs/slides/preview_7min/
용어: 진행도 기반 접합 / 단계적 대체 동작(감속→보조 궤적→등속 외삽→위치 유지→정지) / 보조 판단 계층 / 비전 보정 / AI 결과 검증기 / 안전 감시기"""
from pathlib import Path
import pace_py.tools.make_deck as D
from pace_py.tools.make_deck import S, prs, W, H, A, F, rgb
from pptx.util import Inches, Pt
D.PV = D.OUT / "preview_7min"; D.PV.mkdir(parents=True, exist_ok=True)
VF = D.ROOT / "validation/figures/verification"
NAVY, INK, BODY, MUTED, LINE, SOFT, ACC, ACC2, DARK, WHITE, RED, GREEN, ORANGE = "0F1E3D", "1B2B4B", "3A4658", "7B879A", "DCE4EE", "F4F8FC", "2457A6", "5B8DD9", "0F1E3D", "FFFFFF", "C62828", "2E7D32", "E07B1A"


class P(S):
    """절제된 배경(흰색 → 아주 연한 파랑), 하단 푸터, 상단 섹션 표시."""
    def __init__(self, section=None):
        super().__init__(); bg = self.s.background.fill; st = bg.gradient_stops; st[0].color.rgb = rgb("FFFFFF"); st[1].color.rgb = rgb("EAF2FA")
        self.text(0.7, H - 0.5, 6, 0.3, "피지컬100  ·  PACE  ·  PAC 2026 HD현대로보틱스 과제 4", 8.5, color=MUTED)
        if section: self.text(0.7, 0.42, 8, 0.3, section.upper(), 9.5, bold=True, color=ACC)

    def title(self, t, sub=None):
        self.text(0.62, 0.68, W - 1.3, 0.75, t, 26, bold=True, color=INK)
        if sub: self.text(0.7, 1.38, W - 1.4, 0.4, sub, 12, color=MUTED)
        self.rect(0.7, 1.85, 0.6, 0.04, fill=ACC)

    def tile(self, x, y, w, h, title, body, tsize=12.5, bsize=11, accent=False):
        self.rect(x, y, w, h, fill=WHITE if accent else SOFT, line=LINE if accent else None, radius=0.05)
        if accent: self.rect(x, y + 0.2, 0.05, h - 0.4, fill=ACC)
        self.text(x + 0.22, y + 0.13, w - 0.35, 0.42, title, tsize, bold=True, color=INK)
        if body: self.text(x + 0.22, y + 0.55, w - 0.35, h - 0.62, body, bsize, color=BODY, lsp=1.22)

    def kpi(self, x, y, w, h, big, small, color=ACC):
        self.rect(x, y, w, h, fill=WHITE, line=LINE, radius=0.05); self.rect(x, y, w, 0.05, fill=color)
        self.text(x, y + 0.12, w, h * 0.52, big, 24, bold=True, color=color, align="c", valign="m"); self.text(x + 0.1, y + h * 0.62, w - 0.2, h * 0.36, small, 10, color=BODY, align="c")

    def frame(self, path, x, y, w=None, h=None):
        box = self.img(path, x, y, w=w, h=h); self.rect(box[0] - 0.02, box[1] - 0.02, box[2] + 0.04, box[3] + 0.04, fill=None, line=LINE, radius=0.02); return box

    def note(self, x, y, w, t): self.text(x, y, w, 0.4, t, 9.5, color=MUTED)

    def banner(self, x, y, w, h, t, size=13):
        self.rect(x, y, w, h, fill=DARK, radius=0.05); self.text(x + 0.2, y, w - 0.4, h, t, size, bold=True, color=WHITE, align="c", valign="m")


def arch(sl, x, y, w, h, hi=None):
    rows = [("AI 추론 계층", "GPU · 비실시간 · 10 Hz", [("ai", "AI 모델 (교체 가능) → 1 s 액션 청크")]),
            ("보조 판단 계층", "일반 코어 · 30~100 Hz", [("eye", "비전 보정\n용접선 검출 → 보정값"), ("mlp", "보조 궤적 생성 (MLP)\n100 ms 마다 1 s"), ("proc", "공정 상태 판단\n→ 파라미터 · 이벤트")]),
            ("실시간 제어 계층", "격리 코어 · 1 kHz · 학습 모델 없음", [("val", "AI 결과 검증기\n범위·시간·유효성"), ("splice", "진행도 기반 접합\n실측 위치에서 잇기"), ("pace", "단계적 대체 동작\n감속→보조 궤적→정지"), ("mon", "안전 감시기\n정지 결정 (규칙)")]),
            ("하드웨어 추상화 계층 (HAL)", "함수 5개 · 정지 3단계 · 실행시간 계약", [("hal", "MuJoCo 락스텝 · ros2_control · UR5e · Panda · iiwa14 · xArm7")])]
    rh = (h - 0.25 * 3) / 4; yy = y
    for title, sub, blocks in rows:
        sl.rect(x, yy, w, rh, fill=SOFT, radius=0.05); sl.text(x + 0.15, yy + 0.05, 3.2, 0.3, title, 10.5, bold=True, color=INK); sl.text(x + 3.3, yy + 0.07, w - 3.4, 0.3, sub, 8.5, color=MUTED)
        bw = (w - 0.3 - 0.1 * (len(blocks) - 1)) / len(blocks); bx = x + 0.15
        for bk, bt in blocks:
            on = (hi == bk) if hi else True; sl.rect(bx, yy + 0.45, bw, rh - 0.55, fill=WHITE, line=(ACC if (hi and on) else LINE), radius=0.04, lw=1.8 if (hi and on) else 0.75)
            sl.text(bx + 0.05, yy + 0.47, bw - 0.1, rh - 0.59, bt, 9 if len(blocks) > 1 else 10, bold=bool(hi and on), color=INK if (not hi or on) else "A7B0BE", align="c", valign="m"); bx += bw + 0.1
        if title[:3] != "하드웨": sl.arrow(x + w / 2, yy + rh, x + w / 2, yy + rh + 0.25, color="A7B0BE", lw=1.2)
        yy += rh + 0.25


def build():
    # 1 표지
    s = P(); s.rect(0, 0, 0.35, H, fill=ACC)
    s.text(1.1, 1.5, 9, 0.35, "PAC 2026 · HD현대로보틱스 과제 4 · AI 추론·실시간 제어 통합형 RTOS 기반 로봇 상위제어 플랫폼", 10.5, bold=True, color=ACC)
    s.text(1.05, 2.0, 11.5, 1.8, "AI 가 늦어도 멈추지 않는\n실시간 로봇 제어 플랫폼", 38, bold=True, color=INK, lsp=1.15)
    s.text(1.1, 4.0, 11, 0.5, "진행도 기반 접합 (PACE, Progress-Aware Control Engine)", 15, color=BODY)
    s.rect(1.1, 4.75, 0.6, 0.04, fill=ACC); s.text(1.1, 4.9, 8, 0.4, "팀 피지컬100  ·  윤도원 · 권희재", 14, bold=True, color=INK)
    # 2 문제
    s = P("01 · 문제의 정합성"); s.title("AI 가 늦으면 로봇이 멈추고, 멈추면 용접은 불량이 된다", "AI 추론 시간은 흔들리고, 제어 주기는 1 ms 로 일정해야 한다 — 두 시간축이 어긋나는 순간이 문제다")
    s.frame(A / "fail_baseline.gif", 0.7, 2.1, w=5.0); s.note(0.7, 6.6, 5.6, "▲ 기존 방식(시간 순서 재생): AI 응답 6 s 지연 → 유지 → 정지 → 용접 불량 (실측 로그)")
    s.tile(6.6, 2.1, 6.1, 1.25, "추론 지연과 지터", "모델 연산량과 공유 자원 간섭으로 AI 결과의 도착 시각이 흔들린다 → 제어 명령 갱신이 늦고 불규칙해진다")
    s.tile(6.6, 3.5, 6.1, 1.25, "적용 시점의 불일치", "늦게 온 판단은 이미 지나간 구간의 것 → 지금 위치에 그대로 적용하면 틀린 보정이 된다")
    s.rect(6.6, 4.9, 6.1, 1.8, fill=DARK, radius=0.05); s.text(6.8, 4.98, 5.7, 0.35, "문제 정의", 10, bold=True, color="9FB6DC"); s.text(6.8, 5.35, 5.7, 1.3, "AI 결과의 관측·도착 시점이 제어 주기와 어긋나도, 1 ms 주기를 지키면서 작업을 멈추지 않고 올바르게 반영하는 상위 제어 구조", 13, color=WHITE, lsp=1.25)
    # 3 원인
    s = P("01 · 문제의 정합성 — 원인"); s.title("AI 결과가 준비되는 시점과 제어 명령을 갱신해야 하는 시점이 다르다")
    y0 = 2.45; s.text(0.7, y0 - 0.05, 2.2, 0.4, "제어 주기 1 ms", 11.5, bold=True, color=INK)
    for i in range(40): s.rect(3.0 + i * 0.24, y0, 0.12, 0.3, fill=ACC)
    s.text(0.7, y0 + 0.95, 2.2, 0.4, "AI 결과 도착", 11.5, bold=True, color=INK)
    for xi in (3.0, 4.15, 5.8, 6.3, 8.5, 9.2, 11.6): s.arrow(xi, y0 + 1.55, xi, y0 + 1.05, color=ORANGE, lw=2.5)
    s.text(3.0, y0 + 1.6, 9.6, 0.35, "도착 간격이 불규칙 → 어떤 주기는 새 결과 없이, 어떤 주기는 이미 지난 결과로 갱신된다", 10.5, color=MUTED)
    s.tile(0.7, 4.85, 5.9, 1.3, "① 모델 연산량 → 기본 지연", "AI 결과 생성 주기(수십~수백 ms) > 제어 주기(1 ms)")
    s.tile(6.8, 4.85, 5.9, 1.3, "② 공유 CPU·GPU 자원 간섭 → 도착 시각 흔들림", "같은 모델·같은 입력이라도 완료 시각이 달라진다")
    s.text(0.7, 6.35, W - 1.4, 0.5, "→ 제어기는 '늦고 · 끊기고 · 틀린' AI 결과를 전제로 설계해야 한다", 14, bold=True, color=ACC, align="c")
    # 4 아키텍처
    s = P("02 · 기술 성숙도 — 구조"); s.title("4계층 분리: AI 와 제어를 다른 코어에 두고, 락프리 공유메모리로만 잇는다")
    arch(s, 0.7, 2.1, 7.4, 4.7)
    s.tile(8.4, 2.1, 4.3, 1.42, "① 분리", "AI·보조 판단은 일반 코어, 제어는 격리 코어 1 kHz · 제어 루프 안에 락·메모리 할당·ROS 없음", accent=True)
    s.tile(8.4, 3.72, 4.3, 1.42, "② 진행도 기반 접합", "AI 액션 청크를 시간이 아니라 진행도로 잇는다 → 늦게 와도 현재 위치에서 자연스럽게 연결", accent=True)
    s.tile(8.4, 5.34, 4.3, 1.42, "③ 단계적 대체 동작", "AI 가 끊기면 감속 → 보조 궤적 → 등속 외삽 → 위치 유지 → 정지 · 정지는 규칙(안전 감시기)만 결정", accent=True)
    # 5 동작 흐름
    s = P("02 · 기술 성숙도 — 동작 흐름"); s.title("AI 가 끊겨도 용접은 이어진다 — 네 단계")
    cells = [("① AI 응답 끊김 → 감속", A / "pace_1_no_ai.gif", "남은 참조로 0.2배까지 감속, 멈추지 않는다"), ("② 보조 궤적 생성 (MLP)", A / "pace_2_local.gif", "관절 이력 300 ms → 1 s 궤적을 100 ms 마다"),
             ("③ 비전 보정", F / "s7_eye_frames_ep1.png", "토치 카메라로 용접선 검출 → 0.3 mm 안 유지"), ("④ AI 복귀 → 진행도 기반 접합", A / "pace_3_splice.gif", "현재 관절값을 청크에 투영해 가장 가까운 점부터 잇기")]
    cw, ch = 2.85, 2.0
    for i, (t, m, c) in enumerate(cells):
        x = 0.7 + i * (cw + 0.22); s.text(x, 2.05, cw, 0.4, t, 11.5, bold=True, color=INK); s.frame(m, x, 2.45, w=cw, h=ch); s.text(x, 4.6, cw, 0.9, c, 10.5, color=BODY, lsp=1.2)
        if i < 3: s.arrow(x + cw + 0.03, 3.45, x + cw + 0.19, 3.45, color="A7B0BE", lw=1.4)
    s.banner(0.7, 5.7, W - 1.4, 1.0, "시간으로 맞추면 점프, 진행도로 맞추면 연속  —  정지 결정은 규칙(안전 감시기)만, 학습 모델은 교체 가능한 부품", 12.5)
    # 6 핵심 결과
    s = P("02 · 기술 성숙도 — 핵심 결과"); s.title("같은 6 s AI 단절 — 기존 방식은 33 % 에서 정지, PACE 는 100 % 완주")
    s.frame(A / "compare_full.gif", 0.7, 2.1, w=8.6)
    s.kpi(9.6, 2.1, 3.1, 1.2, "33 % → 100 %", "용접 진행률 (정지 vs 완주)", ORANGE); s.kpi(9.6, 3.45, 3.1, 1.2, "≥ 10 s", "정지 없이 버티는 단절 길이 (기존 2 s)"); s.kpi(9.6, 4.8, 3.1, 1.2, "0.26 mm", "단절 복귀 뒤 용접선 오차 (기존 5.2 mm)")
    s.note(0.7, 6.3, 8.6, "MuJoCo 락스텝 1 kHz · 실측 로그 렌더 · 좌: 시간 순서 재생 + 유지 → 정지 / 우: 진행도 기반 접합 + 단계적 대체 동작")
    # 7 실시간 검증
    s = P("02 · 기술 성숙도 — 실시간 검증"); s.title("환경값을 고정하고 실제 1 kHz 루프에서 측정 — 주기 1 ms, 지터 ±100 μs")
    s.frame(F / "paper/fig3_jitter_under_load.png", 0.7, 2.1, w=7.6)
    s.kpi(8.6, 2.1, 4.1, 1.15, "0 / 532,000", "1 ms 주기 미스 (12개 실행, 장애 주입 포함)", GREEN); s.kpi(8.6, 3.4, 4.1, 1.15, "max 17 μs", "주기 지터 · GPU 추론 중 13 μs · 부하 중 96 μs"); s.kpi(8.6, 4.7, 4.1, 1.15, "10.3 ms", "카메라 캡처 → 제어 반영 (추론 6.5 + 반영 0.5)")
    s.text(0.7, 4.95, 7.6, 1.5, "환경: RT 커널 6.8.1 · CCX 단위 코어 격리(CPU 4-7, 20-23) · SCHED_FIFO 99 · mlockall · performance governor\n효과: 일반 커널 max 592 / 1,325 μs → 76 / 20 μs (cyclictest 60 s)\nAI 부하 5조건(없음 · CPU 부하 · CPU 추론 · GPU 추론 · GPU+부하) 모두 주기 미스 0, 100 μs 초과 0", 10.5, color=BODY, lsp=1.3)
    # 8 현장 기능
    s = P("03 · 현장 적용 가능성"); s.title("비전 보정 · 접촉력 대응 · 공정 파라미터 · 4 로봇 — 같은 제어기, 같은 메시지")
    panels = [("비전 AI 기반 목표 위치 보정", F / "s7_ep1_lateral.png", "고정구 오차 1.47 → 0.29 mm\n비전 보정 4 s 중단에도 0.30 mm"), ("접촉력 → 속도·높이 조정", F / "s11_contact_ep1.png", "53 N 접촉: 0.5× 감속 + 높이 +26 mm\n돌출부를 넘어 완주"),
              ("공정 상태 → 아크 출력 조정", F / "s11_process_gap_ep0.png", "속도 0.2× 구간 아크 100 → 30 %\n입열 지수 1.7 (제어 없으면 5.0)"), ("4 로봇 · 2 백엔드", F / "robots4_ep1_t20s.png", "4 로봇 모두 0.30~0.32 mm\n핵심 코드 변경 0 줄")]
    pw = (W - 1.4 - 0.25 * 3) / 4
    for i, (t, m, c) in enumerate(panels):
        x = 0.7 + i * (pw + 0.25); s.text(x, 2.05, pw, 0.4, t, 11, bold=True, color=INK); s.rect(x, 2.45, pw, 2.5, fill=WHITE, line=LINE, radius=0.04); s.img(m, x + 0.08, 2.53, w=pw - 0.16, h=2.34); s.text(x, 5.05, pw, 1.1, c, 10.5, color=BODY, lsp=1.2)
    s.note(0.7, 6.3, W - 1.4, "센서·공정 신호는 HAL 공통 상태와 파라미터·이벤트 메시지로 들어온다 → 실 로봇에서는 힘 센서·용융풀 판단 모델이 같은 자리에 들어간다")
    # 9 절제
    s = P("02 · 기술 성숙도 — 절제 실험"); s.title("생성 모델이라서 버티는가? — 핵심은 접합과 대체 동작이다")
    s.frame(A / "ablation.png", 0.7, 2.1, w=8.3)
    s.tile(9.3, 2.1, 3.4, 1.9, "같은 조건에서 보조 궤적 생성기만 교체", "없음 / 등속 외삽 / 회귀 MLP / flow matching · 입력·출력·크기·증강 동일", accent=True)
    s.tile(9.3, 4.2, 3.4, 1.9, "결과", "오프라인 오차는 FM 이 낫지만 폐루프 10 s 단절은 MLP 0.59 mm vs FM 17 mm → 기본값은 회귀 MLP", accent=True)
    s.note(0.7, 5.45, 8.3, "FM 의 17 mm 는 손목 회전 드리프트가 복귀 접합에서 드러나는 과도 응답 — 점프 비례 블렌딩으로 2.3 mm 까지 줄어든다 (플랫폼 쪽 보완)")
    # 10 사업화·도입
    s = P("04 · 사업화·실증 연계 — 05 · 기업 도입 의향"); s.title("AI 모델과 로봇을 바꿔 끼우는 상위 제어 미들웨어")
    s.tile(0.7, 2.1, 3.9, 2.3, "제품 형태", "RTOS 상위 제어 미들웨어\n· 메시지 규격 5종 (경로 · 보정 · 파라미터 · 이벤트 · 계약)\n· HAL 함수 5개 + 정지 3단계\n· 검증기 · 접합 · 대체 동작 · 안전 감시기", accent=True)
    s.tile(4.75, 2.1, 3.9, 2.3, "지식재산 후보", "· 진행도 기반 접합 (관절 투영 + 점프 비례 블렌딩)\n· 단계적 대체 동작 (감속 → 보조 궤적 → 외삽 → 정지)\n· 물리 기준 안전 감시기의 AI 결과 승인", accent=True)
    s.tile(8.8, 2.1, 3.9, 2.3, "도입 경로", "· 기존 ros2_control 드라이버를 그대로 HAL 로\n· AI 모델은 교체 가능 (ACT / VLA / 자체 모델)\n· 시뮬 → 실 로봇: 플러그인 1개 + 정지 단계 매핑", accent=True)
    s.rect(0.7, 4.65, W - 1.4, 1.6, fill=DARK, radius=0.05); s.text(0.9, 4.72, W - 1.8, 0.35, "기대 효과 (산출 논리)", 10, bold=True, color="9FB6DC")
    s.text(0.9, 5.08, W - 1.8, 1.15, "용접 정지 1회 = 비드 결함 + 재작업 + 라인 정지. PACE 는 AI 단절 6 s 에서도 정지 0회 · 완주 (시뮬 실측)\n→ 절감액 = (연간 AI 지연 기인 정지 횟수) × (재작업·라인 정지 비용) — 출제기업 현장 데이터로 산출. 투자는 소프트웨어와 격리 코어 구성뿐, 추가 하드웨어 없음", 12, color=WHITE, lsp=1.3)
    # 11 마무리
    s = P("마무리"); s.text(1, 1.9, W - 2, 0.9, "AI 는 늦어도 되고, 로봇은 멈추지 않는다", 32, bold=True, color=INK, align="c")
    s.kpi(0.7, 3.3, 2.9, 1.3, "0 / 532,000", "1 ms 주기 미스", GREEN); s.kpi(3.85, 3.3, 2.9, 1.3, "17 μs", "주기 지터 max"); s.kpi(7.0, 3.3, 2.9, 1.3, "100 %", "6 s 단절 완주 (기존 33 %)", ORANGE); s.kpi(10.15, 3.3, 2.9, 1.3, "0 줄", "로봇 4종 교체 시 핵심 코드 변경", "6A1B9A")
    s.text(1, 5.1, W - 2, 0.9, "진행도 기반 접합 + 단계적 대체 동작 + 규칙 기반 정지\n어떤 AI 모델이든, 어떤 로봇이든, 1 kHz 제어기는 흔들리지 않는다", 15, color=BODY, align="c", lsp=1.3)
    prs.save(D.OUT / "PACE_발표_7분.pptx"); print("saved", D.OUT / "PACE_발표_7분.pptx")


if __name__ == "__main__":
    build(); D.preview()
