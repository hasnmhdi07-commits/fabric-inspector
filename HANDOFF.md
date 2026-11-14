# Fabric Inspector: project handoff

Written 2026-11-14. Read this first when continuing the project in a new Claude session.
To continue, open the folder `C:\thesis` in Claude Code and say: "Read HANDOFF.md and continue."

## 1. What the project is

Thesis: "Fabric defect detection with AI cause/remedy analysis".
The app photographs fabric, finds defects with a YOLO11 model, and gives severity, likely causes, remedy and
prevention from a rule-based knowledge base. It never invents causes.

- 4 defect classes: `hole_tear`, `stain`, `slub_neps`, `broken_pick_end`
- Extra checks: shade (ΔE CMC 2:1) and bow/skew (ASTM D3882 definitions)
- Severity: ASTM D5430 4-point system when the image scale (px/mm) is known, otherwise relative size
- Verdict has three states: `defects`, `none`, `cannot` (photo too dark / bright / blurred / small).
  The app never says "acceptable" for a whole fabric.
- Design: the "fern" theme (green #2f7d3b, pick-glass icon). Spec: `thesis_docs/app_spec_v2.md`.
- Method notes for the thesis text: `thesis_docs/methods_notes.md` (section 1e = dataset v4).

## 2. Where everything lives

| What | Where |
|---|---|
| Live web app | https://fabric-inspector.vercel.app |
| Android APK download | https://fabric-inspector.vercel.app/download/FabricInspector.apk |
| iPhone setup guide | https://fabric-inspector.vercel.app/iphone.html |
| Server API | `POST https://fabric-inspector.vercel.app/api/analyze` (add `?format=html` for a result page), `GET /api/health` |
| GitHub repo | https://github.com/hasnmhdi07-commits/fabric-inspector (branch `main`) |
| Vercel project | `fabric-inspector`, region Mumbai (`bom1`) |

Folders in `C:\thesis`:

- `web_static/` : the web app (also the main screen of the Android app). `js/app.js` (UI + engine),
  `js/detector.js`, `js/shade.js`, `js/skew.js`, `js/kb.js`, `js/verdict.js`, `js/camera.js`, `js/store.js`,
  `css/app.css`, `model/best.onnx`, `sw.js` (generated).
- `server/` + `api/index.mjs` : Express API on Vercel. It reuses the same JavaScript engine as the web app.
- `android/` : native Kotlin app (no libraries). `MainActivity.kt` hosts the web app in a WebView;
  `BubbleService.kt` is the floating bubble.
- `src/app/` : Windows PyQt6 bubble app (`main.py`, `engine.py`, `verdict.py`, `report_html.py`).
- `scripts/` : `build_static.py`, `make_v4.py` (dataset), `make_colab_notebook.py`.
- `notebooks/train_colab.ipynb` : Colab training notebook.
- `data/`, `upload/`, `runs/`, `venv/`, `node_modules/` : not in git.
- `hf_token.txt`, `roboflow_key.txt` : credential files. Never open, commit or upload them.

## 3. What is finished

**Web app (v3, live).** Live camera with torch and camera switch, photo upload, drag-and-drop and paste,
select-area (crop taken from the full-resolution photo), tappable numbered boxes linked to finding cards,
history of the last 60 checks (on the device only), share and report export, settings screen, animations,
works offline after the first visit.
Floating bubble (`js/bubble.js`, added 2026-11-14): in Chrome/Edge on a computer it is a small always-on-top
window (Document Picture-in-Picture). "Select area" captures the screen (the browser asks once), shows it
frozen in a full-screen window, the user drags a box, and the AI checks it on the device; the result shows in
the floating window and in the app. Other browsers get a draggable bubble inside the page. Phone browsers
cannot draw over other apps, so there "Select area" works on the open photo. Quick actions everywhere: Select
area, Photo from gallery, Take photo, Open Fabric Inspector, last check, Hide bubble, Turn off.

**Android app 0.4 (emulator-tested 2026-11-14).** Bubble on/off is a switch in Settings (no card on the Scan
screen). Switching on asks for all permissions in one go and continues by itself after "Display over other apps";
the screen-capture consent is an Android rule and appears each time the bubble starts (Android 14+: whole screen
only, no "single app" choice). Select area now opens the full app with the area as the photo, checked on the phone
(no server). Phones with app 0.1/0.2 must install the new APK.
**Android app 0.3.** Tapping the bubble opens the same Quick actions panel
(gallery/camera open the app and check on the phone; Hide bubble keeps capture on and the notification gets
"Show bubble"). "Take photo" needs the web app deployed with the `('action', 'camera')` handler.
**Android app 0.2.** Main screen is the web app with the AI running on the phone; floating bubble
over other apps (select an area, sent to the server); receives photos shared from other apps; Android share
sheet. First start needs internet (about 27 MB). The app loads the web app from the live site, so a new
model reaches phones without a new APK.

**Server API.** Stateless, stores nothing. Same results as the browser engine.

**Windows app.** Fern restyle done; runs from source, not packaged as an installer.

**iPhone.** No native app (Apple does not allow a bubble). Uses AssistiveTouch + a Shortcut that posts a
screenshot to the API; the guide page explains the setup.

**Dataset v4.** `upload/fabric4_v4.zip` (618 MB): train 5,901 / val 804 / test 402 images.
Fixes over v3: line-scan strips cut into full-resolution tiles, neps and thick yarn now mapped (they were
dropped before), knots merged into `slub_neps`, at most 4 copies per photo. No v3 test or validation photo
is in v4 training.

## 4. Model status

- **Current model: R5v4** (YOLO11n, 960 px, 80 epochs on dataset v4), file `models/bestr5.pt`,
  exported to `web_static/model/best.onnx` and `models/best.onnx` at 960 px (10.9 MB).
- **Quality gate met:** test mAP@0.5 = 0.619 on the v4 test set (gate 0.60). Per class AP50: hole_tear 0.768,
  stain 0.725, slub_neps 0.464, broken_pick_end 0.518; precision 0.648, recall 0.587
  (`results/test_results_fabric4_v4.csv`, `results/colab_test_results.csv`). Best val mAP50 0.682 near epoch 70.
- Earlier runs: R1 0.469 (v1 test), R1v2 0.522 (v2 test). The test sets differ per dataset version; for a fair
  comparison in the thesis, also evaluate R5v4 on the v2 test set.
- Speed (WebAssembly, 1 thread, this PC): 0.58 s per photo at 960 px vs 0.25 s for the old 640 px model.
- The input size is read from the model file everywhere (browser/server: `modelSize()` in `detector.js` reads the
  Ultralytics `imgsz` metadata; Windows app: the ONNX input shape). `build_static.py` exports at the training size.
- Possible next runs: R4 (YOLO11s at 960) as the accuracy reference; own fabric photos for training/testing.

**When a new `best.pt` arrives:**

```
venv\Scripts\python.exe scripts\build_static.py path\to\best.pt        # exports at its training size
```

Then run the tests and deploy (section 5). The headless-Edge test profile keeps an offline copy: delete its
`edge_cdp` folder (path in `tests/test_static.py`) before the parity test after a model change.

## 5. How to build, test and deploy

Node and Git are installed but may not be on PATH in a new shell:

```
$env:Path = "C:\Program Files\nodejs;C:\Program Files\Git\cmd;$env:Path"
```

**After any change in `web_static/`** (required, it regenerates the offline cache list):

```
venv\Scripts\python.exe scripts\build_static.py
```

**Tests:**

```
node server\test_api.mjs                      # 17 server tests
venv\Scripts\python.exe tests\test_verdict.py # 30 verdict checks, Python = JavaScript
venv\Scripts\python.exe tests\test_static.py  # browser vs Python parity in headless Edge
venv\Scripts\python.exe tests\test_bubble.py  # web bubble, menu, screen capture, area picker
venv\Scripts\python.exe tests\test_live.py https://fabric-inspector.vercel.app
node server\test_live.mjs                     # 6 live API tests
```

**Deploy:** commit, push, then

```
npx --yes vercel deploy --prod --yes
```

Git commits use the author `hasnmhdi07-commits` with the address
`hasnmhdi07-commits@users.noreply.github.com` (keep the personal email out of commits).

**Android build:**

```
cd C:\thesis\android
$env:JAVA_HOME='C:\android-dev\jdk'; $env:ANDROID_HOME='C:\android-dev\sdk'
C:\android-dev\gradle-8.7\bin\gradle.bat --no-daemon -q assembleDebug
```

Then copy `android\app\build\outputs\apk\debug\app-debug.apk` to
`web_static\download\FabricInspector.apk`, run `build_static.py`, and deploy.

**Android emulator** (AVD `fabric34`, start it with `Start-Process`, it exits when run as a background task):

```
$env:ANDROID_AVD_HOME='C:\android-dev\avd'
Start-Process C:\android-dev\sdk\emulator\emulator.exe -ArgumentList '-avd','fabric34','-no-snapshot-save','-no-audio','-no-boot-anim'
C:\android-dev\sdk\platform-tools\adb.exe install -r <apk>
```

## 6. Things that are easy to break

- `server/result_page.mjs` and `web_static/iphone.html` both use `web_static/css/app.css`. After a style
  change, look at both pages.
- The web engine and the Python engine must give the same results (thesis claim). Do not change resizing or
  pre-processing on one side only; `tests/test_static.py` checks this.
- Renaming or restructuring web files: phones keep the old version cached. The page reloads itself when a
  new offline cache takes over, and `sw.js` downloads files one by one with retries.
- Vercel request body limit is 4.5 MB (server allows 4.4 MB).
- The duplicate Vercel projects `fabric-inspector-6zh5` and `fabric-inspector-pt6k` are unused leftovers.
  Delete them only if the user says so.

## 7. Not done yet

1. Train on dataset v4 and swap the new model in (section 4). This is the most important step.
2. Test on real phones: the new APK (camera, upload, bubble) and the iPhone Shortcut. So far the APK was
   tested only on the emulator; "Upload photo" inside the APK and the bubble's select-and-analyse step were
   not re-tested in version 0.2.
3. Bangla (EN / বাংলা) on all platforms. Claude drafts, the user reviews the textile terms.
4. Own fabric photos for training and testing (the public data does not look like the user's fabric).
5. Windows installer; on-device analysis for the Android bubble (it uses the server now).
6. Open questions for the user: keep knots inside `slub_neps` (rebuild with `--no-knots` to undo)?
   Delete the two duplicate Vercel projects?
