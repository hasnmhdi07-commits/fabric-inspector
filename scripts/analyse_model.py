"""Analyse a trained model on the TEST split:
 1. overall metrics (should reproduce the Colab numbers)
 2. per-source-dataset metrics (which dataset is the model weak on?)
 3. best confidence threshold for the app (max F1)
Usage: python scripts\\analyse_model.py models\\R1_yolo11n_640_best.pt R1 [imgsz]
Output: results/<RUN>_per_source.csv, printed summary
"""
import sys, csv
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from ultralytics import YOLO

weights, run = sys.argv[1], sys.argv[2]
imgsz = int(sys.argv[3]) if len(sys.argv) > 3 else 640
MERGED = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(r"C:\thesis\data\merged")   # dataset to test on
run = run + ("" if MERGED.name == "merged" else f"_on_{MERGED.name}")
WORK = Path(r"C:\thesis\results") / f"{run}_analysis"
WORK.mkdir(parents=True, exist_ok=True)
names = yaml.safe_load((MERGED / "data.yaml").read_text())["names"]
man = pd.read_csv(MERGED / "manifest.csv")
test = man[man.split == "test"]
model = YOLO(weights)


def evaluate(img_files, tag):
    lst = WORK / f"{tag}.txt"
    lst.write_text("\n".join(str(MERGED / "images" / "test" / f) for f in img_files))
    y = WORK / f"{tag}.yaml"
    y.write_text(yaml.safe_dump({"path": str(MERGED), "train": str(lst), "val": str(lst),
                                 "nc": len(names), "names": names}))
    return model.val(data=str(y), split="val", imgsz=imgsz, batch=16, device="cpu", workers=0,
                     plots=False, verbose=False, project=str(WORK), name=tag, exist_ok=True)


# 1 + 3: whole test set
m = evaluate(test.file.tolist(), "all")
f1 = m.box.f1_curve.mean(0)                 # mean F1 over classes vs confidence
best_conf = float(m.box.px[int(np.argmax(f1))])
print(f"\nALL TEST ({len(test)} imgs): P {m.box.mp:.3f} R {m.box.mr:.3f} mAP50 {m.box.map50:.3f} mAP50-95 {m.box.map:.3f}")
print(f"best confidence threshold (max mean F1 = {f1.max():.3f}): {best_conf:.2f}")
per_cls_f1 = m.box.f1_curve[:, int(np.argmax(f1))]
print("F1 per class at that threshold:", {names[i]: round(float(v), 3) for i, v in enumerate(per_cls_f1)})

# 2: per source dataset
rows = []
for src, g in test.groupby("source"):
    if g.n_boxes.sum() == 0:
        continue
    r = evaluate(g.file.tolist(), src)
    row = {"source": src, "images": len(g), "boxes": int(g.n_boxes.sum()),
           "P": round(r.box.mp, 3), "R": round(r.box.mr, 3), "mAP50": round(r.box.map50, 3)}
    for ci, ap in zip(r.box.ap_class_index, r.box.ap50):
        row[f"AP50_{names[int(ci)]}"] = round(float(ap), 3)
    rows.append(row)
df = pd.DataFrame(rows).sort_values("mAP50")
df.to_csv(Path(r"C:\thesis\results") / f"{run}_per_source.csv", index=False)
pd.set_option("display.width", 200); pd.set_option("display.max_columns", 20)
print("\nPER SOURCE (test split):")
print(df.to_string(index=False))
