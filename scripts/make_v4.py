"""Dataset v4: built for the small / thin defects that R1-R2 miss (slub, nep, knot, broken pick/end).

What changes compared with v3, and why (each point is a finding of the source audit, 2026-11-14):
 1. TILING. One source (fabric_defect_stage2_ra_m, 2,900 line-scan photos) is 2048 x 240 px. Scaled to the
    640 px training size a knot becomes ~6 px and a cut pick ~4 px high - too small to learn. v4 cuts every
    long strip into overlapping tiles (length = 2 x height) at full resolution.
 2. CLEANING PER TILE. v2 removed a whole image when it contained any defect type we do not use (otherwise that
    defect is taught as "normal fabric"). For strips v4 removes only the tiles that contain such a defect.
 3. LABEL MAP FIX. In merge_datasets.py the entries "thick yarn" and "030 - nep" were swallowed by a comment on
    the same line, so neps and thick yarn were dropped although the class is called slub_neps. v4 maps them.
 4. KNOTS. Two sources already label "Knot-Slub" as one class. v4 maps "Knot"/"knots" to slub_neps as well, so
    the class means: local thick place in a yarn (slub, nep, knot). Switch off with --no-knots.
 5. BALANCE. One source is 9,455 augmented copies of only 400 photos. In training v4 keeps at most MAX_COPIES
    copies of one original photo (Ultralytics augments on the fly anyway).
 6. fabric-defects-77bcs stays excluded (label quality, v3 decision).

Fair comparison: every photo that was in v1/v2/v3 keeps its split (if a duplicate group mixes splits, the whole
group goes test > val > train, so nothing that was ever a test image can enter training). The v3 test images are
therefore a subset of the v4 test split with unchanged labels.

Usage: python scripts\\make_v4.py [--dry-run] [--no-knots] [--out C:\\thesis\\data\\merged_v4]
"""
import argparse, csv, hashlib, random, re, shutil, sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import yaml

sys.path.insert(0, str(Path(__file__).parent))
import merge_datasets as M

ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--no-knots", action="store_true")
ap.add_argument("--out", default=r"C:\thesis\data\merged_v4")
args = ap.parse_args()

OUT = Path(args.out)
V1_MANIFEST = Path(r"C:\thesis\data\merged\manifest.csv")
EXCLUDE = {"rf_fabric-defects-77bcs"}
MAX_COPIES = 4            # training copies kept per original photo
STRIP_COPIES = 2          # ... and per original strip (each strip already gives several tiles)
STRIP_ASPECT = 3.0        # long side / short side above this = strip -> tiled
TILE_LEN, TILE_STEP = 2.0, 1.5      # in units of the short side (25 % overlap)
KEEP_BOX, DIRTY_BOX = 0.30, 0.10    # share of a box inside the tile: keep a used box / reject tile for an unused one
CLASSES, SEED = M.CLASSES, M.SEED

CLASS_MAP = dict(M.CLASS_MAP)
CLASS_MAP.update({"thick yarn": "slub_neps", "030 - nep": "slub_neps"})
if not args.no_knots:
    CLASS_MAP.update({"knot": "slub_neps", "knots": "slub_neps"})


def read_boxes(txt, id_to_our):
    """[(class index or None for an unused defect type, cx, cy, w, h)], normalised; polygons -> boxes."""
    out = []
    if not txt.exists():
        return out
    for line in txt.read_text().split("\n"):
        p = line.split()
        if len(p) < 5:
            continue
        our = id_to_our.get(int(float(p[0])))
        v = list(map(float, p[1:]))
        if len(v) > 4:
            xs, ys = v[0::2], v[1::2]
            v = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(xs) - min(xs), max(ys) - min(ys)]
        if v[2] <= 0 or v[3] <= 0:
            continue
        out.append((CLASSES.index(our) if our else None, *v))
    return out


def collect():
    recs, report = [], {}
    for ds in sorted(M.RAW.glob("rf_*")):
        if ds.name in EXCLUDE:
            continue
        meta = yaml.safe_load((ds / "data.yaml").read_text(encoding="utf-8"))
        names = meta["names"]
        names = names if isinstance(names, list) else [names[k] for k in sorted(names)]
        id_to_our = {i: CLASS_MAP.get(M.norm(n)) for i, n in enumerate(names)}
        report[ds.name] = {"mapped": {n: id_to_our[i] for i, n in enumerate(names) if id_to_our[i]},
                           "dropped": [n for i, n in enumerate(names) if not id_to_our[i]]}
        for img in ds.rglob("*"):
            if img.suffix.lower() not in M.IMG_EXT or img.parent.name != "images":
                continue
            boxes = read_boxes(img.parent.parent / "labels" / (img.stem + ".txt"), id_to_our)
            recs.append(dict(src=ds.name, img=img, boxes=boxes, group_key=f"rf:{M.base_stem(img.stem).lower()}"))
    mor = M.RAW / "fabric_stain_moratuwa"
    if mor.exists():
        report[mor.name] = {"mapped": {"stain (folder)": "stain"}, "dropped": []}
        for sub in ("stain", "defect_free"):
            for img in (mor / "images" / sub).glob("*"):
                if img.suffix.lower() in M.IMG_EXT:
                    boxes = read_boxes(mor / "annotations" / sub / (img.stem + ".txt"), {0: "stain"})
                    recs.append(dict(src=mor.name, img=img, boxes=boxes, group_key=f"{mor.name}:{sub}/{img.stem}"))
    for fab in sorted(p for p in M.OWN.glob("*") if p.is_dir()):       # your own photos, one folder per fabric
        img_dir = fab / "images" if (fab / "images").exists() else fab
        for img in img_dir.glob("*"):
            if img.suffix.lower() in M.IMG_EXT:
                txt = (fab / "labels" / (img.stem + ".txt")) if (fab / "labels").exists() else img.with_suffix(".txt")
                boxes = read_boxes(txt, {i: c for i, c in enumerate(CLASSES)})
                recs.append(dict(src="own_photos", img=img, boxes=boxes, group_key=f"own:{fab.name}"))
    return recs, report


def fine_hash(path):
    """256-bit difference hash. The 64-bit hash of merge_datasets.py is the same for many DIFFERENT photos of
    plain fabric (hundreds of line-scan strips fell into one 'duplicate' group), so v4 confirms every 64-bit
    match with this finer hash before calling two images the same photo."""
    img = cv2.imread(str(path), cv2.IMREAD_REDUCED_GRAYSCALE_2)
    if img is None:
        return None
    small = cv2.resize(img, (17, 16), interpolation=cv2.INTER_AREA)
    return int("".join("1" if b else "0" for b in (small[:, 1:] > small[:, :-1]).flatten()), 2)


SAME_PHOTO_BITS = 24      # of 256: re-compressed copies differ in a few bits, different photos in ~128


def tiles_of(w, h):
    """Tile rectangles (x0, y0, x1, y1) in pixels, or None if the image is not a long strip."""
    long_, short = max(w, h), min(w, h)
    if long_ / short < STRIP_ASPECT:
        return None
    tl, st = round(TILE_LEN * short), round(TILE_STEP * short)
    starts = list(range(0, max(long_ - tl, 0) + 1, st))
    if starts[-1] + tl < long_:
        starts.append(long_ - tl)                     # last tile ends exactly at the edge
    return [(s, 0, s + tl, h) if w >= h else (0, s, w, s + tl) for s in starts]


def units_of(rec, w, h):
    """Final training images made from one source image: [(tile index or None, rect or None, label lines)].
    Images / tiles that show a defect type we do not use are left out (it would be taught as background)."""
    rects = tiles_of(w, h)
    if rects is None:
        if any(b[0] is None for b in rec["boxes"]):
            return []
        return [(None, None, [f"{c} {x:.6f} {y:.6f} {bw:.6f} {bh:.6f}" for c, x, y, bw, bh in rec["boxes"]])]
    out = []
    for ti, (x0, y0, x1, y1) in enumerate(rects):
        lines, dirty = [], False
        for c, cx, cy, bw, bh in rec["boxes"]:
            bx0, bx1, by0, by1 = (cx - bw / 2) * w, (cx + bw / 2) * w, (cy - bh / 2) * h, (cy + bh / 2) * h
            ix0, ix1, iy0, iy1 = max(bx0, x0), min(bx1, x1), max(by0, y0), min(by1, y1)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            frac = (ix1 - ix0) * (iy1 - iy0) / ((bx1 - bx0) * (by1 - by0))
            if c is None:
                dirty = dirty or frac > DIRTY_BOX
            elif frac >= KEEP_BOX:
                tw, th = x1 - x0, y1 - y0
                lines.append(f"{c} {((ix0 + ix1) / 2 - x0) / tw:.6f} {((iy0 + iy1) / 2 - y0) / th:.6f} "
                             f"{(ix1 - ix0) / tw:.6f} {(iy1 - iy0) / th:.6f}")
            else:
                dirty = True                          # a used defect cut off at the tile edge: ambiguous, skip tile
        if not dirty:
            out.append((ti, (x0, y0, x1, y1), lines))
    return out


def main():
    recs, report = collect()
    print("=== Label mapping per source (v4) ===")
    for src, r in report.items():
        print(f"[{src}]  used: {', '.join(f'{n}->{c}' for n, c in r['mapped'].items())}")
        if r["dropped"]:
            print(f"      not used: {', '.join(map(str, r['dropped']))}")

    # image sizes (needed to recognise strips); cheap header read via OpenCV
    print(f"\nReading {len(recs)} image sizes and fingerprints ...", flush=True)
    uf, by_hash = M.UnionFind(), {}
    for i, r in enumerate(recs):
        im = cv2.imread(str(r["img"]), cv2.IMREAD_REDUCED_GRAYSCALE_2)
        if im is None:
            r["units"] = []; continue
        r["h"], r["w"] = im.shape[0] * 2, im.shape[1] * 2
        r["units"] = units_of(r, r["w"], r["h"])
        uf.union(("rec", i), ("key", r["group_key"]))
        # line-scan strips all share the camera's lighting profile, so even the fine hash calls different
        # strips "the same photo"; they are identified by file name only (Roboflow copies share the name stem)
        is_strip = bool(r["units"]) and r["units"][0][0] is not None or tiles_of(r["w"], r["h"]) is not None
        hsh = M.dhash(r["img"]) if r["src"] != "own_photos" and not is_strip else None
        if hsh:
            fine = fine_hash(r["img"])
            for other_fine, j in by_hash.setdefault(hsh, []):
                if bin(fine ^ other_fine).count("1") <= SAME_PHOTO_BITS:
                    uf.union(("rec", i), ("rec", j)); break
            else:
                by_hash[hsh].append((fine, i))
    usable = [i for i, r in enumerate(recs) if r["units"]]
    print(f"Source images usable: {len(usable)} of {len(recs)} "
          f"(strips: {sum(1 for i in usable if recs[i]['units'][0][0] is not None)})")

    groups = defaultdict(list)
    for i in usable:
        groups[uf.find(("rec", i))].append(i)

    # splits: keep the v1 assignment of every known photo; new groups are split 70/20/10 per rarest class
    old = {}
    with open(V1_MANIFEST, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            old[row["original_path"].lower()] = row["split"]
    rank = {"train": 0, "val": 1, "test": 2}
    split_of, fresh, mixed = {}, [], 0
    for gid, idx in groups.items():
        seen = {old[str(recs[i]["img"]).lower()] for i in idx if str(recs[i]["img"]).lower() in old}
        if seen:
            split_of[gid] = max(seen, key=rank.get); mixed += len(seen) > 1
        else:
            fresh.append(gid)
    cls_total = Counter(int(l.split()[0]) for i in usable for u in recs[i]["units"] for l in u[2])
    by_cls = defaultdict(list)
    for gid in fresh:
        present = {int(l.split()[0]) for i in groups[gid] for u in recs[i]["units"] for l in u[2]}
        by_cls[min(present, key=lambda c: cls_total[c]) if present else "bg"].append(gid)
    rng = random.Random(SEED)
    for key, gids in sorted(by_cls.items(), key=lambda kv: str(kv[0])):
        gids.sort(key=str); rng.shuffle(gids)
        n = len(gids); n_tr, n_va = round(n * M.SPLIT[0]), round(n * M.SPLIT[1])
        for j, g in enumerate(gids):
            split_of[g] = "train" if j < n_tr else "val" if j < n_tr + n_va else "test"
    print(f"Groups: {len(groups)}; kept their old split: {len(groups) - len(fresh)} "
          f"(of which {mixed} mixed-split duplicate groups moved to the stricter split); new: {len(fresh)}")

    # copies: val/test one per original photo; train at most MAX_COPIES
    final = []          # (rec index, unit)
    for gid, idx in groups.items():
        s = split_of[gid]
        per_key = defaultdict(list)
        for i in idx:
            k = recs[i]["group_key"]
            per_key[str(recs[i]["img"]) if k.startswith("own:") else k].append(i)
        for k, members in per_key.items():
            members.sort(key=lambda i: str(recs[i]["img"]))
            random.Random(f"{SEED}{k}").shuffle(members)
            if s != "train":      # val/test: keep the very copy that v1-v3 used, so the old test images stay identical
                members.sort(key=lambda i: str(recs[i]["img"]).lower() not in old)
            strip = recs[members[0]]["units"][0][0] is not None
            for i in members[: (STRIP_COPIES if strip else MAX_COPIES) if s == "train" else 1]:
                final += [(i, u, s) for u in recs[i]["units"]]
    # background (defect-free) images / tiles: at most 10 % per split
    kept = []
    for s in ("train", "val", "test"):
        d = [x for x in final if x[2] == s and x[1][2]]
        b = [x for x in final if x[2] == s and not x[1][2]]
        random.Random(SEED).shuffle(b)
        kept += d + b[: int(M.BG_FRACTION * len(d) / (1 - M.BG_FRACTION))]

    stats, per_src = defaultdict(Counter), defaultdict(Counter)
    for i, u, s in kept:
        stats[s]["images"] += 1; per_src[recs[i]["src"]][s] += 1
        stats[s]["tiles"] += u[0] is not None
        for l in u[2]:
            stats[s][CLASSES[int(l.split()[0])]] += 1
    print(f"\n{'split':6} {'images':>7} {'(tiles)':>8} " + " ".join(f"{c:>16}" for c in CLASSES))
    for s in ("train", "val", "test"):
        print(f"{s:6} {stats[s]['images']:>7} {stats[s]['tiles']:>8} " + " ".join(f"{stats[s][c]:>16}" for c in CLASSES))
    print("(class columns = number of boxes)\n\nImages per source   train / val / test")
    for src, c in sorted(per_src.items()):
        print(f"   {src:40} {c['train']:>6} {c['val']:>6} {c['test']:>6}")

    if args.dry_run:
        print("\nDRY RUN - nothing written."); return

    if OUT.exists():
        shutil.rmtree(OUT)
    for s in ("train", "val", "test"):
        (OUT / "images" / s).mkdir(parents=True); (OUT / "labels" / s).mkdir(parents=True)
    manifest, cache = [], (None, None)
    kept.sort(key=lambda x: str(recs[x[0]]["img"]))
    for i, (ti, rect, lines), s in kept:
        r = recs[i]
        if cache[0] != i:
            cache = (i, cv2.imread(str(r["img"])))
        img = cache[1]
        if img is None:
            continue
        uid = hashlib.md5(str(r["img"]).encode()).hexdigest()[:8]
        name = re.sub(r"[^\w\-]", "_", f"{r['src'][:28]}__{M.base_stem(r['img'].stem)[:40]}_{uid}") + (f"_t{ti}" if ti is not None else "")
        if rect is not None:
            x0, y0, x1, y1 = rect; img = img[y0:y1, x0:x1]
        elif max(img.shape[:2]) > M.MAX_SIDE:
            f = M.MAX_SIDE / max(img.shape[:2])
            img = cv2.resize(img, (round(img.shape[1] * f), round(img.shape[0] * f)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(OUT / "images" / s / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        (OUT / "labels" / s / f"{name}.txt").write_text("\n".join(lines))
        manifest.append([f"{name}.jpg", s, r["src"], str(r["img"]), len(lines), "" if ti is None else ti])
    with open(OUT / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["file", "split", "source", "original_path", "n_boxes", "tile"]); w.writerows(manifest)
    (OUT / "data.yaml").write_text(yaml.safe_dump({
        "path": ".", "train": "images/train", "val": "images/val", "test": "images/test",
        "nc": len(CLASSES), "names": CLASSES}, sort_keys=False))
    with open(Path(r"C:\thesis\results\dataset_v4_split_stats.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["split", "images", "tiles"] + CLASSES)
        for s in ("train", "val", "test"):
            w.writerow([s, stats[s]["images"], stats[s]["tiles"]] + [stats[s][c] for c in CLASSES])
    print(f"\nWritten {len(manifest)} images to {OUT}")


if __name__ == "__main__":
    main()
