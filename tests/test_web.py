"""End-to-end test of the running web app via the Gradio client (same path as a browser).
Usage: python tests\\test_web.py [url]   (default http://127.0.0.1:7860)"""
import sys, time, re
from gradio_client import Client, handle_file

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7860"
for _ in range(60):                     # wait for the server to come up
    try:
        c = Client(url, verbose=False); break
    except Exception:
        time.sleep(2)
else:
    sys.exit("server not reachable")

cases = [("web/examples/hole_example.jpg", True, False, False),
         ("web/examples/stain_example.jpg", True, True, False),
         ("web/examples/skew_example.jpg", False, False, True)]
CHECKS = ["Local defects (AI)", "Shade (ΔE)", "Bow / skew"]
for path, d, sh, sk in cases:
    t0 = time.time()
    chosen = [n for n, on in zip(CHECKS, (d, sh, sk)) if on]
    gal, html, f = c.predict(handle_file(path), chosen, 0.23, 0, 1.0, 3.0, 2.0, "horizontal", api_name="/analyse")
    text = re.sub(r"<[^>]+>", " ", html)
    overall = re.search(r"Overall:\s*\S+\s*(\w+)", text)
    print(f"{path.split('/')[-1]:18} views={len(gal)} overall={overall.group(1) if overall else '?'} "
          f"report_file={'ok' if f else 'missing'} round-trip {time.time() - t0:.1f}s")
    if "skew" in path:
        m = re.search(r"Skew [\d.]+% \([^)]*\), Bow [\d.]+%", text)
        print("   ", m.group(0) if m else text[:200], "(true: skew 4%, bow 1.5%)")
print("WEB OK")
