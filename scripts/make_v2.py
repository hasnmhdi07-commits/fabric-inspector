"""Dataset v2 = v1 minus PARTIALLY-LABELLED images.

Problem found in R1 analysis: v1 kept images where some defects were labelled with a class we use
and OTHER defects had a class we dropped (e.g. Knot, loose-thread, Thick-Missing yarn). Those
unlabelled-but-visible defects teach the model "this defect = normal fabric" (label noise).
v2 removes every image that contains ANY dropped defect label.

The train/val/test assignment of every remaining image is kept IDENTICAL to v1, so v1 and v2 models
can be compared fairly on the v2 test set.
Usage: python scripts\\make_v2.py [--dry-run] [--exclude-source NAME ...]
"""
import argparse, os, shutil, sys
from collections import Counter
from pathlib import Path
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from merge_datasets import CLASS_MAP, norm, CLASSES  # same mapping as v1

V1 = Path(r"C:\thesis\data\merged")
V2 = Path(r"C:\thesis\data\merged_v2")
RAW = Path(r"C:\thesis\data\raw\public")

ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--exclude-source", nargs="*", default=[])
ap.add_argument("--out", default=str(V2), help="output folder (v3 = v2 rules + excluded sources)")
args = ap.parse_args()
V2 = Path(args.out)

man = pd.read_csv(V1 / "manifest.csv")
unmapped_ids = {}
for ds in RAW.glob("rf_*"):
    names = yaml.safe_load((ds / "data.yaml").read_text(encoding="utf-8"))["names"]
    names = names if isinstance(names, list) else [names[k] for k in sorted(names)]
    unmapped_ids[ds.name] = {i for i, n in enumerate(names) if CLASS_MAP.get(norm(n)) is None}


def has_dropped_defect(row):
    if row.source not in unmapped_ids:
        return False
    img = Path(row.original_path)
    txt = img.parent.parent / "labels" / (img.stem + ".txt")
    if not txt.exists():
        return False
    for line in txt.read_text().split("\n"):
        p = line.split()
        if len(p) >= 5 and int(float(p[0])) in unmapped_ids[row.source]:
            return True
    return False


man["partial"] = man.apply(has_dropped_defect, axis=1)
man["excluded"] = man.source.isin(args.exclude_source)
keep = man[~man.partial & ~man.excluded]

print("Partially-labelled images removed, per source and split:")
print(pd.crosstab(man[man.partial].source, man[man.partial].split, margins=True).to_string())
print(f"\nv1: {len(man)} images -> v2: {len(keep)} images")
cnt = Counter()
for _, r in keep.iterrows():
    for line in (V1 / "labels" / r.split / (Path(r.file).stem + ".txt")).read_text().split("\n"):
        if line.strip():
            cnt[(r.split, CLASSES[int(line.split()[0])])] += 1
print(f"\n{'split':6} {'images':>7} " + " ".join(f"{c:>16}" for c in CLASSES))
for s in ("train", "val", "test"):
    print(f"{s:6} {int((keep.split == s).sum()):>7} " + " ".join(f"{cnt[(s, c)]:>16}" for c in CLASSES))

if args.dry_run:
    print("\nDRY RUN - nothing written."); sys.exit()

if V2.exists():
    shutil.rmtree(V2)
for s in ("train", "val", "test"):
    (V2 / "images" / s).mkdir(parents=True); (V2 / "labels" / s).mkdir(parents=True)
for _, r in keep.iterrows():
    stem = Path(r.file).stem
    for sub, ext in (("images", ".jpg"), ("labels", ".txt")):
        src, dst = V1 / sub / r.split / (stem + ext), V2 / sub / r.split / (stem + ext)
        try:
            os.link(src, dst)           # hard link: no extra disk space
        except OSError:
            shutil.copy2(src, dst)
keep.drop(columns=["partial", "excluded"]).to_csv(V2 / "manifest.csv", index=False)
shutil.copy2(V1 / "data.yaml", V2 / "data.yaml")
print(f"\nWritten {len(keep)} images to {V2}")
