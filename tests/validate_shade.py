"""Validate the delta E shade module.
Part A: synthetic textured fabric with a KNOWN colour shift -> compare measured vs true delta E CMC(2:1).
Part B: real 'Shade variation' photos (Roboflow dyeing-defects set): is delta E inside the labelled
        shade-variation box higher than outside?  + example heat maps.
Output: results/shade_validation.csv, results/shade_examples/*.jpg
"""
import sys, csv
from pathlib import Path
import cv2
import numpy as np
import yaml
from skimage.color import lab2rgb, deltaE_cmc

sys.path.insert(0, r"C:\thesis")
from src.shade.delta_e import analyse_shade

OUT = Path(r"C:\thesis\results"); (OUT / "shade_examples").mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(0)


def textured(lab_color, H=400, W=400, seed=0):
    """Fabric-like texture: yarn pattern modulates lightness by +-6 L*, plus noise."""
    r = np.random.default_rng(seed)
    y, x = np.mgrid[0:H, 0:W]
    pattern = np.cos(2 * np.pi * y / 7) * 0.6 + np.cos(2 * np.pi * x / 6) * 0.4
    lab = np.zeros((H, W, 3)); lab[...] = lab_color
    lab[..., 0] += 6 * pattern + r.normal(0, 1.0, (H, W))
    rgb = np.clip(lab2rgb(lab), 0, 1)
    return cv2.cvtColor((rgb * 255).round().astype(np.uint8), cv2.COLOR_RGB2BGR)


# ---------- Part A: synthetic ----------
bases = [(30, 5, -30), (55, 40, 25), (70, -20, 10), (45, 10, 10), (80, 2, 5), (40, 30, -10)]  # navy, red, green, brown, ecru, purple
rows = []
for bi, base in enumerate(bases):
    for k in range(10):
        shift = rng.normal(0, 1, 3) * rng.uniform(0.2, 2.0)
        test = np.array(base) + shift
        true = float(deltaE_cmc(np.array(base, float).reshape(1, 1, 3), test.reshape(1, 1, 3), kL=2, kC=1)[0, 0])
        img = np.hstack([textured(base, seed=k), textured(test, seed=k + 50)])
        r = analyse_shade(img, ref_rect=(20, 20, 360, 360), test_rect=(420, 20, 360, 360), tolerance=1.0)
        rows.append(dict(base=str(base), true_dE_cmc=round(true, 3), meas_dE_cmc=round(r.value, 3),
                         abs_err=round(abs(r.value - true), 3), true_pass=true <= 1.0, meas_pass=r.passed))
        if bi < 3 and k == 0:
            cv2.imwrite(str(OUT / "shade_examples" / f"synthetic_{bi}.jpg"), r.overlay)

with open(OUT / "shade_validation.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
err = np.array([r["abs_err"] for r in rows])
agree = np.mean([r["true_pass"] == r["meas_pass"] for r in rows]) * 100
print(f"Part A - {len(rows)} synthetic pairs (true dE CMC {min(r['true_dE_cmc'] for r in rows):.2f}-"
      f"{max(r['true_dE_cmc'] for r in rows):.2f}): MAE {err.mean():.3f}, max {err.max():.3f}, "
      f"pass/fail agreement {agree:.1f}%")

# ---------- Part B: real shade-variation photos ----------
ds = Path(r"C:\thesis\data\raw\shade\rf_dyeing_defects")
names = yaml.safe_load((ds / "data.yaml").read_text())["names"]
names = names if isinstance(names, list) else [names[i] for i in sorted(names)]
sv = [i for i, n in enumerate(names) if n.lower().startswith("shade")]
inside_higher, n_img, ratios = 0, 0, []
for img_path in sorted(ds.rglob("images/*.jpg")):
    lbl = img_path.parent.parent / "labels" / (img_path.stem + ".txt")
    boxes = [list(map(float, l.split()[1:5])) for l in lbl.read_text().splitlines()
             if l.strip() and int(l.split()[0]) in sv] if lbl.exists() else []
    if not boxes:
        continue
    img = cv2.imread(str(img_path)); H, W = img.shape[:2]
    r = analyse_shade(img, tolerance=1.0)
    heat = cv2.resize(r.heatmap, (W, H), interpolation=cv2.INTER_NEAREST)
    mask = np.zeros((H, W), bool)
    for xc, yc, bw, bh in boxes:
        mask[int((yc - bh / 2) * H):int((yc + bh / 2) * H), int((xc - bw / 2) * W):int((xc + bw / 2) * W)] = True
    if mask.all() or not mask.any():
        continue
    ins, out = heat[mask].mean(), heat[~mask].mean()
    n_img += 1; inside_higher += ins > out; ratios.append(ins / max(out, 1e-6))
    if n_img <= 6:
        vis = r.overlay.copy()
        for xc, yc, bw, bh in boxes:
            cv2.rectangle(vis, (int((xc - bw / 2) * W), int((yc - bh / 2) * H)),
                          (int((xc + bw / 2) * W), int((yc + bh / 2) * H)), (255, 255, 255), 2)
        cv2.imwrite(str(OUT / "shade_examples" / f"real_{n_img}.jpg"), vis)
print("Part B NOTE: these are uncontrolled web photos (crumpled fabric, folds, shadows, text overlays);"
      " lighting differences dominate, so they CANNOT validate dE. Reported for transparency only.")
print(f"Part B - {n_img} real shade-variation images: dE higher inside labelled area in "
      f"{inside_higher}/{n_img} ({inside_higher / max(n_img, 1) * 100:.0f}%), median inside/outside ratio "
      f"{np.median(ratios) if ratios else float('nan'):.2f}")
