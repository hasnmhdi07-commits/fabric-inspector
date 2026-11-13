// Automatic test of the API (starts it on a free port, calls it like the phone and the web page would).
// Run:  node server/test_api.mjs
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { app } from "./app.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const EX = path.join(HERE, "..", "web_static", "examples");
let pass = 0, failN = 0;
const check = (name, ok, info = "") => { ok ? pass++ : failN++; console.log(`${ok ? "PASS" : "FAIL"}  ${name}${info ? "  (" + info + ")" : ""}`); };

const server = app.listen(0, "127.0.0.1");
await new Promise((r) => server.once("listening", r));
const base = `http://127.0.0.1:${server.address().port}`;
const hole = await readFile(path.join(EX, "hole_example.jpg"));
const stain = await readFile(path.join(EX, "stain_example.jpg"));

let r = await fetch(`${base}/api/health`), j = await r.json();
check("health answers", r.status === 200 && j.ok && j.model.file === "best.onnx" && j.stores === "nothing", `model ${j.model?.sha256}`);

r = await fetch(`${base}/api/analyze`, { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: hole }); j = await r.json();
const holes = (j.items ?? []).filter((i) => i.defect === "hole_tear");
check("raw body upload: 3 holes found", r.status === 200 && j.ok && holes.length === 3, `${j.totalMs} ms`);
check("verdict: defects state with a title", j.verdict?.state === "defects" && j.verdict.title === "3 defects" && j.verdict.severity === "major", j.verdict?.title);
check("each finding has causes, remedy, prevention", holes.every((i) => i.causes?.length && i.remedy?.length && i.prevention?.length));
check("shade and skew are off by default", !(j.items ?? []).some((i) => ["shade_variation", "skewing", "bowing"].includes(i.defect)));

const form = new FormData(); form.append("image", new Blob([stain], { type: "image/jpeg" }), "stain.jpg");
r = await fetch(`${base}/api/analyze?shade=1&skew=1`, { method: "POST", body: form }); j = await r.json();
const kinds = new Set((j.items ?? []).map((i) => i.defect));
check("form upload with shade + skew: 8 stains", r.status === 200 && (j.items ?? []).filter((i) => i.defect === "stain").length === 8, `${j.totalMs} ms`);
check("shade, skew and bow results present", ["shade_variation", "skewing", "bowing"].every((k) => kinds.has(k)));

r = await fetch(`${base}/api/analyze?conf=0.81`, { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: hole }); j = await r.json();
check("confidence setting is applied", j.ok && j.items.length === 1 && j.settings.conf === 0.81, `${j.items?.length} box`);

const skew = await readFile(path.join(EX, "skew_example.jpg"));
r = await fetch(`${base}/api/analyze`, { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: skew }); j = await r.json();
check("nothing found -> 'No defects detected', never 'acceptable'", j.verdict?.state === "none" && j.verdict.title === "No defects detected" && !/acceptable/i.test(JSON.stringify(j.verdict)), j.verdict?.detail);

r = await fetch(`${base}/api/analyze`, { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: Buffer.from("this is not a photo") }); j = await r.json();
check("not a photo -> clear message", r.status === 415 && !j.ok && j.error && j.fix);

r = await fetch(`${base}/api/analyze`, { method: "POST" }); j = await r.json();
check("no photo -> clear message", r.status === 400 && !j.ok && j.fix);

r = await fetch(`${base}/api/analyze`, { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: Buffer.alloc(5 * 1024 * 1024, 1) }); j = await r.json();
check("photo above 4 MB -> clear message", r.status === 413 && !j.ok && /too large/i.test(j.error));

r = await fetch(`${base}/api/analyze?defects=0`, { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: hole }); j = await r.json();
check("all checks off -> clear message", r.status === 400 && !j.ok);

// result page for the iPhone Shortcut
r = await fetch(`${base}/api/analyze?format=html`, { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: hole });
let page = await r.text();
check("format=html: self-contained result page", r.status === 200 && /text\/html/.test(r.headers.get("content-type")) && page.includes("3 defects") &&
  page.includes("data:image/jpeg;base64,") && !/<script|<link|src="http/i.test(page), `${(page.length / 1024).toFixed(0)} KB`);
check("format=html: 3 boxes drawn, causes included", (page.match(/fill="none"/g) || []).length === 3 && page.includes("Likely causes"));
if (process.argv[2]) (await import("node:fs")).writeFileSync(process.argv[2], page);
r = await fetch(`${base}/api/analyze?format=html`, { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: Buffer.from("x") }); page = await r.text();
check("format=html: errors are a readable page too", r.status === 415 && page.includes("could not be read as a photo") && page.includes("<html"));

r = await fetch(`${base}/nothing-here`); j = await r.json();
check("unknown address -> clear message", r.status === 404 && !j.ok);

server.close();
console.log(`\n${pass} passed, ${failN} failed`);
process.exit(failN ? 1 : 0);
