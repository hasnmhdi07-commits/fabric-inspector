"""Generates notebooks/train_colab.ipynb (run once; edit THIS file, not the notebook)."""
import json
from pathlib import Path

cells = []
def md(s): cells.append({"cell_type": "markdown", "metadata": {}, "source": s.strip()})
def code(s): cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s.strip()})

md("""
# Fabric defect detection - YOLO training on Colab
**Before you start:** Runtime → Change runtime type → **T4 GPU** → Save.
Upload `fabric4_v4.zip` to Google Drive in a folder called **`thesis`** (so: `MyDrive/thesis/fabric4_v4.zip`).

Run the cells **top to bottom**. Train **one run per Colab session** (each takes ~1–3 h).
Everything is saved to Google Drive, so nothing is lost if Colab disconnects — use the *Resume* cell.

| Run | Model | Image size | Why (for the thesis) |
|---|---|---|---|
| R1 | YOLO11n | 640 | Baseline: smallest, fastest model |
| R2 | YOLO11s | 640 | Bigger model: does more capacity help? |
| R3 | YOLOv8s | 640 | Older generation, same size: is YOLO11 better than YOLOv8? |
| R4 | YOLO11s | 960 | Higher resolution: helps small defects (neps, broken picks)? |
| R5 | YOLO11n | 960 | Same model as R1, only resolution changed: effect of resolution alone |
""")
md("## 1. Check GPU, connect Google Drive, install Ultralytics")
code("""
!nvidia-smi --query-gpu=name,memory.total --format=csv
from google.colab import drive
drive.mount('/content/drive')
!pip -q install ultralytics==8.4.211
""")
md("## 2. Copy dataset from Drive to Colab's fast local disk and unzip")
code("""
import os, yaml, zipfile, shutil
DATASET = 'fabric4_v4'            # v1 'fabric4', v2 cleaned, v3 = v2 without 77bcs, v4 = strip tiles + neps/knots (make_v4.py)
DRIVE = '/content/drive/MyDrive/thesis'
RUNS = f'{DRIVE}/runs'            # results are saved here (persist on Drive)
DATA = f'/content/{DATASET}'
TAG = {'fabric4': '', 'fabric4_v2': 'v2', 'fabric4_v3': 'v3', 'fabric4_v4': 'v4'}[DATASET]   # run folders: R1, R1v2, R5v3 ...
os.makedirs(RUNS, exist_ok=True)
if not os.path.exists(f'{DATA}/data.yaml'):
    shutil.copy(f'{DRIVE}/{DATASET}.zip', f'/content/{DATASET}.zip')
    zipfile.ZipFile(f'/content/{DATASET}.zip').extractall(DATA)
cfg = yaml.safe_load(open(f'{DATA}/data.yaml'))
cfg['path'] = DATA
yaml.safe_dump(cfg, open(f'{DATA}/data_colab.yaml', 'w'), sort_keys=False)
for s in ('train', 'val', 'test'):
    print(s, len(os.listdir(f'{DATA}/images/{s}')), 'images')
print('classes:', cfg['names'])
""")
md("""
## 3. Train — choose ONE run per session
Change `RUN` to `'R1'` ... `'R5'`. Settings are identical except model / image size,
so differences in results come only from that change (a fair comparison).
""")
code("""
from ultralytics import YOLO
RUN = 'R5'   # <-- change this each session (R5 on fabric4_v4 = the recommended run: saves as R5v4)
SETTINGS = {
    'R1': dict(model='yolo11n.pt', imgsz=640, batch=32),
    'R2': dict(model='yolo11s.pt', imgsz=640, batch=16),
    'R3': dict(model='yolov8s.pt', imgsz=640, batch=16),
    'R4': dict(model='yolo11s.pt', imgsz=960, batch=8),
    'R5': dict(model='yolo11n.pt', imgsz=960, batch=16),   # same model as R1, only resolution changed
}[RUN]
model = YOLO(SETTINGS['model'])     # starts from COCO-pretrained weights (transfer learning)
model.train(
    data=f'{DATA}/data_colab.yaml',
    imgsz=SETTINGS['imgsz'], batch=SETTINGS['batch'],
    epochs=80, patience=20,          # stop early if val mAP does not improve for 20 epochs
    project=RUNS, name=RUN + TAG, exist_ok=True,
    seed=0, deterministic=True,      # reproducible
    workers=2, plots=True, save_period=10,
)
""")
md("### If Colab disconnected during training: run cell 1 and 2 again, then this cell")
code("""
from ultralytics import YOLO
RUN = 'R5'   # <-- the run that was interrupted (DATASET in cell 2 must be the one it was started with)
YOLO(f'{RUNS}/{RUN}{TAG}/weights/last.pt').train(resume=True)
""")
md("""
## 4. Evaluate every finished run on the TEST set (never seen during training)
Produces the numbers for your results chapter: precision, recall, mAP@0.5, mAP@0.5:0.95,
per-class AP and the confusion matrix (saved as an image in `runs/<RUN>_test/`).
""")
code("""
import pandas as pd
from ultralytics import YOLO
rows = []
# every trained model found on Drive is tested on the SAME test set (dataset loaded in cell 2) -> fair comparison;
# each model is evaluated at the image size it was trained with (read from its args.yaml)
for RUN in sorted(d for d in os.listdir(RUNS) if os.path.exists(f'{RUNS}/{d}/weights/best.pt')):
    w = f'{RUNS}/{RUN}/weights/best.pt'
    imgsz = yaml.safe_load(open(f'{RUNS}/{RUN}/args.yaml')).get('imgsz', 640)
    m = YOLO(w).val(data=f'{DATA}/data_colab.yaml', split='test', imgsz=imgsz, batch=16,
                    project=RUNS, name=f'{RUN}_test_{DATASET}', exist_ok=True, plots=True)
    row = dict(run=RUN, test_set=DATASET, precision=m.box.mp, recall=m.box.mr, mAP50=m.box.map50, mAP50_95=m.box.map)
    for i, name in m.names.items():
        row[f'AP50_{name}'] = m.box.ap50[i] if i < len(m.box.ap50) else None
    row['ms_per_image'] = m.speed['inference']
    rows.append(row)
df = pd.DataFrame(rows).round(3)
df.to_csv(f'{RUNS}/test_results_{DATASET}.csv', index=False)
df
""")
md("""
## 5. Look at results
Files on your Drive in `thesis/runs/`:
- `R*/results.png` — training curves (loss going down, mAP going up)
- `R*_test/confusion_matrix_normalized.png` — which classes get confused
- `R*_test/val_batch*_pred.jpg` — example predictions
- `test_results.csv` — comparison table
- `R*/weights/best.pt` — **the trained model**; download the best one into `C:\\thesis\\models\\`
""")
code("""
from IPython.display import Image, display
for RUN in sorted(d for d in os.listdir(RUNS) if os.path.exists(f'{RUNS}/{d}/weights/best.pt')):
    p = f'{RUNS}/{RUN}_test_{DATASET}/confusion_matrix_normalized.png'
    if os.path.exists(p):
        print(RUN); display(Image(p, width=600))
""")

nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"provenance": []},
      "kernelspec": {"name": "python3", "display_name": "Python 3"}}, "nbformat": 4, "nbformat_minor": 0}
out = Path(r"C:\thesis\notebooks\train_colab.ipynb")
out.write_text(json.dumps(nb, indent=1), encoding="utf-8")
print("saved", out)
