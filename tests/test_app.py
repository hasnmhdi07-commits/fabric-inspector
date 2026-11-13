"""Automatic test of the app: engine on real test images + GUI rendered off-screen to PNG files.
Run from C:\\thesis:  venv\\Scripts\\python.exe tests\\test_app.py
"""
import os, sys, time
from pathlib import Path
import cv2
import pandas as pd

ROOT = Path(r"C:\thesis"); sys.path.insert(0, str(ROOT))
OUT = ROOT / "results" / "app_test"; OUT.mkdir(parents=True, exist_ok=True)

# ---------- 1. engine
from src.app.engine import Analyzer, Settings, report_to_text
an = Analyzer(ROOT / "models" / "best.pt")
man = pd.read_csv(ROOT / "data" / "merged_v2" / "manifest.csv")
test = man[(man.split == "test") & (man.n_boxes > 0)]
picks = [g.iloc[0] for _, g in test.groupby("source")][:6]
times = []
for i, r in enumerate(picks):
    img = cv2.imread(str(ROOT / "data" / "merged_v2" / "images" / "test" / r.file))
    t0 = time.perf_counter()
    rep = an.analyse(img, Settings(do_shade=True, do_skew=True))
    times.append((time.perf_counter() - t0) * 1000)
    cv2.imwrite(str(OUT / f"engine_{i}_{r.source[:20]}.jpg"), rep.views["Defects"])
    if i == 0:
        print(report_to_text(rep)[:1500], "\n...")
    print(f"[{r.source}] true boxes {r.n_boxes}, detected {sum('box' in x for x in rep.items)}, "
          f"overall {rep.worst}, {times[-1]:.0f} ms {rep.timings_ms}")
print(f"engine OK, mean time (defects+shade+skew, CPU) {sum(times) / len(times):.0f} ms")

# ---------- 2. GUI off-screen
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEventLoop, QTimer, Qt
from src.app.main import Panel, Bubble
app = QApplication(sys.argv)
panel = Panel()
panel.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)   # render with real fonts, but invisible

def wait(cond, timeout=60):
    t = time.time()
    while not cond() and time.time() - t < timeout:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50); time.sleep(0.02)
    assert cond(), "timeout"

wait(lambda: panel.analyzer is not None)
panel.cb_def.setChecked(True); panel.cb_shade.setChecked(True); panel.cb_skew.setChecked(True)
panel.btn_cfg.setChecked(False)
img = cv2.imread(str(ROOT / "data" / "merged_v2" / "images" / "test" / picks[0].file))
panel.show(); panel.set_image(img, picks[0].file)
wait(lambda: panel.report is not None)
app.processEvents()
panel.grab().save(str(OUT / "gui_panel.png"))
panel.btn_cfg.setChecked(True); app.processEvents()
panel.grab().save(str(OUT / "gui_panel_settings.png"))
panel.save_report()
b = Bubble(lambda: None); b.badge = "#d03b3b"
b.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen); b.show(); app.processEvents()
b.grab().save(str(OUT / "gui_bubble.png"))
print("GUI OK:", panel.lb_status.text())
print("views:", list(panel.report.views))
