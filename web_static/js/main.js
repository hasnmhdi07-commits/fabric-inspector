// Fabric Defect Inspector - in-browser app (all analysis runs on the user's device).
// Engine = same pipeline as src/app/engine.py: YOLO -> shade -> bow/skew -> knowledge base.
import { Detector } from "./detector.js";
import { analyseShade } from "./shade.js";
import { analyseSkewBow } from "./skew.js";
import { loadKB, assess, verdictHtml, reportHtml, reportText, SEVERITY_ORDER } from "./kb.js";
import { photoProblem, makeVerdict } from "./verdict.js";
import { limitSize, toCanvas } from "./imgutil.js";

const MAX_SIDE = 1600;
const CLASS_COLOR = { hole_tear: "rgb(42,120,214)", stain: "rgb(235,104,52)", slub_neps: "rgb(27,175,122)", broken_pick_end: "rgb(237,161,0)" };
const $ = (id) => document.getElementById(id);
let detector = null, image = null, imageName = "", report = null;

// ------------------------------------------------------------------ engine
export async function analyse(img, s) {
  const W = img.width, H = img.height, items = [], views = {}, notes = [], t = {};
  const problem = photoProblem(img);        // third verdict state: say why and what to do, analyse nothing
  if (problem) return { items, views: { Photo: toCanvas(img) }, notes, timings: t, imageSize: [W, H], problem, verdict: makeVerdict(items, problem, s.doDefects) };
  if (s.doDefects) {
    const t0 = performance.now();
    const dets = await detector.detect(img, { conf: s.conf, iou: 0.5 });
    t.detection = performance.now() - t0;
    for (const d of dets) {
      const [x1, y1, x2, y2] = d.box;
      const r = assess(d.name, { boxWH: [x2 - x1, y2 - y1], imageWH: [W, H], pxPerMm: s.pxPerMm || null, confidence: d.conf });
      r.box = d.box; items.push(r);
    }
    if (!items.length) notes.push(`No local defects found at confidence >= ${s.conf.toFixed(2)}.`);
  }
  if (s.doShade) {
    const t0 = performance.now();
    const excl = items.filter((r) => r.box).map((r) => [r.box[0], r.box[1], r.box[2] - r.box[0], r.box[3] - r.box[1]]);
    const sh = analyseShade(img, { tolerance: s.shadeTol, excludeRects: excl });
    t.shade = performance.now() - t0;
    const r = assess("shade_variation", { deltaE: sh.value, shadeTolerance: s.shadeTol });
    r.measure = sh.summary; r.shade = sh.details; r.value = sh.value; items.push(r);
    views["Shade heat map"] = renderShade(sh);
  }
  if (s.doSkew) {
    const t0 = performance.now();
    try {
      const sk = analyseSkewBow(img, { weft: s.weft, skewTol: s.skewLimit, bowTol: s.bowLimit });
      for (const [name, o] of [["skewing", { skewPct: sk.skewPct, skewLimit: s.skewLimit }], ["bowing", { bowPct: sk.bowPct, bowLimit: s.bowLimit }]]) {
        const r = assess(name, o); r.measure = sk.summary; r.skew = { skewPct: sk.skewPct, bowPct: sk.bowPct };
        r.value = Math.abs(name === "skewing" ? sk.skewPct : sk.bowPct); items.push(r);
      }
      views["Weft line (bow/skew)"] = renderSkew(sk);
    } catch (e) { notes.push(`Bow/skew check skipped: ${e.message}`); }
    t.bow_skew = performance.now() - t0;
  }
  const si = (x) => SEVERITY_ORDER.indexOf(x);
  items.sort((a, b) => si(b.severity) - si(a.severity) || (b.confidence ?? 0) - (a.confidence ?? 0));
  items.forEach((r, i) => (r.index = i + 1));
  if (s.doShade || s.doSkew) notes.push("Shade and bow/skew need a flat fabric photo taken straight from above in even light; other photos give only indicative values.");
  return { items, views: { Defects: renderDefects(img, items), ...views }, notes, timings: t, imageSize: [W, H], pxPerMm: s.pxPerMm || 0, problem: null, verdict: makeVerdict(items, null, s.doDefects) };
}

// ------------------------------------------------------------------ drawing
function renderDefects(img, items) {
  const cv = toCanvas(img), g = cv.getContext("2d"), m = Math.max(img.width, img.height);
  const lw = Math.max(2, Math.round(m / 400)), fs = Math.max(12, Math.round(m / 55));
  g.font = `600 ${fs}px system-ui, sans-serif`; g.textBaseline = "bottom";
  for (const r of items) {
    if (!r.box) continue;
    const [x1, y1, x2, y2] = r.box, col = CLASS_COLOR[r.defect] || "#fff";
    g.strokeStyle = col; g.lineWidth = lw; g.strokeRect(x1, y1, x2 - x1, y2 - y1);
    const label = `${r.index} ${r.defect} ${(r.confidence * 100).toFixed(0)}%`, tw = g.measureText(label).width;
    const ty = y1 - fs - 6 > 0 ? y1 - 2 : y2 + fs + 6;
    g.fillStyle = col; g.fillRect(x1, ty - fs - 4, tw + 8, fs + 6);
    g.fillStyle = "#fff"; g.fillText(label, x1 + 4, ty);
  }
  return cv;
}

function renderShade(sh) {
  const o = sh.overlay, cv = toCanvas(o), g = cv.getContext("2d");
  g.strokeStyle = "rgb(200,200,200)"; g.lineWidth = 1;
  for (const [x, y, w, h] of o.excl) g.strokeRect(x, y, w, h);
  const bw = Math.min(o.width - 20, 256), y0 = o.height - 30;
  for (let i = 0; i < bw; i++) {
    const v = i / bw, c = [1.5 - Math.abs(4 * v - 3), 1.5 - Math.abs(4 * v - 2), 1.5 - Math.abs(4 * v - 1)].map((x) => Math.round(Math.max(0, Math.min(1, x)) * 255));
    g.fillStyle = `rgb(${c})`; g.fillRect(10 + i, y0, 1, 14);
  }
  g.fillStyle = "#fff"; g.font = "12px system-ui"; g.fillText("0", 10, y0 - 4); g.fillText(`ΔE ${o.legend.toFixed(1)}`, bw - 30, y0 - 4);
  return cv;
}

function renderSkew(sk) {
  const v = sk.view, cv = toCanvas(v), g = cv.getContext("2d");
  g.strokeStyle = "rgb(90,90,90)"; g.lineWidth = 1;
  for (const x of v.edges.slice(1, -1)) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, v.height); g.stroke(); }
  const p = v.pts;
  g.strokeStyle = "rgb(255,255,0)"; g.lineWidth = 2; g.beginPath(); g.moveTo(...p[0]); g.lineTo(...p[p.length - 1]); g.stroke();
  g.strokeStyle = "rgb(255,0,0)"; g.lineWidth = 3; g.beginPath(); g.moveTo(...p[0]); p.slice(1).forEach((q) => g.lineTo(...q)); g.stroke();
  g.font = "600 22px system-ui"; g.fillStyle = sk.passed ? "rgb(0,200,0)" : "rgb(255,60,60)";
  g.fillText(`skew ${Math.abs(sk.skewPct).toFixed(2)}%  bow ${Math.abs(sk.bowPct).toFixed(2)}%  ${sk.passed ? "PASS" : "FAIL"}`, 10, 30);
  return cv;
}

// ------------------------------------------------------------------ UI
function settings() {
  return {
    doDefects: $("chkDef").checked, doShade: $("chkShade").checked, doSkew: $("chkSkew").checked,
    conf: +$("conf").value, pxPerMm: +$("pxmm").value || 0, shadeTol: +$("tol").value,
    skewLimit: +$("skewLim").value, bowLimit: +$("bowLim").value, weft: $("weft").value,
  };
}
const status = (m) => ($("status").textContent = m);

async function loadImage(blobOrUrl, name) {
  const blob = typeof blobOrUrl === "string" ? await (await fetch(blobOrUrl)).blob() : blobOrUrl;
  let bmp;
  try {
    bmp = await createImageBitmap(blob, { imageOrientation: "from-image" });
  } catch {                                             // older Safari: decode via <img> (also applies EXIF rotation)
    bmp = await new Promise((res, rej) => {
      const im = new Image(), url = URL.createObjectURL(blob);
      im.onload = () => { URL.revokeObjectURL(url); res(im); }; im.onerror = rej; im.src = url;
    });
  }
  const cv = document.createElement("canvas"); cv.width = bmp.naturalWidth || bmp.width; cv.height = bmp.naturalHeight || bmp.height;
  const g = cv.getContext("2d"); g.drawImage(bmp, 0, 0);
  const id = g.getImageData(0, 0, cv.width, cv.height);
  return { img: { data: id.data, width: id.width, height: id.height }, name };
}

async function setImage(blobOrUrl, name) {
  const { img } = await loadImage(blobOrUrl, name);
  const lim = limitSize(img, MAX_SIDE);
  image = lim.img; image.factor = lim.factor; imageName = name;
  const pv = $("preview"); pv.innerHTML = ""; const c = toCanvas(image); pv.appendChild(c);
  $("analyse").disabled = !detector;
  await run();
}

async function run() {
  if (!image) return status("Choose or take a photo first.");
  if (!detector) return status("Please wait - the AI model is still loading…");
  const s = settings(); s.pxPerMm *= image.factor || 1;
  if (!(s.doDefects || s.doShade || s.doSkew)) return status("Tick at least one check.");
  status("Analysing…"); $("analyse").disabled = true;
  await new Promise((r) => setTimeout(r, 30));          // let the browser paint the status first
  const t0 = performance.now();
  try {
    report = await analyse(image, s);
    showReport(report, performance.now() - t0);
  } catch (e) { status("Error: " + e.message); console.error(e); }
  $("analyse").disabled = false;
}

function showReport(rep, ms) {
  $("verdict").innerHTML = verdictHtml(rep);
  const tabs = $("tabs"); tabs.innerHTML = ""; tabs.hidden = Object.keys(rep.views).length < 2;
  Object.keys(rep.views).forEach((name, i) => {
    const b = document.createElement("button"); b.textContent = name.split(" (")[0]; b.className = "tab" + (i ? "" : " active");
    b.onclick = () => { [...tabs.children].forEach((x) => x.classList.remove("active")); b.classList.add("active"); showView(name); };
    tabs.appendChild(b);
  });
  showView(Object.keys(rep.views)[0]);
  $("report").innerHTML = reportHtml(rep);
  $("results").hidden = false; $("download").hidden = false;
  status(`${imageName}: ${rep.verdict.title} - ${ms.toFixed(0)} ms (on this device)`);
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function showView(name) {
  const v = $("view"); v.innerHTML = ""; v.appendChild(report.views[name]);
}

function download() {
  const txt = `Source: ${imageName}\n` + reportText(report);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([txt], { type: "text/plain" }));
  a.download = `fabric_report_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.txt`;
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

function wireUI() {
  for (const id of ["fileCam", "fileAny"]) $(id).addEventListener("change", (e) => { const f = e.target.files[0]; if (f) setImage(f, f.name); e.target.value = ""; });
  $("analyse").onclick = run;
  $("download").onclick = download;
  $("conf").oninput = () => ($("confVal").textContent = (+$("conf").value).toFixed(2));
  document.querySelectorAll(".example").forEach((b) => (b.onclick = () => setImage(b.dataset.src, b.dataset.src.split("/").pop())));
  const drop = $("preview");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) setImage(f, f.name); });
  window.addEventListener("paste", (e) => { const f = [...e.clipboardData.files][0]; if (f) setImage(f, "pasted image"); });
  let deferred = null;
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e; $("install").hidden = false; });
  $("install").onclick = async () => { if (deferred) { deferred.prompt(); await deferred.userChoice; deferred = null; $("install").hidden = true; } };
}

async function init() {
  wireUI();
  status("Loading AI model (about 25 MB the first time, then works offline)…");
  await loadKB("kb.json");
  detector = await Detector.create("model/best.onnx");
  $("analyse").disabled = !image;
  const mode = detector.backend.startsWith("compat") ? " (compatibility mode for this older device - a bit slower)" : "";
  status((image ? "Ready." : "Ready - take or choose a fabric photo.") + mode);
  if (image) run();
}

const ready = init().catch((e) => { status("Could not start: " + e.message); console.error(e); throw e; });
if ("serviceWorker" in navigator && location.protocol !== "file:") navigator.serviceWorker.register("sw.js").catch(() => {});

// test hook used by the automatic tests (tests/test_static.py)
window.fabricApp = {
  ready,
  backend: () => detector && detector.backend,
  async analyseUrl(url, s) {
    await ready;
    const { img } = await loadImage(url, url);
    const lim = limitSize(img, MAX_SIDE);
    const full = { doDefects: true, doShade: false, doSkew: false, conf: 0.23, pxPerMm: 0, shadeTol: 1, skewLimit: 3, bowLimit: 2, weft: "horizontal", ...s };
    const rep = await analyse(lim.img, full);
    return { size: rep.imageSize, timings: rep.timings, notes: rep.notes, verdict: rep.verdict,
             items: rep.items.map((r) => ({ defect: r.defect, severity: r.severity, confidence: r.confidence, box: r.box, basis: r.severity_basis, shade: r.shade, skew: r.skew })) };
  },
};
