"""Parity + function test of the in-browser app (web_static) against the Python implementation.
Runs the real page in headless Edge (Chrome DevTools Protocol) and compares results image by image.
Usage: venv\\Scripts\\python.exe tests\\test_static.py
"""
import json, subprocess, sys, time, base64, urllib.request
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
import websocket
from skimage.color import deltaE_cmc, deltaE_ciede2000

ROOT = Path(r"C:\thesis"); sys.path.insert(0, str(ROOT))
OUT = ROOT / "results" / "app_test"; OUT.mkdir(parents=True, exist_ok=True)
SCR = Path(r"C:\Users\User\AppData\Local\Temp\claude\ec29f026d20d029c\27709ee3-7185-49e6-a3d8-856c0287e50b\scratchpad")
PORT, DBG = 8765, 9333
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i + 1e-9)


srv = subprocess.Popen([sys.executable, str(ROOT / "tests" / "serve_static.py"), str(PORT), str(ROOT)])
edge = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", f"--remote-debugging-port={DBG}",
                         f"--user-data-dir={SCR / 'edge_cdp'}", "about:blank"])
try:
    for _ in range(50):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{DBG}/json")); break
        except Exception:
            time.sleep(0.3)
    ws = websocket.create_connection([t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"], timeout=600)
    msg_id, console = 0, []

    def cdp(method, **params):
        global msg_id
        msg_id += 1; ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
        while True:
            m = json.loads(ws.recv())
            if m.get("method") == "Runtime.exceptionThrown":
                console.append("EXCEPTION " + json.dumps(m["params"]["exceptionDetails"])[:400])
            elif m.get("method") == "Runtime.consoleAPICalled" and m["params"]["type"] in ("error", "warning"):
                console.append(" ".join(str(a.get("value", a.get("description", ""))) for a in m["params"]["args"])[:300])
            if m.get("id") == msg_id:
                if "error" in m: raise RuntimeError(m["error"])
                return m["result"]

    def js(expr):
        r = cdp("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r: raise RuntimeError(json.dumps(r["exceptionDetails"])[:800])
        return r["result"].get("value")

    cdp("Runtime.enable"); cdp("Page.enable")
    QUERY = "?legacy=1" if "--legacy" in sys.argv else ""          # force the no-SIMD compatibility engine
    cdp("Page.navigate", url=f"http://127.0.0.1:{PORT}/web_static/index.html{QUERY}")
    t0 = time.time()
    for _ in range(600):
        time.sleep(0.2)
        try:
            if js("!!(window.fabricApp)"): break
        except Exception: pass
    js("window.fabricApp.ready.then(() => true)")
    print(f"page + model ready in {time.time() - t0:.1f} s; engine: {js('window.fabricApp.backend()')}; "
          f"status: {js('document.getElementById(`status`).textContent')}")
    if "--quick" in sys.argv:
        r = js("window.fabricApp.analyseUrl('/web_static/examples/hole_example.jpg', {doShade:true, doSkew:true})")
        print("hole example:", [(x["defect"], x["severity"], round(x["confidence"], 3) if x["confidence"] else None) for x in r["items"]],
              {k: round(v) for k, v in r["timings"].items()})

    # ---------- 1. delta E formulas vs skimage
    rng = np.random.default_rng(1)
    P = np.c_[rng.uniform(5, 95, 300), rng.uniform(-60, 60, 300), rng.uniform(-60, 60, 300)]
    Q = P + rng.normal(0, 3, P.shape)
    res = np.array(js(f"import('/web_static/js/shade.js').then(m => {json.dumps(np.stack([P, Q], 1).tolist())}"
                      f".map(([p,q]) => [m.deltaECMC(p,q,2,1), m.deltaE2000(p,q), ...m.rgb2lab(0.2,0.5,0.7)]))"))
    ref_cmc = deltaE_cmc(P[:, None], Q[:, None], kL=2, kC=1)[:, 0]
    ref_00 = deltaE_ciede2000(P[:, None], Q[:, None])[:, 0]
    from skimage.color import rgb2lab
    print(f"dE CMC max abs diff vs skimage {np.abs(res[:, 0] - ref_cmc).max():.2e}; dE2000 {np.abs(res[:, 1] - ref_00).max():.2e}; "
          f"rgb2lab {np.abs(res[0, 2:] - rgb2lab(np.array([[[0.2, 0.5, 0.7]]]))[0, 0]).max():.2e}")

    # ---------- 2. knowledge base rules
    kbres = js("import('/web_static/js/kb.js').then(m => [m.fourPoint(76.2), m.fourPoint(76.3), m.fourPoint(25.4,true), m.fourPoint(26,true), m.fourPoint(229)])")
    print("4-point boundaries JS:", kbres, "(expected [1, 2, 2, 4, 4])")

    # ---------- 3. full pipeline parity on real images
    from src.app.engine import Analyzer, Settings
    py = Analyzer(ROOT / "web_static" / "model" / "best.onnx")
    man = pd.read_csv(ROOT / "data" / "merged_v2" / "manifest.csv")
    test = man[(man.split == "test") & (man.n_boxes > 0)].groupby("source").head(3)
    rows = []
    for _, r in test.iterrows():
        rel = f"data/merged_v2/images/test/{r.file}"
        j = js(f"window.fabricApp.analyseUrl('/{rel}', {{doShade:true}})")
        p = py.analyse(cv2.imread(str(ROOT / rel)), Settings(do_shade=True))
        jd = [i for i in j["items"] if i.get("box")]; pd_ = [i for i in p.items if "box" in i]
        matched, cdiff = 0, []
        for a in pd_:
            best = max(jd, key=lambda b: _iou(a["box"], b["box"]) if b["defect"] == a["defect"] else -1, default=None) if jd else None
            if best and best["defect"] == a["defect"] and _iou(a["box"], best["box"]) > 0.8:
                matched += 1; cdiff.append(abs(a["confidence"] - best["confidence"]))
        jsh = next(i for i in j["items"] if i["defect"] == "shade_variation")["shade"]["dE_cmc21"]
        psh = next(i for i in p.items if i["defect"] == "shade_variation")
        rows.append(dict(source=r.source[:22], py_dets=len(pd_), js_dets=len(jd), matched=matched,
                         max_conf_diff=round(max(cdiff), 3) if cdiff else 0,
                         py_shade=round(float(psh["severity_basis"].split("= ")[1].split(" ")[0]), 2), js_shade=round(jsh, 2),
                         js_ms=round(sum(j["timings"].values()))))
    df = pd.DataFrame(rows); pd.set_option("display.width", 200)
    print(df.to_string(index=False))
    print(f"detections: python {df.py_dets.sum()}, browser {df.js_dets.sum()}, matched (same class, IoU>0.8) {df.matched.sum()}")

    # ---------- 4. bow/skew on synthetic fabric with known truth
    ns = {}; exec((ROOT / "tests" / "validate_skew.py").read_text().split("rows = []")[0], ns)
    sk_dir = OUT / "synthetic_skew"; sk_dir.mkdir(exist_ok=True)
    from src.skew.bow_skew import analyse_skew_bow
    errs = []
    for i, (s_true, b_true) in enumerate([(0, 0), (2, 0), (-3, 1), (5, 2), (1, -2), (8, 3)]):
        img = ns["synth_fabric"](s_true, b_true, weft_p=7 + i, warp_p=6 + i % 3, seed=i)
        cv2.imwrite(str(sk_dir / f"s{i}.png"), img)
        j = js(f"window.fabricApp.analyseUrl('/results/app_test/synthetic_skew/s{i}.png', {{doDefects:false, doSkew:true}})")
        jsk = next(x for x in j["items"] if x.get("skew"))["skew"]
        pr = analyse_skew_bow(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
        errs.append((abs(jsk["skewPct"] - s_true), abs(jsk["bowPct"] - b_true), abs(pr.skew_pct - s_true), abs(pr.bow_pct - b_true)))
        print(f"  true skew {s_true:+}% bow {b_true:+}% | browser {jsk['skewPct']:+.2f} {jsk['bowPct']:+.2f} | python {pr.skew_pct:+.2f} {pr.bow_pct:+.2f}")
    e = np.array(errs)
    print(f"bow/skew MAE vs truth - browser: skew {e[:, 0].mean():.3f}, bow {e[:, 1].mean():.3f} | python: skew {e[:, 2].mean():.3f}, bow {e[:, 3].mean():.3f}")

    # ---------- 5. UI screenshots (phone + PC) after clicking an example
    for name, w, h, mobile in (("static_phone", 412, 915, True), ("static_pc", 1366, 900, False)):
        cdp("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=mobile)
        cdp("Page.reload"); time.sleep(1)
        for _ in range(300):
            time.sleep(0.2)
            try:
                if js("!!window.fabricApp") and js("window.fabricApp.ready.then(()=>true)"): break
            except Exception: pass
        js("document.getElementById('chkShade').checked = true; document.querySelector('.example[data-src*=stain]').click(); true")
        for _ in range(200):
            time.sleep(0.2)
            if js("!document.getElementById('results').hidden && !window.fabricApp.busy()"): break
        time.sleep(1.5)                                             # let the result animations finish
        js("indexedDB.deleteDatabase('fabric-inspector'); window.scrollTo(0, 0); true")
        full_h = js("document.documentElement.scrollHeight")
        if not mobile: print(f"desktop page height {full_h} for a {h} px window:", "PASS fits without scrolling" if full_h <= h + 1 else "FAIL page scrolls")
        cdp("Emulation.setDeviceMetricsOverride", width=w, height=min(full_h, 4000), deviceScaleFactor=1, mobile=mobile)
        time.sleep(0.5)
        png = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=True)["data"]
        (OUT / f"{name}.png").write_bytes(base64.b64decode(png))
        print(f"screenshot {name}.png ({w}x{min(full_h, 4000)}); result: {js('document.querySelector(`#verdict b`).textContent')}")
    print("console errors/warnings:", console or "none")
finally:
    edge.kill(); srv.kill()
