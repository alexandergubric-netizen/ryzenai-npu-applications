/* Washi core: state, server API, small UI kit (toasts, menus, modals), command registry. */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PX = 96 / 72;          // CSS pixels per PDF point at 100 %

const S = {
  docs: {},          // id -> server info
  views: {},         // id -> per-document view state
  order: [],         // tab order
  active: null,
  settings: {},
  ai: { supported: false, enabled: false, state: "offline" },
  tool: "select",
  style: { color: "#ffd84d", stroke: "#e2452f", fill: null, width: 2, size: 14, opacity: 1, font: "sans", stamp: "Approved" },
  ribbonTab: "home",
  side: "thumbs",
  sideOpen: true,
  right: null,       // null | "props" | "ai"
  sel: null,         // selected annotation {p, id, ...}
};
const MARK_COLORS = ["#ffd84d", "#8bd17c", "#7cc3ff", "#ff9fc2", "#ffb35c", "#c7a4ff"];
const INK_COLORS = ["#e2452f", "#27407a", "#2f8f4e", "#d99a17", "#3d8fd1", "#8a4fb8", "#1b2130", "#ffffff"];

function view(id = S.active) {
  if (!id) return null;
  if (!S.views[id]) S.views[id] = { zoom: 1, fit: S.settings.zoom || "fit-width", page: 0, layout: S.settings.layout || "continuous",
    selPages: new Set(), hits: [], hitIdx: -1, query: "", pinfo: {}, annots: {}, rendered: {}, scroll: null };
  return S.views[id];
}
const doc = () => (S.active ? S.docs[S.active] : null);

/* ------------------------------------------------------------------ server */
async function api(path, body = {}) {
  const r = await fetch("/api/" + path, { method: "POST", headers: { "Content-Type": "application/json", "X-Washi": WASHI.token }, body: JSON.stringify(body) });
  let data = null;
  try { data = await r.json(); } catch (e) { /* empty */ }
  if (!r.ok) {
    const err = new Error((data && data.error) || `${r.status} ${r.statusText}`);
    err.password = data && data.password;
    err.data = data || {};
    throw err;
  }
  if (data && data.doc) updateDoc(data.doc);
  return data;
}

async function apiStream(path, body, onEvent, signal) {
  const r = await fetch("/api/" + path, { method: "POST", headers: { "Content-Type": "application/json", "X-Washi": WASHI.token }, body: JSON.stringify(body), signal });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).error || msg; } catch (e) { /* empty */ }
    throw new Error(msg);
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
  if (buf.trim()) onEvent(JSON.parse(buf));
}

async function upload(file, purpose = "open", password = "") {
  const r = await fetch("/api/upload", { method: "PUT", headers: { "X-Washi": WASHI.token, "X-Name": encodeURIComponent(file.name), "X-Purpose": purpose, "X-Password": encodeURIComponent(password) }, body: file });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || "upload failed");
  if (data.doc) updateDoc(data.doc);
  return data;
}

const pageURL = (d, p, scale, pv, fmt) => `/api/page?d=${d}&p=${p}&s=${scale}&v=${pv}${fmt ? "&f=" + fmt : ""}&t=${encodeURIComponent(WASHI.token)}`;

/* Called with every fresh server info for a document: keeps per-page caches honest. */
function updateDoc(info) {
  const old = S.docs[info.id];
  S.docs[info.id] = info;
  const v = view(info.id);
  if (old) {
    const structural = old.pages.length !== info.pages.length;
    info.pages.forEach((pg, i) => {
      const o = old.pages[i];
      if (structural || !o || o.pv !== pg.pv || o.rot !== pg.rot || o.w !== pg.w || o.h !== pg.h) {
        delete v.pinfo[i]; delete v.annots[i];
      }
    });
    if (structural) { v.pinfo = {}; v.annots = {}; v.selPages = new Set([...v.selPages].filter((p) => p < info.pages.length)); }
  }
  document.dispatchEvent(new CustomEvent("doc-changed", { detail: { id: info.id, old } }));
}

/* ------------------------------------------------------------------ toasts */
function toast(msg, opts = {}) {
  const el = document.createElement("div");
  el.className = "toast" + (opts.err ? " err" : "");
  el.innerHTML = icon(opts.err ? "info" : opts.icon || "check") + `<span>${esc(msg)}</span>`;
  if (opts.action) {
    const b = document.createElement("button");
    b.textContent = opts.action.label;
    b.onclick = () => { opts.action.fn(); kill(); };
    el.appendChild(b);
  }
  $("#toasts").appendChild(el);
  const kill = () => { el.classList.add("out"); setTimeout(() => el.remove(), 300); };
  setTimeout(kill, opts.ms || (opts.err ? 6000 : 3200));
  return el;
}
const fail = (e) => { console.error(e); toast(e.message || String(e), { err: true }); };

/* ------------------------------------------------------------------ menus */
let menuClose = null;
function showMenu(x, y, items, opts = {}) {
  closeMenu();
  const m = document.createElement("div");
  m.className = "menu" + (opts.cls ? " " + opts.cls : "");
  if (opts.node) m.appendChild(opts.node);
  for (const it of items || []) {
    if (it === "-") { m.appendChild(document.createElement("hr")); continue; }
    if (it.header) { const h = document.createElement("div"); h.className = "mh"; h.textContent = it.header; m.appendChild(h); continue; }
    const b = document.createElement("button");
    if (it.danger) b.className = "danger";
    b.innerHTML = (it.icon ? icon(it.icon) : "") + `<span>${esc(it.label)}</span>` + (it.kbd ? `<kbd>${esc(it.kbd)}</kbd>` : "") + (it.check ? icon("check") : "");
    b.onclick = () => { closeMenu(); it.action && it.action(); };
    if (it.disabled) b.disabled = true, b.style.opacity = .4;
    m.appendChild(b);
  }
  $("#menuRoot").appendChild(m);
  const r = m.getBoundingClientRect();
  m.style.left = clamp(x, 6, innerWidth - r.width - 6) + "px";
  m.style.top = (y + r.height > innerHeight - 6 ? Math.max(6, y - r.height - (opts.above || 0)) : y) + "px";
  const away = (e) => { if (!m.contains(e.target)) closeMenu(); };
  const key = (e) => { if (e.key === "Escape") closeMenu(); };
  setTimeout(() => { addEventListener("pointerdown", away, true); addEventListener("keydown", key, true); });
  menuClose = () => { removeEventListener("pointerdown", away, true); removeEventListener("keydown", key, true); m.remove(); menuClose = null; };
  return m;
}
function closeMenu() { if (menuClose) menuClose(); }
function menuAt(el, items, opts) { const r = el.getBoundingClientRect(); return showMenu(r.left, r.bottom + 4, items, { above: r.height + 8, ...opts }); }

/* ------------------------------------------------------------------ modals */
function modal({ title, icon: ic = "info", body = "", buttons = [{ label: "OK", value: true, primary: true }], wide = false, onOpen, validate }) {
  return new Promise((resolve) => {
    const back = document.createElement("div");
    back.className = "modal-back";
    back.innerHTML = `<div class="modal${wide ? " wide" : ""}" role="dialog" aria-modal="true">
      <div class="modal-head"><span class="mi">${icon(ic)}</span><h2>${esc(title)}</h2><button class="icon-btn" data-x>${icon("x")}</button></div>
      <div class="modal-body"></div><div class="modal-foot"></div></div>`;
    const bodyEl = $(".modal-body", back);
    if (typeof body === "string") bodyEl.innerHTML = body; else bodyEl.appendChild(body);
    const values = () => {
      const o = {};
      $$("[name]", bodyEl).forEach((el) => {
        if (el.type === "checkbox") o[el.name] = el.checked;
        else if (el.type === "radio") { if (el.checked) o[el.name] = el.value; }
        else if (el.type === "number" || el.type === "range") o[el.name] = el.value === "" ? null : Number(el.value);
        else o[el.name] = el.value;
      });
      return o;
    };
    const done = (v) => { back.remove(); removeEventListener("keydown", key, true); resolve(v); };
    const foot = $(".modal-foot", back);
    buttons.forEach((b) => {
      const el = document.createElement("button");
      el.className = "btn" + (b.primary ? " primary" : "") + (b.danger ? " danger" : "") + (b.ghost ? " ghost" : "");
      el.innerHTML = (b.icon ? icon(b.icon) : "") + esc(b.label);
      el.onclick = () => {
        if (b.value === null || b.value === false || b.value === undefined || b.value === "cancel") return done(b.value ?? null);
        const vals = values();
        if (validate && b.primary) { const err = validate(vals); if (err) return toast(err, { err: true }); }
        done(b.value === "form" ? vals : b.value);
      };
      foot.appendChild(el);
    });
    $("[data-x]", back).onclick = () => done(null);
    back.addEventListener("pointerdown", (e) => { if (e.target === back) done(null); });
    const key = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); done(null); }
      if (e.key === "Enter" && !e.shiftKey && e.target.tagName !== "TEXTAREA" && e.target.tagName !== "BUTTON") {
        const p = buttons.find((b) => b.primary);
        if (p) { e.preventDefault(); $$(".modal-foot .btn", back)[buttons.indexOf(p)].click(); }
      }
    };
    addEventListener("keydown", key, true);
    $("#modalRoot").appendChild(back);
    hydrateIcons(back);
    const first = $("input:not([type=hidden]):not([type=checkbox]):not([type=radio]), textarea, select", bodyEl);
    if (first) setTimeout(() => { first.focus(); first.select && first.select(); }, 30);
    onOpen && onOpen(bodyEl, back);
  });
}
const confirmBox = (title, text, ok = "OK", danger = false) =>
  modal({ title, icon: danger ? "trash" : "info", body: `<p>${esc(text)}</p>`, buttons: [{ label: "Cancel", value: null, ghost: true }, { label: ok, value: true, primary: !danger, danger }] });
async function promptBox(title, label, value = "", opts = {}) {
  const r = await modal({ title, icon: opts.icon || "pencil", body: `<div class="fld"><label>${esc(label)}</label><input name="v" type="${opts.type || "text"}" value="${esc(value)}" ${opts.placeholder ? `placeholder="${esc(opts.placeholder)}"` : ""}></div>${opts.note ? `<p class="note muted">${esc(opts.note)}</p>` : ""}`,
    buttons: [{ label: "Cancel", value: null, ghost: true }, { label: opts.ok || "OK", value: "form", primary: true }] });
  return r ? r.v : null;
}

/* ------------------------------------------------------------------ commands */
const CMD = {};
function cmd(id, def) { CMD[id] = { id, ...def }; }
async function run(id, ...args) {
  const c = CMD[id];
  if (!c) return console.warn("no command", id);
  if (c.needsDoc && !doc()) return toast("Open a PDF first");
  if (c.enabled && !c.enabled()) return;   // e.g. Ctrl+Z with nothing to undo: quietly nothing
  try { await c.run(...args); } catch (e) { fail(e); }
}
function enabled(id) { const c = CMD[id]; if (!c) return false; if (c.needsDoc && !doc()) return false; return c.enabled ? c.enabled() : true; }
function kbdLabel(k) { return k ? k.replace("Mod", "Ctrl").replace(/\+/g, " ") : ""; }

/* Point at a control on screen ("show me" in help and AI answers). */
function spotlight(id) {
  const c = CMD[id];
  if (c && c.tab && $("#ribbon") && !$("#ribbon").classList.contains("hidden")) setRibbonTab(c.tab);
  setTimeout(() => {
    const el = $(`[data-cmd="${id}"]:not(.hidden)`);
    if (el) { el.scrollIntoView({ block: "nearest", inline: "nearest" }); el.classList.remove("spot"); void el.offsetWidth; el.classList.add("spot"); setTimeout(() => el.classList.remove("spot"), 3400); }
  }, 60);
}

/* tiny markdown for AI answers (escaped first) */
function md(text) {
  const lines = esc(text).split("\n");
  let out = "", list = null;
  const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*(?!\s)(.+?)\*/g, "$1<i>$2</i>").replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\((?:p\.|page|pages|str\.|strana)\s*(\d+)(?:\s*[-–]\s*(\d+))?\)/gi, (m, a) => `<span class="pg" data-page="${a}">${m}</span>`)
    .replace(/\[(?:p\.|page)\s*(\d+)\]/gi, (m, a) => `<span class="pg" data-page="${a}">${m}</span>`);
  const flush = () => { if (list) { out += `</${list}>`; list = null; } };
  for (const raw of lines) {
    const l = raw.trimEnd();
    let m;
    if ((m = l.match(/^\s*#{1,4}\s+(.*)/))) { flush(); out += `<h3>${inline(m[1])}</h3>`; }
    else if ((m = l.match(/^\s*[-*•]\s+(.*)/))) { if (list !== "ul") { flush(); out += "<ul>"; list = "ul"; } out += `<li>${inline(m[1])}</li>`; }
    else if ((m = l.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== "ol") { flush(); out += "<ol>"; list = "ol"; } out += `<li>${inline(m[1])}</li>`; }
    else if (!l.trim()) { flush(); }
    else { flush(); out += `<p>${inline(l)}</p>`; }
  }
  flush();
  return out;
}

function fmtBytes(n) {
  if (n == null) return "";
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(0) + " KB";
  return (n / 1048576).toFixed(1).replace(/\.0$/, "") + " MB";
}
function pdfDate(s) {
  const m = /D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?/.exec(s || "");
  if (!m) return s || "";
  return `${m[3] || "01"}.${m[2] || "01"}.${m[1]}${m[4] ? ` ${m[4]}:${m[5] || "00"}` : ""}`;
}
