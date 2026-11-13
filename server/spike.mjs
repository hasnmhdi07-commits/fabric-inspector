// Spike: does the analysis engine run outside the browser, how fast, and how much memory?
// Usage: node spike.mjs [image ...]      (default: the three example photos)
// Writes spike_result.json so the detections can be compared with the Python engine.
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { getEngine, analyse } from "./engine.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const mb = () => (process.memoryUsage().rss / 1048576).toFixed(0);
const files = process.argv.length > 2 ? process.argv.slice(2)
  : ["hole_example.jpg", "stain_example.jpg", "skew_example.jpg"].map((f) => path.join(HERE, "..", "web_static", "examples", f));

console.log(`node ${process.version}, memory at start ${mb()} MB`);
const { loadMs } = await getEngine();
console.log(`engine loaded (cold start) in ${loadMs.toFixed(0)} ms, memory ${mb()} MB`);

const out = {};
for (const f of files) {
  const buf = await readFile(f);
  const t0 = performance.now();
  const rep = await analyse(buf, { doShade: true, doSkew: true });
  const ms = performance.now() - t0;
  const t = Object.entries(rep.timings).map(([k, v]) => `${k} ${v.toFixed(0)}`).join(", ");
  console.log(`\n${path.basename(f)}  ${rep.imageSize.join("x")}  total ${ms.toFixed(0)} ms (${t})  memory ${mb()} MB  verdict=${rep.verdict.severity ?? rep.verdict.state}: ${rep.verdict.title}`);
  for (const r of rep.items) {
    console.log(`  #${r.index} ${r.defect} ${r.severity}` + (r.box ? ` conf ${r.confidence.toFixed(3)} box ${r.box.map((v) => v.toFixed(0)).join(",")}` : ` | ${r.measure ?? ""}`));
  }
  out[path.basename(f)] = { size: rep.imageSize, ms, verdict: rep.verdict, items: rep.items.map((r) => ({ defect: r.defect, severity: r.severity, confidence: r.confidence ?? null, box: r.box ?? null, measure: r.measure ?? null })) };
}
await writeFile(path.join(HERE, "spike_result.json"), JSON.stringify(out, null, 1));
console.log(`\npeak memory ${(process.resourceUsage().maxRSS / 1024).toFixed(0)} MB`);
