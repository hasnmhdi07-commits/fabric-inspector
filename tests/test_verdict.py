"""Checks of the three-state verdict (spec v2, section 4) and that Python and JavaScript agree.
Run from C:\\thesis:  venv\\Scripts\\python.exe tests\\test_verdict.py
"""
import json, subprocess, sys, tempfile
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(r"C:\thesis"); sys.path.insert(0, str(ROOT))
from src.app.engine import Analyzer, Settings, report_to_text
from src.app.report_html import report_html
from src.app.verdict import make_verdict, photo_problem, photo_metrics
from src.knowledge.kb import assess

NODE = r"C:\Program Files\nodejs\node.exe"
passed = 0
def check(cond, msg):
    global passed
    assert cond, "FAILED: " + msg
    passed += 1
    print("PASS ", msg)

# ---------- 1. verdict rules
v = make_verdict([])
check(v["state"] == "none" and v["title"] == "No defects detected" and "check the fabric visually" in v["detail"],
      "nothing found -> 'No defects detected' + visual-check reminder")
hole = assess("hole_tear", box_wh_px=(40, 40), image_wh_px=(1280, 960), px_per_mm=2.0, confidence=0.9); hole["box"] = [0, 0, 40, 40]   # 20 mm -> 2 points
stain = assess("stain", box_wh_px=(300, 40), image_wh_px=(1280, 960), px_per_mm=2.0, confidence=0.8); stain["box"] = [0, 0, 300, 40]
v = make_verdict([hole, stain])
check(v["state"] == "defects" and v["title"] == "2 defects · 4 points" and v["severity"] == "major", f"with scale: '{v['title']}', {v['severity']}")
h2 = assess("hole_tear", box_wh_px=(60, 40), image_wh_px=(1280, 960), confidence=0.9); h2["box"] = [0, 0, 60, 40]
v = make_verdict([h2])
check(v["title"] == "1 defect" and v["points"] is None and "image scale" in v["detail"], "no scale: '1 defect', asks for the image scale")
shade_ok = assess("shade_variation", delta_e=0.5); shade_bad = assess("shade_variation", delta_e=2.5)
check(make_verdict([shade_ok])["state"] == "none", "shade within tolerance alone -> still 'No defects detected'")
v = make_verdict([shade_bad])
check(v["state"] == "defects" and v["title"] == "Shade out of tolerance", f"shade fail only: '{v['title']}'")
v = make_verdict([h2, shade_bad, assess("skewing", skew_pct=7.0)])
check(v["title"] == "1 defect · shade out of tolerance · skew over limit" and v["severity"] == "critical", f"mixed: '{v['title']}'")
v = make_verdict([], {"code": "too_dark", "title": "Photo too dark to analyse", "fix": "Retake it in even daylight, straight from above."})
check(v["state"] == "cannot" and v["severity"] is None, "problem -> 'cannot' state")

# ---------- 2. photo checks
ex = {p.stem: cv2.imread(str(p)) for p in (ROOT / "web_static" / "examples").glob("*.jpg")}
base = ex["hole_example"]
variants = {
    "good": base, "stain": ex["stain_example"], "skew": ex["skew_example"],
    "dark": (base * 0.1).astype(np.uint8),
    "bright": np.clip(base.astype(np.float32) * 0.2 + 235, 0, 255).astype(np.uint8),
    "blurred": cv2.GaussianBlur(base, (0, 0), 12),
    "small": base[:50, :50],
    "plain": np.full((400, 400, 3), 128, np.uint8),
}
expect = {"good": None, "stain": None, "skew": None, "dark": "too_dark", "bright": "too_bright", "blurred": "blurred",
          "small": "too_small", "plain": "blurred"}
for k, im in variants.items():
    p = photo_problem(im)
    check((p or {}).get("code") == expect[k], f"photo check '{k}': {(p or {}).get('code')} (mean {photo_metrics(im)[0]:.0f}, sharpness {photo_metrics(im)[1]:.1f})")

man = sorted((ROOT / "data" / "merged_v3" / "images" / "test").glob("*.jpg"))
if man:
    rej = {}
    for f in man:
        p = photo_problem(cv2.imread(str(f)))
        if p: rej[p["code"]] = rej.get(p["code"], 0) + 1
    n_rej = sum(rej.values())
    check(n_rej <= 0.02 * len(man), f"real test photos wrongly rejected: {n_rej} of {len(man)} {rej or ''}")

# ---------- 3. engine + report wording
an = Analyzer()
check(an.model_path.name == "best.onnx", "engine default model is the ONNX model (same as browser and server)")
rep = an.analyse(variants["dark"], Settings())
txt, htm = report_to_text(rep), report_html(rep)
check(rep.verdict["state"] == "cannot" and not rep.items and "too dark" in txt and "too dark" in htm, "dark photo -> cannot analyse, with the fix")
rep = an.analyse(variants["skew"], Settings())
txt, htm = report_to_text(rep), report_html(rep)
check(rep.verdict["state"] == "none" and rep.worst is None, "photo without local defects -> 'none' state")
check("acceptable" not in txt.lower() and "acceptable" not in htm.lower() and "No defects detected" in htm, "report never says 'acceptable'")
rep = an.analyse(variants["good"], Settings(do_shade=True, do_skew=True))
txt, htm = report_to_text(rep), report_html(rep)
check(rep.verdict["state"] == "defects" and rep.verdict["n_defects"] == 3, f"hole example: '{rep.verdict['title']}'")
check("acceptable" not in txt.lower() and "acceptable" not in htm.lower(), "report with passing measurements never says 'acceptable'")

# ---------- 4. Python and JavaScript give the same verdict
tmp = Path(tempfile.mkdtemp())
for k, im in variants.items():
    cv2.imwrite(str(tmp / f"{k}.png"), im)
r = subprocess.run([NODE, str(ROOT / "server" / "spike.mjs")] + [str(tmp / f"{k}.png") for k in variants],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
assert r.returncode == 0, r.stderr[-800:]
js = json.loads((ROOT / "server" / "spike_result.json").read_text(encoding="utf-8"))
for k, im in variants.items():
    pv = an.analyse(im, Settings(do_shade=True, do_skew=True)).verdict
    check(js[f"{k}.png"]["verdict"] == pv, f"same verdict in Python and JavaScript for '{k}': {pv['title']}")

print(f"\n{passed} checks passed")
