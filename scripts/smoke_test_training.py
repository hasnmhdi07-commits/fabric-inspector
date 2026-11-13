"""Mini end-to-end test of the Colab pipeline on the local CPU (1 epoch, 2% of data).
Uses the real zip, so it also proves the upload file is correct."""
import sys, yaml, zipfile
from pathlib import Path
from ultralytics import YOLO

work = Path(sys.argv[1])
data = work / "fabric4"
zipfile.ZipFile(r"C:\thesis\upload\fabric4.zip").extractall(data)
cfg = yaml.safe_load(open(data / "data.yaml")); cfg["path"] = str(data)
yaml.safe_dump(cfg, open(data / "data_colab.yaml", "w"), sort_keys=False)

model = YOLO(r"C:\thesis\models\yolo11n.pt")
model.train(data=str(data / "data_colab.yaml"), imgsz=320, batch=8, epochs=1, fraction=0.02,
            project=str(work / "runs"), name="smoke", exist_ok=True, workers=0, plots=False, device="cpu")
m = YOLO(str(work / "runs" / "smoke" / "weights" / "best.pt")).val(
    data=str(data / "data_colab.yaml"), split="test", imgsz=320, batch=8, workers=0, plots=True,
    project=str(work / "runs"), name="smoke_test", exist_ok=True, device="cpu")
print(f"\nSMOKE TEST OK  mAP50={m.box.map50:.3f}  (meaningless after 1 tiny epoch - only checks the pipeline)")
print("per-class AP50:", dict(zip(m.names.values(), [round(x, 3) for x in m.box.ap50])))
