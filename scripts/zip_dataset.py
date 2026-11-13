"""Zip data/merged -> upload/fabric4.zip for Google Drive (images stored, not re-compressed)."""
import zipfile
import sys
from pathlib import Path

# usage: zip_dataset.py [dataset_dir] [zip_name]   default: data\merged -> fabric4.zip
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\thesis\data\merged")
OUT = Path(r"C:\thesis\upload") / (sys.argv[2] if len(sys.argv) > 2 else "fabric4.zip")
OUT.parent.mkdir(exist_ok=True)
files = [p for p in SRC.rglob("*") if p.is_file()]
with zipfile.ZipFile(OUT, "w") as z:
    for p in files:
        z.write(p, p.relative_to(SRC), compress_type=zipfile.ZIP_STORED if p.suffix == ".jpg" else zipfile.ZIP_DEFLATED)
print(f"saved {OUT} ({len(files)} files, {OUT.stat().st_size / 1e6:.0f} MB)")
