// Floating bubble for the web app (the Android app has its own native bubble; this one is not used there).
//  - Chrome / Edge on a computer: the bubble is a small window that stays on top of every other app
//    (Document Picture-in-Picture). "Select area" captures the screen: the browser asks once which screen to
//    share (Android also asks once per bubble session), then each check takes a fresh picture of it, the user
//    drags over the fabric and the area is analysed on this device.
//  - Other computer browsers: the bubble floats inside the page; "Select area" captures a shared window/screen.
//  - Phone browsers cannot capture the screen or draw over other apps: there "Select area" works on a photo.
import { verdictHtml, reportHtml } from "./kb.js";

const mobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent) || (navigator.maxTouchPoints > 1 && /Macintosh/.test(navigator.userAgent));
export const canFloat = "documentPictureInPicture" in window && window.top === window && !mobile;
export const canCapture = !mobile && !!(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia);

const SVG = (d, extra = "") => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"${extra}>${d}</svg>`;
const ICON = {
  area: SVG('<path d="M4 9V5.5A1.5 1.5 0 0 1 5.5 4H9M15 4h3.5A1.5 1.5 0 0 1 20 5.5V9M20 15v3.5a1.5 1.5 0 0 1-1.5 1.5H15M9 20H5.5A1.5 1.5 0 0 1 4 18.5V15"/>'),
  gallery: SVG('<rect x="3.5" y="5" width="17" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m4.5 17.5 5-5 3.5 3.5 2.5-2.5 4 4"/>'),
  camera: SVG('<path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2l1.4-2h6.2l1.4 2h2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z"/><circle cx="12" cy="13" r="3.5"/>'),
  back: SVG('<path d="M14.5 5.5 8 12l6.5 6.5"/>'),
};
let glassN = 0;
const glass = (id = "bpg" + ++glassN) => `<svg viewBox="0 0 54 54" aria-hidden="true"><defs><radialGradient id="${id}" cx="35%" cy="30%" r="75%"><stop offset="0" stop-color="#86cf8d"/><stop offset=".45" stop-color="#63b96c"/><stop offset="1" stop-color="#3f8f48"/></radialGradient></defs>
<circle cx="27" cy="27" r="27" fill="url(#${id})"/><circle cx="27" cy="27" r="17" fill="rgba(255,255,255,.10)" stroke="#fff" stroke-width="2.2"/>
<path d="M14 27h26M27 14v26" stroke="rgba(255,255,255,.55)" stroke-width="1"/><path d="M17 27v-5M21 27v-3M25 27v-3M29 27v-3M33 27v-3M37 27v-5" stroke="#fff" stroke-width="1.1"/>
<path d="M39.5 39.5l6 6" stroke="#f0bf45" stroke-width="4" stroke-linecap="round"/></svg>`;
const SEV_DOT = { minor: "#a86f12", major: "#cf5a24", critical: "#c23a3a" };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * app = { analyseCapture(canvas, rect) -> report, analyseFile(file) -> report, camera(), open(),
 *         selectInPhoto(), pickFile(), toast(msg), onChange(state) }
 */
export class Bubble {
  constructor(app) {
    this.app = app;
    this.state = "off";          // off | on | hidden (hidden: the screen share stays, the bubble is out of sight)
    this.mode = null;            // pip | page
    this.pip = null; this.btn = null; this.back = null;
    this.stream = null; this.video = null;
    this.last = null;            // the newest report (any source), shown at the top of the menu
    this.busy = false;
    this.closingOnPurpose = false;
  }

  // ------------------------------------------------------------------ start / hide / stop
  /** Must be called from a click (the browser only opens the floating window after a user action). */
  async start() {
    if (canFloat) {
      try { await this.openPip(); this.mode = "pip"; this.set("on"); return; }
      catch (e) { console.warn("floating window not available", e); }
    }
    this.mode = "page"; this.showPageBubble(); this.set("on");
  }

  hide() {
    if (this.mode === "pip") this.closePip(); else this.removePageBubble();
    this.set("hidden");
  }

  stop() {
    if (this.mode === "pip") this.closePip(); else this.removePageBubble();
    this.stopStream();
    this.mode = null; this.set("off");
  }

  set(state) {
    this.state = state;
    try { localStorage.setItem("fi-bubble", state === "on" && this.mode === "page" ? "page" : ""); } catch { /* private mode */ }
    this.app.onChange(state);
  }

  /** The in-page bubble comes back after a reload (a floating window cannot open without a click). */
  restore() {
    let saved = "";
    try { saved = localStorage.getItem("fi-bubble") || ""; } catch { /* ignore */ }
    if (saved === "page" && !canFloat) { this.mode = "page"; this.showPageBubble(); this.set("on"); }
  }

  /** Called by the app after every check, whatever started it. */
  setLast(report) {
    this.last = report;
    if (this.btn) { const dot = this.btn.querySelector("i"), c = report && SEV_DOT[report.verdict.severity]; dot.hidden = !c; dot.style.background = c || ""; }
    if (this.pip && !this.busy && this.pip.document.body.dataset.view === "menu") this.renderMenu();
  }

  // ------------------------------------------------------------------ the menu (same items as the Android bubble)
  menuHtml() {
    const r = this.last;
    const last = r ? `<button class="qa-last" data-a="last"><span class="qa-dot" style="background:${SEV_DOT[r.verdict.severity] || (r.verdict.state === "none" ? "#63b96c" : "#9aa59d")}"></span>` +
      `<span><small>Last check</small><b>${esc(r.verdict.title)}</b></span><span class="qa-chev">›</span></button>` : "";
    const areaSub = canCapture ? "" : `<small>in the open photo</small>`;
    return `<div class="qa-head">${glass()}<b>Quick actions</b></div>${last}
      <div class="qa-grid">
        <button class="qa-tile" data-a="area"><i style="--c:#2f7d3b">${ICON.area}</i><span>Select area${areaSub}</span></button>
        <button class="qa-tile" data-a="gallery"><i style="--c:#2a78d6">${ICON.gallery}</i><span>Photo from gallery</span></button>
        <button class="qa-tile" data-a="camera"><i style="--c:#e7b53a;--f:#2b2205">${ICON.camera}</i><span>Take photo</span></button>
        <button class="qa-tile" data-a="app"><i class="glass">${glass()}</i><span>Open Fabric Inspector</span></button>
      </div>
      <p class="qa-msg" hidden></p>
      <div class="qa-row"><button data-a="hide">Hide bubble</button><button data-a="off">Turn off</button></div>`;
  }

  wireMenu(root, win) {
    root.addEventListener("click", (e) => {
      const b = e.target.closest("[data-a]");
      if (b && !this.busy) this.act(b.dataset.a, win);
    });
  }

  message(text) {
    const doc = this.pip ? this.pip.document : document;
    const m = doc.querySelector(".qa-msg");
    if (m) { m.textContent = text; m.hidden = !text; }
    else if (text) this.app.toast(text);
  }

  async act(a, win) {
    const inPip = !!this.pip && win === this.pip;
    this.message("");
    if (a === "off") return this.stop();
    if (a === "hide") return this.hide();
    if (a === "area") return this.selectArea(win);
    if (a === "gallery") return inPip ? this.galleryInPip() : (this.closePanel(), this.app.pickFile());
    if (a === "camera" || a === "app" || a === "last") {
      if (inPip && a === "last" && this.last) return this.renderResult(this.last);
      this.closePanel();
      if (inPip) this.focusApp();
      return a === "camera" ? this.app.camera() : this.app.open(a === "last");
    }
  }

  /** From the floating window back to the app tab. */
  focusApp() {
    try { window.focus(); } catch { /* not allowed */ }
    setTimeout(() => { if (document.hidden && this.pip) this.message("The result is in the Fabric Inspector tab. Use “Back to tab” at the top of this window."); }, 500);
  }

  // ------------------------------------------------------------------ floating window (Chrome / Edge on a computer)
  async openPip() {
    const w = await window.documentPictureInPicture.requestWindow({ width: 340, height: 460 });
    copyStyles(document, w.document);
    w.document.title = "Fabric Inspector";
    w.document.body.className = "pipbody";
    this.pip = w;
    w.addEventListener("pagehide", () => {
      if (this.pip !== w) return;
      this.pip = null;
      if (!this.closingOnPurpose && this.state === "on") { this.stopStream(); this.mode = null; this.set("off"); }   // closed with its X
    });
    this.renderMenu();
  }

  closePip() {
    if (!this.pip) return;
    this.closingOnPurpose = true;
    try { this.pip.close(); } catch { /* already closed */ }
    this.pip = null; this.closingOnPurpose = false;
  }

  renderMenu() {
    const b = this.pip.document.body;
    b.dataset.view = "menu";
    b.innerHTML = `<div class="qa pip">${this.menuHtml()}</div>`;
    this.wireMenu(b.firstElementChild, this.pip);
  }

  renderWait(text) {
    const b = this.pip.document.body;
    b.dataset.view = "wait";
    b.innerHTML = `<div class="qa pip qa-wait"><span class="qa-spin"></span><b>${esc(text)}</b></div>`;
  }

  renderResult(rep) {
    const b = this.pip.document.body;
    b.dataset.view = "result";
    b.innerHTML = `<div class="pipres"><button class="pipback" data-a="menu">${ICON.back}Quick actions</button>
      ${verdictHtml(rep)}<div class="report">${reportHtml(rep)}</div>
      <div class="pipact"><button class="btn primary sm" data-a="area">Select another area</button><button class="btn sm" data-a="app">Open in app</button></div></div>`;
    b.firstElementChild.addEventListener("click", (e) => {
      const x = e.target.closest("[data-a]");
      if (!x || this.busy) return;
      if (x.dataset.a === "menu") this.renderMenu(); else this.act(x.dataset.a, this.pip);
    });
  }

  galleryInPip() {
    const doc = this.pip.document, input = doc.createElement("input");
    input.type = "file"; input.accept = "image/*";
    input.onchange = async () => {
      const f = input.files[0];
      if (f) await this.runCheck(() => this.app.analyseFile(f));
    };
    input.click();
  }

  async runCheck(job) {
    this.busy = true;
    if (this.pip) this.renderWait("Analysing…");
    try {
      const rep = await job();
      if (this.pip) { if (rep) this.renderResult(rep); else this.renderMenu(); }
    } catch (e) {
      console.error(e);
      if (this.pip) { this.renderMenu(); this.message("The analysis failed: " + e.message); } else this.app.toast("The analysis failed: " + e.message);
    } finally { this.busy = false; }
  }

  // ------------------------------------------------------------------ bubble inside the page (other browsers)
  showPageBubble() {
    if (this.btn) { this.btn.hidden = false; return; }
    const b = document.createElement("button");
    b.className = "fbub"; b.setAttribute("aria-label", "Fabric Inspector quick actions");
    b.innerHTML = glass() + "<i hidden></i>";
    let pos = null;
    try { pos = JSON.parse(localStorage.getItem("fi-bubble-pos") || "null"); } catch { /* ignore */ }
    const place = (x, y) => { b.style.left = x + "px"; b.style.top = y + "px"; };
    const snap = () => {
      const s = b.offsetWidth, r = b.getBoundingClientRect();
      const x = r.left + s / 2 < innerWidth / 2 ? 8 : innerWidth - s - 8;
      const y = Math.min(Math.max(r.top, 70), innerHeight - s - 90);
      place(x, y);
      try { localStorage.setItem("fi-bubble-pos", JSON.stringify({ right: x > 8, y: y / innerHeight })); } catch { /* ignore */ }
    };
    document.body.appendChild(b);
    const s = b.offsetWidth || 58;
    place(pos && !pos.right ? 8 : innerWidth - s - 8, pos ? pos.y * innerHeight : innerHeight * 0.55);
    let start = null, moved = false;
    b.addEventListener("pointerdown", (e) => { start = [e.clientX, e.clientY, b.offsetLeft, b.offsetTop]; moved = false; b.setPointerCapture(e.pointerId); });
    b.addEventListener("pointermove", (e) => {
      if (!start) return;
      const dx = e.clientX - start[0], dy = e.clientY - start[1];
      if (Math.abs(dx) + Math.abs(dy) > 8) { moved = true; b.classList.add("drag"); }
      if (moved) place(start[2] + dx, start[3] + dy);
    });
    const up = () => { if (!start) return; start = null; b.classList.remove("drag"); if (moved) snap(); else this.openPanel(); };
    b.addEventListener("pointerup", up); b.addEventListener("pointercancel", () => { start = null; b.classList.remove("drag"); snap(); });
    b.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this.openPanel(); } });
    window.addEventListener("resize", () => { if (this.btn && !this.btn.hidden) snap(); });
    this.btn = b;
    if (this.last) this.setLast(this.last);
  }

  removePageBubble() { this.closePanel(); if (this.btn) this.btn.hidden = true; }

  openPanel() {
    if (this.back) return;
    const back = document.createElement("div");
    back.className = "qa-back";
    const r = this.btn.getBoundingClientRect();
    back.innerHTML = `<div class="qa" style="--ox:${r.left + r.width / 2}px;--oy:${r.top + r.height / 2}px">${this.menuHtml()}</div>`;
    back.addEventListener("click", (e) => { if (e.target === back) this.closePanel(); });
    this.wireMenu(back.firstElementChild, window);
    document.body.appendChild(back);
    this.btn.hidden = true;
    this.back = back;
    this.onKey = (e) => { if (e.key === "Escape") this.closePanel(); };
    document.addEventListener("keydown", this.onKey);
    back.querySelector(".qa-tile").focus({ preventScroll: true });
  }

  closePanel() {
    if (!this.back) return;
    this.back.remove(); this.back = null;
    document.removeEventListener("keydown", this.onKey);
    if (this.btn && this.state === "on") this.btn.hidden = false;
  }

  // ------------------------------------------------------------------ select an area of the screen
  async selectArea(win) {
    if (!canCapture) { this.closePanel(); return this.app.selectInPhoto(); }
    const inPip = !!this.pip && win === this.pip;
    let stream;
    try { stream = await this.ensureStream(win); }
    catch (e) {
      this.message(e && e.name === "NotAllowedError" ? "Screen sharing was not allowed, so the bubble cannot see the fabric. Tap Select area and choose a screen." : "The screen could not be shared: " + (e && e.message));
      return;
    }
    if (!inPip) { this.closePanel(); if (this.btn) this.btn.hidden = true; await wait(150); }   // nothing of ours in the picture
    let shot;
    try { shot = await this.grab(stream); }
    catch (e) { if (this.btn && this.state === "on") this.btn.hidden = false; return this.message("The screen could not be captured. Try again."); }
    let rect;
    if (inPip) {
      rect = await this.pickInPopup(shot);
      if (rect === "blocked") {                           // the share dialog took too long: one more click opens it
        const b = this.pip.document.body;
        b.dataset.view = "ready";
        b.innerHTML = `<div class="qa pip qa-wait"><b>Screen sharing is on</b><button class="btn primary" data-go>Select the area</button><button class="btn sm" data-x>Cancel</button></div>`;
        rect = await new Promise((res) => {
          b.querySelector("[data-go]").onclick = async () => { try { shot = await this.grab(stream); res(await this.pickInPopup(shot)); } catch { res(null); } };
          b.querySelector("[data-x]").onclick = () => res(null);
        });
        if (rect === "blocked") { this.renderMenu(); return this.message("The browser blocked the selection window. Allow pop-ups for this site and try again."); }
      }
    } else {
      rect = await pickArea(document, shot);
    }
    if (this.btn && this.state === "on" && !this.back) this.btn.hidden = false;
    if (!rect) { if (inPip && this.pip.document.body.dataset.view !== "menu") this.renderMenu(); return; }
    await this.runCheck(() => this.app.analyseCapture(shot, rect));
  }

  async ensureStream(win) {
    if (this.stream && this.stream.active) return this.stream;
    const opts = { video: { displaySurface: "monitor", frameRate: { ideal: 5, max: 10 } }, audio: false, selfBrowserSurface: "include", surfaceSwitching: "include", monitorTypeSurfaces: "include" };
    let stream;
    try { stream = await win.navigator.mediaDevices.getDisplayMedia(opts); }
    catch (e) { if (win === window || e.name === "NotAllowedError") throw e; stream = await navigator.mediaDevices.getDisplayMedia(opts); }
    this.stream = stream;
    stream.getVideoTracks()[0].addEventListener("ended", () => { if (this.stream === stream) this.stopStream(); });   // "Stop sharing"
    const v = document.createElement("video");
    v.muted = true; v.playsInline = true; v.srcObject = stream;
    await v.play().catch(() => {});
    this.video = v;
    return stream;
  }

  stopStream() {
    if (this.stream) for (const t of this.stream.getTracks()) t.stop();
    if (this.video) this.video.srcObject = null;
    this.stream = null; this.video = null;
  }

  /** A fresh picture of the shared screen, at full resolution. */
  async grab(stream) {
    const track = stream.getVideoTracks()[0];
    let src = null;
    if ("ImageCapture" in window) {
      try { src = await Promise.race([new window.ImageCapture(track).grabFrame(), wait(900).then(() => null)]); } catch { src = null; }
    }
    if (!src) {
      const v = this.video;
      for (let i = 0; i < 30 && !(v.videoWidth > 0); i++) await wait(50);
      if (!(v.videoWidth > 0)) throw new Error("no picture");
      src = v;
    }
    const w = src.videoWidth || src.width, h = src.videoHeight || src.height;
    const cv = document.createElement("canvas"); cv.width = w; cv.height = h;
    cv.getContext("2d").drawImage(src, 0, 0, w, h);
    if (src.close) src.close();
    return cv;
  }

  /** The frozen screen in a window as large as the screen. "blocked" = the browser did not open it. */
  async pickInPopup(shot) {
    const sw = screen.availWidth, sh = screen.availHeight;
    const pop = this.pip.open("", "fi-select", `popup,left=${screen.availLeft || 0},top=${screen.availTop || 0},width=${sw},height=${sh}`);
    if (!pop) return "blocked";
    pop.document.title = "Select the fabric - Fabric Inspector";
    copyStyles(document, pop.document);
    pop.document.body.className = "pickbody";
    try { pop.focus(); } catch { /* ignore */ }
    const closed = new Promise((res) => { const t = setInterval(() => { if (pop.closed) { clearInterval(t); res(null); } }, 400); });
    const rect = await Promise.race([pickArea(pop.document, shot), closed]);
    try { pop.close(); } catch { /* ignore */ }
    return rect;
  }
}

/** Shows `shot` filling the page; the user drags a rectangle. Resolves [x, y, w, h] in shot pixels, or null. */
export function pickArea(doc, shot) {
  return new Promise((resolve) => {
    const win = doc.defaultView;
    const root = doc.createElement("div");
    root.className = "pick";
    root.innerHTML = `<div class="pick-stage"><div class="pick-frame"><canvas></canvas><div class="pick-sel" hidden><i></i><i></i><i></i><i></i></div></div></div>
      <p class="pick-hint">Drag over the fabric you want to check</p>
      <div class="pick-bar"><button class="btn" data-x>Cancel</button><button class="btn primary" data-go disabled>Analyse area</button></div>`;
    doc.body.appendChild(root);
    const frame = root.querySelector(".pick-frame"), cv = root.querySelector("canvas"), sel = root.querySelector(".pick-sel");
    const hint = root.querySelector(".pick-hint"), go = root.querySelector("[data-go]");
    cv.width = shot.width; cv.height = shot.height; cv.getContext("2d").drawImage(shot, 0, 0);
    const fit = () => {
      const st = root.querySelector(".pick-stage").getBoundingClientRect();
      const k = Math.min(st.width / shot.width, st.height / shot.height);
      frame.style.width = Math.round(shot.width * k) + "px"; frame.style.height = Math.round(shot.height * k) + "px";
    };
    fit(); win.addEventListener("resize", fit);
    let r = null, start = null;
    const pos = (e) => { const b = frame.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - b.left) / b.width)), Math.min(1, Math.max(0, (e.clientY - b.top) / b.height))]; };
    frame.addEventListener("pointerdown", (e) => { e.preventDefault(); frame.setPointerCapture(e.pointerId); start = pos(e); });
    frame.addEventListener("pointermove", (e) => {
      if (!start) return;
      const [x, y] = pos(e);
      r = [Math.min(x, start[0]), Math.min(y, start[1]), Math.abs(x - start[0]), Math.abs(y - start[1])];
      sel.style.cssText = `left:${r[0] * 100}%;top:${r[1] * 100}%;width:${r[2] * 100}%;height:${r[3] * 100}%`;
      sel.hidden = false; root.classList.add("has");
    });
    const up = () => {
      if (!start) return; start = null;
      const ok = r && r[2] * shot.width >= 64 && r[3] * shot.height >= 64;
      go.disabled = !ok;
      hint.textContent = ok ? "Area selected. Drag again to change it." : "That area is too small. Drag a larger one.";
      if (!ok) { sel.hidden = true; root.classList.remove("has"); r = null; }
      else go.focus({ preventScroll: true });
    };
    frame.addEventListener("pointerup", up); frame.addEventListener("pointercancel", up);
    const done = (v) => { win.removeEventListener("resize", fit); doc.removeEventListener("keydown", key); root.remove(); resolve(v); };
    const key = (e) => { if (e.key === "Escape") done(null); if (e.key === "Enter" && !go.disabled) go.click(); };
    doc.addEventListener("keydown", key);
    root.querySelector("[data-x]").onclick = () => done(null);
    go.onclick = () => {
      if (!r) return;
      const x = Math.round(r[0] * shot.width), y = Math.round(r[1] * shot.height);
      done([x, y, Math.min(shot.width - x, Math.round(r[2] * shot.width)), Math.min(shot.height - y, Math.round(r[3] * shot.height))]);
    };
  });
}

/** A new window (floating window, selection window) gets the page's styles. */
function copyStyles(from, to) {
  for (const sheet of from.styleSheets) {
    try {
      const style = to.createElement("style");
      style.textContent = [...sheet.cssRules].map((r) => r.cssText).join("\n");
      to.head.appendChild(style);
    } catch {                                                // other-origin sheet (the web fonts): link it
      if (!sheet.href) continue;
      const link = to.createElement("link"); link.rel = "stylesheet"; link.href = sheet.href;
      to.head.appendChild(link);
    }
  }
}

