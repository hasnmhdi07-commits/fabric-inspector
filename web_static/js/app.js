// Fabric Inspector - web app (all analysis runs on the user's device).
// Engine = same pipeline as src/app/engine.py: YOLO -> shade -> bow/skew -> knowledge base.
// The same page is the main screen of the Android app (window.FabricNative is then present).
import { Detector } from "./detector.js";
import { analyseShade } from "./shade.js";
import { analyseSkewBow } from "./skew.js";
import { loadKB, assess, verdictHtml, reportHtml, reportText, SEVERITY_ORDER, SEV_COLOR } from "./kb.js";
import { photoProblem, makeVerdict, SEV_LABEL } from "./verdict.js";
import { limitSize, toCanvas, placeLabel } from "./imgutil.js";
import { Camera } from "./camera.js";
import { listScans, getScan, addScan, deleteScan, clearScans } from "./store.js";
import { Bubble, canFloat, canCapture } from "./bubble.js";

const MAX_SIDE = 1600;          // analysis size (same on every platform)
const MAX_ORIGINAL = 4096;      // kept in memory so a selected area is analysed at full detail
const CLASS_COLOR = { hole_tear: "rgb(42,120,214)", stain: "rgb(235,104,52)", slub_neps: "rgb(27,175,122)", broken_pick_end: "rgb(237,161,0)" };
const $ = (id) => document.getElementById(id);
const native = window.FabricNative || null;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let detector = null;
let orig = null, origName = "";         // the photo as loaded
let crop = null;                        // [x, y, w, h] in orig pixels, or null = whole photo
let image = null, report = null;        // what was analysed, and the result
let busy = false, runId = 0;

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
  // "Defects" is the plain photo: the page draws the boxes on top so they can be tapped
  return { items, views: { Defects: toCanvas(img), ...views }, notes, timings: t, imageSize: [W, H], pxPerMm: s.pxPerMm || 0, problem: null, verdict: makeVerdict(items, null, s.doDefects) };
}

// ------------------------------------------------------------------ drawing
/** Photo with boxes drawn into it (for sharing and saving). */
function renderDefects(img, items) {
  const cv = toCanvas(img), g = cv.getContext("2d"), m = Math.max(img.width, img.height);
  const lw = Math.max(2, Math.round(m / 400)), fs = Math.max(12, Math.round(m / 55));
  g.font = `600 ${fs}px system-ui, sans-serif`; g.textBaseline = "bottom";
  const found = items.filter((r) => r.box), placed = [];
  for (const r of found) {
    const [x1, y1, x2, y2] = r.box;
    g.strokeStyle = CLASS_COLOR[r.defect] || "#fff"; g.lineWidth = lw; g.strokeRect(x1, y1, x2 - x1, y2 - y1);
  }
  for (const r of found) {                                // labels after all boxes, never on top of each other
    const col = CLASS_COLOR[r.defect] || "#fff", label = `${r.index} ${r.defect} ${(r.confidence * 100).toFixed(0)}%`;
    const tw = g.measureText(label).width + 8, th = fs + 6, [lx, ly] = placeLabel(r.box, tw, th, img.width, img.height, placed);
    g.fillStyle = col; g.fillRect(lx, ly, tw, th);
    g.fillStyle = "#fff"; g.fillText(label, lx + 4, ly + th - 2);
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

// ------------------------------------------------------------------ small UI helpers
const scan = $("scr-scan"), frame = $("frame");
const setState = (s) => { scan.dataset.state = s; $("app").classList.toggle("immersive", s === "camera"); };
function status(msg, cls = "") { $("status").textContent = msg; $("engine").className = "engine " + cls; if (cls !== "loading") $("enginePct").textContent = ""; }
let toastTimer = 0;
function toast(msg, ms = 3200) {
  const t = $("toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), ms);
}

// ------------------------------------------------------------------ settings (remembered on this device)
const FIELDS = ["chkDef", "chkShade", "chkSkew", "conf", "pxmm", "tol", "skewLim", "bowLim", "weft", "keepHistory"];
const DEFAULTS = {};
function settings() {
  return {
    doDefects: $("chkDef").checked, doShade: $("chkShade").checked, doSkew: $("chkSkew").checked,
    conf: +$("conf").value, pxPerMm: +$("pxmm").value || 0, shadeTol: +$("tol").value,
    skewLimit: +$("skewLim").value, bowLimit: +$("bowLim").value, weft: $("weft").value,
  };
}
const fieldVal = (el) => (el.type === "checkbox" ? el.checked : el.value);
const setField = (el, v) => { if (el.type === "checkbox") el.checked = !!v; else el.value = v; };
function saveSettings() {
  try { localStorage.setItem("fi-settings", JSON.stringify(Object.fromEntries(FIELDS.map((id) => [id, fieldVal($(id))])))); } catch { /* private mode */ }
  $("confVal").textContent = (+$("conf").value).toFixed(2);
  if (native) native.setChecks($("chkShade").checked, $("chkSkew").checked);     // the bubble uses the same extra checks
}
function loadSettings() {
  for (const id of FIELDS) DEFAULTS[id] = fieldVal($(id));
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem("fi-settings") || "{}"); } catch { /* ignore */ }
  for (const id of FIELDS) if (id in saved) setField($(id), saved[id]);
  if (!(settings().doDefects || settings().doShade || settings().doSkew)) $("chkDef").checked = true;
  saveSettings();
}

// ------------------------------------------------------------------ photos
async function decode(blob) {
  let bmp;
  try {
    bmp = await createImageBitmap(blob, { imageOrientation: "from-image" });
  } catch {                                             // older Safari: decode via <img> (also applies EXIF rotation)
    bmp = await new Promise((res, rej) => {
      const im = new Image(), url = URL.createObjectURL(blob);
      im.onload = () => { URL.revokeObjectURL(url); res(im); };
      im.onerror = () => rej(new Error("This file is not a photo the browser can open.")); im.src = url;
    });
  }
  return bmp;
}

/** maxSide = 0: exact pixels (used by the automatic tests). */
async function loadImage(blobOrUrl, maxSide = 0) {
  const blob = typeof blobOrUrl === "string" ? await (await fetch(blobOrUrl)).blob() : blobOrUrl;
  const bmp = await decode(blob);
  const w = bmp.naturalWidth || bmp.width, h = bmp.naturalHeight || bmp.height;
  const f = maxSide ? Math.min(1, maxSide / Math.max(w, h)) : 1;
  const cv = document.createElement("canvas"); cv.width = Math.round(w * f); cv.height = Math.round(h * f);
  const g = cv.getContext("2d", { willReadFrequently: true }); g.imageSmoothingQuality = "high"; g.drawImage(bmp, 0, 0, cv.width, cv.height);
  if (bmp.close) bmp.close();
  const id = g.getImageData(0, 0, cv.width, cv.height);
  return { data: id.data, width: id.width, height: id.height };
}

function cropImage(img, [x, y, w, h]) {
  const data = new Uint8ClampedArray(w * h * 4);
  for (let r = 0; r < h; r++) data.set(img.data.subarray(((y + r) * img.width + x) * 4, ((y + r) * img.width + x + w) * 4), r * w * 4);
  return { data, width: w, height: h };
}

async function setImage(blobOrUrl, name) {
  closeCamera(); go("scan");
  try {
    orig = await loadImage(blobOrUrl, MAX_ORIGINAL);
  } catch (e) { toast(e.message || "This photo could not be opened."); return; }
  origName = name; crop = null;
  return run();
}

/** A picture of the screen (floating bubble): the whole picture is kept, the selected area is analysed. */
async function analyseCapture(cv, [x, y, w, h]) {
  closeCamera(); go("scan");
  const f = Math.min(1, MAX_ORIGINAL / Math.max(cv.width, cv.height));
  const W = Math.round(cv.width * f), H = Math.round(cv.height * f);
  const c2 = document.createElement("canvas"); c2.width = W; c2.height = H;
  const g = c2.getContext("2d", { willReadFrequently: true }); g.imageSmoothingQuality = "high"; g.drawImage(cv, 0, 0, W, H);
  const id = g.getImageData(0, 0, W, H);
  orig = { data: id.data, width: W, height: H }; origName = "Screen";
  const cx = Math.min(W - 1, Math.round(x * f)), cy = Math.min(H - 1, Math.round(y * f));
  crop = [cx, cy, Math.max(1, Math.min(W - cx, Math.round(w * f))), Math.max(1, Math.min(H - cy, Math.round(h * f)))];
  return run();
}

function showPhoto() {
  frame.style.setProperty("--w", image.width); frame.style.setProperty("--h", image.height);
  frame.style.animation = "none"; void frame.offsetWidth; frame.style.animation = "";
  $("view").replaceChildren(toCanvas(image));
  $("boxes").replaceChildren(); $("tabs").replaceChildren();
  frame.classList.remove("noboxes");
  setState("photo");
  $("btnWhole").hidden = !crop;
}

async function run() {
  if (!orig || busy) return null;
  const s = settings();
  if (!(s.doDefects || s.doShade || s.doSkew)) { toast("Switch on at least one check."); return null; }
  busy = true; const id = ++runId;
  endSelect();
  const src = crop ? cropImage(orig, crop) : orig;
  const lim = limitSize(src, MAX_SIDE);
  image = lim.img; s.pxPerMm *= lim.factor;
  showPhoto();
  $("results").hidden = true; frame.classList.add("scanning");
  if (window.matchMedia("(max-width: 899px)").matches) $("stage").scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    if (!detector) await ready;                              // the photo waits for the model
    // let the scan animation start first (a hidden tab gets no animation frames: the floating bubble works from other apps)
    if (!document.hidden) await new Promise((r) => { requestAnimationFrame(() => setTimeout(r, 60)); setTimeout(r, 250); });
    const t0 = performance.now();
    const rep = await analyse(image, s);
    const ms = performance.now() - t0;
    if (ms < 450 && !document.hidden) await sleep(450 - ms);
    if (id !== runId) return null;
    report = rep; report.ms = ms; report.name = origName + (crop ? " (selected area)" : "");
    showReport();
    if (bubble) bubble.setLast(report);
    saveToHistory().catch((e) => console.warn("history", e));
    return report;
  } catch (e) {
    console.error(e); toast("The analysis failed: " + e.message);
    return null;
  } finally {
    frame.classList.remove("scanning"); busy = false;
  }
}

// ------------------------------------------------------------------ result
function showReport() {
  const rep = report;
  $("verdict").innerHTML = verdictHtml(rep);
  const tabs = $("tabs"), names = Object.keys(rep.views); tabs.replaceChildren();
  if (names.length > 1) for (const [i, name] of names.entries()) {
    const b = document.createElement("button"); b.textContent = name.split(" (")[0]; b.className = "tab" + (i ? "" : " active");
    b.onclick = () => { for (const x of tabs.children) x.classList.remove("active"); b.classList.add("active"); showView(name); };
    tabs.appendChild(b);
  }
  showView(names[0]);
  // tappable boxes, numbered like the finding cards
  const [W, H] = rep.imageSize, boxes = $("boxes"); boxes.replaceChildren(); boxes.classList.remove("dim");
  rep.items.filter((r) => r.box).forEach((r, i) => {
    const [x1, y1, x2, y2] = r.box, d = document.createElement("div");
    d.className = "box" + (y1 / H < 0.09 ? " low" : "") + (x1 / W > 0.9 ? " edge" : ""); d.dataset.i = r.index;
    d.style.cssText = `left:${(x1 / W) * 100}%;top:${(y1 / H) * 100}%;width:${((x2 - x1) / W) * 100}%;height:${((y2 - y1) / H) * 100}%;--c:${SEV_COLOR[r.severity]};--i:${i}`;
    d.title = `#${r.index} ${r.name} - ${SEV_LABEL[r.severity]}`;
    d.innerHTML = `<b>${r.index}</b>`;
    d.onclick = (e) => { e.stopPropagation(); highlight(r.index, true); };
    boxes.appendChild(d);
  });
  $("report").innerHTML = reportHtml(rep);
  const conf = +$("conf").value, warn = !rep.when && settings().doDefects && conf > 0.5;    // a high threshold hides most defects
  $("confWarn").hidden = !warn;
  if (warn) $("confWarn").firstChild.textContent = `Detection confidence is set to ${conf.toFixed(2)} (default 0.23), so defects the AI is less sure about are hidden.`;
  const shownAt = performance.now();      // the first card opens by itself: that must not dim the other boxes
  for (const f of $("report").querySelectorAll(".finding")) f.addEventListener("toggle", () => { if (f.open && performance.now() - shownAt > 400) highlight(+f.dataset.i, false); });
  const [w, h] = rep.imageSize;
  $("meta").textContent = `${rep.name} · ${w} × ${h} px` + (rep.ms != null ? ` · ${rep.ms.toFixed(0)} ms on this device` : "") + (rep.when ? ` · ${fmtTime(rep.when)}` : "");
  $("results").hidden = false;
  $("results").style.animation = "none"; void $("results").offsetWidth; $("results").style.animation = "";
  status(detector ? "Ready" : "Loading AI…", detector ? "" : "loading");
}

function showView(name) {
  $("view").replaceChildren(report.views[name]);
  frame.classList.toggle("noboxes", name !== "Defects");
}

function highlight(index, scroll) {
  const boxes = $("boxes");
  let any = false;
  for (const b of boxes.children) { const on = +b.dataset.i === index; b.classList.toggle("on", on); any ||= on; }
  boxes.classList.toggle("dim", any);
  for (const f of $("report").querySelectorAll(".finding")) {
    const on = +f.dataset.i === index; f.classList.toggle("on", on && any);
    if (on && scroll) { f.open = true; f.scrollIntoView({ behavior: "smooth", block: "nearest" }); }
  }
}
function clearHighlight() {
  $("boxes").classList.remove("dim");
  for (const b of $("boxes").children) b.classList.remove("on");
  for (const f of $("report").querySelectorAll(".finding.on")) f.classList.remove("on");
}

function newScan() {
  runId++; orig = image = report = crop = null; endSelect();
  $("results").hidden = true; setState("empty");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ------------------------------------------------------------------ select an area (like a lens)
let selRect = null;       // fractions of the frame: [x, y, w, h]
function beginSelect() {
  if (!image || busy) return;
  frame.classList.add("selecting"); frame.classList.remove("has"); $("btnArea").setAttribute("aria-pressed", "true");
  $("areabar").hidden = false; $("areaGo").disabled = true; $("sel").hidden = true; selRect = null;
  $("areaHint").textContent = "Drag over the part of the fabric you want to check.";
  clearHighlight();
}
function endSelect() {
  frame.classList.remove("selecting", "has"); $("btnArea").setAttribute("aria-pressed", "false");
  $("areabar").hidden = true; $("sel").hidden = true; selRect = null;
}
function wireSelect() {
  let start = null;
  const pos = (e) => { const r = frame.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; };
  frame.addEventListener("pointerdown", (e) => {
    if (!frame.classList.contains("selecting")) return;
    e.preventDefault(); frame.setPointerCapture(e.pointerId); start = pos(e);
  });
  frame.addEventListener("pointermove", (e) => {
    if (!start) return;
    const [x, y] = pos(e), s = $("sel");
    selRect = [Math.min(x, start[0]), Math.min(y, start[1]), Math.abs(x - start[0]), Math.abs(y - start[1])];
    s.style.cssText = `left:${selRect[0] * 100}%;top:${selRect[1] * 100}%;width:${selRect[2] * 100}%;height:${selRect[3] * 100}%`;
    s.hidden = false; frame.classList.add("has");
  });
  const up = () => {
    if (!start) return; start = null;
    const r = frame.getBoundingClientRect(), ok = selRect && selRect[2] * r.width > 28 && selRect[3] * r.height > 28;
    $("areaGo").disabled = !ok;
    $("areaHint").textContent = ok ? "Area selected. Drag again to change it." : "That area is too small. Drag a larger one.";
    if (!ok) { $("sel").hidden = true; frame.classList.remove("has"); selRect = null; }
  };
  frame.addEventListener("pointerup", up); frame.addEventListener("pointercancel", up);
  frame.addEventListener("click", () => { if (!frame.classList.contains("selecting")) clearHighlight(); });
  $("btnArea").onclick = () => (frame.classList.contains("selecting") ? endSelect() : beginSelect());
  $("areaCancel").onclick = endSelect;
  $("areaGo").onclick = () => {
    if (!selRect) return;
    const base = crop || [0, 0, orig.width, orig.height];     // the selection is taken from the full-detail photo
    const x = Math.round(base[0] + selRect[0] * base[2]), y = Math.round(base[1] + selRect[1] * base[3]);
    const w = Math.max(1, Math.min(orig.width - x, Math.round(selRect[2] * base[2]))), h = Math.max(1, Math.min(orig.height - y, Math.round(selRect[3] * base[3])));
    crop = [x, y, w, h]; run();
  };
  $("btnWhole").onclick = () => { crop = null; run(); };
}

// ------------------------------------------------------------------ camera
const camera = new Camera($("video"));
async function openCamera() {
  if (!Camera.supported) return $("fileCam").click();
  try {
    setState("camera");
    await camera.start();
    $("camTorch").hidden = !camera.hasTorch; $("camTorch").classList.remove("on");
  } catch (e) {
    closeCamera();
    if (e && (e.name === "NotAllowedError" || e.name === "SecurityError")) toast("Camera access was not allowed. Allow it in the browser or app settings, or upload a photo.", 5000);
    else $("fileCam").click();                              // no usable camera stream: use the system camera
  }
}
function closeCamera() {
  if (scan.dataset.state !== "camera") return;
  camera.stop(); setState(image && report ? "photo" : "empty");
}
async function shoot() {
  try {
    const blob = await camera.capture();
    const f = $("flash"); f.classList.remove("go"); void f.offsetWidth; f.classList.add("go");
    if (navigator.vibrate) navigator.vibrate(15);
    await sleep(120);
    await setImage(blob, "Camera photo");
  } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ history
const fmtTime = (t) => {
  const d = new Date(t), now = new Date(), day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 864e5), hm = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return diff === 0 ? `Today ${hm}` : diff === 1 ? `Yesterday ${hm}` : `${d.toLocaleDateString([], { day: "numeric", month: "short", year: d.getFullYear() === now.getFullYear() ? undefined : "numeric" })} ${hm}`;
};
const toBlob = (cv, q = 0.85) => new Promise((res) => cv.toBlob(res, "image/jpeg", q));
const slim = (r) => { const { shade, ...rest } = r; return rest; };

async function saveToHistory() {
  if (!$("keepHistory").checked || !report || report.problem) return;
  const src = toCanvas(image), th = document.createElement("canvas"), side = Math.min(src.width, src.height);
  th.width = th.height = 160;
  th.getContext("2d").drawImage(src, (src.width - side) / 2, (src.height - side) / 2, side, side, 0, 0, 160, 160);
  await addScan({
    time: Date.now(), name: report.name, verdict: report.verdict, items: report.items.map(slim), notes: report.notes,
    imageSize: report.imageSize, pxPerMm: report.pxPerMm, timings: report.timings, ms: report.ms,
    thumb: await toBlob(th, 0.8), photo: await toBlob(src, 0.88),
  });
  refreshHistoryCount();
}

async function refreshHistoryCount() {
  let n = 0;
  try { n = (await listScans()).length; } catch { /* storage blocked */ }
  $("histCount").textContent = n; $("histCount").hidden = !n; $("histInfo").textContent = n;
  return n;
}

let thumbUrls = [];
async function renderHistory() {
  let all = [];
  try { all = await listScans(); } catch { /* storage blocked */ }
  for (const u of thumbUrls) URL.revokeObjectURL(u); thumbUrls = [];
  const list = $("histList"); list.replaceChildren();
  $("histEmpty").hidden = all.length > 0; $("histClear").hidden = !all.length;
  all.forEach((rec, i) => {
    const v = rec.verdict, url = URL.createObjectURL(rec.thumb); thumbUrls.push(url);
    const row = document.createElement("div"); row.className = "hist"; row.tabIndex = 0; row.setAttribute("role", "button"); row.style.setProperty("--i", i);
    const chip = v.severity ? `<span class="chip ${v.severity}">${SEV_LABEL[v.severity]}</span>` : `<span class="chip ${v.state}">${v.state === "none" ? "No defects" : "Not analysed"}</span>`;
    row.innerHTML = `<img alt="" src="${url}"><span class="t">${chip}<b></b><small></small></span><button class="del" aria-label="Delete this check"><svg class="ic"><use href="#i-trash"/></svg></button>`;
    row.querySelector("b").textContent = v.title; row.querySelector("small").textContent = `${fmtTime(rec.time)} · ${rec.name}`;
    const open = () => openScan(rec.id);
    row.onclick = open; row.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } };
    row.querySelector(".del").onclick = async (e) => {
      e.stopPropagation(); row.classList.add("gone"); await deleteScan(rec.id); await sleep(220); renderHistory(); refreshHistoryCount();
    };
    list.appendChild(row);
  });
}

async function openScan(id) {
  const rec = await getScan(id);
  if (!rec) return;
  runId++; closeCamera(); endSelect();
  orig = await loadImage(rec.photo); origName = rec.name.replace(/ \(selected area\)$/, ""); crop = null; image = orig;
  report = { ...rec, views: { Defects: toCanvas(image) }, problem: null, when: rec.time, ms: null };
  go("scan"); showPhoto(); showReport();
}

// ------------------------------------------------------------------ share / export
const stamp = () => new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
const fullText = () => `Fabric Inspector report\nSource: ${report.name}\n` + reportText({ timings: {}, ...report });
function saveFile(blob, name) {
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
async function share() {
  if (!report) return;
  const cv = renderDefects(image, report.items), text = fullText(), name = `fabric_check_${stamp()}.jpg`;
  if (native) return native.share(cv.toDataURL("image/jpeg", 0.9).split(",")[1], text);
  const file = new File([await toBlob(cv, 0.9)], name, { type: "image/jpeg" });
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try { await navigator.share({ files: [file], title: "Fabric check: " + report.verdict.title, text }); } catch { /* cancelled */ }
  } else { saveFile(file, name); toast("The marked photo was saved to your downloads."); }
}
function download() {
  if (!report) return;
  if (native) return native.share("", fullText());
  saveFile(new Blob([fullText()], { type: "text/plain" }), `fabric_report_${stamp()}.txt`);
}

// ------------------------------------------------------------------ navigation
const SCREENS = ["scan", "history", "settings"];
function go(name, push = true) {
  if (!SCREENS.includes(name)) name = "scan";
  if ($("app").dataset.screen === name) return;
  if (name !== "scan") closeCamera();
  $("app").dataset.screen = name;
  for (const s of SCREENS) $("scr-" + s).classList.toggle("active", s === name);
  for (const b of document.querySelectorAll(".navbtn")) b.classList.toggle("active", b.dataset.go === name);
  if (push && location.hash.slice(1) !== name) history.pushState(null, "", name === "scan" ? location.pathname + location.search : "#" + name);
  if (name === "history") renderHistory();
  window.scrollTo(0, 0);
}

// ------------------------------------------------------------------ floating bubble (web; the Android app has a native one)
let bubble = null;
function bubbleCardUi(state) {
  $("bubbleOn").checked = state === "on";
  $("webBubbleState").textContent = state !== "on" ? bubbleIntro
    : bubble.pip ? "On. The bubble floats above your other windows; click it for quick actions."
    : "On. Tap the bubble at the edge of the page for quick actions." + (canFloat ? " “Float over other windows” keeps it above other apps." : "");
}
const bubbleIntro = canFloat ? "A small bubble that stays on top of all your windows. Click it to select any part of the screen and check it."
  : canCapture ? "Quick actions in a bubble. Select area checks a window you share, such as a photo viewer."
  : "Quick actions in a bubble on this page. For a bubble over other apps, use the Android app.";
function wireBubble() {
  if (native) return;
  bubble = new Bubble({
    analyseCapture, toast,
    analyseFile: (f) => setImage(f, f.name),
    camera: () => { go("scan"); openCamera(); },
    open: (showLast) => { go("scan"); if (showLast && report) $("results").scrollIntoView({ behavior: "smooth", block: "start" }); },
    pickFile: () => $("fileAny").click(),
    selectInPhoto: () => {
      go("scan");
      if (image && report && !busy) { beginSelect(); $("stage").scrollIntoView({ behavior: "smooth", block: "start" }); }
      else { toast("Choose a photo first, then drag over the part you want to check.", 4500); $("fileAny").click(); }
    },
    onChange: bubbleCardUi,
  });
  $("bubbleOn").addEventListener("change", (e) => { if (e.target.checked) bubble.start(); else bubble.stop(); });
  bubbleCardUi("off");
  bubble.restore();
}

// ------------------------------------------------------------------ Android app bridge
function bubbleUi(on) {
  for (const id of ["bubbleToggle", "bubbleToggle2"]) { $(id).textContent = on ? "Stop" : "Start"; $(id).classList.toggle("primary", !on); }
  $("bubbleState").textContent = on ? "The bubble is on. Open any app that shows fabric and tap the bubble." : "Check fabric shown in any other app: camera, gallery, WhatsApp, a PDF.";
}
function wireNative() {
  if (!native) return;
  document.body.classList.add("native");
  for (const el of document.querySelectorAll(".nativeonly")) el.hidden = false;
  for (const id of ["bubbleToggle", "bubbleToggle2"]) $(id).onclick = () => native.toggleBubble();
  bubbleUi(native.bubbleRunning());
  // called by the app: ("bubble", on, message), ("shared") when a photo was shared to the app, ("action", "camera")
  window.fabricNative = (type, a, b) => {
    if (type === "bubble") { bubbleUi(!!a); if (b) toast(b, 6000); }
    if (type === "shared") takeShared();
    if (type === "action" && a === "camera") { go("scan"); openCamera(); }      // "Take photo" in the bubble
  };
  // the phone's Back button: true = handled here
  window.fabricBack = () => {
    if (scan.dataset.state === "camera") { closeCamera(); return true; }
    if (frame.classList.contains("selecting")) { endSelect(); return true; }
    if ($("app").dataset.screen !== "scan") { go("scan"); return true; }
    if (scan.dataset.state === "photo") { newScan(); return true; }
    return false;
  };
  takeShared();
}
async function takeShared() {
  const b64 = native.takeShared();
  if (!b64) return;
  const blob = await (await fetch("data:image/jpeg;base64," + b64)).blob();
  setImage(blob, "Shared photo");
}

// ------------------------------------------------------------------ wiring
function wireUI() {
  for (const b of document.querySelectorAll("[data-go]")) b.addEventListener("click", () => go(b.dataset.go));
  window.addEventListener("popstate", () => go(location.hash.slice(1) || "scan", false));
  window.addEventListener("scroll", () => document.querySelector(".top").classList.toggle("scrolled", window.scrollY > 4), { passive: true });

  for (const id of ["fileCam", "fileAny"]) $(id).addEventListener("change", (e) => { const f = e.target.files[0]; if (f) setImage(f, f.name); e.target.value = ""; });
  for (const b of document.querySelectorAll(".example")) b.onclick = () => setImage(b.dataset.src, b.dataset.src.split("/").pop());
  $("btnCamera").onclick = openCamera;
  $("camClose").onclick = closeCamera; $("camShutter").onclick = shoot;
  $("camFlip").onclick = () => camera.flip().then(() => ($("camTorch").hidden = !camera.hasTorch)).catch(() => toast("No second camera found."));
  $("camTorch").onclick = async () => { try { $("camTorch").classList.toggle("on", await camera.toggleTorch()); } catch { toast("The torch is not available."); } };
  document.addEventListener("visibilitychange", () => { if (document.hidden) closeCamera(); });

  $("confReset").onclick = () => { $("conf").value = DEFAULTS.conf; saveSettings(); toast("Detection confidence is back to 0.23."); if (image && report) run(); };
  $("btnNew").onclick = newScan; $("btnShare").onclick = share; $("download").onclick = download;
  wireSelect();

  const drop = $("drop");
  window.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  window.addEventListener("dragleave", (e) => { if (!e.relatedTarget) drop.classList.remove("over"); });
  window.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) setImage(f, f.name); });
  window.addEventListener("paste", (e) => { const f = [...e.clipboardData.files][0]; if (f) setImage(f, "Pasted image"); });

  for (const id of FIELDS) $(id).addEventListener("input", saveSettings);
  for (const id of ["chkDef", "chkShade", "chkSkew"]) $(id).addEventListener("change", () => { if (image && report && !report.when) run(); });
  $("resetSettings").onclick = () => { for (const id of FIELDS) setField($(id), DEFAULTS[id]); saveSettings(); toast("Settings are back to the defaults."); };
  $("histClear").onclick = async () => { if (confirm("Delete all saved checks from this device?")) { await clearScans(); renderHistory(); refreshHistoryCount(); } };

  let deferred = null;
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e; $("installRow").hidden = false; });
  $("install").onclick = async () => { if (deferred) { deferred.prompt(); await deferred.userChoice; deferred = null; $("installRow").hidden = true; } };
}

/** Downloads the model with a progress figure (instant once the app is cached for offline use). */
async function fetchModel(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`model download failed (${res.status})`);
  const total = +res.headers.get("content-length") || 0;
  if (!res.body || !total) return new Uint8Array(await res.arrayBuffer());
  const buf = new Uint8Array(total), reader = res.body.getReader();
  let n = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (n + value.length > total) return new Uint8Array(await (await fetch(url)).arrayBuffer());   // size header was for a compressed body
    buf.set(value, n); n += value.length;
    $("enginePct").textContent = Math.round((n / total) * 100) + "%";
  }
  return n === total ? buf : buf.subarray(0, n);
}

async function init() {
  loadSettings(); wireUI(); wireNative(); wireBubble();
  go(location.hash.slice(1) || "scan", false);
  refreshHistoryCount();
  status("Loading AI", "loading");
  await loadKB("kb.json");
  const bytes = await fetchModel("model/best.onnx");
  status("Starting AI", "loading");
  detector = await Detector.create(bytes);
  $("engineInfo").textContent = (detector.backend.startsWith("compat") ? "compatibility (slower)" : "fast (SIMD)") + ` · model ${detector.size} px`;
  status("Ready");
}

const ready = init().catch((e) => { status("Could not start: " + e.message, "error"); console.error(e); throw e; });
ready.catch(() => {});
if ("serviceWorker" in navigator && location.protocol !== "file:") {
  // an update replaces every cached file at once; reload so the page never mixes two versions
  if (navigator.serviceWorker.controller) navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!busy && !image && !(bubble && bubble.state !== "off")) location.reload(); else toast("An update is ready. It is used the next time you open the app.", 5000);
  });
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

// test hook used by the automatic tests (tests/test_static.py)
window.fabricApp = {
  ready,
  backend: () => detector && detector.backend,
  bubble: () => bubble,
  analyseCapture,
  busy: () => busy,
  async analyseUrl(url, s) {
    await ready;
    const img = await loadImage(url);
    const lim = limitSize(img, MAX_SIDE);
    const full = { doDefects: true, doShade: false, doSkew: false, conf: 0.23, pxPerMm: 0, shadeTol: 1, skewLimit: 3, bowLimit: 2, weft: "horizontal", ...s };
    const rep = await analyse(lim.img, full);
    return { size: rep.imageSize, timings: rep.timings, notes: rep.notes, verdict: rep.verdict,
             items: rep.items.map((r) => ({ defect: r.defect, severity: r.severity, confidence: r.confidence, box: r.box, basis: r.severity_basis, shade: r.shade, skew: r.skew })) };
  },
};
