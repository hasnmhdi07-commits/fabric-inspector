// Test the DEPLOYED API and compare it with the engine on this PC (same photo -> same result).
// Run:  node server/test_live.mjs https://fabric-inspector.vercel.app
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { analyse } from "./engine.mjs";

const base = (process.argv[2] || "https://fabric-inspector.vercel.app").replace(/\/$/, "");
const HERE = path.dirname(fileURLToPath(import.meta.url));
const EX = path.join(HERE, "..", "web_static", "examples");
let pass = 0, failN = 0;
const check = (name, ok, info = "") => { ok ? pass++ : failN++; console.log(`${ok ? "PASS" : "FAIL"}  ${name}${info ? "  (" + info + ")" : ""}`); };
const timed = async (url, opt) => { const t0 = performance.now(); const r = await fetch(url, opt); const text = await r.text(); let j = null; try { j = JSON.parse(text); } catch {} return { r, j, text, ms: Math.round(performance.now() - t0) }; };

let x = await timed(`${base}/api/health`);
check("health (first call = cold start)", x.r.status === 200 && x.j?.ok, `${x.ms} ms round trip, engine load ${x.j?.engineLoadMs} ms, model ${x.j?.model?.sha256}` + (x.j ? "" : ` | ${x.r.status} ${x.text.slice(0, 200)}`));
if (!x.j?.ok) { console.log("\nAPI not reachable - stopping."); process.exit(1); }

for (const f of ["hole_example.jpg", "stain_example.jpg", "skew_example.jpg"]) {
  const buf = await readFile(path.join(EX, f));
  const local = await analyse(buf, { doShade: true, doSkew: true });
  const times = [];
  let live = null;
  for (let i = 0; i < 3; i++) {
    x = await timed(`${base}/api/analyze?shade=1&skew=1`, { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: buf });
    times.push(x.ms); live = x.j;
  }
  const key = (it) => `${it.defect}|${it.severity}|${it.confidence?.toFixed(4) ?? ""}|${it.box?.map((v) => v.toFixed(1)).join(",") ?? ""}|${it.measure ?? ""}`;
  const same = live?.ok && live.items.length === local.items.length && live.items.every((it, i) => key(it) === key(local.items[i]));
  check(`${f}: live result identical to this PC`, same, `${live?.items?.length} findings; server ${live?.totalMs} ms; round trips ${times.join(", ")} ms`);
  if (!same && live?.items) for (let i = 0; i < Math.max(live.items.length, local.items.length); i++) {
    const a = live.items[i] ? key(live.items[i]) : "-", b = local.items[i] ? key(local.items[i]) : "-";
    if (a !== b) console.log(`     live : ${a}\n     local: ${b}`);
  }
}

x = await timed(`${base}/api/analyze`, { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: Buffer.from("not a photo") });
check("not a photo -> clear message", x.r.status === 415 && x.j?.fix);
x = await timed(`${base}/`);
check("web page is served from the same address", x.r.status === 200 && /Fabric/i.test(x.text));

console.log(`\n${pass} passed, ${failN} failed`);
process.exit(failN ? 1 : 0);
