"""Floating bubble of the web app in headless Edge: card, in-page bubble, quick-action menu, screen capture
(fake screen), the area picker (real mouse drag) and analysis of the selected area. Saves screenshots.
Usage: venv\\Scripts\\python.exe tests\\test_bubble.py
"""
import base64, json, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
import websocket

ROOT = Path(r"C:\thesis")
OUT = ROOT / "results" / "app_test"; OUT.mkdir(parents=True, exist_ok=True)
PORT, DBG = 8766, 9334
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
profile = tempfile.mkdtemp(prefix="edge_bubble_")
fails = []


def check(ok, what):
    print(("PASS " if ok else "FAIL ") + what)
    if not ok: fails.append(what)


srv = subprocess.Popen([sys.executable, str(ROOT / "tests" / "serve_static.py"), str(PORT), str(ROOT)])
edge = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", f"--remote-debugging-port={DBG}", f"--user-data-dir={profile}",
                         "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                         "--auto-select-desktop-capture-source=Entire screen", "--window-size=1280,860", "about:blank"])
try:
    for _ in range(50):
        try: tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{DBG}/json")); break
        except Exception: time.sleep(0.3)
    ws = websocket.create_connection([t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"], timeout=300)
    n, errors = 0, []

    def cdp(method, **params):
        global n
        n += 1; ws.send(json.dumps({"id": n, "method": method, "params": params}))
        while True:
            m = json.loads(ws.recv())
            if m.get("method") == "Runtime.exceptionThrown": errors.append(json.dumps(m["params"]["exceptionDetails"])[:300])
            if m.get("id") == n:
                if "error" in m: raise RuntimeError(m["error"])
                return m["result"]

    def js(expr):
        r = cdp("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True, userGesture=True)
        if "exceptionDetails" in r: raise RuntimeError(json.dumps(r["exceptionDetails"])[:600])
        return r["result"].get("value")

    def click(x, y):
        for t in ("mousePressed", "mouseReleased"):
            cdp("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)

    def drag(a, b, steps=8):
        cdp("Input.dispatchMouseEvent", type="mousePressed", x=a[0], y=a[1], button="left", clickCount=1)
        for i in range(1, steps + 1):
            cdp("Input.dispatchMouseEvent", type="mouseMoved", x=a[0] + (b[0] - a[0]) * i / steps, y=a[1] + (b[1] - a[1]) * i / steps, button="left", buttons=1)
        cdp("Input.dispatchMouseEvent", type="mouseReleased", x=b[0], y=b[1], button="left", clickCount=1)

    def center(sel):
        return js(f"(() => {{ const r = document.querySelector({json.dumps(sel)}).getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }})()")

    def shot(name):
        (OUT / name).write_bytes(base64.b64decode(cdp("Page.captureScreenshot", format="png")["data"]))

    cdp("Runtime.enable"); cdp("Page.enable")
    cdp("Emulation.setDeviceMetricsOverride", width=1280, height=860, deviceScaleFactor=1, mobile=False)
    cdp("Page.navigate", url=f"http://127.0.0.1:{PORT}/web_static/index.html")
    for _ in range(300):
        time.sleep(0.2)
        try:
            if js("!!(window.fabricApp && window.fabricApp.backend())"): break
        except Exception: pass
    js("fabricApp.ready")
    time.sleep(0.8); shot("start_desktop.png")
    st = js("(() => { const a = document.querySelector('.stagecol').getBoundingClientRect(), b = document.getElementById('sidecards').getBoundingClientRect(); return [a.top, a.bottom, b.top, b.bottom]; })()")
    check(abs(st[0] - st[2]) < 2 and abs(st[1] - st[3]) < 2, f"start screen: both columns line up top and bottom {st}")
    # 1. on by default: a small bubble on the page edge; the switch is in Settings
    check(js("!!document.querySelector('.fbub') && !document.querySelector('.fbub').hidden"), "bubble on the page by default")
    check(js("document.getElementById('bubbleOn').checked"), "Settings switch is on")
    check(js("!document.querySelector('.qa-back')") and js("!fabricApp.bubble().pip"), "nothing opens by itself")
    print("   settings text:", js("document.getElementById('webBubbleState').textContent"))
    # 2. drag the bubble: it snaps to the nearest edge
    bx, by = center(".fbub"); drag((bx, by), (300, 400)); time.sleep(0.5)
    left = js("document.querySelector('.fbub').offsetLeft")
    check(abs(left) < 2 and js("document.querySelector('.fbub').classList.contains('dock-l')"), f"bubble docks at the left edge (left={left:.0f})")

    # 3. tap: the quick-action menu
    bx, by = center(".fbub"); click(bx, by); time.sleep(0.6)
    tiles = js("[...document.querySelectorAll('.qa-back .qa-tile')].map(t => t.textContent.trim())")
    print("   tiles:", tiles)
    check(len(tiles) == 4 and tiles[0].startswith("Select area"), "menu has 4 tiles")
    check(js("[...document.querySelectorAll('.qa-row button')].map(b => b.textContent).join('|')") == "Hide bubble|Turn off", "menu has Hide / Turn off")
    shot("bubble_menu_web.png")
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'})); true"); time.sleep(0.3)
    check(js("!document.querySelector('.qa-back')"), "Escape closes the menu")
    bx, by = center(".fbub"); click(bx, by); time.sleep(0.6)
    if js("!!document.querySelector('.qa-float')"):
        x, y = center(".qa-float"); click(x, y); time.sleep(1.2)
        check(js("!!fabricApp.bubble().pip") and js("fabricApp.bubble().pip.document.body.dataset.view") == "menu", "Float over other windows opens the floating menu")
        check(js("document.querySelector('.fbub').hidden"), "page bubble hides while floating")
        js("fabricApp.bubble().collapse(); true"); time.sleep(0.3)
        check(js("fabricApp.bubble().pip.document.body.dataset.view") == "bubble", "floating window collapses to the bubble")
        js("fabricApp.bubble().closePip(); fabricApp.bubble().showPageBubble(); true"); time.sleep(0.3)
    else:
        js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'})); true"); time.sleep(0.3)

    # 4. screen capture (fake screen) -> picture
    sz = js("(async () => { const b = fabricApp.bubble(); const s = await b.ensureStream(window); const c = await b.grab(s); return [c.width, c.height]; })()")
    print("   captured screen:", sz)
    check(sz and sz[0] > 100 and sz[1] > 100, "screen capture gives a picture")

    # 5. area picker with a real drag, then the selected area is analysed on the device
    js("""(async () => {
      const im = new Image(); im.src = 'examples/stain_example.jpg'; await im.decode();
      const c = document.createElement('canvas'); c.width = 1920; c.height = 1080; const g = c.getContext('2d');
      g.fillStyle = '#334'; g.fillRect(0, 0, 1920, 1080); g.drawImage(im, 600, 200, 800, 800 * im.height / im.width);
      window.__shot = c;
      const mod = await import('./js/bubble.js');
      window.__pick = mod.pickArea(document, c);
      return true; })()""")
    time.sleep(0.6)
    shot("bubble_pick_empty.png")
    fr = js("(() => { const r = document.querySelector('.pick-frame').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
    a = (fr[0] + fr[2] * 600 / 1920, fr[1] + fr[3] * 200 / 1080)
    b = (fr[0] + fr[2] * 1400 / 1920, fr[1] + fr[3] * 900 / 1080)
    drag(a, b); time.sleep(0.3)
    shot("bubble_pick_selected.png")
    check(js("!document.querySelector('.pick [data-go]').disabled"), "Analyse area enabled after a drag")
    x, y = center(".pick [data-go]"); click(x, y)
    rect = js("window.__pick")
    print("   selected rect (screen px):", rect)
    check(rect and abs(rect[0] - 600) < 15 and abs(rect[2] - 800) < 20, "selected rectangle maps to screen pixels")
    rep = js("(async () => { const r = await fabricApp.analyseCapture(window.__shot, await window.__pick); return r && { v: r.verdict, n: r.items.length, size: r.imageSize, name: r.name }; })()")
    print("   result:", rep)
    check(rep and rep["name"] == "Screen (selected area)", "selected screen area analysed")
    time.sleep(0.8)
    check(js("!document.querySelector('.fbub i').hidden") == bool(rep and rep["v"].get("severity")), "bubble dot shows the last verdict")
    shot("bubble_result_web.png")
    bx, by = center(".fbub"); click(bx, by); time.sleep(0.5)
    check(js("!!document.querySelector('.qa-last')"), "menu shows the last check")
    shot("bubble_menu_last.png")
    x, y = center(".qa-row button:last-child"); click(x, y); time.sleep(0.3)
    check(js("fabricApp.bubble().state") == "off" and js("!fabricApp.bubble().stream"), "Turn off stops the bubble and the screen share")
    check(not js("document.getElementById('bubbleOn').checked"), "Settings switch follows Turn off")

    # 6. phone width: card layout, bubble does not cover the tab bar
    cdp("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
    js("fabricApp.bubble().start(); true"); time.sleep(0.6)
    r = js("(() => { const r = document.querySelector('.fbub').getBoundingClientRect(); return [r.left, r.right, r.bottom]; })()")
    check(r[0] < 390 - 30 and r[2] <= 844 - 62, f"bubble docked on the phone screen edge, above the tab bar {r}")
    bx, by = center(".fbub"); click(bx, by); time.sleep(0.6)
    w = js("document.querySelector('.qa').getBoundingClientRect().width")
    check(w <= 390 - 32 + 1, f"menu fits the phone width ({w:.0f}px)")
    shot("bubble_menu_phone.png")
    check(not errors, "no JavaScript errors" + ("" if not errors else ": " + errors[0]))
finally:
    edge.terminate(); srv.terminate()
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
