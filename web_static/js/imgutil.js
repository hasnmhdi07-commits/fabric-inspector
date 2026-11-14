// Image helpers matching the OpenCV operations used in the Python version.

/** Area (box-filter) resize, like cv2.INTER_AREA for downscaling. src: Float32Array, c channels. */
export function resizeArea(src, w, h, c, nw, nh) {
  const tmp = new Float32Array(nw * h * c);
  const sx = w / nw;
  for (let x = 0; x < nw; x++) {                       // horizontal pass
    const a = x * sx, b = a + sx;
    const i0 = Math.floor(a), i1 = Math.min(Math.ceil(b), w);
    for (let y = 0; y < h; y++) {
      for (let k = 0; k < c; k++) {
        let s = 0;
        for (let i = i0; i < i1; i++) {
          const wgt = Math.min(i + 1, b) - Math.max(i, a);
          s += wgt * src[(y * w + i) * c + k];
        }
        tmp[(y * nw + x) * c + k] = s / sx;
      }
    }
  }
  const out = new Float32Array(nw * nh * c);
  const sy = h / nh;
  for (let y = 0; y < nh; y++) {                       // vertical pass
    const a = y * sy, b = a + sy;
    const j0 = Math.floor(a), j1 = Math.min(Math.ceil(b), h);
    for (let x = 0; x < nw; x++) {
      for (let k = 0; k < c; k++) {
        let s = 0;
        for (let j = j0; j < j1; j++) {
          const wgt = Math.min(j + 1, b) - Math.max(j, a);
          s += wgt * tmp[(j * nw + x) * c + k];
        }
        out[(y * nw + x) * c + k] = s / sy;
      }
    }
  }
  return out;
}

/** Downscale an RGBA ImageData-like {data,width,height} so the longest side <= maxSide (INTER_AREA). */
export function limitSize(img, maxSide) {
  const { width: w, height: h } = img;
  const f = Math.min(1, maxSide / Math.max(w, h));
  if (f >= 1) return { img, factor: 1 };
  const nw = Math.round(w * f), nh = Math.round(h * f);
  const src = new Float32Array(w * h * 3);
  for (let i = 0; i < w * h; i++) for (let k = 0; k < 3; k++) src[i * 3 + k] = img.data[i * 4 + k];
  const r = resizeArea(src, w, h, 3, nw, nh);
  const data = new Uint8ClampedArray(nw * nh * 4);
  for (let i = 0; i < nw * nh; i++) {
    for (let k = 0; k < 3; k++) data[i * 4 + k] = Math.round(r[i * 3 + k]);
    data[i * 4 + 3] = 255;
  }
  return { img: { data, width: nw, height: nh }, factor: f };
}

/** Bilinear resize of RGB (from RGBA) like cv2.INTER_LINEAR (half-pixel centres). Returns Float32Array RGB. */
export function resizeBilinearRGB(img, nw, nh) {
  const { data, width: w, height: h } = img;
  const out = new Float32Array(nw * nh * 3);
  const sx = w / nw, sy = h / nh;
  for (let y = 0; y < nh; y++) {
    let fy = (y + 0.5) * sy - 0.5; let y0 = Math.floor(fy); let ty = fy - y0;
    if (y0 < 0) { y0 = 0; ty = 0; } if (y0 >= h - 1) { y0 = h - 1; ty = 0; }
    const y1 = Math.min(y0 + 1, h - 1);
    for (let x = 0; x < nw; x++) {
      let fx = (x + 0.5) * sx - 0.5; let x0 = Math.floor(fx); let tx = fx - x0;
      if (x0 < 0) { x0 = 0; tx = 0; } if (x0 >= w - 1) { x0 = w - 1; tx = 0; }
      const x1 = Math.min(x0 + 1, w - 1);
      for (let k = 0; k < 3; k++) {
        const a = data[(y0 * w + x0) * 4 + k], b = data[(y0 * w + x1) * 4 + k];
        const c = data[(y1 * w + x0) * 4 + k], d = data[(y1 * w + x1) * 4 + k];
        out[(y * nw + x) * 3 + k] = (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty;
      }
    }
  }
  return out;
}

/** Gray like cv2.COLOR_RGB2GRAY (rounded). */
export function toGray(img) {
  const { data, width: w, height: h } = img;
  const g = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) g[i] = Math.round(0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2]);
  return g;
}

/** JET-like colormap: v in [0,1] -> [r,g,b] 0-255 */
export function jet(v) {
  const c = (x) => Math.max(0, Math.min(1, x));
  return [c(1.5 - Math.abs(4 * v - 3)) * 255, c(1.5 - Math.abs(4 * v - 2)) * 255, c(1.5 - Math.abs(4 * v - 1)) * 255];
}

/** Create a canvas with the given RGBA image drawn on it. */
export function toCanvas(img) {
  const cv = document.createElement("canvas");
  cv.width = img.width; cv.height = img.height;
  cv.getContext("2d").putImageData(new ImageData(new Uint8ClampedArray(img.data), img.width, img.height), 0, 0);
  return cv;
}

/** Where to put a box label (w x h) so it stays inside the image and does not cover labels already placed.
 *  Tries: above the box, below it, inside its top-left corner, above / inside at the right edge.
 *  placed: array of earlier label rectangles [x, y, w, h] (the new one is added). Returns [x, y] (top-left). */
export function placeLabel([x1, y1, x2, y2], w, h, W, H, placed) {
  const fitX = (x) => Math.max(0, Math.min(W - w, x));
  const tries = [[x1, y1 - h], [x1, y2], [x1, y1], [x2 - w, y1 - h], [x2 - w, y1], [x2 - w, y2]]
    .map(([x, y]) => [fitX(x), y]).filter(([, y]) => y >= 0 && y + h <= H);
  const free = ([x, y]) => placed.every(([px, py, pw, ph]) => x >= px + pw || x + w <= px || y >= py + ph || y + h <= py);
  const spot = tries.find(free) || tries[0] || [fitX(x1), Math.max(0, Math.min(H - h, y1))];
  placed.push([spot[0], spot[1], w, h]);
  return spot;
}
