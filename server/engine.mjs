// Server-side analysis engine: the SAME JavaScript modules as the browser app (web_static/js),
// so a photo gives the same result on the server as on the device.
// Only two things differ from the browser: how the image is decoded (no <canvas> here) and that
// no pictures are drawn - the API returns numbers and text, the client draws the boxes.
import { readFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import sharp from "sharp";

import { Detector } from "../web_static/js/detector.js";
import { analyseShade } from "../web_static/js/shade.js";
import { analyseSkewBow } from "../web_static/js/skew.js";
import { loadKB, assess, worstSeverity, SEVERITY_ORDER } from "../web_static/js/kb.js";
import { limitSize } from "../web_static/js/imgutil.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(HERE, "..", "web_static");
export const MAX_SIDE = 1600;
export const DEFAULTS = { doDefects: true, doShade: false, doSkew: false, conf: 0.23, pxPerMm: 0,
                          shadeTol: 1, skewLimit: 3, bowLimit: 2, weft: "horizontal" };

let enginePromise = null;

/** Loads the model and knowledge base once per server process (reused by later requests). */
export function getEngine() {
  enginePromise ??= (async () => {
    const t0 = performance.now();
    const ort = await import(pathToFileURL(path.join(STATIC, "ort", "ort.wasm.min.mjs")).href);
    ort.env.wasm.wasmPaths = pathToFileURL(path.join(STATIC, "ort") + path.sep).href;
    ort.env.wasm.numThreads = 1;
    const kb = await readFile(path.join(STATIC, "kb.json"));
    await loadKB("data:application/json;base64," + kb.toString("base64"));
    const model = await readFile(path.join(STATIC, "model", "best.onnx"));
    const d = Object.create(Detector.prototype);          // same detect() code as the browser
    d.ort = ort; d.backend = "server (WebAssembly)";
    d.session = await ort.InferenceSession.create(new Uint8Array(model), { executionProviders: ["wasm"] });
    d.input = d.session.inputNames[0]; d.output = d.session.outputNames[0];
    return { detector: d, loadMs: performance.now() - t0 };
  })();
  return enginePromise;
}

/** Image bytes (JPEG, PNG, WebP ...) -> {data: RGBA, width, height}.
 *  sharp uses libjpeg-turbo, the same JPEG decoder family as OpenCV and browsers; a pure-JavaScript
 *  decoder gave different pixels (shade dE 2.58 instead of 1.88 on the hole example).
 *  .rotate() applies the phone's EXIF orientation, as browsers do. */
export async function decodeImage(buf) {
  try {
    const { data, info } = await sharp(buf).rotate().toColourspace("srgb").ensureAlpha().raw()
      .toBuffer({ resolveWithObject: true });
    return { data: new Uint8Array(data.buffer, data.byteOffset, data.length), width: info.width, height: info.height };
  } catch {
    throw new Error("This file could not be read as a photo. Send a JPEG or PNG image.");
  }
}

/** Full analysis of one image. Mirrors analyse() in web_static/js/main.js, without drawing. */
export async function analyse(buf, settings = {}) {
  const { detector } = await getEngine();
  const s = { ...DEFAULTS, ...settings };
  const t = {};
  let t0 = performance.now();
  const lim = limitSize(await decodeImage(buf), MAX_SIDE);
  const img = lim.img;
  s.pxPerMm *= lim.factor;
  t.decode = performance.now() - t0;
  const W = img.width, H = img.height, items = [], notes = [];

  if (s.doDefects) {
    t0 = performance.now();
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
    t0 = performance.now();
    const excl = items.filter((r) => r.box).map((r) => [r.box[0], r.box[1], r.box[2] - r.box[0], r.box[3] - r.box[1]]);
    const sh = analyseShade(img, { tolerance: s.shadeTol, excludeRects: excl });
    t.shade = performance.now() - t0;
    const r = assess("shade_variation", { deltaE: sh.value, shadeTolerance: s.shadeTol });
    r.measure = sh.summary; r.shade = sh.details; items.push(r);
  }
  if (s.doSkew) {
    t0 = performance.now();
    try {
      const sk = analyseSkewBow(img, { weft: s.weft, skewTol: s.skewLimit, bowTol: s.bowLimit });
      for (const [name, o] of [["skewing", { skewPct: sk.skewPct, skewLimit: s.skewLimit }], ["bowing", { bowPct: sk.bowPct, bowLimit: s.bowLimit }]]) {
        const r = assess(name, o); r.measure = sk.summary; r.skew = { skewPct: sk.skewPct, bowPct: sk.bowPct }; items.push(r);
      }
    } catch (e) { notes.push(`Bow/skew check skipped: ${e.message}`); }
    t.bow_skew = performance.now() - t0;
  }
  const si = (x) => SEVERITY_ORDER.indexOf(x);
  items.sort((a, b) => si(b.severity) - si(a.severity) || (b.confidence ?? 0) - (a.confidence ?? 0));
  items.forEach((r, i) => (r.index = i + 1));
  if (s.doShade || s.doSkew) notes.push("Shade and bow/skew need a flat fabric photo taken straight from above in even light; other photos give only indicative values.");
  return { imageSize: [W, H], scaleFactor: lim.factor, worst: worstSeverity(items), items, notes, timings: t };
}
