"""Quick automatic checks of all non-YOLO modules. Run:  venv\\Scripts\\python.exe tests\\test_modules.py"""
import sys
import numpy as np
import cv2
from skimage.color import lab2rgb, deltaE_cmc

sys.path.insert(0, r"C:\thesis")
from src.knowledge.kb import load_kb, assess, four_point, points_per_100_sq_yd, format_report
from src.shade.delta_e import analyse_shade, grey_scale_grade

passed = 0
def check(cond, msg):
    global passed
    assert cond, "FAILED: " + msg
    passed += 1

# --- knowledge base structure ---
kb = load_kb()
for key in ["hole_tear", "stain", "slub_neps", "broken_pick_end", "shade_variation", "bowing", "skewing"]:
    e = kb["defects"][key]
    check(all(k in e for k in ("name", "causes", "remedy", "prevention", "severity")), f"{key} complete")
    check(len(e["causes"]) >= 3 and all("stage" in c and "cause" in c for c in e["causes"]), f"{key} causes")

# --- 4-point system boundaries (ASTM D5430) ---
check(four_point(76.2) == 1 and four_point(76.3) == 2, "3 inch boundary")
check(four_point(152.4) == 2 and four_point(228.6) == 3 and four_point(229) == 4, "6/9 inch boundaries")
check(four_point(25.4, True) == 2 and four_point(26, True) == 4, "hole 1 inch boundary")
check(abs(points_per_100_sq_yd(20, 100, 60) - 12.0) < 1e-9, "points per 100 sq yd formula")

# --- severity rules ---
check(assess("hole_tear", box_wh_px=(10, 10), image_wh_px=(1000, 1000))["severity"] in ("major", "critical"), "hole >= major")
check(assess("stain", box_wh_px=(100, 50), image_wh_px=(1000, 1000), px_per_mm=1)["points"] == 2, "stain 100 mm -> 2 pts")
check(assess("shade_variation", delta_e=0.8)["severity"] == "acceptable", "shade within tol")
check(assess("shade_variation", delta_e=3.5)["severity"] == "critical", "shade far off")
check(assess("skewing", skew_pct=4.0)["severity"] == "major", "skew 4% major")
check(assess("bowing", bow_pct=1.0)["severity"] == "acceptable", "bow 1% ok")
check(grey_scale_grade(0.1) == "5" and grey_scale_grade(1.7) == "4" and grey_scale_grade(20) == "1", "grey scale")

# --- white balance: a strong colour cast must not change the measured delta E much ---
def patch(lab, H=300, W=300):
    a = np.zeros((H, W, 3)); a[...] = lab
    a[..., 0] += 5 * np.cos(2 * np.pi * np.arange(H)[:, None] / 7)
    return (np.clip(lab2rgb(a), 0, 1) * 255).round().astype(np.uint8)
ref_lab, test_lab = np.array([50., 20., 15.]), np.array([50.5, 21.0, 14.0])
true = float(deltaE_cmc(ref_lab.reshape(1, 1, 3), test_lab.reshape(1, 1, 3), kL=2, kC=1)[0, 0])
white = np.full((300, 200, 3), 245, np.uint8)
rgb = np.hstack([patch(ref_lab), patch(test_lab), white])
lin = (rgb / 255.0) ** 2.2 * np.array([1.0, 0.85, 0.6])           # yellowish lamp: blue reduced
cast = cv2.cvtColor(((lin ** (1 / 2.2)) * 255).round().astype(np.uint8), cv2.COLOR_RGB2BGR)
clean = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
r_clean = analyse_shade(clean, ref_rect=(20, 20, 260, 260), test_rect=(320, 20, 260, 260))
r_cast = analyse_shade(cast, ref_rect=(20, 20, 260, 260), test_rect=(320, 20, 260, 260))
r_wb = analyse_shade(cast, ref_rect=(20, 20, 260, 260), test_rect=(320, 20, 260, 260), white_rect=(620, 20, 160, 260))
print(f"white balance: true dE {true:.2f} | clean {r_clean.value:.2f} | with colour cast {r_cast.value:.2f} "
      f"| cast + white-paper correction {r_wb.value:.2f}")
check(abs(r_wb.value - true) < abs(r_cast.value - true) or abs(r_wb.value - true) < 0.05, "white balance helps")

print(f"\nALL {passed} CHECKS PASSED\n")
print(format_report(assess("broken_pick_end", box_wh_px=(400, 12), image_wh_px=(1280, 960), px_per_mm=3.0, confidence=0.81)))
