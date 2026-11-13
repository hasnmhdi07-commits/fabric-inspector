// Verdict rules (spec v2, section 4) - JavaScript port of src/app/verdict.py. Must give the same answer.
//   "defects": something found      -> highest severity + "N defects · P points"
//   "none":    nothing found        -> "No defects detected" + reminder to check visually (never "acceptable")
//   "cannot":  photo not analysable -> reason + what to do
export const DARK_BELOW = 25, BRIGHT_ABOVE = 245, BLUR_BELOW = 1.2, MIN_SIDE = 64;
export const SEV_LABEL = { acceptable: "Within limit", minor: "Minor", major: "Major", critical: "Critical" };
const MEASURE_FAIL = { shade_variation: "shade out of tolerance", skewing: "skew over limit", bowing: "bow over limit" };
const VISUAL_CHECK = "The AI can miss defects, so check the fabric visually.";
const ORDER = ["acceptable", "minor", "major", "critical"];

/** img: {data: RGBA, width, height} -> [mean grey, variance of the Laplacian] */
export function photoMetrics(img) {
  const { data, width: w, height: h } = img, n = w * h;
  const g = new Float64Array(n);
  let sum = 0;
  for (let i = 0; i < n; i++) { g[i] = Math.floor(0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2] + 0.5); sum += g[i]; }
  let s = 0, s2 = 0, m = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x, l = g[i - w] + g[i + w] + g[i - 1] + g[i + 1] - 4 * g[i];
      s += l; s2 += l * l; m++;
    }
  }
  const mean = s / m;
  return [sum / n, s2 / m - mean * mean];
}

/** null if the photo can be analysed, else {code, title, fix}. */
export function photoProblem(img) {
  if (Math.min(img.width, img.height) < MIN_SIDE)
    return { code: "too_small", title: "Image too small to analyse", fix: `Select a larger area or move closer: at least ${MIN_SIDE} x ${MIN_SIDE} pixels.` };
  const [mean, sharp] = photoMetrics(img);
  if (mean < DARK_BELOW) return { code: "too_dark", title: "Photo too dark to analyse", fix: "Retake it in even daylight, straight from above." };
  if (mean > BRIGHT_ABOVE) return { code: "too_bright", title: "Photo too bright to analyse", fix: "Retake it without glare or flash, in even daylight." };
  if (sharp < BLUR_BELOW) return { code: "blurred", title: "Photo too blurred to analyse", fix: "Hold the camera still, tap to focus on the fabric and retake the photo." };
  return null;
}

export function makeVerdict(items, problem = null, defectsChecked = true) {
  if (problem) return { state: "cannot", severity: null, title: problem.title, detail: problem.fix, n_defects: 0, points: null };
  const found = items.filter((r) => r.severity !== "acceptable");
  if (!found.length) {
    return defectsChecked
      ? { state: "none", severity: null, title: "No defects detected", detail: VISUAL_CHECK, n_defects: 0, points: null }
      : { state: "none", severity: null, title: "Measurements within limits", detail: "Defect detection was switched off for this check.", n_defects: 0, points: null };
  }
  const severity = found.reduce((w, r) => (ORDER.indexOf(r.severity) > ORDER.indexOf(w) ? r.severity : w), "acceptable");
  const boxes = found.filter((r) => r.box), n = boxes.length;
  const points = n && boxes.every((r) => r.points != null) ? boxes.reduce((a, r) => a + r.points, 0) : null;
  const parts = [];
  if (n) {
    parts.push(`${n} defect${n !== 1 ? "s" : ""}`);
    if (points != null) parts.push(`${points} point${points !== 1 ? "s" : ""}`);
  }
  for (const r of found) if (MEASURE_FAIL[r.defect]) parts.push(MEASURE_FAIL[r.defect]);
  let title = parts.join(" · ");
  title = title[0].toUpperCase() + title.slice(1);
  let detail;
  if (n && points == null) detail = "Severity from relative size. Set the image scale (px/mm) for ASTM D5430 points.";
  else if (n) detail = "ASTM D5430 4-point system. Highest severity first.";
  else detail = defectsChecked ? "No local defects found. " + VISUAL_CHECK : "Highest severity first.";
  return { state: "defects", severity, title, detail, n_defects: n, points };
}
