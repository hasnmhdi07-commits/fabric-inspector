// Rule-based knowledge base (JavaScript port of src/knowledge/kb.py + report_html.py).
// Causes/remedies come ONLY from kb.json (generated from knowledge_base.yaml).
import { SEV_LABEL } from "./verdict.js";
export const SEVERITY_ORDER = ["acceptable", "minor", "major", "critical"];
export const SEV_COLOR = { acceptable: "#0ca30c", minor: "#b07800", major: "#d0612f", critical: "#d03b3b" };
export const SEV_ICON = { acceptable: "✓", minor: "!", major: "!!", critical: "✕" };
const MM_PER_INCH = 25.4;
const sevIdx = (s) => SEVERITY_ORDER.indexOf(s);

let KB = null;
export async function loadKB(url = "kb.json") {
  KB = await (await fetch(url)).json();
  return KB;
}

/** ASTM D5430 4-point system penalty points for one defect. */
export function fourPoint(lengthMm, isHole = false) {
  const inch = Math.round((lengthMm / MM_PER_INCH) * 1e6) / 1e6;
  if (isHole) return inch <= 1 ? 2 : 4;
  if (inch <= 3) return 1;
  if (inch <= 6) return 2;
  if (inch <= 9) return 3;
  return 4;
}

const pointsToSeverity = (p) => ({ 1: "minor", 2: "minor", 3: "major", 4: "critical" })[p];

/** Same rules as kb.assess() in Python. */
export function assess(defect, o = {}) {
  const entry = KB.defects[defect];
  const rule = entry.severity.rule;
  let severity = entry.severity.default, points = null, basis = "";
  const shadeTol = o.shadeTolerance ?? 1.0, skewLimit = o.skewLimit ?? 3.0, bowLimit = o.bowLimit ?? 2.0;

  if ((rule === "hole" || rule === "length") && o.boxWH) {
    const longest = Math.max(o.boxWH[0], o.boxWH[1]);
    if (o.pxPerMm) {
      const lengthMm = longest / o.pxPerMm;
      points = fourPoint(lengthMm, rule === "hole");
      severity = pointsToSeverity(points);
      basis = `4-point system (ASTM D5430): defect length ${lengthMm.toFixed(0)} mm -> ${points} point(s)`;
    } else if (o.imageWH) {
      const frac = (o.boxWH[0] * o.boxWH[1]) / (o.imageWH[0] * o.imageWH[1]);
      if (rule === "hole") severity = frac > 0.02 ? "critical" : "major";
      else severity = frac < 0.01 ? "minor" : frac < 0.10 ? "major" : "critical";
      basis = `relative size ${(frac * 100).toFixed(1)}% of image (no scale given - add a ruler / set px per mm ` +
              `for a real 4-point score)`;
    }
    if (rule === "hole" && sevIdx(severity) < sevIdx("major")) severity = "major";
    if (defect === "broken_pick_end") {
      const [bw, bh] = o.boxWH;
      if (bw >= 3 * bh) basis += "; horizontal line -> likely broken/missing PICK (weft): check weft insertion and weft stop motion";
      else if (bh >= 3 * bw) basis += "; vertical line -> likely broken END (warp): check sizing, warp tension and warp stop motion";
    }
  } else if (rule === "delta_e" && o.deltaE != null) {
    const t = shadeTol, d = o.deltaE;
    severity = d <= t ? "acceptable" : d <= 1.5 * t ? "minor" : d <= 3 * t ? "major" : "critical";
    basis = `dE CMC(2:1) = ${d.toFixed(2)} vs tolerance ${t}`;
  } else if (rule === "skew" && o.skewPct != null) {
    const s = Math.abs(o.skewPct), lim = skewLimit;
    severity = s <= lim ? "acceptable" : s <= 2 * lim ? "major" : "critical";
    basis = `skew ${s.toFixed(2)}% vs limit ${lim}%`;
  } else if (rule === "bow" && o.bowPct != null) {
    const b = Math.abs(o.bowPct), lim = bowLimit;
    severity = b <= lim ? "acceptable" : b <= 2 * lim ? "major" : "critical";
    basis = `bow ${b.toFixed(2)}% vs limit ${lim}%`;
  }
  return {
    defect, name: entry.name, description: entry.description, severity, points,
    severity_basis: basis || "default severity for this defect type",
    confidence: o.confidence ?? null,
    causes: entry.causes, remedy: entry.remedy, prevention: entry.prevention,
  };
}

export function worstSeverity(items) {
  return items.reduce((w, r) => (sevIdx(r.severity) > sevIdx(w) ? r.severity : w), "acceptable");
}

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/** Same layout as report_html.py */
export function reportHtml(rep, maxItems = 3) {
  const v = rep.verdict;
  const vcol = v.severity ? SEV_COLOR[v.severity] : v.state === "cannot" ? SEV_COLOR.critical : "inherit";
  const chip = v.severity ? `<span class="chip" style="background:${vcol}">${SEV_LABEL[v.severity].toUpperCase()}</span> ` : "";
  const out = [`<div class="verdict ${v.state}">${chip}<b${v.severity ? "" : ` style="color:${vcol}"`}>${esc(v.title)}</b><div class="sec">${esc(v.detail)}</div></div>`];
  for (const r of rep.items) {
    const col = SEV_COLOR[r.severity];
    const conf = r.confidence != null ? ` &nbsp;·&nbsp; confidence ${(r.confidence * 100).toFixed(0)}%` : "";
    const pts = r.points != null ? ` &nbsp;·&nbsp; ${r.points} pt` : "";
    let s = `<div class="finding" style="border-left-color:${col}">` +
      `<b>#${r.index} ${esc(r.name)}</b> &nbsp;<b style="color:${col}">${SEV_LABEL[r.severity].toUpperCase()}</b>${pts}${conf}` +
      `<div class="sec">${esc(r.severity_basis)}</div>`;
    if (r.measure) s += `<div class="sec">${esc(r.measure)}</div>`;
    if (r.severity !== "acceptable") {
      s += `<b>Likely causes</b><ul>${r.causes.slice(0, maxItems).map((c) => `<li><i>${esc(c.stage)}</i>: ${esc(c.cause)}</li>`).join("")}</ul>`;
      s += `<b>Remedy</b><ul>${r.remedy.slice(0, maxItems).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
      s += `<b>Prevention</b><ul>${r.prevention.slice(0, maxItems).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
    }
    out.push(s + "</div>");
  }
  for (const n of rep.notes) out.push(`<p class="sec">ℹ ${esc(n)}</p>`);
  if (rep.items.length) out.push(`<p class="mut">Causes and remedies come from the rule-based knowledge base (most common causes for this ` +
           `defect type) - confirm on the production line. Full lists are in the downloadable report.</p>`);
  return out.join("");
}

/** Same as report_to_text() in engine.py */
export function reportText(rep) {
  const v = rep.verdict;
  const head = v.severity ? `${SEV_LABEL[v.severity].toUpperCase()} - ${v.title}` : v.title;
  const L = [`Fabric inspection report - result: ${head}`, `   ${v.detail}`, `Image ${rep.imageSize[0]}x${rep.imageSize[1]} px`, ""];
  for (const r of rep.items) {
    L.push(`#${r.index} ${r.name} - ${SEV_LABEL[r.severity].toUpperCase()}` +(r.confidence != null ? ` (confidence ${(r.confidence * 100).toFixed(0)}%)` : ""));
    L.push(`   basis: ${r.severity_basis}`);
    if (r.measure) L.push(`   measurement: ${r.measure}`);
    L.push("   likely causes:", ...r.causes.map((c) => `     - [${c.stage}] ${c.cause}`));
    L.push("   remedy:", ...r.remedy.map((x) => `     - ${x}`));
    L.push("   prevention:", ...r.prevention.map((x) => `     - ${x}`), "");
  }
  L.push(...rep.notes.map((n) => `note: ${n}`));
  L.push("Timings (ms): " + Object.entries(rep.timings).map(([k, v]) => `${k} ${v.toFixed(0)}`).join(", "));
  return L.join("\n");
}
