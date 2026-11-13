// Bow / skew measurement - JavaScript port of src/skew/bow_skew.py (projection-profile method).
import { resizeArea, toGray } from "./imgutil.js";

/** OpenCV-style CLAHE (clipLimit 2, 8x8 tiles) on a uint8 gray image (values in Float32Array). */
function clahe(src, w, h, clip = 2.0, tiles = 8) {
  // pad to a multiple of the tile grid (BORDER_REFLECT_101), as OpenCV does
  const pw = w % tiles ? w + tiles - (w % tiles) : w, ph = h % tiles ? h + tiles - (h % tiles) : h;
  const refl = (i, n) => (i < 0 ? -i : i >= n ? 2 * n - 2 - i : i);
  const tw = pw / tiles, th = ph / tiles, area = tw * th;
  const limit = Math.max(Math.floor((clip * area) / 256), 1), scale = 255 / area;
  const luts = [];
  for (let ty = 0; ty < tiles; ty++) for (let tx = 0; tx < tiles; tx++) {
    const hist = new Int32Array(256);
    for (let y = ty * th; y < (ty + 1) * th; y++) for (let x = tx * tw; x < (tx + 1) * tw; x++)
      hist[src[refl(y, h) * w + refl(x, w)]]++;
    let clipped = 0;
    for (let i = 0; i < 256; i++) if (hist[i] > limit) { clipped += hist[i] - limit; hist[i] = limit; }
    const batch = Math.floor(clipped / 256); let resid = clipped - batch * 256;
    for (let i = 0; i < 256; i++) hist[i] += batch;
    if (resid > 0) { const step = Math.max(Math.floor(256 / resid), 1); for (let i = 0; i < 256 && resid > 0; i += step, resid--) hist[i]++; }
    const lut = new Uint8Array(256); let sum = 0;
    for (let i = 0; i < 256; i++) { sum += hist[i]; lut[i] = Math.min(255, Math.round(sum * scale)); }
    luts.push(lut);
  }
  const out = new Float32Array(w * h);
  for (let y = 0; y < h; y++) {
    const tyf = y / th - 0.5; let ty1 = Math.floor(tyf); const ya = tyf - ty1; let ty2 = ty1 + 1;
    ty1 = Math.max(ty1, 0); ty2 = Math.min(ty2, tiles - 1);
    for (let x = 0; x < w; x++) {
      const txf = x / tw - 0.5; let tx1 = Math.floor(txf); const xa = txf - tx1; let tx2 = tx1 + 1;
      tx1 = Math.max(tx1, 0); tx2 = Math.min(tx2, tiles - 1);
      const v = src[y * w + x];
      const r = (luts[ty1 * tiles + tx1][v] * (1 - xa) + luts[ty1 * tiles + tx2][v] * xa) * (1 - ya) +
                (luts[ty2 * tiles + tx1][v] * (1 - xa) + luts[ty2 * tiles + tx2][v] * xa) * ya;
      out[y * w + x] = Math.round(r);
    }
  }
  return out;
}

function prep(img, weft = "horizontal", maxSide = 1200) {
  let g = toGray(img), w = img.width, h = img.height;
  if (weft === "vertical") {                            // rotate 90 deg counter-clockwise
    const r = new Float32Array(w * h);
    for (let y = 0; y < w; y++) for (let x = 0; x < h; x++) r[y * h + x] = g[x * w + (w - 1 - y)];
    g = r; [w, h] = [h, w];
  }
  const s = maxSide / Math.max(w, h);
  if (s < 1) {
    const nw = Math.round(w * s), nh = Math.round(h * s);
    g = resizeArea(g, w, h, 1, nw, nh).map(Math.round); w = nw; h = nh;
  }
  return { g: clahe(g, w, h), w, h };
}

/** Stripe sharpness of the row profile after shearing the strip so lines at `deg` become horizontal. */
function sharpness(g, W, x0, sw, h, deg, margin) {
  const t = Math.tan((deg * Math.PI) / 180), n = h - 2 * margin, prof = new Float64Array(n);
  for (let x = 0; x < sw; x++) {
    const off = t * (x - sw / 2), col = x0 + x;
    for (let j = 0; j < n; j++) {
      const yf = margin + j + off, y0 = Math.floor(yf), a = yf - y0;
      prof[j] += (1 - a) * g[y0 * W + col] + a * g[(y0 + 1) * W + col];
    }
  }
  let mean = 0; const d = new Float64Array(n - 1);
  for (let j = 0; j < n - 1; j++) { d[j] = (prof[j + 1] - prof[j]) / sw; mean += d[j]; }
  mean /= n - 1; let v = 0;
  for (let j = 0; j < n - 1; j++) v += (d[j] - mean) ** 2;
  return v / (n - 1);
}

function weftAngle(g, W, x0, x1, h, maxAngle = 12) {
  const sw = x1 - x0, margin = Math.ceil(Math.tan((maxAngle * Math.PI) / 180) * sw / 2) + 2;
  if (h - 2 * margin < 20) throw new Error("strip too short for the angle range");
  let best = 0, bs = -1;
  for (let a = -maxAngle; a <= maxAngle + 1e-9; a += 0.25) {
    const s = sharpness(g, W, x0, sw, h, a, margin); if (s > bs) { bs = s; best = a; }
  }
  const fine = [], sc = [];
  for (let i = 0; i <= 30; i++) { const a = best - 0.3 + 0.02 * i; fine.push(a); sc.push(sharpness(g, W, x0, sw, h, a, margin)); }
  const i = sc.indexOf(Math.max(...sc));
  if (i > 0 && i < fine.length - 1) {
    const den = sc[i - 1] - 2 * sc[i] + sc[i + 1];
    return fine[i] + (den !== 0 ? (0.5 * (sc[i - 1] - sc[i + 1])) / den : 0) * 0.02;
  }
  return fine[i];
}

export function analyseSkewBow(img, { weft = "horizontal", nStrips = 7, skewTol = 3.0, bowTol = 2.0, maxAngle = 12 } = {}) {
  const { g, w, h } = prep(img, weft);
  const edges = Array.from({ length: nStrips + 1 }, (_, i) => Math.floor((w * i) / nStrips));
  const angles = [];
  for (let i = 0; i < nStrips; i++) angles.push(weftAngle(g, w, edges[i], edges[i + 1], h, maxAngle));
  const ys = [0];
  for (let i = 0; i < nStrips; i++) ys.push(ys[i] + Math.tan((angles[i] * Math.PI) / 180) * (edges[i + 1] - edges[i]));
  const W = edges[nStrips] - edges[0];
  const skew = ((ys[nStrips] - ys[0]) / W) * 100;
  let k = 0, dmax = 0;
  const dev = ys.map((y, i) => y - (ys[0] + ((ys[nStrips] - ys[0]) * (edges[i] - edges[0])) / W));
  dev.forEach((d, i) => { if (Math.abs(d) > Math.abs(dmax)) { dmax = d; k = i; } });
  const bow = (dmax / W) * 100;
  const passed = Math.abs(skew) <= skewTol && Math.abs(bow) <= bowTol;
  const side = skew > 0 ? "right side lower" : "left side lower";
  const bowType = (Math.sign(bow) || 1) > 0 ? "bow (centre lagging / sagging)" : "bow (centre leading)";
  const summary = `Skew ${Math.abs(skew).toFixed(2)}% (${side}), Bow ${Math.abs(bow).toFixed(2)}% ${bowType} -> ` +
                  `${passed ? "PASS" : "FAIL"} (limits: skew ${skewTol}%, bow ${bowTol}%).`;
  const yMid = h / 2 - (Math.max(...ys) + Math.min(...ys)) / 2;
  const gray = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) { gray[i * 4] = gray[i * 4 + 1] = gray[i * 4 + 2] = g[i]; gray[i * 4 + 3] = 255; }
  return { skewPct: skew, bowPct: bow, angles, passed, summary, tolerances: { skew: skewTol, bow: bowTol },
           view: { data: gray, width: w, height: h, edges, pts: edges.map((x, i) => [x, ys[i] + yMid]) } };
}
