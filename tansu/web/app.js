"use strict";
const T = "1";   // the HttpOnly session cookie is the credential; the X-Tansu header marks the page's own requests
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("--")) el.style.setProperty(k, v);
    else if (k === "value") el.value = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
}
const svg = (d, cls = "i") => h("span", { html: `<svg class="${cls}" viewBox="0 0 24 24">${d}</svg>`, style: { display: "contents" } });
const I = {
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  check: '<path class="draw" d="M5 12.5l4.5 4.5L19 7.5"/>',
  tick: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7z" fill="currentColor" stroke="none"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
  chev: '<path d="M9 6l6 6-6 6"/>',
  down: '<path d="M6 9l6 6 6-6"/>',
  box: '<path d="M4 8h16v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zM3 4h18v4H3zM10 12h4"/>',
  chest: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 9h16M4 15h16M10 6h4M10 12h4M10 18h4"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  open: '<path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
  out: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  warn: '<path d="M12 8v5M12 16.5v.5M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
  merge: '<path d="M7 4v5a5 5 0 0 0 5 5h0a5 5 0 0 1 5 5v1M17 4v5a5 5 0 0 1-3 4.6"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
  photo: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M21 16l-5-5-8 8"/>',
  video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3z"/>',
  audio: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
  doc: '<path d="M6 3h8l4 4v14H6z"/><path d="M9 12h6M9 16h6M14 3v4h4"/>',
  code: '<path d="M8 8l-4 4 4 4M16 8l4 4-4 4M13 6l-2 12"/>',
};
const CAT = {
  photo: ["Photos", "photo"], video: ["Videos", "video"], audio: ["Audio", "audio"], document: ["Documents", "doc"],
  spreadsheet: ["Spreadsheets", "doc"], presentation: ["Presentations", "doc"], ebook: ["E-books", "doc"],
  code: ["Code", "code"], design: ["Design & 3D", "photo"], archive: ["Archives", "box"], software: ["Software", "box"],
  data: ["Data & backups", "box"], font: ["Fonts", "doc"], mail: ["Mail", "doc"], other: ["Other", "file"],
};
const EXT = {};
Object.entries({
  photo: "jpg jpeg png heic heif webp avif gif bmp tif tiff raw cr2 cr3 nef arw dng", video: "mp4 mkv mov avi wmv webm m4v mts 3gp",
  audio: "mp3 m4a aac flac wav ogg opus wma", document: "pdf doc docx odt rtf txt md", spreadsheet: "xls xlsx xlsm ods csv",
  presentation: "ppt pptx odp key", ebook: "epub mobi azw3 djvu", code: "py js ts jsx tsx java c cpp h cs go rs rb php html css json yaml yml toml xml sh ps1 bat sql ipynb",
  design: "psd ai svg sketch fig blend stl dwg", archive: "zip 7z rar gz xz bz2 zst tar iso", software: "exe msi apk dll jar",
  data: "db sqlite bak log dat gpx", font: "ttf otf woff woff2", mail: "eml msg pst mbox",
}).forEach(([c, s]) => s.split(" ").forEach((e) => (EXT[e] = c)));
const catOf = (name) => EXT[(name.split(".").pop() || "").toLowerCase()] || "other";
const cc = (c) => `var(--c-${CAT[c] ? c : "other"})`;
const fc = (f) => `var(--f-${f === "zip" ? "zip" : f === "7z" ? "7z" : (f || "").startsWith("tar") ? "tar" : "x"})`;
const KCOL = ["var(--k1)", "var(--k2)", "var(--k3)", "var(--k4)", "var(--k5)", "var(--k6)"];
const hash = (s) => { let x = 7; for (const ch of s) x = (x * 31 + ch.charCodeAt(0)) >>> 0; return x; };
const folderColor = (path) => (path ? KCOL[hash(path.split("/")[0].toLowerCase()) % 6] : "var(--k2)");
const FMT_NAME = { zip: "ZIP", "7z": "7z", "tar.xz": "TAR.XZ" };
const FMT_EXT = { zip: ".zip", "7z": ".7z", "tar.xz": ".tar.xz" };
const LAYOUTS = [["keep", "Keep folders"], ["by_type", "By type"], ["by_date", "By date"], ["flat", "Flat"]];
const LEVELS = [["fast", "Fast"], ["balanced", "Balanced"], ["max", "Max"]];
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;

const S = { settings: {}, llm: "offline", models: [], view: "archive", cards: new Map(), jobs: new Map(), folders: [],
  lib: null, libFolder: "", detail: null, aiQueue: [], aiBusy: null, care: null, careJob: null, version: -1, docks: new Map(), lastItems: [] };

// ------------------------------------------------------------------ the logo: a kaidan-tansu (staircase chest)
const LOGO = {
  frame: [[6, 14, 40, 45], [6, 40, 68, 71], [6, 66, 96, 96]],
  // x0, y0, x1, y1, colour, order in which the drawers land in the opening animation
  drawers: [[10, 18, 36, 41, 1, 5], [10, 44, 36, 67, 2, 3], [39, 44, 64, 67, 3, 4], [10, 70, 36, 92, 4, 0], [39, 70, 64, 92, 5, 1], [67, 70, 92, 92, 6, 2]],
  stars: [[80, 25, 9.5, "var(--k2)"], [91.5, 41, 4.2, "var(--k4)"], [70, 41, 2.8, "var(--k1)"]],
};
function starPath(cx, cy, r) {
  let d = "";
  for (let i = 0; i < 8; i++) {
    const a = Math.PI / 4 * i - Math.PI / 2, rr = i % 2 ? r * .28 : r;
    d += (i ? "L" : "M") + (cx + rr * Math.cos(a)).toFixed(2) + " " + (cy + rr * Math.sin(a)).toFixed(2);
  }
  return d + "Z";
}
function logoSVG() {
  const id = "sh" + Math.random().toString(36).slice(2, 8);
  const rect = (x0, y0, x1, y1, rx, extra = "") => `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" rx="${rx}" ${extra}/>`;
  let s = `<svg class="logo" viewBox="0 0 100 100"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".28"/><stop offset=".45" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".12"/></linearGradient></defs>`;
  s += `<g class="lg-paper"><g transform="rotate(9 22.5 14)">${rect(14, 3, 31, 24, 1.6, 'class="sheet"')}${rect(17, 7.5, 28, 8.7, .6, 'class="ln"')}${rect(17, 10.5, 28, 11.7, .6, 'class="ln"')}${rect(17, 13.5, 24, 14.7, .6, 'class="ln"')}</g></g>`;
  s += `<g class="lg-rim">${LOGO.frame.map(([a, b, c, d]) => rect(a - .7, b - .7, c + .7, d + .7, 5.6)).join("")}</g>`;
  s += `<g class="lg-frame">${LOGO.frame.map(([a, b, c, d]) => rect(a, b, c, d, 5)).join("")}</g>`;
  for (const [x0, y0, x1, y1, k, o] of LOGO.drawers) {
    const mx = (x0 + x1) / 2, my = (y0 + y1) / 2 + .5;
    s += `<g class="lg-d" style="--o:${o}">${rect(x0, y0, x1, y1, 2.6, `fill="var(--k${k})"`)}${rect(x0, y0, x1, y1, 2.6, `fill="url(#${id})"`)}${rect(mx - 4.8, my - 1.6, mx + 4.8, my + 1.6, 1.6, 'class="lg-pull"')}</g>`;
  }
  for (const [cx, cy, r, c] of LOGO.stars) s += `<path class="lg-star" d="${starPath(cx, cy, r)}" fill="${c}"/>`;
  return s + "</svg>";
}

// ------------------------------------------------------------------ opening animation
function splash() {
  const sp = $("#splash");
  let off = false;
  try { off = localStorage.getItem("tansu.splash") === "off"; } catch (e) { /* storage blocked */ }
  const finish = () => {
    if (sp.classList.contains("out")) return;
    sp.classList.add("out");
    document.body.classList.remove("booting");
    document.body.classList.add("ready");
    setTimeout(() => { sp.classList.add("gone"); placeTabKnob(); }, 700);
  };
  if (off || REDUCED) { sp.classList.add("gone"); document.body.classList.remove("booting"); document.body.classList.add("ready"); return; }
  $("#spLogo").innerHTML = logoSVG();
  $("#spWord").append(...[..."Tansu"].map((ch, i) => h("span", { "--n": i }, ch)));
  sp.addEventListener("click", finish);
  setTimeout(finish, 2900);
}

// ------------------------------------------------------------------ server
async function api(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "X-Tansu": T, "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(j.error || r.statusText); e.password = j.password; throw e; }
  return j;
}
async function* stream(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "X-Tansu": T, "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || r.statusText); }
  const rd = r.body.getReader(), dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await rd.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (line) yield JSON.parse(line);
    }
  }
}
function toast(msg) {
  const t = h("div", { class: "toast" }, msg);
  document.body.append(t);
  setTimeout(() => t.remove(), 3500);
}
const fmtSize = (n) => { if (n == null) return "–"; const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return (i ? n.toFixed(n < 10 ? 1 : 0) : Math.round(n)) + " " + u[i]; };
const fmtSecs = (s) => s < 1 ? "< 1 s" : s < 60 ? `${Math.round(s)} s` : s < 3600 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`;
const fmtDate = (t) => t ? new Date(t * 1000).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "–";
const pct = (a, b) => b ? Math.round((1 - a / b) * 100) : 0;
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

function seg(options, value, onChange) {
  const el = h("div", { class: "seg" });
  const knob = h("span", { class: "knob" });
  el.append(knob);
  const btns = options.map(([v, label]) => h("button", { "data-v": v, onclick: () => { set(v); onChange(v); } }, label));
  el.append(...btns);
  function place() {
    const on = btns.find((b) => b.classList.contains("on"));
    if (on && on.offsetWidth) { knob.style.left = on.offsetLeft + "px"; knob.style.width = on.offsetWidth + "px"; }
  }
  function set(v) { btns.forEach((b) => b.classList.toggle("on", b.dataset.v === v)); requestAnimationFrame(place); }
  set(value);
  el.set = set;
  el.mark = (v) => btns.forEach((b) => { const has = b.querySelector(".spark"); if (b.dataset.v === v && !has) b.append(svg(I.spark, "i spark")); if (b.dataset.v !== v && has) has.parentElement.remove(); });
  new ResizeObserver(place).observe(el);
  return el;
}
function toggle(on, onChange) {
  const b = h("button", { class: "toggle" + (on ? " on" : "") });
  b.addEventListener("click", () => { b.classList.toggle("on"); onChange(b.classList.contains("on")); });
  b.set = (v) => b.classList.toggle("on", !!v);
  return b;
}

// ------------------------------------------------------------------ the packing stage: real files fly into a drawer
class Stage {
  /* names: [{name, c}] - real file names with their category colour; out = files fly out (extracting) */
  constructor({ names, label, total, est, files, out = false, small = false, onCancel }) {
    this.names = names.length ? names : [{ name: "file", c: "other" }];
    this.total = total || 0; this.est = est || 0; this.files = files || 0; this.out = out;
    this.i = 0; this.p = 0; this.state = "pack"; this.t0 = performance.now(); this.pileKey = "";
    this.pile = h("div", { class: "pile" });
    this.count = h("div", { class: "count" });
    this.stack = h("div", { class: "stack" });
    this.slot = h("div", { class: "slot" }, this.stack);
    this.meter = h("i");
    this.chest = h("div", { class: "chest" }, h("div", { class: "body" }), h("div", { class: "legs" }, h("i"), h("i")), this.slot,
      h("div", { class: "drw d1" }), h("div", { class: "drw d2" }, h("span", { class: "tag" }, label || "Archives"), h("span", { class: "meter" }, this.meter)),
      h("div", { class: "drw d3" }), h("div", { class: "scan" }));
    this.rb = h("b"); this.rs = h("span");
    this.bar = h("div", { class: "pbar" });
    this.hanko = h("div", { class: "hanko" }, svg(I.tick), out ? "DONE" : "VERIFIED");
    this.el = h("div", { class: "stage" + (out ? " out" : "") + (small ? " small" : "") },
      h("div", { class: "floor" }), h("div", { class: "readout" }, this.rb, this.rs), this.pile, this.count, this.chest, this.hanko, this.bar,
      onCancel ? h("button", { class: "btn small ghost cancel", onclick: onCancel }, "Cancel") : null);
    this.pile.append(this.count);
    this.renderPile();
    requestAnimationFrame(() => this.chest.classList.add("open"));
    this.timer = setInterval(() => this.tick(), out ? 240 : 210);
  }
  next() { const n = this.names[this.i++ % this.names.length]; return n; }
  renderPile() {
    const left = this.out ? Math.min(5, Math.ceil(this.p * 5)) : Math.max(this.p >= 1 ? 0 : 1, Math.ceil((1 - this.p) * 5));
    const key = left + ":" + Math.round(this.p * 200);
    if (key === this.pileKey) return;
    this.pileKey = key;
    $$(".pc", this.pile).forEach((x) => x.remove());
    for (let k = 0; k < left; k++) {
      const n = this.names[(this.i + k) % this.names.length];
      this.pile.prepend(h("div", { class: "pc", "--c": cc(n.c), style: { bottom: 8 + k * 14 + "px", left: (k % 2) * 6 + "px", transform: `rotate(${(k % 3 - 1) * 2.5}deg)`, zIndex: 5 - k } },
        h("i"), h("span", {}, n.name)));
    }
    const remaining = this.files ? Math.max(0, Math.round(this.files * (this.out ? this.p : 1 - this.p))) : null;
    this.count.textContent = remaining == null ? "" : this.out ? `${remaining.toLocaleString()} unpacked` : remaining ? `${remaining.toLocaleString()} file${remaining === 1 ? "" : "s"} to go` : "all in the drawer";
  }
  tick() {
    if (this.state !== "pack" || REDUCED || document.hidden) return;
    const st = this.el.getBoundingClientRect();
    if (!st.width) return;
    const slot = this.slot.getBoundingClientRect(), pile = this.pile.getBoundingClientRect();
    const n = this.next();
    const fly = h("div", { class: "fly", "--c": cc(n.c) }, h("i"), h("span", {}, n.name));
    this.el.append(fly);
    const a = { x: pile.left - st.left + 10 + Math.random() * 40, y: pile.top - st.top + 30 + Math.random() * 40 };
    const b = { x: slot.left - st.left + slot.width / 2 - 50, y: slot.top - st.top + 2 };
    const [from, to] = this.out ? [b, { x: a.x, y: a.y - 10 }] : [a, b];
    const mid = { x: (from.x + to.x) / 2, y: Math.min(from.y, to.y) - 55 - Math.random() * 30 };
    const rot = (Math.random() - .5) * 30;
    const frames = this.out
      ? [{ transform: `translate(${from.x}px,${from.y}px) scale(.3) rotate(0)`, opacity: 0 }, { transform: `translate(${mid.x}px,${mid.y}px) scale(.95) rotate(${rot}deg)`, opacity: 1, offset: .45 }, { transform: `translate(${to.x}px,${to.y}px) scale(1) rotate(0)`, opacity: 0 }]
      : [{ transform: `translate(${from.x}px,${from.y}px) scale(1) rotate(0)`, opacity: 0 }, { opacity: 1, offset: .1 }, { transform: `translate(${mid.x}px,${mid.y}px) scale(.9) rotate(${rot}deg)`, opacity: 1, offset: .55 }, { transform: `translate(${to.x}px,${to.y}px) scale(.32) rotate(${-rot / 2}deg)`, opacity: .2 }];
    const anim = fly.animate(frames, { duration: 820 + Math.random() * 200, easing: "cubic-bezier(.45,.05,.4,1)" });
    anim.onfinish = () => {
      fly.remove();
      if (this.out) return;
      this.chest.classList.remove("gulp"); void this.chest.offsetWidth; this.chest.classList.add("gulp");
      if (this.stack.children.length < 9) this.stack.append(h("b", { "--c": cc(n.c) }));
      this.stack.style.height = Math.min(22, this.stack.children.length * 5 * (.4 + this.p)) + "px";
    };
  }
  update(j) {
    this.p = j.progress;
    this.bar.style.width = (j.progress * 100).toFixed(1) + "%";
    this.meter.style.width = (Math.min(j.progress / .82, 1) * 100).toFixed(0) + "%";
    const verifying = /verif/i.test(j.phase || "");
    if (verifying && this.state === "pack") { this.state = "verify"; this.el.classList.add("verify"); }
    const eta = j.eta != null ? ` · ${fmtSecs(j.eta)} left` : "";
    if (this.out) {
      this.rb.textContent = `${Math.round(j.progress * 100)}%`;
      this.rs.textContent = `Unpacking${eta}`;
    } else if (this.state === "verify") {
      this.rb.textContent = "Checking every checksum…";
      this.rs.textContent = `${Math.round(j.progress * 100)}%${eta}`;
    } else {
      const f = Math.min(j.progress / .82, 1);
      this.rb.textContent = `${fmtSize(this.total * f)} → ${fmtSize(this.est * f)}`;
      this.rs.textContent = `${j.status === "queued" ? "Waiting for a free worker" : "Packing"} · ${Math.round(j.progress * 100)}%${eta}`;
    }
    this.renderPile();
  }
  /* small archives finish in a blink: let the drawer play out for a moment before closing it */
  complete(ok, r, after) {
    const left = (REDUCED || !ok ? 0 : this.out ? 1900 : 2900) - (performance.now() - this.t0);
    const done = () => { this.finish(ok, r); if (after) setTimeout(after, ok && !REDUCED ? 1300 : 0); };
    if (left < 300) return done();
    const start = performance.now(), p0 = this.p;
    const step = () => {
      const t = Math.min((performance.now() - start) / left, 1), p = p0 + (1 - p0) * t;
      this.update({ progress: p * .999, phase: !this.out && p > .82 ? "Verifying" : "Packing", status: "running", eta: null });
      if (t < 1) requestAnimationFrame(step); else done();
    };
    step();
  }
  finish(ok, r) {
    clearInterval(this.timer);
    this.state = "end";
    this.el.classList.remove("verify");
    $$(".cancel", this.el).forEach((b) => b.remove());
    this.bar.style.width = "100%";
    if (!ok) { this.el.classList.add("error"); this.chest.classList.remove("open"); this.rb.textContent = r || "Stopped"; this.rs.textContent = "nothing was saved"; return; }
    this.p = 1;
    this.renderPile();
    this.meter.style.width = "100%";
    if (r && !this.out) {
      this.stack.style.setProperty("--ratio", Math.max(.25, r.size / Math.max(r.original, 1)).toFixed(2));
      this.stack.style.transformOrigin = "bottom";
      this.chest.classList.add("squeeze");
      this.rb.textContent = `${fmtSize(r.original)} → ${fmtSize(r.size)}`;
      this.rs.textContent = `−${pct(r.size, r.original)}% · ${r.verified === "not checked" ? "saved" : "verified"} · ${fmtSecs(r.secs)}`;
    } else if (r) {
      this.rb.textContent = `${r.files.toLocaleString()} files`;
      this.rs.textContent = "unpacked";
    }
    setTimeout(() => { this.chest.classList.remove("open"); this.el.classList.add("done"); }, REDUCED ? 0 : 650);
  }
  destroy() { clearInterval(this.timer); this.el.remove(); }
}

// ------------------------------------------------------------------ tabs
function setView(v) {
  S.view = v;
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
  placeTabKnob();
  $$(".view").forEach((el) => el.classList.toggle("on", el.id === "v" + v[0].toUpperCase() + v.slice(1)));
  if (v === "library") loadLibrary();
  if (v === "care" && !S.care && !S.careJob) runCheckup(false);
  window.scrollTo({ top: 0 });
}
function placeTabKnob() {
  const on = $("#tabs button.on"), k = $("#tabs .knob");
  if (on) { k.style.left = on.offsetLeft + "px"; k.style.width = on.offsetWidth + "px"; }
}

// ------------------------------------------------------------------ adding files
async function pick(kind) {
  try {
    const b = await api("/api/pick", { kind });
    if (b) addBatch(b);
  } catch (e) { toast(e.message); }
}
async function readEntries(entry, path, out) {
  if (entry.isFile) {
    await new Promise((res) => entry.file((f) => { out.push([f, path + f.name]); res(); }, res));
  } else if (entry.isDirectory) {
    const rd = entry.createReader();
    let batch;
    do {
      batch = await new Promise((res) => rd.readEntries(res, () => res([])));
      for (const e of batch) await readEntries(e, path + entry.name + "/", out);
    } while (batch.length);
  }
}
async function dropped(dt) {
  const entries = [...dt.items].map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  const list = [];
  if (entries.length) for (const e of entries) await readEntries(e, "", list);
  else for (const f of dt.files) list.push([f, f.name]);
  if (!list.length) return;
  const total = list.reduce((a, [f]) => a + f.size, 0);
  const sess = Math.random().toString(36).slice(2, 12);
  compactDrop();
  const bar = h("div", { class: "jbar" }), txt = h("span", {}, "Reading dropped files…");
  const ph = h("div", { class: "card" }, h("div", { class: "job", style: { marginTop: 0 } }, h("div", { class: "spin" }), h("div", { class: "jt" }, h("b", {}, `${list.length} dropped file${list.length > 1 ? "s" : ""} · ${fmtSize(total)}`), txt), bar));
  $("#batches").prepend(ph);
  let done = 0;
  try {
    for (const [f, rel] of list) {
      await new Promise((res, rej) => {
        const x = new XMLHttpRequest();
        x.open("PUT", "/api/drop");
        x.setRequestHeader("X-Tansu", T);
        x.setRequestHeader("X-Session", sess);
        x.setRequestHeader("X-Rel", encodeURIComponent(rel));
        x.setRequestHeader("X-Mtime", String(f.lastModified || ""));
        x.upload.onprogress = (e) => { bar.style.width = ((done + e.loaded) / Math.max(total, 1) * 100).toFixed(1) + "%"; };
        x.onload = () => (x.status === 200 ? res() : rej(new Error(x.responseText)));
        x.onerror = () => rej(new Error("upload failed"));
        x.send(f);
      });
      done += f.size;
      txt.textContent = `Copying… ${fmtSize(done)} of ${fmtSize(total)}`;
    }
    ph.remove();
    addBatch(await api("/api/drop_done", { session: sess }));
  } catch (e) { ph.remove(); toast(e.message); }
}
const shortRoot = () => (S.settings.root || "").replace(/^.*\\(.*\\.*)$/, "$1");
function compactDrop() {
  const d = $("#drop");
  if (d.classList.contains("compact")) return;
  d.classList.add("compact");
  $("#dropTitle").textContent = "Add more";
  $("#dropText").innerHTML = "Files, folders, a drop, or Explorer → Send to → Tansu";
}
function expandDrop() {
  if (S.cards.size) return;
  $("#drop").classList.remove("compact");
  $("#dropTitle").textContent = "What goes in the chest today?";
  $("#dropText").innerHTML = `Add files or folders. Tansu measures them, the AI on your NPU picks the best archive type and the right drawer in <b>${shortRoot()}</b>, then packs and verifies it.`;
}

// ------------------------------------------------------------------ batch cards
function addBatch(b) {
  compactDrop();
  const old = S.cards.get(b.id);
  if (old) { old.update(b); return old; }
  const c = new Batch(b);
  S.cards.set(b.id, c);
  $("#batches").prepend(c.el);
  if (S.settings.ai && S.settings.auto_advise && S.llm !== "unsupported" && !b.has_ai) queueAdvice(c);
  return c;
}

class Batch {
  constructor(b) {
    this.b = b;
    this.touched = new Set();
    this.cur = { ...b.plan, recycle: b.recycle || false, skip_junk: S.settings.skip_junk, append_to: null };
    this.el = h("div", { class: "card batch" });
    this.build();
  }
  update(b) {
    this.b = b;
    const keep = {};
    for (const k of this.touched) keep[k] = this.cur[k];
    this.cur = { ...this.cur, ...b.plan, ...keep };
    this.build();
  }
  get facts() { return this.b.facts; }

  build() {
    const f = this.facts, el = this.el;
    el.innerHTML = "";
    const cats = Object.entries(f.by_cat);
    const main = cats[0] ? cats[0][0] : "other";
    this.titleEl = h("div", { class: "title" });
    const facts = [];
    if (f.dates) {
      const a = new Date(f.dates.min * 1000).getFullYear(), z = new Date(f.dates.max * 1000).getFullYear();
      facts.push(a === z ? `${a}` : `${a}–${z}`);
    }
    facts.push(`${Math.round(f.precompressed * 100)}% already compressed`);
    if (f.junk.files) facts.push(`${f.junk.files} junk file${f.junk.files > 1 ? "s" : ""} (${fmtSize(f.junk.bytes)}) left out`);
    if (f.project.length) facts.push("code project");
    if (f.truncated) facts.push("very large - first 400 000 files");
    const sens = f.sensitive.length ? h("span", { class: "warn", title: f.sensitive.join("\n"), "--n": facts.length }, "Personal / financial names") : null;
    el.append(
      h("div", { class: "top" },
        h("div", { class: "thumb", "--c": cc(main) }, svg(I[CAT[main] ? CAT[main][1] : "file"])),
        h("div", { class: "meta" }, this.titleEl,
          h("div", { class: "sub" }, `${f.count.toLocaleString()} file${f.count === 1 ? "" : "s"}${f.dirs ? ` in ${f.dirs.toLocaleString()} folder${f.dirs === 1 ? "" : "s"}` : ""} · ${fmtSize(f.total)}${this.b.temp ? " · dropped copy" : ""}`),
          h("div", { class: "facts" }, facts.map((t, i) => h("span", { "--n": i }, t)), sens)),
        h("button", { class: "iconbtn x", title: "Remove from the list", onclick: () => this.dismiss() }, svg(I.x))),
    );
    el.append(h("div", { class: "catbar" }, cats.map(([c, v], i) => h("i", { "--c": cc(c), style: { width: (v.bytes / Math.max(f.total, 1) * 100) + "%", animationDelay: i * 70 + "ms" }, title: `${(CAT[c] || CAT.other)[0]}: ${v.files} files, ${fmtSize(v.bytes)}` }))));
    el.append(h("div", { class: "legend" }, cats.slice(0, 7).map(([c, v]) => h("span", { "--c": cc(c) }, `${(CAT[c] || CAT.other)[0]} ${fmtSize(v.bytes)}`))));
    el.append(h("div", { class: "roots" }, f.roots.slice(0, 12).map((r) => h("div", { class: "root", title: r.path },
      svg(r.dir ? I.folder : I.file), h("span", {}, r.name), h("small", {}, r.dir ? `${r.files} files · ${fmtSize(r.size)}` : fmtSize(r.size)),
      f.roots.length > 1 ? h("button", { title: "Leave this out", onclick: () => this.removeRoot(r.path) }, svg(I.x)) : null)),
      f.roots.length > 12 ? h("div", { class: "root" }, h("span", {}, `+${f.roots.length - 12} more`)) : null));

    const edit = h("div", { class: "editable" });
    // advice
    this.adv = h("div", { class: "advice" });
    this.askIn = h("input", { class: "field", placeholder: "Tell Tansu what you want… e.g. “smallest possible”, “put it under Work”, “name it Tax 2025”" });
    this.askIn.addEventListener("keydown", (e) => { if (e.key === "Enter") this.ask(); });
    edit.append(this.adv, h("div", { class: "ask" }, this.askIn, h("button", { class: "btn small", onclick: () => this.ask() }, svg(I.spark), "Ask")));
    this.renderAdvice();

    // format
    this.fmtBox = h("div", { class: "formats" });
    this.levelSeg = seg(LEVELS, this.cur.level, (v) => { this.set("level", v); });
    edit.append(h("div", { class: "label", "--lc": "var(--k4)" }, "Archive type"), this.fmtBox, h("div", { class: "row2" }, h("div", { class: "opt" }, "Compression", this.levelSeg)));

    // destination
    this.folderIn = h("input", { class: "field", list: "folderList", value: this.cur.folder, spellcheck: "false" });
    this.nameIn = h("input", { class: "field", value: this.cur.name });
    this.folderIn.addEventListener("input", () => { this.set("folder", this.folderIn.value, false); this.renderPath(); this.loadAppend(); });
    this.nameIn.addEventListener("input", () => { this.set("name", this.nameIn.value, false); this.renderPath(); this.renderTitle(); });
    this.pathEl = h("div", { class: "pathline" });
    this.appendEl = h("div", { class: "appendbox", hidden: true });
    edit.append(h("div", { class: "label", "--lc": "var(--k2)" }, "Which drawer"),
      h("div", { class: "dest" }, h("label", {}, "Folder in Archives", this.folderIn), h("label", {}, "Name", this.nameIn)),
      this.pathEl, this.appendEl);

    // layout
    this.layoutSeg = seg(LAYOUTS, this.cur.layout, (v) => { this.set("layout", v); this.loadPreview(); });
    this.treeEl = h("div", { class: "ptree" });
    edit.append(h("div", { class: "label", "--lc": "var(--k3)" }, "Inside the archive"), h("div", { class: "layoutrow" }, this.layoutSeg, this.treeEl));

    // options
    this.encT = toggle(this.cur.encrypt, (v) => { this.set("encrypt", v); });
    this.pw1 = h("input", { class: "field", type: "password", placeholder: "Password", autocomplete: "new-password" });
    this.pw2 = h("input", { class: "field", type: "password", placeholder: "Repeat password", autocomplete: "new-password" });
    this.pwMsg = h("span", { class: "msg" });
    [this.pw1, this.pw2].forEach((p) => p.addEventListener("input", () => this.checkPw()));
    this.pwBox = h("div", { class: "pw" }, this.pw1, this.pw2, this.pwMsg);
    this.encRow = h("div", { class: "optrow" }, this.encT, h("span", {}, "Encrypt (AES-256, hides file names) ", h("small", {}, "7z only")));
    this.recT = toggle(this.cur.recycle, (v) => this.set("recycle", v));
    if (this.b.temp) this.recT.setAttribute("disabled", "");
    const recRow = h("div", { class: "optrow", title: this.b.temp ? "These are copies of dropped files - use Add files / Send to for this" : "Only after the archive is verified" }, this.recT, h("span", {}, "Move originals to the Recycle Bin when done"));
    edit.append(h("div", { class: "label", "--lc": "var(--k1)" }, "Options"), h("div", { class: "opts" }, this.encRow, recRow), this.pwBox);
    el.append(edit);

    // footer
    this.sumEl = h("div", { class: "sum grow" });
    this.goBtn = h("button", { class: "btn primary", onclick: () => this.go() }, svg(I.chest), "Archive");
    this.foot = h("div", { class: "foot" }, this.sumEl, this.goBtn);
    el.append(this.foot);
    this.jobEl = h("div");
    if (this.stage) el.append(this.stage.el);
    el.append(this.jobEl);

    this.renderAll();
    this.renderTree(this.b.preview);
    if (this.job) this.renderJob(this.job);
  }

  set(k, v, rerender = true) {
    this.cur[k] = v;
    this.touched.add(k);
    if (k === "format" && v !== "zip") this.cur.append_to = null;
    if (k === "format" && v === "zip") this.loadAppend();
    if (rerender) this.renderAll();
  }
  renderTitle() {
    this.titleEl.textContent = this.cur.append_to && this.cur.format === "zip" ? "Add to " + this.cur.append_to.split("/").pop() : (this.cur.name || "Archive") + FMT_EXT[this.cur.format];
  }
  renderAll() {
    this.renderFormats();
    this.levelSeg.set(this.cur.level);
    this.layoutSeg.set(this.cur.layout);
    if (this.folderIn.value !== this.cur.folder && document.activeElement !== this.folderIn) this.folderIn.value = this.cur.folder;
    if (this.nameIn.value !== this.cur.name && document.activeElement !== this.nameIn) this.nameIn.value = this.cur.name;
    const enc = this.cur.format === "7z";
    this.encRow.style.opacity = enc ? 1 : .45;
    if (!enc) { this.cur.encrypt = false; this.encT.setAttribute("disabled", ""); } else this.encT.removeAttribute("disabled");
    this.encT.set(this.cur.encrypt);
    this.pwBox.hidden = !this.cur.encrypt;
    this.renderPath();
    this.renderSummary();
    this.renderTitle();
    const ai = this.b.has_ai ? this.b.plan : null;
    this.layoutSeg.mark(ai && ai.layout);
    this.levelSeg.mark(ai && ai.level);
  }
  renderFormats() {
    const ai = this.b.has_ai ? this.b.plan.format : null;
    const best = ai || this.b.options[0].fmt;
    this.fmtBox.innerHTML = "";
    this.b.options.forEach((o, i) => {
      const [size, secs] = this.b.levels[o.fmt][this.cur.level];
      const card = h("button", { class: "fmt" + (this.cur.format === o.fmt ? " sel" : ""), "--fc": fc(o.fmt), "--n": i, onclick: () => this.set("format", o.fmt) },
        h("div", { class: "fn" }, h("i"), o.name, o.fmt === best ? h("span", { class: "pick" }, ai ? "AI pick" : "Best") : null),
        h("div", { class: "est" }, "≈ " + fmtSize(size), " ", h("small", {}, `· ${fmtSecs(secs)}`)),
        h("div", { class: "bar" }, h("i", { style: { width: (size / this.facts.total * 100 || 0).toFixed(1) + "%" } })),
        h("div", { class: "fwhy" }, (o.reasons[0] || o.up.split(".")[0]) + "."));
      card.addEventListener("mouseenter", () => showTip(card, o));
      card.addEventListener("mouseleave", hideTip);
      this.fmtBox.append(card);
    });
  }
  renderPath() {
    const parts = (this.cur.folder || "").split(/[\\/]+/).filter(Boolean);
    const known = new Set(S.folders.map((f) => f.toLowerCase()));
    const date = S.settings.date_prefix ? new Date().toISOString().slice(0, 10) + " " : "";
    this.pathEl.innerHTML = "";
    this.pathEl.append(h("span", { class: "seg2" }, "Archives"));
    parts.forEach((p, i) => {
      const sofar = parts.slice(0, i + 1).join("/").toLowerCase();
      this.pathEl.append(svg(I.chev), h("span", { class: "seg2" + (known.has(sofar) ? "" : " new"), style: { animationDelay: i * 50 + "ms" } }, p));
    });
    const appendTo = this.cur.format === "zip" && this.cur.append_to;
    this.pathEl.append(svg(I.chev), h("span", { class: "file" }, appendTo ? "+ into " + appendTo.split("/").pop() : date + (this.cur.name || "Archive") + FMT_EXT[this.cur.format]));
  }
  renderSummary() {
    const [size, secs] = this.b.levels[this.cur.format][this.cur.level];
    this.sumEl.innerHTML = "";
    this.sumEl.append(`${fmtSize(this.facts.total)} → `, h("b", {}, "≈ " + fmtSize(size)), ` (${pct(size, this.facts.total)}% smaller) · about ${fmtSecs(secs + (S.settings.verify ? secs * .15 : 0))}${S.settings.verify ? " incl. verification" : ""}`);
  }
  renderTree(p) {
    if (!p) return;
    this.preview = p;
    this.treeEl.innerHTML = "";
    p.tree.forEach((n, i) => this.treeEl.append(h("div", { class: n.dir ? "d" : "", "--d": n.depth, "--n": i, "--c": n.dir ? null : cc(catOf(n.name)) }, svg(n.dir ? I.folder : I.file), n.name)));
    if (p.entries > p.tree.length) this.treeEl.append(h("div", { class: "more" }, `… ${p.entries.toLocaleString()} entries in total`));
  }
  async loadPreview() {
    try { this.renderTree(await api("/api/preview", { id: this.b.id, layout: this.cur.layout })); } catch (e) { /* card gone */ }
  }
  loadAppend = debounce(async () => {
    if (this.cur.format !== "zip" || !this.cur.folder) { this.appendEl.hidden = true; this.cur.append_to = null; this.renderPath(); return; }
    let list = [];
    try { list = await api("/api/append_candidates", { folder: this.cur.folder }); } catch (e) { /* ignore */ }
    if (!list.length) { this.appendEl.hidden = true; this.cur.append_to = null; this.renderPath(); return; }
    const sel = h("select", { class: "field" }, h("option", { value: "" }, "Create a new archive"), list.map((r) => h("option", { value: r }, "Add to " + r.split("/").pop())));
    sel.value = this.cur.append_to || "";
    sel.addEventListener("change", () => { this.cur.append_to = sel.value || null; this.renderPath(); this.renderTitle(); });
    this.appendEl.innerHTML = "";
    this.appendEl.append(h("span", {}, "This drawer already has ZIPs:"), sel);
    this.appendEl.hidden = false;
  }, 350);

  renderAdvice(state, fresh) {
    const a = this.adv;
    a.innerHTML = "";
    a.classList.toggle("thinking", !!state);
    a.classList.remove("fresh");
    a.append(svg(I.spark, "i spark"));
    if (state) {
      a.append(h("div", {}, h("b", {}, state.title), h("div", { class: "src" }, state.sub || h("span", { class: "shimmer" }))));
      return;
    }
    const p = this.b.plan;
    const why = p.why || "Tansu's suggestion is below.";
    // the answer types itself in, word by word
    a.append(fresh && !REDUCED ? h("div", { class: "typing" }, why.split(/(\s+)/).map((w, i) => h("span", { "--n": i }, w))) : h("div", {}, why));
    if (p.tip) a.append(h("div", { class: "tipline" }, p.tip));
    const src = p.source === "ai" ? `Planned by ${S.settings.model} on the NPU${this.tps ? ` · ${this.tps} tok/s` : ""}${p.note ? ` · after “${p.note}”` : ""}`
      : S.llm === "unsupported" ? "Rule-based plan (the AI advisor needs a Ryzen AI NPU)"
      : S.settings.ai ? (S.llm === "online" ? "Rule-based plan · ask the AI for a second opinion" : "Rule-based plan · the AI is warming up on the NPU") : "Rule-based plan (AI advisor is off)";
    a.append(h("div", { class: "src" }, src));
    if (fresh) { void a.offsetWidth; a.classList.add("fresh"); }
  }
  checkPw() {
    const a = this.pw1.value, b = this.pw2.value;
    let msg = "", bad = false;
    if (a && a.length < 6) { msg = "at least 6 characters"; bad = true; }
    else if (b && a !== b) { msg = "passwords differ"; bad = true; }
    else if (a && a === b) msg = "✓ don't lose it - it cannot be recovered";
    this.pwMsg.textContent = msg;
    this.pwMsg.classList.toggle("bad", bad);
    return a.length >= 6 && a === b;
  }
  applyPlan(p, preview, tps) {
    this.b.plan = p;
    this.b.has_ai = p.source === "ai";
    this.tps = tps;
    const fields = ["format", "level", "encrypt", "folder", "name", "layout"];
    for (const k of fields) if (!this.touched.has(k) || this.askedNow) this.cur[k] = p[k];
    if (this.askedNow) fields.forEach((k) => this.touched.delete(k));
    this.askedNow = false;
    this.renderAdvice(null, true);
    this.renderAll();
    if (preview) this.renderTree(preview);
    this.loadAppend();
  }
  ask() {
    const q = this.askIn.value.trim();
    if (!q) { this.askIn.focus(); return; }
    if (!S.settings.ai) { toast("Turn the AI advisor on in Settings"); return; }
    this.askedNow = true;
    queueAdvice(this, q, true);
  }
  async removeRoot(path) {
    try {
      const b = await api("/api/batch_remove", { id: this.b.id, path });
      if (b) { this.update(b); if (S.settings.ai && S.settings.auto_advise && S.llm !== "unsupported") queueAdvice(this); } else this.remove();
    } catch (e) { toast(e.message); }
  }
  async dismiss() {
    if (this.job && ["queued", "running"].includes(this.job.status)) { await api("/api/cancel", { id: this.job.id }); }
    api("/api/batch_drop", { id: this.b.id }).catch(() => {});
    this.remove();
  }
  remove() {
    S.cards.delete(this.b.id);
    if (this.stage) this.stage.destroy();
    this.el.classList.add("leaving");
    setTimeout(() => { this.el.remove(); expandDrop(); }, 380);
  }
  async go() {
    if (this.cur.encrypt && !this.checkPw()) { toast("Enter the password twice (6+ characters)"); this.pw1.focus(); return; }
    if (!this.cur.name.trim() && !this.cur.append_to) { toast("Give the archive a name"); this.nameIn.focus(); return; }
    const plan = { ...this.cur, why: this.b.plan.why, tip: this.b.plan.tip, source: this.b.plan.source, note: this.b.plan.note };
    try {
      const j = await api("/api/archive", { id: this.b.id, plan, password: this.cur.encrypt ? this.pw1.value : null });
      this.pw1.value = this.pw2.value = "";
      this.renderJob(j);
      S.jobs.set(j.id, j);
      this.stage.el.scrollIntoView({ behavior: "smooth", block: "center" });
      poll();
    } catch (e) { toast(e.message); }
  }
  stageNames() {
    const files = ((this.preview || this.b.preview).tree || []).filter((n) => !n.dir).map((n) => ({ name: n.name, c: catOf(n.name) }));
    return files.length ? files : this.facts.roots.map((r) => ({ name: r.name, c: catOf(r.name) }));
  }
  renderJob(j) {
    this.job = j;
    const el = this.jobEl;
    if (!this.stage) {
      this.el.classList.add("packing");
      this.foot.hidden = true;
      this.stage = new Stage({ names: this.stageNames(), label: (this.cur.folder || "Archives").split("/").slice(-2).join(" / "),
        total: this.facts.total, est: this.b.levels[this.cur.format][this.cur.level][0], files: this.facts.count,
        onCancel: () => api("/api/cancel", { id: j.id }) });
      this.el.insertBefore(this.stage.el, this.jobEl);
    }
    if (["queued", "running"].includes(j.status)) { this.stage.update(j); return; }
    if (this.finished) return;
    this.finished = true;
    el.innerHTML = "";
    if (j.status === "done") {
      const r = j.result;
      this.stage.complete(true, r, () => {
        this.el.classList.remove("packing"); this.el.classList.add("packed");
        el.append(h("div", { class: "job done" }, h("div", { class: "okmark" }, svg(I.check)),
          h("div", { class: "jt" }, h("b", {}, (r.appended ? "Added to " : "Filed in ") + "Archives/" + r.rel),
            h("div", { class: "result" },
              h("span", {}, h("b", {}, fmtSize(r.original)), " → ", h("b", {}, fmtSize(r.size)), " ", h("span", { class: "saved" }, `−${pct(r.size, r.original)}%`)),
              h("span", {}, `${r.files.toLocaleString()} files · ${fmtSecs(r.secs)}`),
              h("span", {}, r.verified === "not checked" ? "not verified" : "✓ " + r.verified),
              r.recycled ? h("span", {}, `${r.recycled} original${r.recycled > 1 ? "s" : ""} → Recycle Bin`) : null,
              r.recycle_failed && r.recycle_failed.length ? h("span", { style: { color: "var(--err)" } }, `couldn't recycle: ${r.recycle_failed.join("; ")}`) : null)),
          h("button", { class: "btn small", onclick: () => api("/api/reveal", { rel: r.rel }) }, svg(I.folder), "Show"),
          h("button", { class: "btn small", onclick: () => { setView("library"); openArchive(r.rel); } }, "In library"),
          h("button", { class: "iconbtn small", title: "Done", onclick: () => this.dismiss() }, svg(I.x))));
      });
      return;
    }
    this.stage.complete(false, j.status === "cancelled" ? "Cancelled" : "Archiving failed");
    el.append(h("div", { class: "job error" }, svg(I.warn), h("div", { class: "jt" }, h("b", {}, j.status === "cancelled" ? "Cancelled - nothing was saved" : "Archiving failed"), h("span", {}, j.error || "")),
      h("button", { class: "btn small", onclick: () => this.reset() }, "Try again")));
  }
  reset() {
    this.job = null; this.finished = false;
    if (this.stage) { this.stage.destroy(); this.stage = null; }
    this.jobEl.innerHTML = "";
    this.el.classList.remove("packing", "packed");
    this.foot.hidden = false;
  }
}

// ------------------------------------------------------------------ AI queue (the NPU runs one request at a time)
function queueAdvice(card, note, front) {
  S.aiQueue = S.aiQueue.filter((q) => q.card !== card);
  const item = { card, note };
  if (front) S.aiQueue.unshift(item); else S.aiQueue.push(item);
  card.renderAdvice({ title: S.aiBusy && S.aiBusy !== card ? "Waiting for the NPU…" : "Tansu is thinking…", sub: null });
  runAdvice();
}
async function runAdvice() {
  if (S.aiBusy || !S.aiQueue.length) return;
  const { card, note } = S.aiQueue.shift();
  if (!S.cards.has(card.b.id) || card.job) { runAdvice(); return; }
  S.aiBusy = card;
  let waited = false;
  try {
    const started = performance.now();
    card.renderAdvice({ title: note ? `Re-planning: “${note}”` : "Tansu is thinking…", sub: null });
    for await (const ev of stream("/api/advise", { id: card.b.id, note })) {
      if (ev.type === "wait") { waited = true; card.renderAdvice({ title: "Loading the AI model onto the NPU…", sub: ev.text }); break; }
      if (ev.type === "think" || ev.type === "tokens") {
        const s = ((performance.now() - started) / 1000).toFixed(0);
        card.renderAdvice({ title: note ? `Re-planning: “${note}”` : "Tansu is thinking…", sub: `${S.settings.model} on the NPU · ${s} s` });
      }
      if (ev.type === "status") card.renderAdvice({ title: "Tansu is thinking…", sub: ev.data });
      if (ev.type === "plan") { card.applyPlan(ev.data, ev.preview, ev.tps); if (note) card.askIn.value = ""; }
      if (ev.type === "error") throw new Error(ev.text);
    }
  } catch (e) {
    card.renderAdvice();
    toast("AI: " + e.message);
  }
  S.aiBusy = null;
  if (waited) {
    S.aiQueue.unshift({ card, note });   // try again once the model is up
    setTimeout(runAdvice, 2500);
  } else runAdvice();
}

// ------------------------------------------------------------------ tooltip
function showTip(el, o) {
  const t = $("#tip");
  t.innerHTML = "";
  t.append(h("h5", {}, o.name), h("div", { class: "up" }, o.up), h("div", { class: "down" }, o.down),
    o.reasons.length ? h("div", { style: { marginTop: "8px", color: "var(--text)" } }, "Here: " + o.reasons.join("; ") + ".") : null);
  const r = el.getBoundingClientRect();
  t.style.left = Math.min(r.left, innerWidth - 320) + "px";
  t.style.top = r.bottom + 8 + "px";
  t.classList.add("on");
  requestAnimationFrame(() => { if (r.bottom + 8 + t.offsetHeight > innerHeight) t.style.top = (r.top - 8 - t.offsetHeight) + "px"; });
}
const hideTip = () => $("#tip").classList.remove("on");

// ------------------------------------------------------------------ library
async function loadLibrary() {
  try {
    S.lib = await api("/api/library");
    S.folders = S.lib.folders.map((f) => f.path).filter(Boolean);
    fillFolderList();
    renderLibrary();
  } catch (e) { toast(e.message); }
}
function fillFolderList() {
  const dl = $("#folderList");
  dl.innerHTML = "";
  S.folders.forEach((f) => dl.append(h("option", { value: f })));
}
function goFolder(p) { S.libFolder = p; $("#q").value = ""; renderLibrary(); }
function renderLibrary() {
  const L = S.lib;
  if (!L) return;
  const st = L.stats;
  const fmts = Object.entries(st.formats);
  const saved = st.original ? st.original - st.packed_known : 0;
  $("#stats").innerHTML = "";
  $("#stats").append(
    h("div", { class: "stat", "--n": 0, "--c": "var(--k4)" }, h("small", {}, "Archives"), h("b", {}, st.count), h("div", { class: "fmtbar" }, fmts.map(([f, n]) => h("i", { "--fc": fc(f), style: { flex: n }, title: `${f}: ${n}` }))),
      h("span", {}, fmts.map(([f, n]) => `${n} ${FMT_NAME[f] || f}`).join(" · ") || "none yet")),
    h("div", { class: "stat", "--n": 1, "--c": "var(--k2)" }, h("small", {}, "On disk"), h("b", {}, fmtSize(st.size)), h("span", {}, shortRoot())),
    h("div", { class: "stat", "--n": 2, "--c": "var(--k3)" }, h("small", {}, "Space saved"), h("b", {}, fmtSize(Math.max(saved, 0))), h("span", {}, st.original ? `${pct(st.packed_known, st.original)}% smaller than the originals` : "–")),
    h("div", { class: "stat", "--n": 3, "--c": "var(--k1)" }, h("small", {}, "Files inside"), h("b", {}, (st.files || 0).toLocaleString()), h("span", {}, st.unlisted ? `${st.unlisted} not indexed yet` : "all searchable")));
  // folder tree
  const tree = $("#tree");
  tree.innerHTML = "";
  L.folders.forEach((n) => {
    const depth = n.path ? n.path.split("/").length : 0;
    const name = n.path ? n.path.split("/").pop() : "All archives";
    tree.append(h("button", { class: "node" + (S.libFolder === n.path ? " on" : ""), "--d": depth, "--c": folderColor(n.path), title: n.path || L.root, onclick: () => goFolder(n.path) },
      n.path ? h("em") : svg(I.chest), h("span", {}, name), h("small", {}, n.archives || "")));
  });
  if ($("#q").value.trim()) return doSearch();
  renderCrumbs();
  // the cabinet: sub-folders of the current folder as drawer fronts
  const cab = $("#cabinet");
  cab.innerHTML = "";
  const depth = S.libFolder ? S.libFolder.split("/").length : 0;
  const kids = L.folders.filter((n) => n.path && n.path.split("/").length === depth + 1 && (!S.libFolder || n.path.startsWith(S.libFolder + "/")));
  kids.forEach((n, i) => cab.append(h("button", { class: "dfront", "--c": folderColor(n.path), "--n": i, onclick: () => goFolder(n.path) },
    n.archives ? h("span", { class: "peek" }) : null, h("span", { class: "lab" }, n.path.split("/").pop()),
    h("span", { class: "cnt" }, `${n.archives} archive${n.archives === 1 ? "" : "s"} · ${fmtSize(n.size)}`), h("span", { class: "pull" }))));
  const list = $("#arcList");
  list.innerHTML = "";
  const arcs = L.archives.filter((a) => S.libFolder ? a.folder === S.libFolder : !kids.length || a.folder === "");
  if (!L.archives.length) {
    list.append(h("div", { class: "empty" }, h("div", { class: "emptyart", html: logoSVG() }), h("b", {}, "The chest is empty"),
      "Archive something on the Archive tab - it will be filed here, with everything inside it searchable."));
    return;
  }
  if (!arcs.length && !kids.length) list.append(h("div", { class: "empty" }, h("b", {}, "Nothing in this drawer")));
  if (!S.libFolder && kids.length) {
    // at the top: the latest archives from all drawers
    const recent = L.archives.slice(0, 8);
    list.append(h("div", { class: "label", "--lc": "var(--k2)" }, "Latest"));
    recent.forEach((a, i) => list.append(arcRow(a, i)));
    return;
  }
  arcs.forEach((a, i) => list.append(arcRow(a, i)));
}
function renderCrumbs(extra) {
  const c = $("#crumbs");
  c.innerHTML = "";
  c.append(h("button", { onclick: () => goFolder("") }, "Archives"));
  const parts = S.libFolder ? S.libFolder.split("/") : [];
  parts.forEach((p, i) => {
    const path = parts.slice(0, i + 1).join("/");
    c.append(svg(I.chev), i === parts.length - 1 ? h("b", {}, p) : h("button", { onclick: () => goFolder(path) }, p));
  });
  c.append(h("span", { class: "spacer" }), extra || "",
    h("button", { class: "btn small ghost", onclick: () => api("/api/reveal", { rel: S.libFolder }) }, svg(I.folder), "Open in Explorer"));
}
function fmtIcon(fmt, encrypted) {
  return h("div", { class: "ficon", "--fc": fc(fmt) }, (fmt || "?").replace("tar.", "t."), encrypted ? h("span", { class: "lock" }, svg(I.lock)) : null);
}
function arcRow(a, i) {
  const ratio = a.original ? `−${pct(a.size, a.original)}%` : "";
  return h("button", { class: "arc" + (S.detail === a.rel ? " on" : ""), "--n": i, "--fc": fc(a.fmt), onclick: () => openArchive(a.rel) },
    fmtIcon(a.fmt, a.encrypted),
    h("div", { style: { minWidth: 0 } }, h("div", { class: "an" }, a.name),
      h("div", { class: "ad" }, [a.folder || "top level", a.files != null ? `${a.files.toLocaleString()} files` : "not indexed", fmtDate(a.created), a.by === "found" ? "added outside Tansu" : null].filter(Boolean).join(" · "))),
    h("div", { class: "ar" }, h("b", {}, fmtSize(a.size)), ratio ? h("span", { class: "saved" }, ratio) : ""));
}
const doSearch = debounce(async () => {
  const q = $("#q").value.trim();
  $("#qClear").hidden = !q;
  if (!q) { renderLibrary(); return; }
  const res = await api("/api/search", { q }).catch(() => []);
  const list = $("#arcList");
  list.innerHTML = "";
  $("#cabinet").innerHTML = "";
  renderCrumbs(h("span", { style: { color: "var(--muted)" } }, `${res.reduce((a, r) => a + r.count, 0)} files in ${res.length} archives`));
  if (!res.length) { list.append(h("div", { class: "empty" }, h("b", {}, "Nothing found"), "Tansu searched the names of every file inside every indexed archive.")); return; }
  const by = new Map(S.lib.archives.map((a) => [a.rel, a]));
  const words = q.toLowerCase().split(/\s+/);
  const mark = (s) => { const low = s.toLowerCase(); const w = words.find((w) => low.includes(w)); if (!w) return s; const i = low.indexOf(w); return h("span", {}, s.slice(0, i), h("mark", {}, s.slice(i, i + w.length)), s.slice(i + w.length)); };
  res.forEach((r, i) => {
    const a = by.get(r.rel) || { rel: r.rel, name: r.rel.split("/").pop(), folder: r.rel.split("/").slice(0, -1).join("/"), fmt: r.fmt, size: null };
    const row = arcRow(a, i);
    if (r.hits.length) row.append(h("div", { class: "hits" }, r.hits.slice(0, 6).map((x) => h("div", { "--c": cc(catOf(x.name)) }, svg(I.file), mark(x.name), h("span", { style: { color: "var(--faint)" } }, fmtSize(x.size)))),
      r.count > 6 ? h("div", { style: { color: "var(--faint)" } }, `+ ${r.count - 6} more`) : null));
    list.append(row);
  });
}, 220);

// ------------------------------------------------------------------ archive detail
async function openArchive(rel, password) {
  S.detail = rel;
  $$(".arc").forEach((x) => x.classList.remove("on"));
  const d = $("#detail");
  if (!S.lib) await loadLibrary();
  const a = (S.lib && S.lib.archives.find((x) => x.rel === rel)) || { rel, name: rel.split("/").pop(), folder: "" };
  d.innerHTML = "";
  const body = h("div", { class: "db" });
  d.append(h("div", { class: "dh" }, fmtIcon(a.fmt, a.encrypted), h("div", { class: "dtitle" }, h("div", {}, a.name), h("small", {}, "Archives/" + (a.folder ? a.folder + "/" : ""))),
    h("button", { class: "iconbtn", onclick: closeDrawers }, svg(I.x))), body);
  openDrawer(d);
  const kv = h("dl", { class: "kv" });
  const add = (k, v) => v != null && v !== "" && kv.append(h("dt", {}, k), h("dd", {}, v));
  add("Size", a.original ? `${fmtSize(a.size)} (from ${fmtSize(a.original)}, −${pct(a.size, a.original)}%)` : fmtSize(a.size));
  add("Files", a.files != null ? a.files.toLocaleString() : "not indexed yet");
  add("Created", fmtDate(a.created) + (a.by === "found" ? " · found in the library" : ""));
  add("Format", (FMT_NAME[a.fmt] || a.fmt) + (a.level ? ` · ${a.level}` : "") + (a.encrypted ? " · AES-256 encrypted" : ""));
  add("Layout", a.layout && LAYOUTS.find((l) => l[0] === a.layout) ? LAYOUTS.find((l) => l[0] === a.layout)[1] : null);
  add("Verified", a.verified ? "✓ " + fmtDate(a.verified) : null);
  if (a.sources && a.sources.length) add("From", h("div", {}, a.sources.slice(0, 5).map((s) => h("div", { style: { wordBreak: "break-all" } }, s))));
  body.append(kv);
  if (a.why) body.append(h("div", { class: "why" }, h("b", {}, "Why this way · "), a.why));
  // an encrypted archive can be browsed from Tansu's index, but extracting and testing need the password
  const pwIn = a.encrypted ? h("input", { class: "field", type: "password", placeholder: "Password to extract or test", value: password || "" }) : null;
  const pw = () => (pwIn ? pwIn.value : password) || null;
  const needPw = () => { if (pwIn && !pwIn.value) { toast("Enter the archive password first"); pwIn.focus(); return true; } return false; };
  const testBtn = h("button", { class: "btn small", onclick: async () => {
    if (needPw()) return;
    testBtn.setAttribute("disabled", ""); testBtn.textContent = "Testing…";
    try { const r = await api("/api/verify", { rel, password: pw() }); toast(r.ok ? "✓ " + r.msg : "Problem: " + r.msg); } catch (e) { toast(e.message); }
    testBtn.removeAttribute("disabled"); testBtn.textContent = "Test";
  } }, "Test");
  if (pwIn) body.append(h("div", { class: "pwbox" }, svg(I.lock), pwIn));
  body.append(h("div", { class: "dactions" },
    h("button", { class: "btn small primary", onclick: () => !needPw() && extract(rel, null, pw()) }, svg(I.out), "Extract all"),
    h("button", { class: "btn small", onclick: () => !needPw() && extract(rel, null, pw(), true) }, "Extract to…"),
    h("button", { class: "btn small", onclick: () => api("/api/reveal", { rel }) }, svg(I.folder), "Show"),
    h("button", { class: "btn small", onclick: () => api("/api/open", { rel }).catch((e) => toast(e.message)) }, svg(I.open), "Open"),
    testBtn,
    h("button", { class: "btn small ghost danger", onclick: async () => {
      if (!confirm(`Move “${a.name}” to the Recycle Bin?`)) return;
      try { await api("/api/recycle", { rel }); toast("Moved to the Recycle Bin"); closeDrawers(); loadLibrary(); } catch (e) { toast(e.message); }
    } }, svg(I.trash), "Recycle")));
  const mvFolder = h("input", { class: "field", list: "folderList", value: a.folder || "", placeholder: "Folder" });
  const mvName = h("input", { class: "field", value: a.name, placeholder: "Name" });
  body.append(h("div", { class: "label", "--lc": "var(--k2)" }, "Move or rename"), h("div", { class: "movebox" }, mvFolder, mvName,
    h("button", { class: "btn small", onclick: async () => {
      try { const r = await api("/api/move", { rel, folder: mvFolder.value, name: mvName.value }); toast("Moved to Archives/" + r.rel); await loadLibrary(); openArchive(r.rel, password); } catch (e) { toast(e.message); }
    } }, "Apply")));
  const holder = h("div", {}, h("div", { class: "spin", style: { margin: "20px auto" } }));
  body.append(h("div", { class: "label", "--lc": "var(--k3)" }, "Contents"), holder);
  try {
    const r = await api("/api/contents", { rel, password });
    if (S.detail !== rel) return;
    S.lastItems = r.items;
    holder.innerHTML = "";
    holder.append(contentsTree(rel, r.items, () => pw(), a));
  } catch (e) {
    holder.innerHTML = "";
    if (e.password) {
      const p = h("input", { class: "field", type: "password", placeholder: "Archive password" });
      const go = () => openArchive(rel, p.value);
      p.addEventListener("keydown", (ev) => ev.key === "Enter" && go());
      holder.append(h("div", { class: "pwbox" }, svg(I.lock), "This archive is encrypted.", p, h("button", { class: "btn small", onclick: go }, "Unlock")));
      setTimeout(() => p.focus(), 300);
    } else holder.append(h("div", { class: "empty" }, h("b", {}, "Can't read the contents"), e.message));
  }
}
function contentsTree(rel, items, password, a) {
  const root = { name: "", kids: new Map(), size: 0, files: 0, path: "" };
  for (const it of items) {
    const parts = it.name.split("/").filter(Boolean);
    let n = root;
    parts.forEach((p, i) => {
      if (!n.kids.has(p)) n.kids.set(p, { name: p, kids: new Map(), size: 0, files: 0, path: parts.slice(0, i + 1).join("/"), dir: i < parts.length - 1 || it.dir });
      n = n.kids.get(p);
      if (i === parts.length - 1 && !it.dir) { n.dir = false; n.size = it.size; }
    });
  }
  const sum = (n) => { if (!n.dir && n !== root) { n.files = 1; return; } n.size = 0; n.files = 0; for (const k of n.kids.values()) { sum(k); n.size += k.size; n.files += k.files; } };
  sum(root);
  const selected = new Set();
  const filter = h("input", { class: "field", placeholder: `Filter ${items.length.toLocaleString()} entries…` });
  const exBtn = h("button", { class: "btn small", disabled: true, onclick: () => {
    const p = password();
    if (a.encrypted && !p) { toast("Enter the archive password first"); return; }
    extract(rel, [...selected], p);
  } }, svg(I.out), "Extract selected");
  const box = h("div", { class: "ctree" });
  const updateBtn = () => { exBtn.toggleAttribute("disabled", !selected.size); exBtn.lastChild.textContent = selected.size ? `Extract ${selected.size} selected` : "Extract selected"; };
  let budget;
  function row(n, depth) {
    const cb = h("input", { type: "checkbox" });
    cb.checked = selected.has(n.path);
    cb.addEventListener("change", () => { cb.checked ? selected.add(n.path) : selected.delete(n.path); updateBtn(); });
    return h("div", { class: "cnode" + (n.dir ? " dir closed" : ""), "--d": depth, "--c": n.dir ? null : cc(catOf(n.name)) },
      h("span", { class: "tw" }, n.dir ? svg(I.down) : ""), cb, h("span", { class: "ic" }, svg(n.dir ? I.folder : I.file)),
      h("span", { class: "nm", title: n.path }, n.name), h("span", { class: "sz" }, n.dir ? `${n.files.toLocaleString()} · ${fmtSize(n.size)}` : fmtSize(n.size)));
  }
  function renderLevel(n, depth, after) {
    const kids = [...n.kids.values()].sort((x, y) => (y.dir - x.dir) || x.name.localeCompare(y.name));
    let anchor = after;
    for (const k of kids) {
      if (budget-- <= 0) { const more = h("div", { class: "cnode", "--d": depth, style: { color: "var(--faint)" } }, "… use the filter to find more"); anchor ? anchor.after(more) : box.append(more); return anchor; }
      const r = row(k, depth);
      anchor ? anchor.after(r) : box.append(r);
      anchor = r;
      if (k.dir) {
        let open = false, kidsEls = [];
        r.addEventListener("click", (e) => {
          if (e.target.tagName === "INPUT") return;
          open = !open;
          r.classList.toggle("closed", !open);
          if (open) { budget = 1500; const before = r.nextSibling; renderLevel(k, depth + 1, r); kidsEls = []; for (let x = r.nextSibling; x && x !== before; x = x.nextSibling) kidsEls.push(x); }
          else kidsEls.forEach((x) => x.remove());
        });
      }
    }
    return anchor;
  }
  function render() {
    box.innerHTML = "";
    const q = filter.value.trim().toLowerCase();
    budget = 1500;
    if (!q) {
      renderLevel(root, 0, null);
      if (root.kids.size === 1) { const only = box.querySelector(".cnode.dir"); if (only) only.click(); }
      return;
    }
    const hits = items.filter((i) => !i.dir && i.name.toLowerCase().includes(q)).slice(0, 800);
    if (!hits.length) box.append(h("div", { class: "cnode", style: { color: "var(--faint)" } }, "No match"));
    hits.forEach((i) => box.append(row({ name: i.name, path: i.name, size: i.size, dir: false }, 0)));
  }
  filter.addEventListener("input", debounce(render, 150));
  render();
  return h("div", {}, h("div", { class: "ctools" }, filter, exBtn), box);
}

// ------------------------------------------------------------------ extracting: files fly out of the drawer (dock, bottom right)
async function extract(rel, members, password, choose) {
  try {
    const j = await api("/api/extract", { rel, members, password, choose: !!choose });
    if (!j) return;
    S.jobs.set(j.id, j);
    const items = (S.detail === rel ? S.lastItems : []).filter((i) => !i.dir && (!members || members.some((m) => i.name === m || i.name.startsWith(m + "/"))));
    const names = items.slice(0, 24).map((i) => ({ name: i.name.split("/").pop(), c: catOf(i.name) }));
    const st = new Stage({ names, label: rel.split("/").slice(-1)[0].replace(/\.(zip|7z|tar\.xz)$/i, ""), files: items.length, out: true, small: true });
    const line = h("div", { class: "dline" }, h("b", {}, "Extracting " + rel.split("/").pop()));
    const card = h("div", { class: "dcard" }, st.el, line);
    $("#dock").append(card);
    S.docks.set(j.id, { st, card, line });
    poll();
  } catch (e) { toast(e.message); }
}
function updateDock(j) {
  const d = S.docks.get(j.id);
  if (!d) return;
  if (["queued", "running"].includes(j.status)) { d.st.update(j); return; }
  if (d.ended) return;
  d.ended = true;
  const close = () => { d.card.classList.add("leaving"); setTimeout(() => { d.st.destroy(); d.card.remove(); S.docks.delete(j.id); }, 450); };
  d.line.innerHTML = "";
  if (j.status === "done") {
    d.st.complete(true, j.result);
    d.line.append(h("b", {}, `${j.result.files.toLocaleString()} files → ${j.result.dest}`), h("button", { class: "btn small", onclick: () => api("/api/reveal", { path: j.result.dest }) }, svg(I.folder), "Open"),
      h("button", { class: "iconbtn small", onclick: close }, svg(I.x)));
    setTimeout(close, 9000);
  } else {
    d.st.complete(false, j.status === "cancelled" ? "Cancelled" : "Extract failed");
    d.line.append(h("b", { style: { color: "var(--err)" } }, j.error || "Cancelled"), h("button", { class: "iconbtn small", onclick: close }, svg(I.x)));
  }
}

// ------------------------------------------------------------------ care
async function runCheckup(deep) {
  try {
    const j = await api("/api/checkup", { deep });
    S.careJob = j.id;
    S.jobs.set(j.id, j);
    renderCareJob(j);
    poll();
  } catch (e) { toast(e.message); }
}
function renderCareJob(j) {
  const el = $("#careJob");
  el.innerHTML = "";
  if (["queued", "running"].includes(j.status)) {
    el.append(h("div", { class: "job" }, h("div", { class: "spin" }), h("div", { class: "jt" }, h("b", {}, j.title), h("span", {}, j.phase)),
      h("span", { class: "pct" }, Math.round(j.progress * 100) + "%"), h("div", { class: "jbar", style: { width: j.progress * 100 + "%" } })));
    return;
  }
  S.careJob = null;
  if (j.status === "done") { S.care = j.result; renderIssues(); }
  else if (j.status === "error") el.append(h("div", { class: "job error" }, svg(I.warn), h("div", { class: "jt" }, h("b", {}, "Checkup failed"), h("span", {}, j.error))));
}
const ISSUE = {
  broken: [I.warn, "var(--err)"], duplicate: [I.copy, "var(--k1)"], loose_archive: [I.box, "var(--k4)"],
  loose_file: [I.file, "var(--k2)"], similar_folders: [I.merge, "var(--k5)"], empty_folder: [I.folder, "var(--faint)"],
  unlisted: [I.search, "var(--k6)"],
};
async function renderIssues() {
  const box = $("#issues");
  box.innerHTML = "";
  const issues = (S.care && S.care.issues) || [];
  const badge = $("#careBadge");
  const open = issues.filter((i) => !i.done && i.kind !== "unlisted").length;
  badge.hidden = !open;
  badge.textContent = open;
  if (!issues.length) {
    box.append(h("div", { class: "allgood" }, h("div", { class: "okmark" }, svg(I.check)), h("b", {}, "Everything is in its drawer"),
      h("div", {}, S.care && S.care.deep ? "Every archive passed its checksum test." : "Run a deep checkup now and then to test every archive.")));
    return;
  }
  const loose = issues.filter((i) => i.kind === "loose_archive" && !i.done);
  const head = h("div", { class: "label", "--lc": "var(--k1)" }, `${issues.length} thing${issues.length > 1 ? "s" : ""} to look at`, h("span", { class: "spacer" }));
  if (loose.length) {
    const btn = h("button", { class: "btn small", onclick: async () => {
      btn.setAttribute("disabled", ""); btn.lastChild.textContent = "Thinking…";
      try {
        const map = await api("/api/suggest_folders", { rels: loose.map((i) => i.rel) });
        loose.forEach((i) => { i.suggest = map[i.rel]; });
        renderIssues();
      } catch (e) { toast(e.message); btn.removeAttribute("disabled"); }
    } }, svg(I.spark), loose.some((i) => i.suggest) ? "Suggest again" : "Suggest drawers");
    head.append(btn);
  }
  box.append(head);
  issues.forEach((it, n) => {
    const [icon, color] = ISSUE[it.kind] || [I.warn, "var(--muted)"];
    const actions = h("div", { class: "ia" });
    const done = (msg) => { it.done = true; toast(msg); renderIssues(); S.lib = null; };
    const fixIt = async (extra, msg) => {
      try { const r = await api("/api/fix", { issue: it, ...extra }); if (r.batch) { setView("archive"); addBatch(r.batch); it.done = true; renderIssues(); return; } done(msg); } catch (e) { toast(e.message); }
    };
    if (!it.done) {
      if (it.kind === "loose_archive") {
        const f = h("input", { class: "field", list: "folderList", value: it.suggest || "", placeholder: "Folder…" });
        actions.append(f, h("button", { class: "btn small", onclick: () => fixIt({ folder: f.value }, "Filed") }, "Move"));
      } else if (it.kind === "loose_file") actions.append(h("button", { class: "btn small", onclick: () => fixIt({}, "") }, svg(I.chest), "Archive it"));
      else if (it.kind === "empty_folder") actions.append(h("button", { class: "btn small", onclick: () => fixIt({}, "Folder removed") }, "Remove"));
      else if (it.kind === "duplicate") actions.append(h("button", { class: "btn small", onclick: () => fixIt({}, "Copy moved to the Recycle Bin") }, svg(I.trash), "Recycle copy"));
      else if (it.kind === "similar_folders") actions.append(h("button", { class: "btn small", onclick: () => fixIt({}, "Folders merged") }, svg(I.merge), "Merge"));
      else if (it.kind === "unlisted") actions.append(h("button", { class: "btn small", onclick: () => fixIt({}, "Indexed") }, "Index"));
      if (!["similar_folders", "empty_folder", "loose_file"].includes(it.kind)) actions.append(h("button", { class: "iconbtn small", title: "Show in Explorer", onclick: () => api("/api/reveal", { rel: it.rel }) }, svg(I.folder)));
    } else actions.append(h("span", { style: { color: "var(--k3)", fontSize: "13px", fontWeight: 600 } }, "✓ Done"));
    box.append(h("div", { class: "issue" + (it.done ? " done" : ""), "--n": n, "--ic": color },
      h("div", { class: "ii" }, svg(icon)), h("div", { class: "grow" }, h("div", { class: "it" }, it.title), h("div", { class: "idt" }, it.detail)), actions));
  });
  const unl = issues.filter((i) => i.kind === "unlisted" && !i.done);
  if (unl.length > 2) box.append(h("button", { class: "btn small", style: { alignSelf: "flex-start" }, onclick: async () => { const j = await api("/api/index"); S.jobs.set(j.id, j); toast("Indexing in the background"); poll(); } }, `Index all ${unl.length}`));
}

// ------------------------------------------------------------------ drawers + settings
function openDrawer(d) { $$(".drawer").forEach((x) => x !== d && x.classList.remove("on")); d.classList.add("on"); $("#scrim").classList.add("on"); }
function closeDrawers() { $$(".drawer").forEach((x) => x.classList.remove("on")); $("#scrim").classList.remove("on"); S.detail = null; $$(".arc").forEach((x) => x.classList.remove("on")); }
function renderSettings() {
  const s = S.settings;
  $("#setRoot").textContent = s.root;
  $("#setExtract").textContent = s.extract_dir;
  $$("[data-set]").forEach((b) => b.classList.toggle("on", !!s[b.dataset.set]));
  let sp = true;
  try { sp = localStorage.getItem("tansu.splash") !== "off"; } catch (e) { /* storage blocked */ }
  $("#splashToggle").classList.toggle("on", sp);
  const sel = $("#model");
  const models = S.models.length ? S.models : [s.model];
  if (sel.options.length !== models.length) { sel.innerHTML = ""; models.forEach((m) => sel.append(h("option", { value: m }, m))); }
  sel.value = s.model;
}
async function saveSetting(k, v) {
  try {
    S.settings = await api("/api/settings", { [k]: v });
    renderSettings();
    if (["root", "skip_junk"].includes(k)) { const list = await api("/api/batches"); list.forEach(addBatch); S.lib = null; }
    S.cards.forEach((c) => !c.job && c.renderAll());
  } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ polling
let pollTimer = null;
async function poll() {
  clearTimeout(pollTimer);
  let st;
  try { st = await api("/api/state"); } catch (e) { pollTimer = setTimeout(poll, 3000); return; }
  const firstSettings = !S.settings.root;
  S.settings = st.settings;
  S.models = st.models;
  if (firstSettings) { renderSettings(); expandDrop(); }
  const was = S.llm;
  S.llm = st.llm;
  const dot = $("#aiDot"), txt = $("#aiText");
  dot.className = "dot " + (!st.settings.ai ? "" : S.aiBusy ? "busy" : st.llm);
  $("#aboutVer").textContent = `Tansu ${st.app_version} beta`;
  txt.textContent = st.llm === "unsupported" ? "Rules · no NPU" : !st.settings.ai ? "AI off" : st.llm === "online" ? (S.aiBusy ? "Thinking on the NPU" : `${st.settings.model} · NPU`) : st.llm === "starting" ? "Loading model…" : st.llm === "missing" ? "FastFlowLM missing" : "AI offline";
  $("#aiPill").title = st.detail || "Archiving advisor running on the Ryzen AI NPU";
  $("#aiSpeed").textContent = st.tps ? `last answer ${st.tps} tok/s` : "";
  $("#sendto").classList.toggle("on", st.sendto);
  if (was !== "online" && st.llm === "online") S.cards.forEach((c) => !c.b.has_ai && !S.aiBusy && !c.job && c.renderAdvice());
  // batches added by "Send to"
  if (st.version !== S.version) {
    const fresh = S.version !== -1 || st.batches.length;
    S.version = st.version;
    if (fresh) {
      const missing = st.batches.filter((id) => !S.cards.has(id));
      if (missing.length) {
        const list = await api("/api/batches").catch(() => []);
        list.filter((b) => missing.includes(b.id)).forEach((b) => addBatch(b));
        if (S.view !== "archive") setView("archive");
      }
    }
  }
  let active = false;
  for (const j of st.jobs) {
    const before = S.jobs.get(j.id);
    S.jobs.set(j.id, j);
    if (["queued", "running"].includes(j.status)) active = true;
    if (j.kind === "archive") {
      const card = [...S.cards.values()].find((c) => c.job && c.job.id === j.id);
      if (card) card.renderJob(j);
      if (before && before.status !== "done" && j.status === "done") { S.lib = null; if (S.care) S.care.stale = true; }
    } else if (j.kind === "checkup") {
      if (S.careJob === j.id) renderCareJob(j);
    } else if (j.kind === "extract") {
      updateDock(j);
    } else if (before && before.status !== j.status && j.kind === "index" && j.status === "done") {
      S.lib = null;
      if (S.view === "library") loadLibrary();
    }
  }
  if (S.view === "library" && !S.lib) loadLibrary();
  pollTimer = setTimeout(poll, active || S.aiBusy || st.llm === "starting" ? 450 : 2500);
}

// ------------------------------------------------------------------ boot
async function boot() {
  splash();
  $("#brandLogo").innerHTML = logoSVG();
  $("#heroLogo").innerHTML = logoSVG();
  $("#ovLogo").innerHTML = logoSVG();
  $$("#tabs button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
  window.addEventListener("resize", placeTabKnob);
  setTimeout(placeTabKnob, 50);
  $("#btnFiles").onclick = () => pick("files");
  $("#btnFolder").onclick = () => pick("folder");
  $("#btnRoot").onclick = () => api("/api/reveal", { rel: "" });
  $("#btnSettings").onclick = () => { renderSettings(); openDrawer($("#settings")); };
  $("#scrim").onclick = closeDrawers;
  $$("[data-close]").forEach((b) => (b.onclick = closeDrawers));
  $$("[data-set]").forEach((b) => (b.onclick = () => saveSetting(b.dataset.set, !b.classList.contains("on"))));
  $("#model").onchange = (e) => saveSetting("model", e.target.value);
  $("#btnPickRoot").onclick = async () => { S.settings = await api("/api/pick_root"); renderSettings(); S.lib = null; expandDrop(); };
  $("#btnPickExtract").onclick = async () => { S.settings = await api("/api/pick_extract"); renderSettings(); };
  $("#sendto").onclick = async () => { const r = await api("/api/sendto", { on: !$("#sendto").classList.contains("on") }); $("#sendto").classList.toggle("on", r.on); toast(r.on ? "Added to Explorer → Send to" : "Removed from Send to"); };
  $("#splashToggle").onclick = () => { const on = !$("#splashToggle").classList.contains("on"); try { localStorage.setItem("tansu.splash", on ? "on" : "off"); } catch (e) { /* ignore */ } $("#splashToggle").classList.toggle("on", on); };
  $("#btnCheck").onclick = () => runCheckup(false);
  $("#btnDeep").onclick = () => runCheckup(true);
  $("#q").addEventListener("input", doSearch);
  $("#qClear").onclick = () => { $("#q").value = ""; doSearch(); };
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawers(); });
  window.addEventListener("scroll", () => $("#hdr").classList.toggle("scrolled", scrollY > 4));
  let depth = 0;
  window.addEventListener("dragenter", (e) => { if (!e.dataTransfer.types.includes("Files")) return; e.preventDefault(); depth++; $("#overlay").classList.add("on"); });
  window.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) $("#overlay").classList.remove("on"); });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => { e.preventDefault(); depth = 0; $("#overlay").classList.remove("on"); if (S.view !== "archive") setView("archive"); dropped(e.dataTransfer); });

  await poll();
  try {
    S.folders = await api("/api/folders");
    fillFolderList();
    const list = await api("/api/batches");
    list.reverse().forEach(addBatch);
  } catch (e) { /* first start */ }
}
boot();
