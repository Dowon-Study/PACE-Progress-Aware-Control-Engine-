"""진행 보고서 PDF: 설계서(docs/DESIGN.md) + 단계별 진행표(docs/STATUS.md) + 그림을 한 문서로 묶어 HTML → PDF(headless Chrome).
사용: python -m pace_py.tools.make_report --out docs/PACE_진행보고서.pdf"""
import argparse, base64, datetime, re, subprocess
from pathlib import Path
import markdown
ROOT = Path(__file__).resolve().parents[2]
FIGS = [  # (파일, 캡션)
    ("pace_01_progress_tracking.png", "그림 1. 진행도 기반 접합 개요 (아이디어 그림)"),
    ("pace_arch_validated.png", "그림 1b. 검증된 아키텍처 — 청록 실측 검증, 회색 구조/확장 (자체 AI 모델·감속 조언기는 제외)"),
    ("scene_cam_scene.png", "그림 2. 용접선 추종 시연 장면 (UR5e + 토치, 작업대 위 용접선)"),
    ("s7_eye_frames_ep1.png", "그림 3. 토치 카메라 영상과 작은 눈의 용접선 검출"),
    ("s7_ep1_lateral.png", "그림 4. 교시 경로만 vs 눈 보정 vs 눈 끊김 — 실제 용접선 대비 가로 오차"),
    ("s7_ep5_lateral.png", "그림 5. 원호 용접선, 고정구 오차 −9~+6mm 보정"),
    ("s13_robots4_eye_ep1.png", "그림 6. UR5e · Panda · KUKA iiwa14 · UFactory xArm7 — 같은 제어기·같은 눈·같은 교시 경로"),
    ("s8_stop_fault_ur5e.png", "그림 7. 정지 사다리 — HAL 폴트 5초: 아크 OFF → 감속 → 유지 → 비상정지 체결"),
    ("s8_stop_fault_short_panda.png", "그림 8. 정지 사다리 — Panda, HAL 폴트 1초: 유지 후 복귀"),
    ("s13_stop_fault_xarm7.png", "그림 8b. 정지 사다리 — xArm7, HAL 폴트 5초: 네 로봇 동일 타임라인"),
    ("compare_gap6_t16s.png", "그림 8c. 같은 6초 AI 단절 — 좌: 일반 추론 재생(정지, 비드 32.6%) / 우: PACE(로컬 정책으로 계속, 완주). 영상 docs/figures/compare_gap6.mp4"),
    ("s9_gap_local_ep0.png", "그림 9. 공급 중단 길이 스윕 — 기준선 vs 로컬 연속 정책 (정지·LOCAL 재생·가로 오차)"),
    ("s9_local_long_gap6_timeline.png", "그림 10. 6초 중단 타임라인 — 페이싱 → LOCAL 4.1초 → AI 복귀 접합"),
    ("s9c_local_ablation_ep0.png", "그림 10b. 로컬 블록 절제 — 없음 / 규칙 외삽 / 회귀 MLP / flow matching (킥은 모델이 아니라 접합·사다리)"),
    ("s11_conditions_ep0.png", "그림 11. 조건별 시스템 동작 — 정상 / 지연 200ms / 통신 단절 6초"),
    ("s11_contact_ep1.png", "그림 12. 접촉력 기반 조정 — 돌출부 접촉 → 감속 + 스탠드오프 상승 → 복귀"),
    ("s11_process_gap_ep0.png", "그림 13. 공정 상태 추론(규칙) 기반 아크 출력 조정 — 입열 지수 유지"),
    ("s10_ai_ep0_timeline.png", "그림 14. 실제 AI 모델 폐루프 (발산 사례) — 검증기 거부와 감시기 정지가 작동"),
]
PROG_TABLE = """| # | 단계 | 상태 | 핵심 결과 |
|---|---|---|---|
| 0 | 환경 구성 (RT 커널, CCX 격리, ROS 2, MuJoCo, GPU) | ✅ 10-09 | cyclictest 지터 592/1325μs → 76/20μs |
| 1 | 메시지 규격 + 상태 구조체 | ✅ | PATH/PATH_S/CORRECTION/PARAM/EVENT/CONTRACT, 8272B 고정, Python 미러 |
| 2 | 락프리 공유메모리 | ✅ | SPSC 링 4개 + seqlock + 프레임 버퍼, 루프 안 락·할당 없음 |
| 3 | 1kHz 루프 + MuJoCo 락스텝 백엔드 | ✅ | 실제 루프 깨어남 max 유휴 16.7μs / 부하 41.8μs |
| 3b/3c | 용접 장면(UR5e+토치) + GT 데이터 생성기 | ✅ | 225 에피소드, 형상 6종, 7.9GiB, 추종 오차 0.1mm |
| 4 | 가짜 공급자 + 3단계 검증기 + 상태 감시기 | ✅ | 장애 주입 7종 전부 의도한 단계에서 거부 |
| 5 | 진행도 접합 + 비교 정책 3종 | ✅ | 시간 인덱스: 페이싱 불가·2.4× 튐 / 진행도: 0.5× 페이싱·0.26mm 복귀 |
| 6 | 페이싱 + 규칙 외삽 + 사다리 | ✅ | 정지 0회 한계 T: 유지 2s → 페이싱+외삽 4s |
| 7 | 작은 눈(고전 CV) + 기준 경로 + CORRECTION | ✅ 10-10 | 고정구 오차 1.47→0.29mm, 9mm→0.6mm, 눈 4s 끊김 정지 0회 |
| 8 | HAL 정식화 + 로봇 B·C·D + 정지 사다리 | ✅ 10-10 | UR5e/Panda/iiwa14/xArm7/ros2_control 0.29~0.32mm, 폴트→아크 OFF→감속→유지→ESTOP 네 로봇 동일 |
| 9 | 로컬 감독 블록 (flow matching 연속 정책) | ✅ 10-10 | T 4s → ≥10s (1mm 허용 안 6s), 조언기는 관절 이력만으로 무효 |
| 10 | 실제 AI 모델 (ACT급) | 🔶 10-10 | 연결·측정 완료(추론 6.4ms, 지터 불변), 모델 폐루프 발산으로 미달 |
| 11 | 측정·시각화·설계서 | ✅ 10-10 | 접촉력 조정, 공정 상태 파라미터, AI 부하 6조건, 조건별 그림, 설계서 |
| 12 | (예비) 다중 에피소드 평균, 실 로봇 HAL | ⬜ | – |"""

CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: 'Noto Sans CJK KR', 'Noto Sans CJK JP', sans-serif; font-size: 10.5pt; line-height: 1.5; color: #111; }
h1 { font-size: 20pt; border-bottom: 2px solid #333; padding-bottom: 4px; margin-top: 28px; page-break-before: always; }
h1.first { page-break-before: avoid; }
h2 { font-size: 14pt; margin-top: 22px; border-left: 4px solid #2a6; padding-left: 8px; }
h3 { font-size: 12pt; margin-top: 16px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 14px; font-size: 9.5pt; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #999; padding: 4px 6px; vertical-align: top; }
th { background: #eef3f0; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 9pt; background: #f3f3f3; padding: 0 3px; }
pre { background: #f6f6f6; border: 1px solid #ddd; padding: 8px; font-size: 8.5pt; white-space: pre-wrap; }
figure { margin: 14px 0; page-break-inside: avoid; text-align: center; }
figure img { max-width: 100%; max-height: 118mm; }
figcaption { font-size: 9pt; color: #444; margin-top: 4px; }
.cover { text-align: center; margin-top: 120px; }
.cover h1 { border: none; font-size: 26pt; page-break-before: avoid; }
.cover p { font-size: 12pt; color: #333; }
.meta { font-size: 9pt; color: #666; }
blockquote { color: #555; border-left: 3px solid #ccc; margin: 8px 0; padding-left: 10px; }
"""


def md(text): return markdown.markdown(text, extensions=["tables", "fenced_code"])


def fig(name, cap):
    p = ROOT / "docs/figures" / name
    if not p.exists(): return ""
    b = base64.b64encode(p.read_bytes()).decode(); ext = p.suffix[1:]
    return f'<figure><img src="data:image/{ext};base64,{b}"><figcaption>{cap}</figcaption></figure>'


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="docs/PACE_진행보고서.pdf"); a = ap.parse_args()
    design = (ROOT / "docs/DESIGN.md").read_text(encoding="utf-8"); status = (ROOT / "docs/STATUS.md").read_text(encoding="utf-8")
    design_body = design.split("\n---\n", 1)[1] if "\n---\n" in design else design           # 제목 블록 제거
    prog_table = PROG_TABLE
    lessons = "\n\n".join(re.findall(r"(## \d+단계에서 배운 것\n.*?)(?=\n## )", status, re.S))
    today = datetime.date.today().strftime("%Y-%m-%d")
    html = [f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>"]
    html.append(f"""<div class='cover'><h1>AI 추론·실시간 제어 통합형 RTOS 기반<br>로봇 상위제어 플랫폼 — 진행 보고서</h1>
<p>PAC 2026 · HD현대로보틱스 과제 4 · 팀 피지컬100</p><p>아이디어: 진행도 기반 접합 (PACE, Progress-Aware Control Engine)</p>
<p class='meta'>작성일 {today} · 범위: 환경 구성 ~ 12단계 계획 중 1~11단계 · 근거: docs/DESIGN.md, docs/STATUS.md, docs/benchmarks/README.md</p></div>""")
    html.append("<h1>1. 진행 요약</h1>")
    html.append(md("""12단계 구현 계획(docs/IDEA_FIXED.md 12절) 중 1~11단계를 수행했다. 1~9단계와 11단계는 완료, 10단계(실제 AI 모델)는 통합·측정은 완료했으나 모델이 폐루프에서 발산해 미달로 기록했다. 모든 결과는 PREEMPT_RT 커널 위의 실제 1kHz 제어 루프와 MuJoCo 락스텝 시뮬레이터에서 실측했고, C 테스트 8개·Python 테스트 3개가 통과한다.

### 단계별 진행표

""" + prog_table))
    html.append(fig(*FIGS[0])); html.append(fig(*FIGS[1])); html.append(fig(*FIGS[2]))
    html.append("<h1>2. 아키텍처 개념설계와 실측 결과</h1>")
    body = design_body.replace("## 0. 요약", "## 2.0 요약")
    for k in range(1, 11): body = body.replace(f"\n## {k}. ", f"\n## 2.{k} ")
    # 결과 절 뒤에 그림 삽입
    parts = re.split(r"(?=\n## 2\.6 )", body, 1)
    html.append(md(parts[0]))
    for f in FIGS[3:16]: html.append(fig(*f))
    if len(parts) > 1: html.append(md(parts[1]))
    html.append("<h1>3. 단계별로 배운 것 (설계를 바꾼 사실)</h1>"); html.append(md(lessons.replace("## ", "### ")))
    html.append("<h1>4. 결론</h1>")
    html.append(md("""- **한 문장:** AI가 느리든, 끊기든, 틀리든 로봇은 물리적으로 멈춰야 할 때만 멈춘다는 설계 목표를 실제 1kHz 루프로 증명했다. 핵심은 경로를 시간이 아니라 진행도로 이어 붙이는 것과 공백을 사다리로 다루는 것이다.
- **실시간:** 일반 커널 지터 592/1325μs → RT + 코어 격리 후 실제 루프 16.7/41.8μs. AI 추론이 GPU 에서 돌아도 루프 실행 p99 7μs 불변.
- **진행도 접합:** 시간 인덱스 재생은 중단 후 2.4배로 튀고 페이싱이 불가능하지만, 진행도 접합은 0.5배로 느려졌다가 0.26mm 로 복귀한다.
- **멈추지 않고 버티는 길이:** 유지 2초 → 페이싱+외삽 4초 → 로컬 연속 정책 10초 이상. 용접 허용 오차 1mm 안에서는 약 6초. 두 숫자를 구분해 보고한다.
- **비전 보정·HAL·안전 정지·센서·공정:** 고정구 오차 1.47→0.29mm, UR5e·Panda·iiwa14·xArm7·ros2_control 경로 모두 0.29~0.32mm, 폴트 시 아크 OFF→감속→유지→비상정지 동일 타임라인, 접촉 53N 감속·회피 후 완주, 페이싱 구간 입열 지수 1.7 이하 유지.
- **가장 중요한 해석:** 실제 AI 모델이 폐루프에서 발산했을 때 검증기가 잡음 청크를 거부하고 감시기가 정지시켰다. 플랫폼의 가치는 모델 품질과 독립적이다.
- **한계:** 실제 AI 모델의 폐루프 안정성, 에피소드 1~2개 중심의 수치, 관절 이력만으로는 무효인 감속 조언기, GPU+stress 깨어남 96μs 꼬리."""))
    html.append("</body></html>")
    out_html = ROOT / "docs" / "_report.html"; out_html.write_text("\n".join(html), encoding="utf-8")
    out_pdf = ROOT / a.out
    subprocess.run(["google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer", f"--print-to-pdf={out_pdf}", f"file://{out_html}"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    out_html.unlink(); print("saved", out_pdf, out_pdf.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
