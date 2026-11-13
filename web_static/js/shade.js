// Shade variation (CIELAB delta E) - JavaScript port of src/shade/delta_e.py
import { resizeArea, jet } from "./imgutil.js";

const GREY = [[0.4, "5"], [1.25, "4-5"], [2.1, "4"], [2.95, "3-4"], [4.1, "3"], [5.8, "2-3"], [8.2, "2"], [11.6, "1-2"]];
export function greyScaleGrade(de) { for (const [lim, g] of GREY) if (de < lim) return g; return "1"; }

// --- colour conversion identical to skimage.color.rgb2lab (sRGB, D65, 2 deg) ---
const WP = [0.95047, 1.0, 1.08883];
const lin = (c) => (c > 0.04045 ? Math.pow((c + 0.055) / 1.055, 2.4) : c / 12.92);
const f = (t) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
export function rgb2lab(r, g, b) {                       // r,g,b in 0..1
  const R = lin(r), G = lin(g), B = lin(b);
  const X = (0.412453 * R + 0.35758 * G + 0.180423 * B) / WP[0];
  const Y = (0.212671 * R + 0.71516 * G + 0.072169 * B) / WP[1];
  const Z = (0.019334 * R + 0.119193 * G + 0.950227 * B) / WP[2];
  const fx = f(X), fy = f(Y), fz = f(Z);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

// --- delta E formulas identical to skimage.color ---
export function deltaE76(p, q) { return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]); }

export function deltaECMC(ref, t, kL = 2, kC = 1) {
  const [L1, a1, b1] = ref, [L2, a2, b2] = t;
  const C1 = Math.hypot(a1, b1), C2 = Math.hypot(a2, b2);
  let h1 = Math.atan2(b1, a1); if (h1 < 0) h1 += 2 * Math.PI;
  const dC = C1 - C2, dL = L1 - L2;
  const dH2 = 2 * (C1 * C2 - (a1 * a2 + b1 * b2));
  const hd = (h1 * 180) / Math.PI;
  const T = hd >= 164 && hd <= 345 ? 0.56 + Math.abs(0.2 * Math.cos(h1 + (168 * Math.PI) / 180))
                                   : 0.36 + Math.abs(0.4 * Math.cos(h1 + (35 * Math.PI) / 180));
  const c14 = C1 ** 4, F = Math.sqrt(c14 / (c14 + 1900));
  const SL = L1 < 16 ? 0.511 : (0.040975 * L1) / (1 + 0.01765 * L1);
  const SC = 0.638 + (0.0638 * C1) / (1 + 0.0131 * C1);
  const SH = SC * (F * T + 1 - F);
  const d2 = (dL / (kL * SL)) ** 2 + (dC / (kC * SC)) ** 2 + dH2 / SH ** 2;
  return Math.sqrt(Math.max(d2, 0));
}

export function deltaE2000(p, q) {
  const [L1, a1, b1] = p, [L2, a2, b2] = q, PI = Math.PI, rad = PI / 180;
  let Cbar = 0.5 * (Math.hypot(a1, b1) + Math.hypot(a2, b2));
  let c7 = Cbar ** 7;
  const G = 0.5 * (1 - Math.sqrt(c7 / (c7 + 25 ** 7))), sc = 1 + G;
  const pol = (x, y) => { let t = Math.atan2(y, x); if (t < 0) t += 2 * PI; return [Math.hypot(x, y), t]; };
  const [C1, h1] = pol(a1 * sc, b1), [C2, h2] = pol(a2 * sc, b2);
  const Lbar = 0.5 * (L1 + L2), tmp = (Lbar - 50) ** 2;
  const SL = 1 + (0.015 * tmp) / Math.sqrt(20 + tmp);
  const Lt = (L2 - L1) / SL;
  Cbar = 0.5 * (C1 + C2);
  const SC = 1 + 0.045 * Cbar, Ct = (C2 - C1) / SC;
  const hdiff = h2 - h1, hsum = h1 + h2, CC = C1 * C2;
  let dH = hdiff; if (hdiff > PI) dH -= 2 * PI; if (hdiff < -PI) dH += 2 * PI; if (CC === 0) dH = 0;
  const dHt = 2 * Math.sqrt(CC) * Math.sin(dH / 2);
  let Hbar = hsum;
  if (CC !== 0 && Math.abs(hdiff) > PI) Hbar += hsum < 2 * PI ? 2 * PI : -2 * PI;
  if (CC === 0) Hbar *= 2;
  Hbar *= 0.5;
  const T = 1 - 0.17 * Math.cos(Hbar - 30 * rad) + 0.24 * Math.cos(2 * Hbar) + 0.32 * Math.cos(3 * Hbar + 6 * rad) - 0.2 * Math.cos(4 * Hbar - 63 * rad);
  const SH = 1 + 0.015 * Cbar * T, Ht = dHt / SH;
  c7 = Cbar ** 7;
  const Rc = 2 * Math.sqrt(c7 / (c7 + 25 ** 7));
  const dth = 30 * rad * Math.exp(-(((Hbar / rad - 275) / 25) ** 2));
  const Rt = -Math.sin(2 * dth) * Rc * Ct * Ht;
  return Math.sqrt(Math.max(Lt ** 2 + Ct ** 2 + Ht ** 2 + Rt, 0));
}

export function colorDifference(ref, test) {
  const dL = test[0] - ref[0], da = test[1] - ref[1], db = test[2] - ref[2];
  const dC = Math.hypot(test[1], test[2]) - Math.hypot(ref[1], ref[2]);
  const de = deltaE76(ref, test);
  const dH = Math.sqrt(Math.max(de * de - dL * dL - dC * dC, 0));
  const dir = [];
  if (Math.abs(dL) > 0.3) dir.push(dL < 0 ? "darker" : "lighter");
  if (Math.abs(dC) > 0.3) dir.push(dC < 0 ? "duller" : "brighter");
  if (Math.abs(da) > 0.3) dir.push(da < 0 ? "greener" : "redder");
  if (Math.abs(db) > 0.3) dir.push(db < 0 ? "bluer" : "yellower");
  return { dE_cmc21: deltaECMC(ref, test, 2, 1), dE2000: deltaE2000(ref, test), dE_ab: de,
           dL, da, db, dC, dH, direction: dir.join(", ") || "no visible direction", grey_scale: greyScaleGrade(de) };
}

/** cv2.GaussianBlur(5x5, sigma 0) uses the fixed kernel [1,4,6,4,1]/16, border REFLECT_101; output uint8. */
function blur5(img) {
  const { data, width: w, height: h } = img, K = [0.0625, 0.25, 0.375, 0.25, 0.0625];
  const refl = (i, n) => (i < 0 ? -i : i >= n ? 2 * n - 2 - i : i);
  const tmp = new Float32Array(w * h * 3), out = new Uint8ClampedArray(w * h * 3);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) for (let k = 0; k < 3; k++) {
    let s = 0; for (let j = -2; j <= 2; j++) s += K[j + 2] * data[(y * w + refl(x + j, w)) * 4 + k];
    tmp[(y * w + x) * 3 + k] = s;
  }
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) for (let k = 0; k < 3; k++) {
    let s = 0; for (let j = -2; j <= 2; j++) s += K[j + 2] * tmp[(refl(y + j, h) * w + x) * 3 + k];
    out[(y * w + x) * 3 + k] = Math.round(s);
  }
  return out;
}

export function toLab(img) {
  const rgb = blur5(img), n = img.width * img.height, lab = new Float32Array(n * 3);
  const lut = new Float64Array(256); for (let i = 0; i < 256; i++) lut[i] = i / 255;
  for (let i = 0; i < n; i++) {
    const L = rgb2lab(lut[rgb[i * 3]], lut[rgb[i * 3 + 1]], lut[rgb[i * 3 + 2]]);
    lab[i * 3] = L[0]; lab[i * 3 + 1] = L[1]; lab[i * 3 + 2] = L[2];
  }
  return lab;
}

function median(a) { const s = Float64Array.from(a).sort(); const m = s.length >> 1; return s.length % 2 ? s[m] : 0.5 * (s[m - 1] + s[m]); }

/** Same logic as analyse_shade(): reference = median cell colour, test = worst 5% of cells; excluded boxes ignored. */
export function analyseShade(img, { tolerance = 1.0, excludeRects = [] } = {}) {
  const { width: w, height: h } = img;
  const cell = Math.max(8, Math.floor(Math.min(h, w) / 24));
  const lab = toLab(img);
  const rows = Math.max(1, Math.floor(h / cell)), cols = Math.max(1, Math.floor(w / cell));
  const cells = resizeArea(lab, w, h, 3, cols, rows);
  let keep = new Uint8Array(rows * cols).fill(1);
  for (const [x, y, rw, rh] of excludeRects) {
    const c0 = Math.floor((x * cols) / w), c1 = Math.ceil(((x + rw) * cols) / w);
    const r0 = Math.floor((y * rows) / h), r1 = Math.ceil(((y + rh) * rows) / h);
    for (let r = Math.max(r0, 0); r < Math.min(r1, rows); r++) for (let c = Math.max(c0, 0); c < Math.min(c1, cols); c++) keep[r * cols + c] = 0;
  }
  if (keep.reduce((s, v) => s + v, 0) / keep.length < 0.2) keep.fill(1);
  const kept = []; for (let i = 0; i < rows * cols; i++) if (keep[i]) kept.push(i);
  const ref = [0, 1, 2].map((k) => median(kept.map((i) => cells[i * 3 + k])));
  const heat = new Float32Array(rows * cols);
  for (let i = 0; i < rows * cols; i++) heat[i] = deltaECMC(ref, [cells[i * 3], cells[i * 3 + 1], cells[i * 3 + 2]]);
  const order = kept.slice().sort((a, b) => heat[a] - heat[b]);
  const k = Math.max(1, Math.floor(0.05 * kept.length));
  const test = [0, 0, 0];
  for (const i of order.slice(-k)) for (let c = 0; c < 3; c++) test[c] += cells[i * 3 + c] / k;
  const details = colorDifference(ref, test);
  const value = details.dE_cmc21;
  const pct = (kept.filter((i) => heat[i] > tolerance).length / kept.length) * 100;
  for (let i = 0; i < heat.length; i++) if (!keep[i]) heat[i] = 0;
  const passed = value <= tolerance;
  const summary = `Shade ${passed ? "PASS" : "FAIL"}: dE CMC(2:1) = ${details.dE_cmc21.toFixed(2)} (tolerance ${tolerance}), ` +
    `dE2000 = ${details.dE2000.toFixed(2)}, grey scale ~${details.grey_scale}; test area is ${details.direction}. ` +
    `${pct.toFixed(0)}% of the image exceeds tolerance.`;
  return { passed, value, details, pct, heat, rows, cols, ref, test, summary,
           overlay: drawOverlay(img, heat, rows, cols, tolerance, 3 * tolerance, excludeRects) };
}

function drawOverlay(img, heat, rows, cols, tol, vmax, excl) {
  const { width: w, height: h, data } = img;
  const out = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) {
    const r = Math.min(rows - 1, Math.floor((y * rows) / h));
    for (let x = 0; x < w; x++) {
      const c = Math.min(cols - 1, Math.floor((x * cols) / w)), v = heat[r * cols + c];
      const col = jet(Math.min(1, v / vmax)), i = (y * w + x) * 4;
      for (let k = 0; k < 3; k++) out[i + k] = 0.45 * data[i + k] + 0.55 * col[k];
      // white outline around cells beyond tolerance
      const over = v > tol;
      const edge = over && ((x > 0 && Math.floor(((x - 1) * cols) / w) !== c && !(heat[r * cols + c - 1] > tol)) ||
                            (y > 0 && Math.floor(((y - 1) * rows) / h) !== r && !(heat[(r - 1) * cols + c] > tol)) ||
                            (x < w - 1 && Math.floor(((x + 1) * cols) / w) !== c && !(heat[r * cols + Math.min(c + 1, cols - 1)] > tol)) ||
                            (y < h - 1 && Math.floor(((y + 1) * rows) / h) !== r && !(heat[Math.min(r + 1, rows - 1) * cols + c] > tol)));
      if (edge) out[i] = out[i + 1] = out[i + 2] = 255;
      out[i + 3] = 255;
    }
  }
  return { data: out, width: w, height: h, excl, legend: vmax };
}
