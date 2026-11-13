"""Draw YOLO boxes on random merged images -> results/label_preview_<split>.jpg
Use it to visually check that labels are correct (good figure for the thesis too)."""
import random, sys
from pathlib import Path
import cv2, numpy as np

ROOT = Path(r"C:\thesis\data\merged")
CLASSES = ["hole_tear", "stain", "slub_neps", "broken_pick_end"]
COLORS = [(0, 0, 255), (0, 200, 255), (255, 0, 200), (0, 220, 0)]
split = sys.argv[1] if len(sys.argv) > 1 else "train"
n = 16
imgs = sorted((ROOT / "images" / split).glob("*.jpg"))
random.Random(1).shuffle(imgs)
tiles = []
for p in imgs[:n]:
    im = cv2.imread(str(p)); h, w = im.shape[:2]
    for line in (ROOT / "labels" / split / (p.stem + ".txt")).read_text().split("\n"):
        if not line.strip():
            continue
        c, x, y, bw, bh = line.split(); c = int(c)
        x, y, bw, bh = float(x) * w, float(y) * h, float(bw) * w, float(bh) * h
        cv2.rectangle(im, (int(x - bw / 2), int(y - bh / 2)), (int(x + bw / 2), int(y + bh / 2)), COLORS[c], max(2, w // 200))
        cv2.putText(im, CLASSES[c], (int(x - bw / 2), max(15, int(y - bh / 2) - 5)), cv2.FONT_HERSHEY_SIMPLEX, max(0.5, w / 800), COLORS[c], max(1, w // 400))
    tiles.append(cv2.resize(im, (320, 320)))
rows = [np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]
out = Path(r"C:\thesis\results") / f"label_preview_{split}.jpg"
cv2.imwrite(str(out), np.vstack(rows))
print("saved", out)
