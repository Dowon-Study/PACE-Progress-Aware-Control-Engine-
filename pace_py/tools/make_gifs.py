"""발표용 GIF: mp4 구간을 잘라 GIF 로 (ffmpeg 없이 cv2 + PIL). 사용: .venv/bin/python -m pace_py.tools.make_gifs"""
import cv2, numpy as np
from PIL import Image
from pathlib import Path
OUT = Path("docs/slides/assets"); OUT.mkdir(parents=True, exist_ok=True)

def clip(src, out, t0, t1, src_t0=2.0, fps_out=10, crop=None, scale=0.6, colors=128, speed=2.5):
    """speed: 재생 배속 (실시간 대비). 프레임을 건너뛰어 만들고 GIF 는 fps_out 으로 재생"""
    cap = cv2.VideoCapture(src); fps = cap.get(cv2.CAP_PROP_FPS); frames = []
    i0 = int((t0 - src_t0) * fps); i1 = int((t1 - src_t0) * fps); step = max(1, int(round(fps * speed / fps_out)))
    for i in range(i0, i1, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i); ok, f = cap.read()
        if not ok: break
        if crop: x0, y0, x1, y1 = crop; f = f[y0:y1, x0:x1]
        f = cv2.resize(f, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA); frames.append(Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)).quantize(colors=colors, method=Image.Quantize.MEDIANCUT))
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=int(1000 / fps_out), loop=0, optimize=True); print(out, len(frames), "frames", f"{speed}x", f"{Path(out).stat().st_size/1e6:.1f} MB")

if __name__ == "__main__":
    cmp_ = "docs/figures/compare_gap6.mp4"; W, H = 640, 570
    clip(cmp_, OUT / "fail_baseline.gif", 11.0, 20.0, crop=(0, 0, W, H), scale=0.75, speed=2.0)                # 2장: 일반 추론 지연 → 정지·불량
    clip(cmp_, OUT / "pace_1_no_ai.gif", 11.5, 14.6, crop=(W, 0, 2 * W, H), scale=0.75, speed=1.5)               # 5장: AI 답 없음 → 페이싱
    clip(cmp_, OUT / "pace_2_local.gif", 14.6, 18.6, crop=(W, 0, 2 * W, H), scale=0.75, speed=2.0)               # 6장: 로컬(MLP) 보조 궤적
    clip(cmp_, OUT / "pace_3_splice.gif", 18.4, 22.0, crop=(W, 0, 2 * W, H), scale=0.75, speed=1.5)              # 8장: AI 복귀 → 진행도 접합
    clip(cmp_, OUT / "compare_full.gif", 10.0, 28.5, scale=0.55, speed=3.0)                           # 13장: 나란히 전체
    clip("docs/figures/robots4_ep1.mp4", OUT / "robots4.gif", 4.0, 23.5, src_t0=2.5, scale=0.5, speed=3.0)  # 10장: 4 로봇
