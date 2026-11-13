"""Fabric Defect Inspector - web version (works in any browser: PC, Android, iPhone).

Same analysis engine as the Windows app (YOLO + CIELAB shade + bow/skew + rule-based knowledge base).
On a phone, "Upload" offers the camera, and the page can be installed to the home screen (PWA).
Local test:  venv\\Scripts\\python.exe web\\app.py   -> open http://127.0.0.1:7860
"""
import sys, tempfile, time
from pathlib import Path

# works both in the project (C:\thesis\web\app.py) and in the published Space (app.py at the root)
ROOT = Path(__file__).resolve().parent
if not (ROOT / "src").exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

import cv2
import gradio as gr
import numpy as np

from src.app.engine import Analyzer, Settings, report_to_text
from src.app.report_html import report_html

MAX_SIDE = 1600              # phone photos (12 MP) are reduced for speed; YOLO works at 640 px anyway
analyzer = Analyzer(ROOT / "models" / "best.pt")
EXAMPLES = sorted(str(p) for p in (ROOT / ("examples" if (ROOT / "examples").exists() else "web/examples")).glob("*.jpg"))


CHECKS = ["Local defects (AI)", "Shade (ΔE)", "Bow / skew"]


def analyse(img_rgb, checks, conf, px_mm, tol, skew_lim, bow_lim, weft):
    if img_rgb is None:
        raise gr.Error("Please upload a photo or take one with the camera first.")
    checks = checks or []
    do_def, do_shade, do_skew = (c in checks for c in CHECKS)
    if not (do_def or do_shade or do_skew):
        raise gr.Error("Tick at least one check.")
    bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    f = min(1.0, MAX_SIDE / max(bgr.shape[:2]))
    if f < 1:
        bgr = cv2.resize(bgr, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    s = Settings(conf=conf, px_per_mm=(px_mm or 0) * f, shade_tol=tol, skew_limit=skew_lim, bow_limit=bow_lim,
                 weft=weft, do_defects=do_def, do_shade=do_shade, do_skew=do_skew)
    t0 = time.perf_counter()
    rep = analyzer.analyse(bgr, s)
    dt = (time.perf_counter() - t0) * 1000
    gallery = [(cv2.cvtColor(v, cv2.COLOR_BGR2RGB), k) for k, v in rep.views.items()]
    html = report_html(rep, sec="var(--body-text-color-subdued)", mut="var(--body-text-color-subdued)")
    html += f"<p style='font-size:8pt;color:var(--body-text-color-subdued)'>Analysis time {dt:.0f} ms</p>"
    out = Path(tempfile.mkdtemp()) / f"fabric_report_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    out.write_text(report_to_text(rep), encoding="utf-8")
    return gallery, html, gr.File(value=str(out), visible=True)


ABOUT = """
### How it works
1. **AI detection (YOLO11)** finds local defects: *hole/tear, stain, slub/neps, broken pick/end*.
2. **Shade check** compares colours in CIELAB (ΔE CMC 2:1) and draws a heat map.
3. **Bow/skew check** measures the weft-line angle across the width (% bow, % skew).
4. A **rule-based knowledge base** (4-point system ASTM D5430, ASTM D3882) gives severity, likely causes,
   remedy and prevention.

**Photo tips:** fabric flat, camera straight above, even daylight, no shadows.
Shade and bow/skew results are only meaningful for such photos. Add a ruler and enter the
*image scale* for real 4-point scores.

*Thesis prototype - results are decision support, not a replacement for a trained inspector.*
"""

with gr.Blocks(title="Fabric Defect Inspector") as demo:
    gr.Markdown("# 🧵 Fabric Defect Inspector\nUpload or photograph fabric → defects, severity, causes and remedies.")
    with gr.Row():
        with gr.Column(scale=1, min_width=300):
            inp = gr.Image(sources=["upload", "webcam", "clipboard"], type="numpy", label="Fabric photo",
                           height=360)
            checks = gr.CheckboxGroup(CHECKS, value=CHECKS[:1], label="Checks",
                                      info="Shade and bow/skew: only for flat, evenly lit photos")
            with gr.Accordion("Settings", open=False):
                conf = gr.Slider(0.05, 0.9, value=0.23, step=0.01, label="Detection confidence",
                                 info="Lower = finds more defects but more false alarms")
                px_mm = gr.Number(0, label="Image scale (pixels per mm, 0 = unknown)",
                                  info="With a ruler in the photo: pixels between two cm marks ÷ 10")
                tol = gr.Slider(0.2, 5, value=1.0, step=0.1, label="Shade tolerance ΔE CMC(2:1)")
                skew_lim = gr.Slider(0.5, 10, value=3.0, step=0.5, label="Skew limit (%)")
                bow_lim = gr.Slider(0.5, 10, value=2.0, step=0.5, label="Bow limit (%)")
                weft = gr.Radio(["horizontal", "vertical"], value="horizontal", label="Weft direction in photo")
            btn = gr.Button("🔍 Analyse", variant="primary", size="lg")
            if EXAMPLES:
                gr.Examples(EXAMPLES, inputs=inp, label="Try an example")
        with gr.Column(scale=1, min_width=300):
            gal = gr.Gallery(label="Results (swipe / click to switch view)", columns=1, height=420,
                             object_fit="contain", preview=True)
            rep_html = gr.HTML()
            rep_file = gr.File(label="Download full report (.txt)", visible=False)
    with gr.Accordion("About this app", open=False):
        gr.Markdown(ABOUT)

    inputs = [inp, checks, conf, px_mm, tol, skew_lim, bow_lim, weft]
    btn.click(analyse, inputs, [gal, rep_html, rep_file], concurrency_limit=2)
    inp.upload(analyse, inputs, [gal, rep_html, rep_file], concurrency_limit=2)   # auto-analyse new photos

if __name__ == "__main__":
    demo.launch(pwa=True, theme=gr.themes.Soft())
