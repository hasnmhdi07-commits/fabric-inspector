"""Assemble the Hugging Face Space folder (deploy/hf_space) from the project.
Only what the web app needs: app, analysis modules, knowledge base, model, examples, config.
Usage: python scripts\\build_space.py [path\\to\\model.pt]   (default models\\best.pt)
"""
import shutil, sys
from pathlib import Path

ROOT = Path(r"C:\thesis")
OUT = ROOT / "deploy" / "hf_space"
model = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "models" / "best.pt"

if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "models").mkdir(parents=True)

shutil.copy2(ROOT / "web" / "app.py", OUT / "app.py")
shutil.copytree(ROOT / "web" / "examples", OUT / "examples")
for rel in ["src/__init__.py", "src/app/__init__.py", "src/app/engine.py", "src/app/report_html.py",
            "src/knowledge/__init__.py", "src/knowledge/kb.py", "src/knowledge/knowledge_base.yaml",
            "src/shade/__init__.py", "src/shade/delta_e.py",
            "src/skew/__init__.py", "src/skew/bow_skew.py"]:
    (OUT / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / rel, OUT / rel)
shutil.copy2(model, OUT / "models" / "best.pt")

(OUT / "requirements.txt").write_text("""--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.15.0
torchvision==0.29.2
ultralytics==8.4.211
opencv-python-headless
scikit-image==0.26.0
pyyaml
""")
# ultralytics pulls in opencv-python, which needs these system libraries on Linux
(OUT / "packages.txt").write_text("libgl1\nlibglib2.0-0\n")

(OUT / "README.md").write_text("""---
title: Fabric Defect Inspector
emoji: 🧵
colorFrom: indigo
colorTo: gray
sdk: gradio
sdk_version: 6.31.0
python_version: "3.12"
app_file: app.py
pinned: false
license: cc-by-4.0
short_description: AI fabric defect detection with causes and remedies
---

# Fabric Defect Inspector

Thesis prototype: *Fabric defect detection with AI cause/remedy analysis*.

Upload or photograph a fabric (works on PC and phone; can be installed as an app from the browser menu).

- **YOLO11** detects hole/tear, stain, slub/neps, broken pick/end
- **Shade variation**: CIELAB colour difference (ΔE CMC 2:1) with heat map
- **Bow / skew**: weft-line angle analysis (% bow, % skew, ASTM D3882 definitions)
- **Rule-based knowledge base**: severity (4-point system, ASTM D5430), likely causes, remedy, prevention

Results are decision support for a trained inspector, not a replacement.

## Data and credits
The detector was trained on public datasets: Fabric Stain Dataset (University of Moratuwa, CC0) and
Roboflow Universe projects (CC BY 4.0): AITEX-YOLOv8, fabric_defect_stage2_ra_m (fault-annotations),
fabric-defect-detection (pulak-deb-roy), defect-detection (defects-zxmr5), fabric-defects (defect-dataset),
fabric_defect_detection (projectcollege-msi80), labelled-data (fabric-defect-detection-6xxtk).
Example images: stain - Fabric Stain Dataset (CC0); hole - defect-detection (defects-zxmr5, CC BY 4.0);
skew - synthetic.
""", encoding="utf-8")

size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) / 1e6
print(f"Space folder ready: {OUT} ({sum(1 for p in OUT.rglob('*') if p.is_file())} files, {size:.1f} MB)")
print(f"model: {model}")
