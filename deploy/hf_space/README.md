---
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
