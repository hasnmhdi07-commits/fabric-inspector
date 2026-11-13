"""Download shortlisted Roboflow Universe datasets in YOLOv8 format.
Each goes to its own folder under C:\\thesis\\data\\raw\\public\\rf_<project>.
"""
from pathlib import Path
from roboflow import Roboflow

KEY = Path(r"C:\thesis\roboflow_key.txt").read_text().strip()
ROOT = Path(r"C:\thesis\data\raw\public")
# (workspace, project, version)  -- chosen because their classes map to our 4 classes
SHORTLIST = [
    ("aitex-data-set-waiandt", "aitex-yolov8", 2),                 # Broken End/Pick/Yarn, Nep
    ("fault-annotations", "fabric_defect_stage2_ra_m-lfcbg", 7),   # Slub 599, Cutpick, oilMark (replaces stage2)
    ("fabric-defect-detection-6xxtk", "labelled-data", 5),         # Knot-slub, Spot, Hole
    ("pulak-deb-roy", "fabric-defect-detection-erdgo", 22),        # Hole, Spot, Knot-Slub, Thick yarn, Missing yarn, Lose end
    ("defects-zxmr5", "defect-detection-xmqul", 19),               # hole, stain, yarn missing
    ("defect-dataset", "fabric-defects-77bcs", 4),                 # hole, spot, slub, MissPick
    ("projectcollege-msi80", "fabric_defect_detection-yvkgj", 2),  # Hole, Oil spot
]

rf = Roboflow(api_key=KEY)
for ws, proj, ver in SHORTLIST:
    dest = ROOT / f"rf_{proj}"
    if (dest / "data.yaml").exists():
        print(f"skip (already downloaded): {proj}")
        continue
    try:
        rf.workspace(ws).project(proj).version(ver).download("yolov8", location=str(dest), overwrite=True)
        n = sum(1 for _ in dest.rglob("*.jpg")) + sum(1 for _ in dest.rglob("*.png"))
        print(f"OK {proj} v{ver}: {n} images -> {dest}")
    except Exception as e:
        print(f"FAIL {proj} v{ver}: {type(e).__name__}: {e}")

# Shade-variation images: NOT for YOLO, used to test the delta E module
shade = Path(r"C:\thesis\data\raw\shade\rf_dyeing_defects")
if not (shade / "data.yaml").exists():
    rf.workspace("vsj").project("ds-assignment-dyeing-defects").version(2).download("yolov8", location=str(shade), overwrite=True)
    print("OK dyeing defects ->", shade)
