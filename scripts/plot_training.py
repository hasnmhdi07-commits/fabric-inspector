"""Training-curve figure from an Ultralytics results.csv (works for any run R1-R4).
Usage: python scripts\\plot_training.py results\\R1_results.csv R1
Output: results/<RUN>_training_curves.png  (+ prints a short analysis)
"""
import sys
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

csv, run = Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "run"
df = pd.read_csv(csv); df.columns = [c.strip() for c in df.columns]
e = df["epoch"]

# validated categorical palette, slots 1-2 (light mode); neutral inks for text
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.titlecolor": INK, "axes.titleweight": "bold",
                     "axes.titlesize": 11, "figure.facecolor": SURF, "axes.facecolor": SURF})

panels = [
    ("Box loss (localisation)", "train/box_loss", "val/box_loss", "Train", "Validation", "loss"),
    ("Class loss (classification)", "train/cls_loss", "val/cls_loss", "Train", "Validation", "loss"),
    ("Validation mAP", "metrics/mAP50(B)", "metrics/mAP50-95(B)", "mAP@0.5", "mAP@0.5:0.95", "score"),
    ("Validation precision / recall", "metrics/precision(B)", "metrics/recall(B)", "Precision", "Recall", "score"),
]
best = int(df["metrics/mAP50(B)"].idxmax())
mosaic_off = len(df) - 10 + 1 if len(df) > 10 else None   # Ultralytics default close_mosaic=10

fig, axes = plt.subplots(2, 2, figsize=(11, 7.2), constrained_layout=True)
for ax, (title, c1, c2, l1, l2, ylab) in zip(axes.ravel(), panels):
    ax.plot(e, df[c1], color=BLUE, lw=2, label=l1)
    ax.plot(e, df[c2], color=ORANGE, lw=2, label=l2)
    for col, lab, colr in ((c1, l1, BLUE), (c2, l2, ORANGE)):       # direct labels at line ends
        ax.annotate(f"{lab} {df[col].iloc[-1]:.2f}", (e.iloc[-1], df[col].iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9, color=INK)
        ax.plot(e.iloc[-1], df[col].iloc[-1], "o", ms=5, color=colr, mec=SURF, mew=2)
    if mosaic_off:
        ax.axvline(mosaic_off, color=INK2, lw=1, ls=":")
    ax.set_title(title, loc="left"); ax.set_xlabel("epoch"); ax.set_ylabel(ylab)
    ax.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.set_xlim(0, e.iloc[-1] * 1.22)
    if ylab == "score": ax.set_ylim(0, 1)
    ax.legend(frameon=False, loc="upper right" if ylab == "loss" else "upper left", fontsize=9)
ax = axes[1, 0]
ax.annotate(f"best epoch {e[best]}: {df['metrics/mAP50(B)'][best]:.3f}", (e[best], df["metrics/mAP50(B)"][best]),
            xytext=(-150, 40), textcoords="offset points", fontsize=9, color=INK,
            arrowprops=dict(arrowstyle="-", color=INK2, lw=1))
if mosaic_off:
    axes[0, 1].annotate("mosaic augmentation off", (mosaic_off, axes[0, 1].get_ylim()[1]), xytext=(-4, -12),
                        textcoords="offset points", ha="right", fontsize=8, color=INK2)
fig.suptitle(f"{run}: training history ({len(df)} epochs, {df['time'].iloc[-1] / 3600:.1f} h)",
             x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
out = csv.parent / f"{run}_training_curves.png"
fig.savefig(out, dpi=200)
print("saved", out)

# short numeric analysis
last20 = df.tail(20)
print(f"best val mAP50 {df['metrics/mAP50(B)'].max():.3f} at epoch {e[best]}; final {df['metrics/mAP50(B)'].iloc[-1]:.3f}")
print(f"val mAP50 change over last 20 epochs: {last20['metrics/mAP50(B)'].iloc[-1] - last20['metrics/mAP50(B)'].iloc[0]:+.3f}")
print(f"train cls loss last 20: {last20['train/cls_loss'].iloc[0]:.3f} -> {last20['train/cls_loss'].iloc[-1]:.3f}; "
      f"val cls loss: {last20['val/cls_loss'].iloc[0]:.3f} -> {last20['val/cls_loss'].iloc[-1]:.3f}")
