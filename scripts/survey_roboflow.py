"""Query Roboflow Universe projects for classes, image counts, versions, licence.
Appends results to C:\\thesis\\thesis_docs\\dataset_survey.md
"""
import json, sys, urllib.request, urllib.error
from pathlib import Path

KEY = Path(r"C:\thesis\roboflow_key.txt").read_text().strip()
PROJECTS = sys.argv[1:] or [
    "aitex-data-set-waiandt/aitex-yolov8",
    "fabric-defect-x40l3/fabric-defect-classification",
    "fault-annotations/fabric_defect_stage1",
    "fault-annotations/fabric_defect_stage2",
    "pulak-deb-roy/fabric-defect-detection-erdgo",
    "defects-zxmr5/defect-detection-xmqul",
    "fabric-defect-detection-6xxtk/fabric-data-set-eojqe",
    "projectcollege-msi80/fabric_defect_detection-yvkgj",
    "fabric-defect-cfwmt/fabric_defect_detection-ortfl-ipsim",
    "riyans-workspace-tpzu7/garments-defect-detection",
    "istanbul-technical-university-hygeg/fabric-defect-detection-8",
    "defect-dataset/fabric-defects-77bcs",
    "mrkbil-projects/fabric-defect-dataset",
    "irin/fabric-defects-hqvym",
]

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)

rows = ["\n# Roboflow Universe survey (auto-generated)\n",
        "| Project | Type | Images | Classes (count) | Licence | Latest version |", "|---|---|---|---|---|---|"]
for p in PROJECTS:
    try:
        d = get(f"https://api.roboflow.com/{p}?api_key={KEY}")
        pr = d.get("project", {})
        classes = pr.get("classes", {}) or {}
        cls = ", ".join(f"{k} ({v})" for k, v in sorted(classes.items(), key=lambda kv: -kv[1]))
        vers = d.get("versions", [])
        latest = max((v.get("id", "").split("/")[-1] for v in vers), key=lambda s: int(s) if s.isdigit() else 0, default="-")
        row = f"| `{p}` | {pr.get('type','?')} | {pr.get('images','?')} | {cls} | {pr.get('license','?')} | {latest} |"
    except urllib.error.HTTPError as e:
        row = f"| `{p}` | ERROR {e.code} | | | | |"
    except Exception as e:
        row = f"| `{p}` | ERROR {type(e).__name__} | | | | |"
    rows.append(row)
    print(row, flush=True)

out = Path(r"C:\thesis\thesis_docs\dataset_survey.md")
with out.open("a", encoding="utf-8") as f:
    f.write("\n".join(rows) + "\n")
print("appended to", out)
