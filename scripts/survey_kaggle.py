"""Survey Kaggle fabric-defect datasets WITHOUT downloading the images.
For each dataset: licence, description, and image count per folder (= class).
Output: C:\\thesis\\thesis_docs\\dataset_survey.md
"""
import json, subprocess, sys, tempfile, re
from collections import Counter
from pathlib import Path, PurePosixPath

KAGGLE = r"C:\thesis\venv\Scripts\kaggle.exe"
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
REFS = sys.argv[1:] or [
    "priemshpathirana/fabric-stain-dataset",
    "nexuswho/aitex-fabric-image-database",
    "angelolmg/tilda-400",
    "nexuswho/fabric-defects-dataset",
    "ziya07/multi-class-fabric-defect-detection-dataset",
    "rmshashi/fabric-defect-dataset",
    "hodinhtrieu/the-woven-fabric-defect-detection-wfdd",
    "ahmettalhasivrikaya/fabric-defect-detection",
    "k23m23/stain-clothswith-level",
]

def run(args):
    return subprocess.run([KAGGLE, *args], capture_output=True, text=True, encoding="utf-8").stdout

def metadata(ref):
    with tempfile.TemporaryDirectory() as d:
        run(["datasets", "metadata", ref, "-p", d])
        p = Path(d) / "dataset-metadata.json"
        return json.loads(p.read_text(encoding="utf-8")).get("info", {}) if p.exists() else {}

def all_files(ref):
    files, token = [], None
    for _ in range(200):  # safety limit
        args = ["datasets", "files", ref, "--csv", "--page-size", "200"]
        if token:
            args += ["--page-token", token]
        out = run(args)
        token = None
        for line in out.splitlines():
            m = re.match(r"Next Page Token = (\S+)", line)
            if m:
                token = m.group(1)
            elif line and not line.startswith("name,"):
                files.append(line.rsplit(",", 2)[0])
        if not token:
            break
    return files

def folder_counts(files):
    c = Counter()
    for f in files:
        p = PurePosixPath(f)
        if p.suffix.lower() in IMG_EXT:
            c[str(p.parent)] += 1
    return c

lines = ["# Kaggle fabric defect dataset survey (auto-generated)\n"]
for ref in REFS:
    info = metadata(ref)
    files = all_files(ref)
    counts = folder_counts(files)
    lic = ", ".join(l.get("name", "") for l in info.get("licenses", [])) or "UNKNOWN"
    desc = re.sub(r"\s+", " ", info.get("description", ""))[:700]
    lines += [f"## {info.get('title', ref)}", f"- Ref: `{ref}`  ", f"- Licence: **{lic}**  ",
              f"- Subtitle: {info.get('subtitle', '')}  ", f"- Total files listed: {len(files)}, images: {sum(counts.values())}  ",
              f"- Description: {desc}\n", "| Folder | Images |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(counts.items())[:40]]
    if len(counts) > 40:
        lines.append(f"| ... {len(counts) - 40} more folders | |")
    lines.append("")
    print(f"done: {ref} ({lic}, {sum(counts.values())} images, {len(counts)} folders)", flush=True)

out = Path(r"C:\thesis\thesis_docs\dataset_survey.md")
out.write_text("\n".join(lines), encoding="utf-8")
print("saved", out)
