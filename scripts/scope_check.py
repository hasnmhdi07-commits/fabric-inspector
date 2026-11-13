"""Per-source scores on the VALIDATION split (decision basis) + test score with/without a source (transparency).
Usage: python scripts\\scope_check.py <weights> <source-to-check>"""
import sys
from pathlib import Path
import pandas as pd
import yaml
from ultralytics import YOLO

W, SRC = sys.argv[1], sys.argv[2]
D = Path(r"C:\thesis\data\merged_v2"); WORK = Path(r"C:\thesis\results\scope_check"); WORK.mkdir(exist_ok=True, parents=True)
names = yaml.safe_load((D / "data.yaml").read_text())["names"]
man = pd.read_csv(D / "manifest.csv"); m = YOLO(W)

def ev(files, split, tag):
    lst = WORK / f"{tag}.txt"; lst.write_text("\n".join(str(D / "images" / split / f) for f in files))
    y = WORK / f"{tag}.yaml"; y.write_text(yaml.safe_dump({"path": str(D), "train": str(lst), "val": str(lst), "nc": 4, "names": names}))
    r = m.val(data=str(y), split="val", imgsz=640, batch=16, device="cpu", workers=0, plots=False, verbose=False,
              project=str(WORK), name=tag, exist_ok=True)
    ap = {names[int(c)]: round(float(a), 3) for c, a in zip(r.box.ap_class_index, r.box.ap50)}
    return round(r.box.map50, 3), round(r.box.map, 3), ap

val = man[man.split == "val"]
print("VALIDATION split, per source (decision basis):")
for s, g in val.groupby("source"):
    if g.n_boxes.sum():
        mp, _, ap = ev(g.file, "val", f"val_{s}")
        print(f"  {s:36} imgs {len(g):4} boxes {int(g.n_boxes.sum()):4}  mAP50 {mp:.3f}  {ap}")
test = man[man.split == "test"]
for tag, sub in (("test_all", test), (f"test_without_{SRC}", test[test.source != SRC])):
    mp, m95, ap = ev(sub.file, "test", tag)
    print(f"{tag:42} imgs {len(sub):4}  mAP50 {mp:.3f}  mAP50-95 {m95:.3f}  {ap}")
