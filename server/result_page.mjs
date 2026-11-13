// Self-contained result page for the iPhone Shortcut (and anything else that cannot run the web app):
// one HTML document with the photo, the boxes drawn on it, the verdict and the finding cards.
// No JavaScript and no external files, so it displays inside Quick Look. Nothing is stored on the server.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";
import { verdictHtml, reportHtml } from "../web_static/js/kb.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CSS = readFileSync(path.resolve(HERE, "..", "web_static", "css", "app.css"), "utf8");
const CLASS_COLOR = { hole_tear: "#2a78d6", stain: "#eb6834", slub_neps: "#1baf7a", broken_pick_end: "#eda100" };
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const PAGE_MAX = 1000;       // the photo inside the page is reduced to keep the answer small

const shell = (body) => `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><title>Fabric Check</title>
<style>${CSS}
body { padding: 12px 14px 28px; background: var(--surface); }
.sheet { max-width: 640px; margin: 0 auto; display: grid; gap: 10px; }
.brandline { font: 700 13px var(--f-display); letter-spacing: .04em; color: var(--ink-2); }
.shot { position: relative; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: var(--paper); line-height: 0; }
.shot img, .shot svg { width: 100%; height: auto; display: block; }
.shot svg { position: absolute; inset: 0; height: 100%; }
</style></head><body><div class="sheet"><div class="brandline">FABRIC INSPECTOR</div>${body}</div></body></html>`;

/** rep: result of analyse(buf, s, { keepImage: true }) */
export async function resultPage(rep, totalMs) {
  const [W, H] = rep.imageSize, img = rep.image;
  const f = Math.min(1, PAGE_MAX / Math.max(W, H));
  const jpg = await sharp(Buffer.from(img.data.buffer, img.data.byteOffset, img.data.length), { raw: { width: W, height: H, channels: 4 } })
    .removeAlpha().resize(Math.round(W * f), Math.round(H * f)).jpeg({ quality: 78 }).toBuffer();
  const lw = Math.max(2, Math.round(Math.max(W, H) / 300)), fs = Math.max(12, Math.round(Math.max(W, H) / 45));
  const boxes = rep.items.filter((r) => r.box).map((r) => {
    const [x1, y1, x2, y2] = r.box, col = CLASS_COLOR[r.defect] || "#fff";
    const label = `${r.index} ${r.defect} ${(r.confidence * 100).toFixed(0)}%`, tw = label.length * fs * 0.56 + 8;
    const ty = y1 - fs - 6 > 0 ? y1 : Math.min(H, y2 + fs + 6);
    return `<rect x="${x1.toFixed(1)}" y="${y1.toFixed(1)}" width="${(x2 - x1).toFixed(1)}" height="${(y2 - y1).toFixed(1)}" fill="none" stroke="${col}" stroke-width="${lw}"/>` +
      `<rect x="${x1.toFixed(1)}" y="${(ty - fs - 6).toFixed(1)}" width="${tw.toFixed(1)}" height="${fs + 6}" fill="${col}"/>` +
      `<text x="${(x1 + 4).toFixed(1)}" y="${(ty - 5).toFixed(1)}" font-size="${fs}" font-family="system-ui,sans-serif" font-weight="600" fill="#fff">${esc(label)}</text>`;
  }).join("");
  const shot = `<div class="shot"><img alt="Analysed photo" src="data:image/jpeg;base64,${jpg.toString("base64")}">` +
    `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">${boxes}</svg></div>`;
  const foot = `<p class="mut">Analysed in ${(totalMs / 1000).toFixed(1)} s on the server. The photo was not stored.</p>`;
  return shell(verdictHtml(rep) + shot + `<div class="report">${reportHtml(rep)}</div>` + foot);
}

/** Same look for errors, so the phone never shows raw technical text. */
export function errorPage(error, fix) {
  return shell(`<div class="verdict cannot"><b>${esc(error)}</b><small>${esc(fix)}</small></div>`);
}
