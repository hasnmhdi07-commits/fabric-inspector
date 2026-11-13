// Rule-based knowledge base (JavaScript port of src/knowledge/kb.py + report_html.py).
// Causes/remedies come ONLY from kb.json (generated from knowledge_base.yaml).
import { SEV_LABEL } from "./verdict.js";
export const SEVERITY_ORDER = ["acceptable", "minor", "major", "critical"];
export const SEV_COLOR = { acceptable: "#0f7a5c", minor: "#a86f12", major: "#cf5a24", critical: "#c23a3a" };
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

/** Verdict card: the first thing the user reads (same three states on every platform). */
export function verdictHtml(rep) {
  const v = rep.verdict;
  const chip = v.severity ? `<span class="chip ${v.severity}">${SEV_LABEL[v.severity]}</span>` : "";
  return `<div class="verdict ${v.state}">${chip}<b>${esc(v.title)}</b><small>${esc(v.detail)}</small></div>`;
}

/** Measurement tiles + one expandable card per finding (same components as the Windows panel). */
export function reportHtml(rep, maxItems = 3) {
  const out = [];
  const tiles = [["shade_variation", "Shade ΔE CMC 2:1", (x) => x.toFixed(2)], ["skewing", "Skew", (x) => x.toFixed(1) + " %"], ["bowing", "Bow", (x) => x.toFixed(1) + " %"]]
    .map(([key, label, fmt]) => { const r = rep.items.find((i) => i.defect === key); return r && r.value != null ? `<div><span>${label}</span><b${r.severity !== "acceptable" ? ' class="over"' : ""}>${fmt(r.value)}</b></div>` : ""; }).join("");
  if (tiles) out.push(`<div class="measure">${tiles}</div>`);
  const list = (title, rows) => `<h4>${title}</h4><ul>${rows.slice(0, maxItems).map((x) => `<li>${x}</li>`).join("")}</ul>`;
  rep.items.forEach((r, i) => {
    let sub = r.severity_basis;
    if (r.box) {
      const longest = Math.max(r.box[2] - r.box[0], r.box[3] - r.box[1]);
      sub = `${rep.pxPerMm ? (longest / rep.pxPerMm).toFixed(0) + " mm" : longest.toFixed(0) + " px"} · conf ${r.confidence.toFixed(2)}`;
    }
    let body = (r.box ? `<p class="sec">${esc(r.severity_basis)}</p>` : "") + (r.measure ? `<p class="sec">${esc(r.measure)}</p>` : "");
    if (r.severity !== "acceptable") {
      body += list("Likely causes", r.causes.map((c) => `<i>${esc(c.stage)}</i>: ${esc(c.cause)}`)) +
              list("Remedy", r.remedy.map(esc)) + list("Prevention", r.prevention.map(esc));
    }
    out.push(`<details class="finding" data-i="${r.index}" style="--i:${i}"${i === 0 && r.severity !== "acceptable" ? " open" : ""}><summary>` +
      `<span class="stripe" style="background:${SEV_COLOR[r.severity]}"></span>` +
      `<span class="title"><b>#${r.index} ${esc(r.name)}</b><span>${esc(sub)}</span></span>` +
      `<span class="pts"><span class="chip ${r.severity}">${SEV_LABEL[r.severity]}</span>${r.points != null ? r.points + " pt" : ""}</span>` +
      `</summary><div class="body">${body}</div></details>`);
  });
  for (const n of rep.notes) if (!(rep.verdict.state === "none" && n.startsWith("No local defects"))) out.push(`<p class="sec">${esc(n)}</p>`);
  if (rep.items.length) out.push(`<p class="mut">Causes and remedies come from the rule-based knowledge base (most common causes for this ` +
           `defect type). Confirm on the production line. Full lists are in the downloadable report.</p>`);
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
