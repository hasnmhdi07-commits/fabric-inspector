// YOLO11 detector running in the browser with ONNX Runtime Web (WebAssembly).
// Pre/post-processing replicates Ultralytics: letterbox to 640, decode [1, 4+nc, 8400], class-wise NMS.
import { resizeBilinearRGB } from "./imgutil.js";

export const CLASSES = ["hole_tear", "stain", "slub_neps", "broken_pick_end"];
const S = 640;

// WebAssembly SIMD support test (same bytes as the wasm-feature-detect library).
// SIMD exists in Chrome/Edge 91+, Firefox 89+, Safari 16.4+ (iOS 16.4+). Older devices get a compatible engine.
const SIMD_OK = (() => {
  try { return WebAssembly.validate(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0, 1, 5, 1, 96, 0, 1, 123, 3, 2, 1, 0, 10, 10, 1, 8, 0, 65, 0, 253, 15, 253, 98, 11])); }
  catch { return false; }
})();

async function loadOrt() {
  const legacy = !SIMD_OK || new URLSearchParams(location.search).has("legacy");
  const dir = legacy ? "../ort-legacy/" : "../ort/";
  // fast engine: onnxruntime-web 1.31.1 (needs SIMD); compatibility engine: 1.18.0 (has a non-SIMD build)
  const ort = legacy ? await import("../ort-legacy/ort.wasm.min.js") : await import("../ort/ort.wasm.min.mjs");
  ort.env.wasm.wasmPaths = new URL(dir, import.meta.url).href;
  ort.env.wasm.numThreads = 1;        // static hosting has no cross-origin isolation -> single thread
  if (legacy) ort.env.wasm.simd = false;
  return { ort, backend: legacy ? "compatibility engine (no SIMD)" : "fast engine (SIMD)" };
}

export class Detector {
  static async create(modelUrl) {
    const d = new Detector();
    const { ort, backend } = await loadOrt();
    d.ort = ort; d.backend = backend;
    d.session = await ort.InferenceSession.create(modelUrl, { executionProviders: ["wasm"] });
    d.input = d.session.inputNames[0];
    d.output = d.session.outputNames[0];
    return d;
  }

  /** img: {data: RGBA, width, height}. Returns [{cls, name, conf, box:[x1,y1,x2,y2]}] in image pixels. */
  async detect(img, { conf = 0.23, iou = 0.5, maxDet = 300 } = {}) {
    const { width: w, height: h } = img;
    // letterbox (same rounding as ultralytics LetterBox(auto=False))
    const r = Math.min(S / h, S / w);
    const nw = Math.round(w * r), nh = Math.round(h * r);
    const left = Math.round((S - nw) / 2 - 0.1), top = Math.round((S - nh) / 2 - 0.1);
    const rs = resizeBilinearRGB(img, nw, nh);
    const t = new Float32Array(3 * S * S).fill(114 / 255);
    for (let y = 0; y < nh; y++) {
      for (let x = 0; x < nw; x++) {
        const si = (y * nw + x) * 3, di = (top + y) * S + (left + x);
        t[di] = Math.round(rs[si]) / 255;                 // R
        t[S * S + di] = Math.round(rs[si + 1]) / 255;     // G
        t[2 * S * S + di] = Math.round(rs[si + 2]) / 255; // B
      }
    }
    const out = await this.session.run({ [this.input]: new this.ort.Tensor("float32", t, [1, 3, S, S]) });
    const o = out[this.output].data, N = out[this.output].dims[2], nc = out[this.output].dims[1] - 4;

    const cand = [];
    for (let i = 0; i < N; i++) {
      let best = -1, bs = 0;
      for (let c = 0; c < nc; c++) { const s = o[(4 + c) * N + i]; if (s > bs) { bs = s; best = c; } }
      if (bs <= conf) continue;
      const cx = o[i], cy = o[N + i], bw = o[2 * N + i], bh = o[3 * N + i];
      cand.push({ cls: best, conf: bs, b: [cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2] });
    }
    cand.sort((a, b) => b.conf - a.conf);
    const keep = [];
    for (const c of cand) {                                 // class-aware greedy NMS
      if (keep.length >= maxDet) break;
      if (keep.every((k) => k.cls !== c.cls || iouOf(k.b, c.b) <= iou)) keep.push(c);
    }
    return keep.map((k) => {
      const [x1, y1, x2, y2] = k.b;
      const box = [(x1 - left) / r, (y1 - top) / r, (x2 - left) / r, (y2 - top) / r];
      box[0] = clamp(box[0], 0, w); box[2] = clamp(box[2], 0, w);
      box[1] = clamp(box[1], 0, h); box[3] = clamp(box[3], 0, h);
      return { cls: k.cls, name: CLASSES[k.cls], conf: k.conf, box };
    });
  }
}

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
function iouOf(a, b) {
  const ix = Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0]));
  const iy = Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  const inter = ix * iy;
  return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9);
}
