"""Validate bow/skew module on synthetic woven fabric with KNOWN skew % and bow %.
Output: results/skew_validation.csv + results/skew_examples/*.jpg
"""
import sys, csv, itertools
from pathlib import Path
import cv2
import numpy as np

sys.path.insert(0, r"C:\thesis")
from src.skew.bow_skew import analyse_skew_bow

OUT = Path(r"C:\thesis\results")
(OUT / "skew_examples").mkdir(parents=True, exist_ok=True)


def synth_fabric(skew_pct, bow_pct, W=1000, H=800, weft_p=8.0, warp_p=7.0, noise=0.06, seed=0):
    """Plain-weave-like texture. Weft line shape: y = f(x) = skew*x + parabola with bow depth."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:H, 0:W].astype(np.float64)
    f = skew_pct / 100 * x + 4 * (bow_pct / 100 * W) * (x / W) * (1 - x / W)
    # yarn irregularity: slowly varying random displacement (+-0.6 px) and thickness
    jitter = cv2.GaussianBlur(rng.normal(0, 1, (H, W)), (0, 0), 25) * 60
    phase_w = 2 * np.pi * (y - f + jitter) / weft_p
    phase_p = 2 * np.pi * (x + jitter) / warp_p
    weft = np.cos(phase_w)
    warp = np.cos(phase_p)
    interlace = np.sign(np.sin(phase_w / 2) * np.sin(phase_p / 2))   # over/under pattern
    img = 0.5 + 0.22 * weft * (0.7 + 0.3 * interlace) + 0.12 * warp
    img += 0.08 * (x / W - 0.5) + rng.normal(0, noise, (H, W))           # light gradient + sensor noise
    img = cv2.GaussianBlur(img, (3, 3), 0)
    return np.clip(img * 255, 0, 255).astype(np.uint8)


rows = []
cases = list(itertools.product([-5, -2, 0, 1, 2, 3, 5, 8], [-2, 0, 1, 2, 3]))
for i, (skew, bow) in enumerate(cases):
    for seed in range(2):
        rng = np.random.default_rng(100 + i * 2 + seed)
        weft_p, warp_p = rng.uniform(6, 12), rng.uniform(5, 11)
        img = synth_fabric(skew, bow, weft_p=weft_p, warp_p=warp_p, seed=seed)
        r = analyse_skew_bow(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
        rows.append(dict(true_skew=skew, true_bow=bow, weft_period=round(weft_p, 1),
                         meas_skew=round(r.skew_pct, 3), meas_bow=round(r.bow_pct, 3),
                         fft_skew=round(r.skew_pct_fft, 3),
                         err_skew=round(abs(r.skew_pct - skew), 3), err_bow=round(abs(r.bow_pct - bow), 3),
                         err_fft=round(abs(r.skew_pct_fft - skew), 3)))
        if seed == 0 and (skew, bow) in [(3, 0), (0, 2), (5, 3), (-2, -2)]:
            cv2.imwrite(str(OUT / "skew_examples" / f"skew{skew}_bow{bow}.jpg"), r.overlay)

with open(OUT / "skew_validation.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)

e_s = np.array([r["err_skew"] for r in rows]); e_b = np.array([r["err_bow"] for r in rows])
e_f = np.array([r["err_fft"] for r in rows])
print(f"{len(rows)} synthetic images (skew -5..8 %, bow -2..3 %, yarn spacing 6-12 px)")
print(f"Skew (projection): MAE {e_s.mean():.3f} %-points, max {e_s.max():.3f}")
print(f"Bow  (projection): MAE {e_b.mean():.3f} %-points, max {e_b.max():.3f}")
print(f"Skew (FFT check) : MAE {e_f.mean():.3f} %-points, max {e_f.max():.3f}")
worst = sorted(rows, key=lambda r: -(r['err_skew'] + r['err_bow']))[:3]
print("worst cases:", worst)
