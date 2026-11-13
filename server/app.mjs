// Fabric Inspector API (Express, stateless: nothing is stored - the photo is analysed in memory and forgotten).
//   POST /api/analyze   image in -> full result out
//   GET  /api/health    model version and engine status
// The image can be sent in two ways:
//   - as the raw request body (Content-Type: image/jpeg or image/png)   <- iPhone Shortcut
//   - as a form upload, field name "image" (multipart/form-data)        <- web page
// Settings are optional query parameters, e.g. /api/analyze?shade=1&skew=1&conf=0.3&pxPerMm=4.2
import express from "express";
import multer from "multer";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { getEngine, analyse, DEFAULTS } from "./engine.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MODEL = path.resolve(HERE, "..", "web_static", "model", "best.onnx");
const MAX_BYTES = Math.floor(4.4 * 1024 * 1024);       // Vercel refuses request bodies above ~4.5 MB
const TOO_BIG = "Photo is too large to send (limit 4 MB). Reduce it to 1600 pixels on the longest side and try again.";

export const app = express();
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: MAX_BYTES, files: 1 } });

app.use((req, res, next) => {               // lets the web app and the phone apps call the API from any origin
  res.set({ "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Cache-Control": "no-store" });
  if (req.method === "OPTIONS") return res.sendStatus(204);
  next();
});

const fail = (res, status, error, fix) => res.status(status).json({ ok: false, error, fix });
const num = (v, d, lo, hi) => { const x = Number(v); return v === undefined || !Number.isFinite(x) ? d : Math.min(hi, Math.max(lo, x)); };
const flag = (v, d) => (v === undefined ? d : ["1", "true", "yes", "on"].includes(String(v).toLowerCase()));

function settingsFrom(q) {
  return {
    doDefects: flag(q.defects, DEFAULTS.doDefects), doShade: flag(q.shade, DEFAULTS.doShade), doSkew: flag(q.skew, DEFAULTS.doSkew),
    conf: num(q.conf, DEFAULTS.conf, 0.05, 0.9), pxPerMm: num(q.pxPerMm, DEFAULTS.pxPerMm, 0, 100),
    shadeTol: num(q.shadeTol, DEFAULTS.shadeTol, 0.2, 5), skewLimit: num(q.skewLimit, DEFAULTS.skewLimit, 0.5, 10),
    bowLimit: num(q.bowLimit, DEFAULTS.bowLimit, 0.5, 10), weft: q.weft === "vertical" ? "vertical" : "horizontal",
  };
}

let modelInfo = null;
async function getModelInfo() {
  modelInfo ??= (async () => {
    const buf = await readFile(MODEL);
    return { file: "best.onnx", sizeMB: +(buf.length / 1048576).toFixed(1), sha256: createHash("sha256").update(buf).digest("hex").slice(0, 12) };
  })();
  return modelInfo;
}

app.get("/api/health", async (req, res) => {
  try {
    const { detector, loadMs } = await getEngine();
    res.json({ ok: true, engine: detector.backend, engineLoadMs: Math.round(loadMs), model: await getModelInfo(),
               classes: ["hole_tear", "stain", "slub_neps", "broken_pick_end"], stores: "nothing" });
  } catch (e) {
    console.error(e);
    fail(res, 503, "The analysis engine could not start.", "Try again in a minute.");
  }
});

app.post("/api/analyze",
  express.raw({ type: ["image/*", "application/octet-stream"], limit: MAX_BYTES }),
  upload.single("image"),
  async (req, res) => {
    const buf = req.file?.buffer ?? (Buffer.isBuffer(req.body) && req.body.length ? req.body : null);
    if (!buf) return fail(res, 400, "No photo was received.", "Send a JPEG or PNG photo (form field \"image\", or as the request body).");
    const s = settingsFrom(req.query);
    if (!(s.doDefects || s.doShade || s.doSkew)) return fail(res, 400, "No check is switched on.", "Switch on at least one check: defects, shade or bow/skew.");
    try {
      const t0 = performance.now();
      const rep = await analyse(buf, s);
      res.json({ ok: true, ...rep, totalMs: Math.round(performance.now() - t0), settings: s });
    } catch (e) {
      if (/could not be read as a photo/.test(e.message)) return fail(res, 415, "This file could not be read as a photo.", "Send a JPEG or PNG image.");
      console.error(e);
      fail(res, 500, "The photo could not be analysed.", "Try again. If it keeps failing, try another photo.");
    }
  });

app.use((req, res) => fail(res, 404, "This address does not exist.", "Use POST /api/analyze or GET /api/health."));
app.use((err, req, res, next) => {          // upload errors (too large ...) - never show raw technical messages
  if (err?.type === "entity.too.large" || err?.code === "LIMIT_FILE_SIZE") return fail(res, 413, "Photo is too large.", TOO_BIG);
  console.error(err);
  fail(res, 400, "The request could not be read.", "Send one JPEG or PNG photo.");
});

export default app;
