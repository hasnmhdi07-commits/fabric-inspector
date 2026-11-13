"""Merge all public datasets (and later your own photos) into ONE YOLO dataset
with 4 classes, then split 70/20/10 WITHOUT leakage.

Simple explanation (for the thesis defence):
1. Every source dataset uses its own label names ("Hole", "Oil spot", "MissPick"...).
   CLASS_MAP translates them into our 4 classes. Labels we don't use are dropped,
   and images whose defects were ALL dropped are removed (otherwise the model
   would learn that e.g. a knot is "normal fabric").
2. Leakage prevention: augmented copies of the same photo (Roboflow names them
   <original>_jpg.rf.<random>.jpg) and exact duplicates across datasets
   (same image fingerprint = dHash) are put into one GROUP. Your own photos are
   grouped by fabric folder (F01_..., F02_...). Whole groups go to ONE split, so
   the test set never contains a copy or sibling of a training image.
3. Groups are split 70/20/10 separately for each class (stratified), so all
   classes appear in train, val and test.

Usage:
  python scripts\\merge_datasets.py --dry-run     (report only, writes nothing)
  python scripts\\merge_datasets.py               (build data\\merged)
"""
import argparse, csv, hashlib, random, re, shutil
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(r"C:\thesis\data")
RAW = ROOT / "raw" / "public"
OWN = ROOT / "raw" / "own_photos"
OUT = ROOT / "merged"
CLASSES = ["hole_tear", "stain", "slub_neps", "broken_pick_end"]
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
MAX_SIDE = 1280          # resize big photos (keeps upload to Colab small; YOLO labels are normalised so stay valid)
BG_FRACTION = 0.10       # max share of defect-free (background) images
SPLIT = (0.70, 0.20, 0.10)
SEED = 42

CLASS_MAP = {  # lower-case source label -> our class
    "hole": "hole_tear", "cut": "hole_tear",
    "stain": "stain", "stains": "stain", "spot": "stain", "oil spot": "stain", "oilmark": "stain",
    "slub": "slub_neps", "knot-slub": "slub_neps",  # "thick-missing yarn" deliberately NOT mapped (mixes 2 classes) "thick yarn": "slub_neps", "030 - nep": "slub_neps",
    "002 - broken end": "broken_pick_end", "010 - broken pick": "broken_pick_end",
    "006 - broken yarn": "broken_pick_end", "cutpick": "broken_pick_end", "misspick": "broken_pick_end",
    "missing yarn": "broken_pick_end", "yarn missing": "broken_pick_end", "lose end": "broken_pick_end",
}

def norm(name):
    return re.sub(r"\s+", " ", str(name)).strip().lower()

def base_stem(stem):
    """Roboflow augmented copies: 'IMG_12_jpg.rf.abc123' -> 'IMG_12'."""
    return re.sub(r"_(jpg|jpeg|png|bmp|tif|tiff)\.rf\.[0-9a-f]+$", "", stem, flags=re.I)

def dhash(path):
    img = cv2.imread(str(path), cv2.IMREAD_REDUCED_GRAYSCALE_4)
    if img is None:
        return None
    small = cv2.resize(img, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)

def read_labels(txt, id_to_our):
    """Returns (kept_lines, n_dropped). Polygons (segmentation) are converted to boxes."""
    kept, dropped = [], 0
    if not txt.exists():
        return kept, dropped
    for line in txt.read_text().split("\n"):
        parts = line.split()
        if len(parts) < 5:
            continue
        our = id_to_our.get(int(float(parts[0])))
        if our is None:
            dropped += 1
            continue
        vals = list(map(float, parts[1:]))
        if len(vals) > 4:  # polygon -> bounding box
            xs, ys = vals[0::2], vals[1::2]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            vals = [(x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0]
        vals = [min(max(v, 0.0), 1.0) for v in vals]
        if vals[2] <= 0 or vals[3] <= 0:
            continue
        kept.append(f"{CLASSES.index(our)} " + " ".join(f"{v:.6f}" for v in vals))
    return kept, dropped

def collect():
    """Returns list of records: dict(src, img, labels, had_labels, group_key)."""
    recs, report = [], {}
    # 1) Roboflow YOLO exports
    for ds in sorted(RAW.glob("rf_*")):
        meta = yaml.safe_load((ds / "data.yaml").read_text(encoding="utf-8"))
        names = meta["names"]
        names = names if isinstance(names, list) else [names[k] for k in sorted(names)]
        id_to_our = {i: CLASS_MAP.get(norm(n)) for i, n in enumerate(names)}
        report[ds.name] = {"mapped": {n: id_to_our[i] for i, n in enumerate(names) if id_to_our[i]},
                           "dropped": [n for i, n in enumerate(names) if not id_to_our[i]]}
        for img in ds.rglob("*"):
            if img.suffix.lower() not in IMG_EXT or img.parent.name != "images":
                continue
            txt = img.parent.parent / "labels" / (img.stem + ".txt")
            kept, dropped = read_labels(txt, id_to_our)
            had = txt.exists() and txt.read_text().strip() != ""
            recs.append(dict(src=ds.name, img=img, labels=kept, had_labels=had, dropped=dropped,
                             # no dataset prefix: the same original photo re-uploaded in another
                             # Roboflow project gets grouped too (prevents cross-dataset leakage)
                             group_key=f"rf:{base_stem(img.stem).lower()}"))
    # 2) Moratuwa stain dataset (class 0 = stain; defect_free = background)
    mor = RAW / "fabric_stain_moratuwa"
    if mor.exists():
        report[mor.name] = {"mapped": {"stain (folder)": "stain"}, "dropped": []}
        for sub in ("stain", "defect_free"):
            for img in (mor / "images" / sub).glob("*"):
                if img.suffix.lower() not in IMG_EXT:
                    continue
                kept, _ = read_labels(mor / "annotations" / sub / (img.stem + ".txt"), {0: "stain"})
                recs.append(dict(src=mor.name, img=img, labels=kept, had_labels=bool(kept), dropped=0,
                                 group_key=f"{mor.name}:{sub}/{img.stem}"))
    # 3) Your own photos: OWN/<fabric folder>/images/*.jpg + labels/*.txt in our 4-class ids
    for fab in sorted(p for p in OWN.glob("*") if p.is_dir()):
        img_dir = fab / "images" if (fab / "images").exists() else fab
        for img in img_dir.glob("*"):
            if img.suffix.lower() not in IMG_EXT:
                continue
            txt = (fab / "labels" / (img.stem + ".txt")) if (fab / "labels").exists() else img.with_suffix(".txt")
            kept, _ = read_labels(txt, {i: c for i, c in enumerate(CLASSES)})
            recs.append(dict(src="own_photos", img=img, labels=kept, had_labels=bool(kept), dropped=0,
                             group_key=f"own:{fab.name}"))  # whole fabric = one group
    return recs, report

class UnionFind:
    def __init__(self): self.p = {}
    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a, b): self.p[self.find(a)] = self.find(b)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    recs, report = collect()
    print("=== Label mapping per source ===")
    for src, r in report.items():
        print(f"\n[{src}]")
        for n, c in r["mapped"].items():
            print(f"   {n:28} -> {c}")
        if r["dropped"]:
            print(f"   dropped: {', '.join(map(str, r['dropped']))}")

    # remove images whose defects were all unmapped (they contain defects we don't label)
    before = len(recs)
    recs = [r for r in recs if r["labels"] or not r["had_labels"]]
    print(f"\nImages total: {before}, removed (only unused defect types): {before - len(recs)}")

    # cap background images
    defect = [r for r in recs if r["labels"]]
    bg = [r for r in recs if not r["labels"]]
    random.Random(SEED).shuffle(bg)
    max_bg = int(BG_FRACTION * len(defect) / (1 - BG_FRACTION))
    recs = defect + bg[:max_bg]
    print(f"Defect images: {len(defect)}, background kept: {min(len(bg), max_bg)} of {len(bg)}")

    # grouping: same original photo (augmentations) + identical fingerprint across datasets
    print("Fingerprinting images for duplicate detection ...", flush=True)
    uf = UnionFind()
    by_hash = {}
    for i, r in enumerate(recs):
        uf.union(("rec", i), ("key", r["group_key"]))
        h = dhash(r["img"]) if r["src"] != "own_photos" else None
        if h is not None and h != 0:
            if h in by_hash:
                uf.union(("rec", i), ("rec", by_hash[h]))
            else:
                by_hash[h] = i
    groups = defaultdict(list)
    for i in range(len(recs)):
        groups[uf.find(("rec", i))].append(i)
    cross = sum(1 for g in groups.values() if len({recs[i]["src"] for i in g}) > 1)
    print(f"Groups: {len(groups)} (from {len(recs)} images); groups spanning >1 dataset (duplicates): {cross}")

    # stratified group split: each group labelled by its rarest class
    cls_total = Counter(int(l.split()[0]) for r in recs for l in r["labels"])
    by_cls = defaultdict(list)
    for gid, idx in groups.items():
        present = {int(l.split()[0]) for i in idx for l in recs[i]["labels"]}
        key = min(present, key=lambda c: cls_total[c]) if present else "bg"
        by_cls[key].append(gid)
    rng = random.Random(SEED)
    split_of = {}
    for key, gids in by_cls.items():
        gids.sort(key=str); rng.shuffle(gids)
        n = len(gids); n_tr = round(n * SPLIT[0]); n_va = round(n * SPLIT[1])
        for j, g in enumerate(gids):
            split_of[g] = "train" if j < n_tr else "val" if j < n_tr + n_va else "test"

    # val/test must be "real" photos: keep only ONE copy per original photo
    # (augmented duplicates are only useful for training)
    for gid in groups:
        if split_of[gid] != "train":
            seen, keep = set(), []
            for i in groups[gid]:
                k = recs[i]["group_key"]
                if k.startswith("own:"):
                    k = str(recs[i]["img"])  # own photos are all distinct shots
                if k not in seen:
                    seen.add(k); keep.append(i)
            groups[gid] = keep

    # statistics
    stats = defaultdict(Counter)
    for gid, idx in groups.items():
        s = split_of[gid]
        for i in idx:
            stats[s]["images"] += 1
            for l in recs[i]["labels"]:
                stats[s][CLASSES[int(l.split()[0])]] += 1
    print(f"\n{'split':6} {'images':>7} " + " ".join(f"{c:>16}" for c in CLASSES))
    for s in ("train", "val", "test"):
        print(f"{s:6} {stats[s]['images']:>7} " + " ".join(f"{stats[s][c]:>16}" for c in CLASSES))
    print("(class columns = number of boxes)")

    if args.dry_run:
        print("\nDRY RUN - nothing written.")
        return

    # write dataset
    if OUT.exists():
        shutil.rmtree(OUT)
    for s in ("train", "val", "test"):
        (OUT / "images" / s).mkdir(parents=True); (OUT / "labels" / s).mkdir(parents=True)
    manifest = []
    for gid, idx in groups.items():
        s = split_of[gid]
        for i in idx:
            r = recs[i]
            # short, unique, Windows-safe name (original path is kept in manifest.csv)
            uid = hashlib.md5(str(r["img"]).encode()).hexdigest()[:8]
            name = re.sub(r"[^\w\-]", "_", f"{r['src'][:28]}__{base_stem(r['img'].stem)[:40]}_{uid}")
            img = cv2.imread(str(r["img"]))
            if img is None:
                continue
            h, w = img.shape[:2]
            if max(h, w) > MAX_SIDE:
                f = MAX_SIDE / max(h, w)
                img = cv2.resize(img, (round(w * f), round(h * f)), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(OUT / "images" / s / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            (OUT / "labels" / s / f"{name}.txt").write_text("\n".join(r["labels"]))
            manifest.append([f"{name}.jpg", s, r["src"], str(r["img"]), len(r["labels"]), str(gid[1])])
    with open(OUT / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["file", "split", "source", "original_path", "n_boxes", "group"])
        w.writerows(manifest)
    (OUT / "data.yaml").write_text(yaml.safe_dump({
        "path": ".", "train": "images/train", "val": "images/val", "test": "images/test",
        "nc": len(CLASSES), "names": CLASSES}, sort_keys=False))
    with open(Path(r"C:\thesis\results\dataset_split_stats.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["split", "images"] + CLASSES)
        for s in ("train", "val", "test"):
            w.writerow([s, stats[s]["images"]] + [stats[s][c] for c in CLASSES])
    print(f"\nWritten {len(manifest)} images to {OUT}")

if __name__ == "__main__":
    main()
