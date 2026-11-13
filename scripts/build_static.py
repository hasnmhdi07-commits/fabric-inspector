"""Build the in-browser web app folder (web_static/): knowledge base JSON, model, ONNX Runtime Web files,
icons, PWA manifest, offline service worker, Hugging Face static-Space README.
Usage: python scripts\\build_static.py [path\\to\\model.pt]
"""
import hashlib, json, shutil, sys, urllib.request
from pathlib import Path
import cv2
import numpy as np
import yaml

ROOT = Path(r"C:\thesis")
OUT = ROOT / "web_static"
ORT_VER = "1.31.1"
ORT_FILES = ["ort.wasm.min.mjs", "ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm"]

# 1. model (re-export only if a .pt is given)
if len(sys.argv) > 1:
    from ultralytics import YOLO
    p = YOLO(sys.argv[1]).export(format="onnx", imgsz=640, opset=17, simplify=True, dynamic=False)
    (OUT / "model").mkdir(parents=True, exist_ok=True)
    shutil.copy(p, OUT / "model" / "best.onnx")
    print("model exported from", sys.argv[1])

# 2. knowledge base as JSON (single source of truth stays the YAML file)
kb = yaml.safe_load((ROOT / "src" / "knowledge" / "knowledge_base.yaml").read_text(encoding="utf-8"))
(OUT / "kb.json").write_text(json.dumps(kb, ensure_ascii=False, indent=1), encoding="utf-8")

# 3. ONNX Runtime Web (pinned version, downloaded once)
(OUT / "ort").mkdir(exist_ok=True)
for f in ORT_FILES:
    dst = OUT / "ort" / f
    if not dst.exists():
        url = f"https://cdn.jsdelivr.net/npm/onnxruntime-web@{ORT_VER}/dist/{f}"
        with urllib.request.urlopen(url, timeout=120) as r:
            dst.write_bytes(r.read())
        print("downloaded", f, f"{dst.stat().st_size / 1e6:.1f} MB")

# 3b. compatibility engine for devices WITHOUT WebAssembly SIMD (e.g. iPhone with iOS < 16.4):
#     onnxruntime-web 1.18.0 is the last release that ships a non-SIMD build. Loaded only when needed.
LEGACY_VER, LEGACY_FILES = "1.18.0", {"esm/ort.wasm.min.js": "ort.wasm.min.js", "ort-wasm.wasm": "ort-wasm.wasm"}
(OUT / "ort-legacy").mkdir(exist_ok=True)
for src, name in LEGACY_FILES.items():
    dst = OUT / "ort-legacy" / name
    if not dst.exists():
        with urllib.request.urlopen(f"https://cdn.jsdelivr.net/npm/onnxruntime-web@{LEGACY_VER}/dist/{src}", timeout=120) as r:
            dst.write_bytes(r.read())
        print("downloaded legacy", name, f"{dst.stat().st_size / 1e6:.1f} MB")

# 4. examples
shutil.copytree(ROOT / "web" / "examples", OUT / "examples", dirs_exist_ok=True)

# 5. icons: the pick glass (thread-counting lens with a 5 mm reticle and a chalk-yellow handle) on fern green
(OUT / "icons").mkdir(exist_ok=True)
for size in (192, 512):
    S = 4                                                   # draw 4x larger, then shrink = smooth edges
    n, k = size * S, size * S / 54.0
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    d = np.clip(np.hypot(xx - 0.35 * n, yy - 0.30 * n) / (0.75 * n), 0, 1)[..., None]
    c0, c1, c2 = (np.array(c, np.float32) for c in ((141, 207, 134), (108, 185, 99), (72, 143, 63)))   # BGR
    im = np.where(d < .45, c0 + (c1 - c0) * d / .45, c1 + (c2 - c1) * (d - .45) / .55).astype(np.uint8)
    im = np.ascontiguousarray(im)
    P = lambda x, y: (int(round(x * k)), int(round(y * k)))
    W = (255, 255, 255)
    cv2.circle(im, P(27, 27), int(15 * k), W, max(1, int(2.0 * k)), cv2.LINE_AA)
    for a, b in (((16, 27), (38, 27)), ((27, 16), (27, 38))):
        cv2.line(im, P(*a), P(*b), (215, 240, 212), max(1, int(0.9 * k)), cv2.LINE_AA)
    for i in range(6):
        x = 18.25 + i * 3.5
        cv2.line(im, P(x, 27), P(x, 27 - (4.5 if i % 5 == 0 else 2.7)), W, max(1, int(1.0 * k)), cv2.LINE_AA)
    cv2.line(im, P(38, 38), P(43, 43), (69, 191, 240), max(1, int(3.6 * k)), cv2.LINE_AA)
    cv2.imwrite(str(OUT / "icons" / f"icon-{size}.png"), cv2.resize(im, (size, size), interpolation=cv2.INTER_AREA))

# 6. PWA manifest
(OUT / "manifest.webmanifest").write_text(json.dumps({
    "name": "Fabric Inspector", "short_name": "Fabric Inspector", "start_url": "./", "scope": "./",
    "display": "standalone", "background_color": "#ffffff", "theme_color": "#2f7d3b",
    "description": "AI fabric defect detection with causes and remedies - runs on your device",
    "icons": [{"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
              {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}],
}, indent=1), encoding="utf-8")
# 7. service worker: cache everything for offline use; cache name changes when any file changes
all_files = sorted(p.relative_to(OUT).as_posix() for p in OUT.rglob("*")
                   if p.is_file() and p.name not in ("sw.js", "README.md", ".gitattributes"))
files = [f for f in all_files if not f.startswith("ort-legacy/")]   # legacy engine: cached only when used
h = hashlib.sha1(b"sw-logic-v3")      # bump when the service-worker logic below changes
for f in all_files:
    h.update((OUT / f).read_bytes())
version = h.hexdigest()[:10]
# Notes: the host answers "/" with a redirect to /index.html. A cached *redirected* response must never be
# returned for a page navigation (browsers fail with ERR_FAILED), so: page loads = network first, offline
# fallback = cached index.html; other files = cache first. "./" itself is never cached.
(OUT / "sw.js").write_text(f"""// Offline cache (generated by build_static.py) - version {version}
const CACHE = "fdi-{version}";
const FILES = {json.dumps(files)};
const clean = (r) => (r && r.redirected ? r.blob().then((b) => new Response(b, {{ status: 200, headers: r.headers }})) : r);
self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES)).then(() => self.skipWaiting())));
self.addEventListener("activate", (e) => e.waitUntil(caches.keys().then((ks) =>
  Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", (e) => {{
  const req = e.request;
  if (req.method !== "GET") return;
  if (req.mode === "navigate") {{                       // page load: online first, offline fallback
    e.respondWith(fetch(req).catch(() => caches.match("index.html").then(clean)));
    return;
  }}
  e.respondWith(caches.match(req, {{ ignoreSearch: true }}).then((r) => r ? clean(r) : fetch(req).then((res) => {{
    // cache files fetched later (e.g. the compatibility engine on older phones) for offline use
    if (res.ok && !res.redirected && new URL(req.url).origin === location.origin) {{
      const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy));
    }}
    return res;
  }})));
}});
""", encoding="utf-8")

# 8. Hugging Face static Space README
(OUT / "README.md").write_text("""---
title: Fabric Defect Inspector
emoji: 🧵
colorFrom: indigo
colorTo: gray
sdk: static
app_file: index.html
pinned: false
license: cc-by-4.0
short_description: AI fabric defect detection with causes and remedies
---

# Fabric Defect Inspector

Thesis prototype: *Fabric defect detection with AI cause/remedy analysis*. The whole analysis runs **in the
browser** (ONNX Runtime Web): YOLO11 defect detection, CIELAB shade check, weft bow/skew measurement and a
rule-based knowledge base. Photos never leave the device; the app can be installed and works offline.

Training data: Fabric Stain Dataset (University of Moratuwa, CC0) and Roboflow Universe projects (CC BY 4.0) by
aitex-data-set-waiandt, fault-annotations, pulak-deb-roy, defects-zxmr5, defect-dataset, projectcollege-msi80,
fabric-defect-detection-6xxtk. Example images: Fabric Stain Dataset (CC0), defects-zxmr5 (CC BY 4.0), synthetic.
""", encoding="utf-8")

size = sum((OUT / f).stat().st_size for f in files) / 1e6
print(f"web_static ready: {len(all_files)} files ({len(files)} pre-cached, {size:.1f} MB), cache version {version}")
