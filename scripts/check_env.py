"""Environment self-test for the fabric defect thesis project.
Run:  C:\\thesis\\venv\\Scripts\\python.exe C:\\thesis\\scripts\\check_env.py
"""
import sys, platform, importlib, traceback

results = []

def check(name, fn):
    try:
        info = fn()
        results.append((name, "OK", info))
    except Exception as e:
        results.append((name, "FAIL", f"{type(e).__name__}: {e}"))
        traceback.print_exc()

def t_numpy():
    import numpy as np
    return np.__version__

def t_opencv():
    import cv2, numpy as np
    img = np.zeros((64, 64, 3), np.uint8); img[:] = (40, 120, 200)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    edges = cv2.Canny(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 10)
    return f"{cv2.__version__} (Lab + Canny + Hough OK)"

def t_skimage():
    import skimage, numpy as np
    from skimage.color import rgb2lab, deltaE_ciede2000
    a = rgb2lab(np.full((1, 1, 3), [0.5, 0.2, 0.2]))
    b = rgb2lab(np.full((1, 1, 3), [0.52, 0.2, 0.2]))
    dE = float(deltaE_ciede2000(a, b)[0, 0])
    return f"{skimage.__version__} (delta E2000 test = {dE:.2f})"

def t_pandas():
    import pandas as pd
    return pd.__version__

def t_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(); plt.plot([1, 2]); plt.close(fig)
    return matplotlib.__version__

def t_pillow():
    import PIL
    return PIL.__version__

def t_torch():
    import torch
    cuda = torch.cuda.is_available()
    gpu = torch.cuda.get_device_name(0) if cuda else "CPU-only build"
    return f"{torch.__version__} | CUDA available: {cuda} | {gpu}"

def t_ultralytics():
    import ultralytics, numpy as np
    from ultralytics import YOLO
    model = YOLO("yolo11n.pt")  # downloads ~5 MB pretrained weights on first run
    img = np.full((640, 640, 3), 128, np.uint8)
    r = model.predict(img, verbose=False)
    return f"{ultralytics.__version__} (yolo11n loaded, inference ran, {len(r[0].boxes)} boxes on blank image)"

def t_pyqt6():
    from PyQt6.QtWidgets import QApplication, QWidget
    from PyQt6.QtCore import Qt, QT_VERSION_STR
    app = QApplication.instance() or QApplication(sys.argv)
    w = QWidget(); w.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
    w.resize(60, 60)
    return f"Qt {QT_VERSION_STR} (always-on-top frameless widget created)"

def t_mss():
    import mss
    grabber = getattr(mss, "MSS", None) or mss.mss
    with grabber() as s:
        mon = s.monitors[1]
        shot = s.grab({"left": mon["left"], "top": mon["top"], "width": 100, "height": 100})
    return f"{mss.__version__ if hasattr(mss, '__version__') else ''} (screen grab {shot.size.width}x{shot.size.height} OK)"

print(f"Python {sys.version.split()[0]} on {platform.platform()}")
print(f"Interpreter: {sys.executable}\n")
for name, fn in [("numpy", t_numpy), ("opencv", t_opencv), ("scikit-image", t_skimage),
                 ("pandas", t_pandas), ("matplotlib", t_matplotlib), ("pillow", t_pillow),
                 ("torch", t_torch), ("ultralytics", t_ultralytics), ("PyQt6", t_pyqt6), ("mss", t_mss)]:
    check(name, fn)

print()
for name, status, info in results:
    print(f"[{status:4}] {name:13} {info}")
fails = [r for r in results if r[1] != "OK"]
print("\nALL CHECKS PASSED" if not fails else f"\n{len(fails)} CHECK(S) FAILED")
sys.exit(1 if fails else 0)
