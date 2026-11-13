"""Check the published app: files reachable with correct types, then load it in headless Edge and analyse an example.
Usage: python tests\\test_live.py <app-url>"""
import json, subprocess, sys, time, urllib.request
import websocket

URL = sys.argv[1].rstrip("/") + "/"
for f, want in [("", "text/html"), ("js/app.js", "javascript"), ("ort/ort.wasm.min.mjs", "javascript"),
                ("ort/ort-wasm-simd-threaded.wasm", "application/wasm"), ("model/best.onnx", ""),
                ("manifest.webmanifest", ""), ("sw.js", "javascript"), ("kb.json", "json")]:
    for attempt in range(30):
        try:
            r = urllib.request.urlopen(URL + f, timeout=60)
            ct, n = r.headers.get("Content-Type", ""), len(r.read())
            print(f"{'OK ' if want in ct else 'BAD'} {f or 'index.html':34} {r.status} {ct:28} {n / 1e6:6.2f} MB")
            break
        except Exception as e:
            if attempt == 29: print("FAIL", f, e)
            time.sleep(10)

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
prof = r"C:\Users\User\AppData\Local\Temp\claude\ec29f026d20d029c\27709ee3-7185-49e6-a3d8-856c0287e50b\scratchpad\edge_live"
p = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--remote-debugging-port=9334", f"--user-data-dir={prof}", "about:blank"])
try:
    for _ in range(50):
        try: tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9334/json")); break
        except Exception: time.sleep(0.3)
    ws = websocket.create_connection([t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"], timeout=300)
    i = 0
    def cdp(m, **k):
        global i; i += 1; ws.send(json.dumps({"id": i, "method": m, "params": k}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == i: return r.get("result", {})
    def js(e):
        r = cdp("Runtime.evaluate", expression=e, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r: raise RuntimeError(json.dumps(r["exceptionDetails"])[:500])
        return r["result"].get("value")
    cdp("Page.enable"); cdp("Emulation.setDeviceMetricsOverride", width=412, height=915, deviceScaleFactor=2, mobile=True)
    t0 = time.time(); cdp("Page.navigate", url=URL)
    for _ in range(600):
        time.sleep(0.25)
        try:
            if js("!!window.fabricApp"): break
        except Exception: pass
    js("window.fabricApp.ready.then(()=>true)")
    print(f"live page + AI model ready in {time.time() - t0:.1f} s (first visit, phone emulation)")
    r = js("window.fabricApp.analyseUrl('examples/hole_example.jpg', {})")
    print("hole example ->", [(x["defect"], x["severity"], round(x["confidence"], 2)) for x in r["items"]], f"{sum(r['timings'].values()):.0f} ms")
    time.sleep(3)
    print("offline cache (service worker) active:", js("navigator.serviceWorker.getRegistration().then(r => !!(r && r.active))"))
    print("status line:", js("document.getElementById('status').textContent"))
    # repeat visits now go through the service worker (this is what failed before): reload twice, also via "/"
    for k in range(2):
        cdp("Page.navigate", url=URL); time.sleep(1)
        for _ in range(200):
            time.sleep(0.25)
            try:
                if js("!!window.fabricApp"): break
            except Exception: pass
        ok = js("window.fabricApp.ready.then(()=>document.getElementById('status').textContent)")
        sw = js("navigator.serviceWorker.controller ? 'via service worker' : 'direct'")
        print(f"repeat visit {k + 1}: {ok} ({sw})")
finally:
    p.kill()
