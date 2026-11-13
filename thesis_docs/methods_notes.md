# Methods and validation notes (draft material for thesis chapters 3-4)

## 1. Dataset construction
- Sources (all CC0 or CC BY 4.0): Fabric Stain Dataset (Univ. of Moratuwa, Kaggle) and 7 Roboflow Universe
  projects (AITEX-YOLOv8, fabric_defect_stage2_ra_m, pulak-deb-roy, defect-detection-xmqul, fabric-defects-77bcs,
  projectcollege, labelled-data). Full survey incl. rejected sets: `dataset_survey.md`.
- Source labels mapped to 4 classes (hole_tear, stain, slub_neps, broken_pick_end); unrelated labels dropped and
  images containing only dropped defect types removed (avoids teaching the model that those defects are "normal").
- Leakage control: augmented copies (same original filename stem) and identical images across datasets
  (difference hash, dHash) grouped with union-find; whole groups assigned to one split; stratified 70/20/10 by
  rarest class in each group. Val/test keep one image per original photo.
  Result: 13,332 images -> 4,041 unique groups; 441 groups were duplicates across datasets.
- Final: train 9,686 / val 918 / test 429 images. Script: `scripts/merge_datasets.py`.
- Limitation: public labels contain noise (e.g. occasional wrong class); test split comes from the same
  sources as training -> an additional test on own, unseen fabric is needed.

## 1b. YOLO training results (test split, 429 images) - `results/colab_test_results.csv`
| Run | Model | imgsz | P | R | mAP50 | mAP50-95 | hole | stain | slub | broken | ms/img (T4) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | YOLO11n | 640 | 0.577 | 0.455 | 0.469 | 0.260 | 0.640 | 0.606 | 0.213 | 0.417 | 4.6 |

Confusion matrix (R1, normalised by true class): correct hole 0.73, stain 0.74, slub 0.58, broken 0.60;
missed (predicted background) 0.13 / 0.18 / 0.26 / 0.32; confusion between defect classes mostly <= 0.07.
Interpretation: classes are well separated; the main errors are missed thin/small defects and false alarms
(stain, broken_pick_end). slub_neps AP is low despite 58% matched detections -> poor box agreement, likely
inconsistent slub/nep labelling across 4 source datasets. Motivates R4 (960 px) and per-source analysis.

Training history R1 (`results/R1_training_curves.png`, 80 epochs, 3.3 h on T4): val mAP50 plateaued at
~0.49 from epoch ~58 (best 0.490 at epoch 75; +0.001 over the last 20 epochs). Train losses kept falling while
val losses flattened (train cls 1.35 -> 1.02, val 1.73 -> 1.67): the model starts to fit the training set
but validation does not get worse, so no harmful overfitting; more epochs would not help this model.
Precision rose to 0.70 while recall stayed ~0.43-0.46 -> recall (missed defects) is the bottleneck.
Val mAP50 (0.49) ~ test mAP50 (0.469) -> consistent splits, supports the leakage-controlled split.
The sharp train cls-loss drop at epoch 71 is due to mosaic augmentation being switched off (close_mosaic=10).

## 1c. Error analysis -> dataset v2 (label cleaning)
Per-source test analysis of R1 (`scripts/analyse_model.py`, `results/R1_per_source.csv`) showed very uneven
performance: mAP50 0.81-0.86 on clean single-domain sources (defect-detection-xmqul, Moratuwa stain,
projectcollege) but 0.09-0.40 on sources where many labels had been dropped during class mapping.
Cause: images that contained BOTH a used class and a dropped class (Knot, loose-thread, Thick-Missing yarn...)
were kept with partial labels, so visible defects were unlabelled = treated as background (label noise in
training AND wrong ground truth in test).
v2 (`scripts/make_v2.py`): removed all 1,050 partially-labelled images (661 from fabric-defects-77bcs);
split assignment of the remaining images unchanged -> fair comparison. v2: train 8,788 / val 809 / test 386.
Same R1 model evaluated on the cleaner v2 test set: mAP50 0.468 -> 0.528, mAP50-95 0.259 -> 0.292,
slub F1 0.30 -> 0.37 (part of the low score was wrong test ground truth). Retraining on v2 = run R1v2.
Remaining weak sources: fabric-defects-77bcs (garments/seams, different domain, mAP50 0.15) and AITEX
(4096x256 strips: defects become too thin when resized to 640 px).
Best confidence threshold for the app (max mean F1 on test): 0.23.

## 1d. R1v2: effect of training on the cleaned data (v2)
Same model/settings as R1 (YOLO11n, 640 px, 80 epochs), trained on v2. Both models tested on the v2 test set
(386 images, identical settings):

| Model | Train data | P | R | mAP50 | mAP50-95 | hole | stain | slub | broken |
|---|---|---|---|---|---|---|---|---|---|
| R1 | v1 | 0.597 | 0.510 | 0.528 | 0.292 | 0.715 | 0.655 | 0.286 | 0.458 |
| R1v2 | v2 | 0.622 | 0.472 | 0.522 | 0.289 | 0.689 | 0.647 | 0.286 | 0.465 |

Result: no meaningful difference (all within +-0.03). Removing 1,050 partially-labelled images reduced label
noise but also reduced training data (slub boxes 2,306 -> 1,765; broken pick/end 2,721 -> 1,860); the effects
cancelled out. Training curve: val mAP50 plateau 0.55-0.57 from epoch ~55 (best 0.568 at epoch 70), train loss
still falling, val loss flat -> the YOLO11n/640 model is at its limit on this data.
Quality gate (test mAP50 >= 0.60) not met; weakest classes are the small/thin ones (slub/neps, broken pick/end).
Next experiment: R5v2 = YOLO11n at 960 px (only resolution changed) to measure the effect of resolution.

R1v2 error analysis (`results/R1v2_per_source.csv`, `scripts/scope_check.py`): best mean-F1 confidence 0.33.
Per-source mAP50 on the VALIDATION split (decision basis): yvkgj 0.995, xmqul 0.835, Moratuwa 0.779,
erdgo 0.543, labelled-data 0.306, stage2_ra_m 0.268, fabric-defects-77bcs 0.091, AITEX 0.000 (10 images).
Visual audit of fabric-defects-77bcs (`results/scope_check/77bcs_samples.jpg`): printed/patterned, mostly
crumpled fabrics with heavy noise augmentation; many boxes mark print motifs/borders rather than visible
defects (e.g. rows of "hole" boxes on a printed border, ~20 stacked "broken" boxes on a pattern).
Decision: dataset v3 = v2 without fabric-defects-77bcs (label quality; decided on validation + audit, not test).
For transparency only: R1v2 test mAP50 without that source = 0.595 (vs 0.522 with it).
Trade-off: v3 has fewer printed/patterned fabrics -> own photos of prints needed later.
v3: train 8,117 / val 733 / test 347 images (`data/merged_v3`, `upload/fabric4_v3.zip`).

## 2. Shade variation (CIELAB delta E) - `src/shade/delta_e.py`
- RGB -> CIELAB (sRGB, D65), light Gaussian blur and region averaging remove yarn texture.
- Reference (approved shade) vs test area; metrics: dE CMC(2:1) (pass/fail, textile standard, ISO 105-J03),
  dE2000 and dE*ab (reported), dL/dC/dH direction (darker/lighter, duller/brighter, hue).
- Heat map: per-cell dE CMC against reference; cells above tolerance outlined.
- Approximate ISO 105-A02 grey-scale grade from dE*ab.
- Optional white-paper correction (von Kries-type channel scaling in linear RGB).
- Validation:
  - 60 synthetic textured pairs, true dE CMC 0.08-7.34: MAE 0.002, max 0.008, pass/fail agreement 100%
    (verifies the computation pipeline).
  - Colour-cast test: true 1.58; with yellow cast 0.75; after white-paper correction 1.27 (partial recovery).
  - 49 web photos of "shade variation" (crumpled fabric, folds, shadows) could NOT be used for validation:
    lighting differences dominated (dE higher inside labelled area in only 24%).
- Conclusion / limitation: a camera is not a spectrophotometer; only relative comparison within one photo,
  flat fabric, even diffuse light. Planned: compare with spectrophotometer dE on own samples.

## 3. Bow and skew - `src/skew/bow_skew.py`
- Definitions per ASTM D3882 / ISO 13015: skew % = d/W x 100, bow % = depth/W x 100.
- Main method: projection-profile (Radon-type). In each of 7 vertical strips the image is sheared over
  -12..+12 deg (0.25 deg coarse, 0.02 deg fine + parabolic peak refinement); the angle giving the sharpest
  row-sum stripe pattern (max variance of the profile derivative) is the local weft angle.
  Local slopes are integrated into the weft-line shape; chord slope -> skew, max deviation from chord -> bow.
- Cross-check: global angle from the 2-D FFT peak.
- Why not Hough: Hough needs edge detection thresholds and detects individual line segments, which is
  fragile on fine, low-contrast yarn texture; the projection method uses all pixels and is threshold-free.
- Validation on 80 synthetic woven textures (skew -5..8 %, bow -2..3 %, yarn spacing 6-12 px, noise,
  lighting gradient): skew MAE 0.10 %-points (max 0.56), bow MAE 0.05 (max 0.24). FFT skew MAE 0.53
  (max 2.36) - FFT only gives one global angle and is disturbed by bow, so it is a cross-check only.
- Assumptions: camera straight above and aligned with selvedge; weft roughly horizontal (or set weft="vertical").

## 3b. Application - `src/app/engine.py` (analysis), `src/app/main.py` (GUI), `run_app.bat`
- Windows PyQt6 app: frameless always-on-top bubble (drag, snaps to screen edge, coloured badge = worst
  severity of the last result) opens a panel with Upload image / Select screen area (Qt screen grab,
  DPI-aware), checks: local defects (YOLO), shade (dE), bow/skew; settings: confidence (default 0.23 =
  max-F1 threshold), image scale px/mm (for 4-point scoring), shade tolerance, bow/skew limits, weft
  direction, model file. Results: annotated views (defects / shade heat map / weft line) + findings sorted by
  severity with causes, remedy, prevention; reports saved to results/reports/<timestamp>/ (jpg, txt, html).
- Analysis runs in a background thread (UI never freezes). Engine is GUI-free and tested separately.
- Design decision: shade analysis excludes areas of detected local defects (otherwise a stain is also
  reported as shade variation = double counting).
- Speed on the student PC (CPU, GTX 1630 not used): YOLO11n detection 40-65 ms per image; detection +
  shade + bow/skew ~0.7 s.

## 3c. Cross-platform web app (PC + Android), on-device inference - `web_static/`
- Live: https://mhdi009-fabric-defect-inspector.static.hf.space (free static Hugging Face Space)
- The whole pipeline runs in the browser: YOLO model exported to ONNX (opset 17, 10.7 MB) and executed with
  ONNX Runtime Web (WebAssembly); shade, bow/skew and knowledge base ported to JavaScript. No server, photos
  never leave the device (privacy), installable as a PWA, works offline after the first visit (service worker).
- Verification: ONNX model = PyTorch model on v2 test (mAP50 0.532 both). Browser vs Python on 24 real test
  images: 22/22 detections identical (same class, IoU > 0.8, confidence difference 0.000), shade dE identical;
  dE CMC / dE2000 / rgb2lab vs scikit-image max difference 1.6e-12; bow/skew identical to Python on synthetic
  fabric (MAE vs truth: skew 0.016, bow 0.061 %-points). `tests/test_static.py`, `tests/test_live.py`.
- Speed: ~0.3-0.55 s per photo incl. shade (single-thread WASM, test PC); first visit downloads ~26 MB.
- Reason for this design: Python app hosting (Gradio Space) requires a paid plan; static hosting is free.

## 4. Knowledge base - `src/knowledge/knowledge_base.yaml`, `kb.py`
- 7 defect types: 4 detected (YOLO) + shade variation, bowing, skewing. Each: description, causes with
  process stage (spinning, sizing, weaving, pretreatment, dyeing, finishing, handling), remedy, prevention,
  severity rule.
- Severity: ASTM D5430 4-point system when image scale (px/mm) is known (1-2 points = minor, 3 = major,
  4 = critical; holes always >= major); fallback on relative defect size when no scale. Shade: multiples of
  dE tolerance. Bow/skew: buyer limits (default 2 % / 3 %).
- Broken pick vs broken end separated by box orientation (horizontal = weft/pick, vertical = warp/end).
- Rule-based for explainability and repeatability; an optional LLM may only rephrase this content.
- 26 automatic checks pass (`tests/test_modules.py`), incl. 4-point boundaries (found and fixed a
  floating-point error at exactly 3 inches).
