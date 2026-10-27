"use strict";
const T = window.MORPH_TOKEN;
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
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
}
const svg = (d, cls = "i") => h("span", { html: `<svg class="${cls}" viewBox="0 0 24 24">${d}</svg>`, style: { display: "contents" } });
const I = {
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  check: '<path class="draw" d="M5 12.5l4.5 4.5L19 7.5"/>',
  spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7z" fill="currentColor" stroke="none"/>',
  chev: '<path d="M6 9l6 6 6-6"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  open: '<path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
  retry: '<path d="M4 12a8 8 0 0 1 14-5.3L20 9M20 4v5h-5M20 12a8 8 0 0 1-14 5.3L4 15M4 20v-5h5"/>',
  send: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  merge: '<path d="M7 4v5a5 5 0 0 0 5 5h0a5 5 0 0 1 5 5v1M17 4v5a5 5 0 0 1-3 4.6M4 7l3-3 3 3"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  warn: '<path d="M12 8v5M12 16.5v.5M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
};
const CATS = {
  video: "Video", audio: "Audio", image: "Image", document: "Document", ebook: "E-book", presentation: "Presentation",
  spreadsheet: "Spreadsheet", data: "Data", archive: "Archive", font: "Font", subtitle: "Subtitles",
};
const cc = (cat) => `var(--c-${cat || "archive"})`;
const LOSSLESS = new Set(["flac", "wav", "aiff", "alac", "bmp", "tga", "ppm", "tiff", "ico", "icns", "png", "svg"]);
const VIDEO_T = new Set(["mp4", "hevc", "av1", "webm", "mkv", "mov", "m4v", "avi", "wmv", "flv", "mpeg", "ts", "3gp", "ogv"]);
const AUDIO_T = new Set(["mp3", "m4a", "aac", "alac", "flac", "wav", "aiff", "ogg", "opus", "wma", "ac3"]);
const IMAGE_T = new Set(["png", "jpg", "webp", "avif", "heic", "gif", "bmp", "tiff", "ico", "icns", "tga", "jp2", "ppm"]);
const QUAL = [["original", "Original"], ["high", "High"], ["balanced", "Balanced"], ["small", "Small"]];

const S = { settings: {}, engines: {}, models: [], llm: "offline", files: new Map(), jobs: new Map(), aiQueue: [], aiBusy: null };

// ------------------------------------------------------------------ server
async function api(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "X-Morph": T, "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
async function* stream(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "X-Morph": T, "Content-Type": "application/json" }, body: JSON.stringify(body) });
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
  setTimeout(() => t.remove(), 3300);
}
const fmtSize = (n) => { const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return (i ? n.toFixed(1) : n) + " " + u[i]; };
const fmtSecs = (s) => s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const short = (name) => { const m = name.match(/^(.*?)\s*\((.+)\)$/); return m ? [m[1], m[2]] : [name, ""]; };

// ------------------------------------------------------------------ adding files
function upload(file) {
  const ph = placeholder(file.name);
  return new Promise((resolve) => {
    const x = new XMLHttpRequest();
    x.open("PUT", "/api/upload");
    x.setRequestHeader("X-Morph", T);
    x.setRequestHeader("X-Name", encodeURIComponent(file.name));
    x.upload.onprogress = (e) => { if (e.lengthComputable) ph.progress(e.loaded / e.total); };
    x.onload = () => {
      ph.remove();
      try {
        const d = JSON.parse(x.responseText);
        if (d.error) throw new Error(d.error);
        addFile(d);
      } catch (e) { toast(`${file.name}: ${e.message}`); }
      resolve();
    };
    x.onerror = () => { ph.remove(); toast(`Upload failed: ${file.name}`); resolve(); };
    x.send(file);
  });
}
function placeholder(name) {
  compactDrop();
  const bar = h("div", { class: "bar" });
  const pct = h("span", { class: "pct" }, "0%");
  const el = h("div", { class: "card" },
    h("div", { class: "top" },
      h("div", { class: "thumb", "--c": "var(--a1)" }, h("div", { class: "state", style: { border: 0, background: "none" } }, h("div", { class: "spin" }))),
      h("div", { class: "meta" }, h("div", { class: "name" }, name), h("div", { class: "sub" }, "Reading file… ", pct))),
    h("div", { class: "job", style: { marginTop: "14px", padding: "0", height: "3px", border: 0 } }, bar));
  $("#files").prepend(el);
  return {
    progress(f) { bar.style.width = (f * 100).toFixed(1) + "%"; pct.textContent = Math.round(f * 100) + "%"; },
    remove() { el.remove(); },
  };
}
async function addFiles(fileList) {
  const files = [...fileList];
  for (const f of files) await upload(f);
}
async function browse() {
  try {
    const list = await api("/api/pick");
    list.forEach((d, i) => addFile(d, i));
  } catch (e) {
    $("#fileInput").click();
  }
}

// ------------------------------------------------------------------ cards
function compactDrop() {
  const d = $("#drop");
  if (d.classList.contains("compact")) return;
  d.classList.add("compact");
  $("#dropTitle").textContent = "Add more files";
  $("#dropText").innerHTML = "Drop them anywhere, paste with <kbd>Ctrl</kbd>+<kbd>V</kbd> or";
}
function expandDrop() {
  const d = $("#drop");
  d.classList.remove("compact");
  $("#dropTitle").textContent = "Drop anything here";
  $("#dropText").textContent = "Video, music, pictures, documents, e-books, spreadsheets, data, archives, fonts and subtitles — 100+ formats, converted right on this PC.";
}

function addFile(d, n = 0, restored = false) {
  compactDrop();
  const F = {
    d, sel: null, showAll: false, jobs: [],
    opts: { quality: S.settings.quality || "balanced", max_h: 0, max_px: 0, strip: false, start: "", end: "", pages: "" },
    ai: { status: "idle", text: "", picks: [], history: [], open: true, tries: 0 },
  };
  S.files.set(d.id, F);
  buildCard(F, n);
  if (!d.error && !restored && aiOn() && S.settings.auto_advise) advise(F);
  updateBatch();
}

function buildCard(F, n) {
  const d = F.d;
  const thumb = h("div", { class: `thumb ${d.cat || ""}`, "--c": cc(d.cat) },
    h("b", {}, (d.name.split(".").pop() || "?").slice(0, 5)),
    d.cat ? h("span", { class: "cat" }, CATS[d.cat]) : null);
  if (["image", "video", "audio"].includes(d.cat) || ["pdf", "epub", "xps", "mobi", "fb2", "cbz"].includes(d.fid)) {
    const img = h("img", { alt: "", src: `/api/thumb/${d.id}?t=${encodeURIComponent(T)}` });
    img.onload = () => { img.classList.add("ready"); thumb.querySelector("b").style.opacity = 0; };
    img.onerror = () => img.remove();
    thumb.append(img);
  }
  const facts = h("div", { class: "facts" }, (d.facts || []).map((f, i) => h("span", { "--n": i }, f)));
  F.el = h("div", { class: "card", "--n": n },
    h("button", { class: "iconbtn x", title: "Remove", onclick: () => removeFile(F) }, svg(I.x)),
    h("div", { class: "top" }, thumb,
      h("div", { class: "meta" },
        h("div", { class: "name", title: d.name }, d.name),
        h("div", { class: "sub" }, [d.fmt || "Unknown format", d.size_h].filter(Boolean).join(" · ")),
        facts)));
  if (d.error) {
    const err = h("div", { class: "error" }, d.error);
    if (/LibreOffice/.test(d.error)) err.append(h("button", { class: "btn small", onclick: installLO }, "Install LibreOffice"));
    F.el.append(err);
  } else {
    F.targetsEl = h("div");
    F.optsEl = h("div", { class: "opts" }, h("div"));
    F.aiEl = h("div");
    F.jobsEl = h("div", { class: "jobs" });
    F.el.append(F.targetsEl, F.optsEl, F.jobsEl, F.aiEl);
    renderTargets(F);
    renderAI(F);
  }
  $("#files").prepend(F.el);
}

function removeFile(F) {
  F.el.classList.add("leaving");
  setTimeout(() => {
    F.el.remove();
    if (!S.files.size) expandDrop();
  }, 380);
  S.files.delete(F.d.id);
  S.aiQueue = S.aiQueue.filter((x) => x !== F);
  api("/api/remove", { id: F.d.id }).catch(() => {});
  updateBatch();
}

// ------------------------------------------------------------------ targets
function chip(F, t, i, extra = "") {
  const [main, sub] = short(t.name);
  const isAI = F.ai.picks.includes(t.id);
  const c = h("button", {
    class: `chip ${extra} ${isAI ? "aipick" : ""} ${F.sel === t.id ? "sel" : ""}`, "--n": i, "--c": cc(t.cat), "data-id": t.id,
    onclick: () => select(F, t.id),
    onmouseenter: (e) => showTip(e.currentTarget, t), onmouseleave: hideTip,
  }, isAI ? svg(I.spark, "i spark") : null, t.compress ? "Compress" : main, sub && !t.compress ? h("small", {}, sub) : null);
  return c;
}
function renderTargets(F) {
  hideTip();
  const d = F.d, ts = d.targets;
  const byId = Object.fromEntries(ts.map((t) => [t.id, t]));
  const rec = [...F.ai.picks, ...d.picks].filter((id, i, a) => byId[id] && a.indexOf(id) === i).slice(0, 4);
  const comp = ts.find((t) => t.compress);
  const top = rec.map((id, i) => chip(F, byId[id], i, "pick"));
  if (comp) top.push(chip(F, comp, top.length));
  const groups = {};
  for (const t of ts) if (!t.compress) (groups[t.cat] = groups[t.cat] || []).push(t);
  const allInner = h("div", {}, Object.entries(groups).map(([cat, list]) =>
    h("div", { class: "group", "--c": cc(cat) }, h("h4", {}, CATS[cat]), h("div", { class: "chips" }, list.map((t, i) => chip(F, t, i))))));
  const all = h("div", { class: "all" + (F.showAll ? " open" : "") }, allInner);
  const more = h("button", { class: "more" + (F.showAll ? " open" : ""), onclick: () => {
    F.showAll = !F.showAll; all.classList.toggle("open", F.showAll); more.classList.toggle("open", F.showAll);
    more.firstChild.textContent = F.showAll ? "Fewer" : `All ${ts.length} formats`;
  } }, h("span", {}, F.showAll ? "Fewer" : `All ${ts.length} formats`), svg(I.chev));
  F.targetsEl.replaceChildren(
    h("div", { class: "label" }, "Convert to"),
    h("div", { class: "chips" }, top, more), all);
  F.targetsEl.classList.toggle("still", !!F.targetsShown);  // later redraws (AI picks) skip the entrance animation
  F.targetsShown = true;
}
function select(F, id) {
  F.sel = F.sel === id ? null : id;
  $$(".chip", F.targetsEl).forEach((c) => c.classList.toggle("sel", c.dataset.id === F.sel));
  renderOpts(F);
}

// ------------------------------------------------------------------ options
function seg(options, value, onchange) {
  const el = h("div", { class: "seg" });
  const knob = h("div", { class: "knob" });
  el.append(knob);
  const btns = options.map(([v, label]) => h("button", { class: v === value ? "on" : "", onclick: () => {
    btns.forEach((b) => b.classList.remove("on")); b(v).classList.add("on"); move(); onchange(v);
  } }, label));
  const b = (v) => btns[options.findIndex((o) => o[0] === v)];
  function move() {
    const on = el.querySelector("button.on");
    if (!on) return;
    knob.style.left = on.offsetLeft + "px"; knob.style.width = on.offsetWidth + "px";
  }
  el.append(...btns);
  requestAnimationFrame(() => requestAnimationFrame(move));
  return el;
}
function opt(label, control) { return h("div", { class: "opt" }, h("span", {}, label), control); }
function renderOpts(F) {
  const wrap = F.optsEl;
  if (!F.sel) { wrap.classList.remove("open"); return; }
  const d = F.d, t = d.targets.find((x) => x.id === F.sel), o = F.opts, cat = d.cat, sel = F.sel;
  const row = h("div", { class: "optrow" });
  const media = cat === "video" || cat === "audio" || (d.fid === "gif" && VIDEO_T.has(sel));
  const toImage = IMAGE_T.has(sel);
  const quality = (media && !LOSSLESS.has(sel)) || (cat === "image" && (!LOSSLESS.has(sel) || t.compress)) ||
    (d.fid === "pdf" && (sel === "pdf" || toImage)) || (cat === "video" && (sel === "gif" || sel === "webp"));
  if (quality) {
    const q = cat === "video" && VIDEO_T.has(sel) ? QUAL : QUAL.map(([v, l]) => [v, v === "original" ? "Best" : l]);
    row.append(opt("Quality", seg(q, o.quality, (v) => (o.quality = v))));
  }
  if (cat === "video" && (VIDEO_T.has(sel) || sel === "gif" || sel === "webp")) {
    row.append(opt("Resolution", seg([[0, "Keep"], [2160, "4K"], [1080, "1080p"], [720, "720p"], [480, "480p"]], o.max_h, (v) => (o.max_h = v))));
  }
  if (media) {
    const start = h("input", { class: "field", placeholder: "0:00", value: o.start, oninput: (e) => (o.start = e.target.value) });
    const end = h("input", { class: "field", placeholder: "end", value: o.end, oninput: (e) => (o.end = e.target.value) });
    row.append(opt("Trim", h("div", { style: { display: "flex", gap: "6px", alignItems: "center" } }, start, "–", end)));
  }
  if (cat === "image" && (toImage || sel === "pdf")) {
    row.append(opt("Max size", seg([[0, "Keep"], [4096, "4096"], [2048, "2048"], [1024, "1024"], [512, "512"]], o.max_px, (v) => (o.max_px = v))));
    if (sel !== "pdf") {
      const tg = h("button", { class: "toggle" + (o.strip ? " on" : ""), onclick: () => { o.strip = !o.strip; tg.classList.toggle("on", o.strip); } });
      row.append(opt("Metadata", h("label", { class: "check" }, tg, "Strip EXIF/GPS")));
    }
  }
  if (d.fid === "pdf" && sel !== "pdf" && d.info.pages > 1) {
    row.append(opt("Pages", h("input", { class: "field", style: { width: "120px" }, placeholder: `all ${d.info.pages}`, value: o.pages, oninput: (e) => (o.pages = e.target.value) })));
  }
  const btn = h("button", { class: "btn primary", onclick: () => convert(F, sel) }, t.compress ? `Make a smaller ${short(t.name)[0]}` : `Convert to ${t.name}`, svg(I.arrow));
  row.append(h("div", { class: "go" }, btn));
  if (t.note) row.append(h("div", { style: { flexBasis: "100%", fontSize: "12px", color: "var(--muted)" } }, t.note));
  wrap.firstChild.replaceChildren(row);
  wrap.classList.add("open");
}

// ------------------------------------------------------------------ jobs
async function convert(F, target, opts) {
  try {
    const o = { ...(opts || F.opts) };
    if (!o.max_h) delete o.max_h;
    if (!o.max_px) delete o.max_px;
    const job = await api("/api/convert", { id: F.d.id, target, opts: o });
    addJob(F, job);
  } catch (e) { toast(e.message); }
}
function addJob(F, job) {
  const row = h("div", { class: "job" },
    h("div", { class: "glow" }),
    h("div", { class: "state" }, h("div", { class: "spin" })),
    h("div", { class: "info" }, h("div", { class: "t" }, job.label), h("div", { class: "s" }, job.stage)),
    h("span", { class: "pct" }),
    h("div", { class: "acts" }),
    h("div", { class: "bar" }));
  (F ? F.jobsEl : $("#files")).prepend(row);
  S.jobs.set(job.id, { job, row, F });
  updateJob(job);
  poll();
}
function updateJob(job) {
  const J = S.jobs.get(job.id);
  if (!J) return;
  const prev = J.job.status;
  J.job = job;
  const r = J.row;
  const bar = $(".bar", r), pct = $(".pct", r), s = $(".s", r), acts = $(".acts", r), st = $(".state", r);
  r.className = "job " + job.status;
  if (job.status === "running" || job.status === "queued") {
    const indef = job.progress == null;
    bar.classList.toggle("indef", indef);
    if (!indef) bar.style.width = (job.progress * 100).toFixed(1) + "%";
    pct.textContent = indef ? "" : Math.round(job.progress * 100) + "%";
    s.textContent = job.status === "queued" ? "Waiting for a free slot" : job.stage;
    if (!acts.dataset.k) {
      acts.dataset.k = "run";
      acts.replaceChildren(h("button", { class: "iconbtn", title: "Cancel", onclick: () => api("/api/cancel", { id: job.id }) }, svg(I.x)));
    }
    return;
  }
  if (prev === job.status && acts.dataset.k === job.status) return;
  acts.dataset.k = job.status;
  pct.textContent = "";
  if (job.status === "done") {
    st.replaceChildren(svg(I.check));
    $(".t", r).textContent = job.out_name;
    const delta = job.in_size ? (job.out_size - job.in_size) / job.in_size : 0;
    const took = job.t1 && job.t0 ? ` · ${fmtSecs(job.t1 - job.t0)}` : "";
    s.replaceChildren(`${fmtSize(job.in_size || 0)} → ${job.out_size_h} `,
      Math.abs(delta) >= 0.01 ? h("span", { class: "delta " + (delta < 0 ? "down" : "up") }, `${delta < 0 ? "−" : "+"}${Math.abs(delta * 100).toFixed(0)}%`) : "", took);
    acts.replaceChildren(
      h("button", { class: "btn small ghost", onclick: () => api("/api/open", { id: job.id }).catch((e) => toast(e.message)) }, svg(I.open), "Open"),
      h("button", { class: "btn small ghost", onclick: () => api("/api/reveal", { id: job.id }).catch((e) => toast(e.message)) }, svg(I.folder), "Show"));
  } else if (job.status === "error") {
    st.replaceChildren(svg(I.x));
    s.textContent = job.error || "Failed";
    if (J.F?.d) acts.replaceChildren(h("button", { class: "iconbtn", title: "Try again", onclick: () => { r.remove(); convert(J.F, job.target); } }, svg(I.retry)));
  } else if (job.status === "cancelled") {
    st.replaceChildren(svg(I.x));
    s.textContent = "Cancelled";
    acts.replaceChildren(h("button", { class: "iconbtn", title: "Dismiss", onclick: () => r.remove() }, svg(I.x)));
  }
}
let polling = false;
async function poll() {
  if (polling) return;
  polling = true;
  try {
    for (;;) {
      const list = await api("/api/jobs");
      let active = false;
      for (const j of list) {
        if (S.jobs.has(j.id)) updateJob(j);
        if (j.status === "running" || j.status === "queued") active = true;
      }
      if (!active) break;
      await new Promise((r) => setTimeout(r, 350));
    }
  } catch (e) { /* server gone */ }
  polling = false;
}

// ------------------------------------------------------------------ AI advisor
// The panel is built once per file and then updated in place. Rebuilding it on every streamed word
// replayed the fade-in of every line, which made the advice flash and jump while the AI was typing.
function buildAI(F) {
  const a = F.ai;
  const P = {};
  P.input = h("input", { placeholder: "Ask: smallest for WhatsApp? best for editing? …", onkeydown: (e) => {
    if (e.key === "Enter" && P.input.value.trim()) { advise(F, P.input.value.trim()); P.input.value = ""; }
  } });
  P.body = h("div", { class: "body", onclick: (e) => {
    const b = e.target.closest("b.fl");
    if (!b) return;
    select(F, b.dataset.id);
    F.el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } });
  P.st = h("span", { class: "st" });
  P.send = h("button", { class: "btn small", onclick: () => { const q = P.input.value.trim(); advise(F, q || null); P.input.value = ""; } });
  P.el = h("div", { class: "ai" + (a.open ? "" : " closed") },
    h("div", { class: "head", onclick: () => {
      a.open = !a.open; P.el.classList.toggle("closed", !a.open);
      if (a.open && a.status === "idle" && !a.text) advise(F);
    } }, svg(I.spark, "i spark"), "AI advice", P.st),
    h("div", { class: "bodywrap" }, h("div", {}, P.body, h("div", { class: "ask" }, P.input, P.send))));
  F.aiEl.replaceChildren(P.el);
  F.aiParts = P;
  return P;
}
function renderAI(F) {
  if (!aiOn()) { F.aiEl.replaceChildren(); F.aiParts = null; return; }
  const a = F.ai;
  const P = F.aiParts && F.aiEl.contains(F.aiParts.el) ? F.aiParts : buildAI(F);
  const status = { idle: "Ask for advice", wait: "Warming up the NPU…", queued: "Next in line…", busy: "Thinking on the NPU…", done: "", error: "Unavailable" }[a.status];
  const busy = ["busy", "wait", "queued"].includes(a.status);
  P.el.classList.toggle("closed", !a.open);
  P.st.replaceChildren(...[busy ? h("span", { class: "dot busy" }) : null, status, svg(I.chev, "i chev")].filter(Boolean));
  P.send.disabled = busy;
  const sendLabel = a.text || a.status !== "idle" ? "send" : "advise";
  if (P.send.dataset.k !== sendLabel) {
    P.send.dataset.k = sendLabel;
    P.send.replaceChildren(sendLabel === "send" ? svg(I.send) : "Advise me");
  }
  let html;
  if (a.status === "idle" && !a.text) html = '<p class="muted">Not sure which format fits? The local AI compares the options for this exact file.</p>';
  else {
    html = md(a.text, F);
    if (busy && !a.text) html += '<p><span class="thinking"><i></i><i></i><i></i></span></p>';
    if (a.status === "error") html += `<p class="muted">${esc(a.error || "The AI is not available right now.")}</p>`;
  }
  patchHTML(P.body, html, a.status === "busy" && a.text);
}
// Update `el` to match `html`, touching only what changed, so lines already shown keep their place
// and only genuinely new lines play the fade-in.
function patchHTML(el, html, caret) {
  const next = document.createElement("div");
  next.innerHTML = html;
  if (caret) {
    let last = next.lastElementChild;   // the caret sits at the end of the last line, not on a line of its own
    if (last && last.tagName === "UL") last = last.lastElementChild;
    (last || next).append(h("span", { class: "caret" }));
  }
  patchChildren(el, next);
}
function patchChildren(cur, next) {
  const a = [...cur.childNodes], b = [...next.childNodes];
  b.forEach((nb, i) => {
    const ca = a[i];
    if (!ca) return cur.append(nb);
    if (ca.nodeType !== nb.nodeType || ca.nodeName !== nb.nodeName || (ca.nodeType === 1 && ca.className !== nb.className)) return cur.replaceChild(nb, ca);
    if (ca.nodeType === 3) { if (ca.nodeValue !== nb.nodeValue) ca.nodeValue = nb.nodeValue; return; }
    if (ca.isEqualNode(nb)) return;
    for (const at of [...ca.attributes]) if (!nb.hasAttribute(at.name)) ca.removeAttribute(at.name);
    for (const at of [...nb.attributes]) if (ca.getAttribute(at.name) !== at.value) ca.setAttribute(at.name, at.value);
    patchChildren(ca, nb);
  });
  for (let i = b.length; i < a.length; i++) a[i].remove();
}
function md(text, F) {
  const names = {};
  for (const t of F.d.targets) {
    names[t.name.toLowerCase()] = t.id; names[t.id] = t.id;
    const s = short(t.name)[0].toLowerCase();
    if (!(s in names)) names[s] = t.id;
  }
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, (_, x) => {
    const id = names[x.toLowerCase().trim()] || names[x.toLowerCase().replace(/\(.*?\)/g, "").trim()];
    const t = id && F.d.targets.find((y) => y.id === id);
    const label = t ? (t.compress ? `Smaller ${short(t.name)[0]}` : t.name) : x;
    return id ? `<b class="fl" data-id="${id}">${esc(label)}</b>` : `<b>${x}</b>`;
  });
  let out = "", inList = false;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || /^([-*•]|\d+[.)])$/.test(line)) continue;  // a bullet still arriving - don't flash it as a paragraph
    const m = line.match(/^(?:[-*•]|\d+[.)])\s+(.*)/);
    if (m) { if (!inList) { out += "<ul>"; inList = true; } out += `<li>${inline(m[1])}</li>`; }
    else if (line.startsWith("Q: ")) { if (inList) { out += "</ul>"; inList = false; } out += `<div class="q">${esc(line.slice(3))}</div>`; }
    else { if (inList) { out += "</ul>"; inList = false; } out += `<p>${inline(line)}</p>`; }
  }
  return out + (inList ? "</ul>" : "");
}
function advise(F, q) {
  if (!aiOn() || F.d.error) return;
  F.ai.open = true;
  F.ai.pendingQ = q || null;
  if (!S.aiQueue.includes(F) && S.aiBusy !== F) S.aiQueue.push(F);
  if (F.ai.status !== "busy") { F.ai.status = S.llm === "online" ? "queued" : "wait"; renderAI(F); }
  runAI();
}
async function runAI() {
  if (S.aiBusy || !S.aiQueue.length) return;
  const F = S.aiQueue.shift();
  if (!S.files.has(F.d.id)) return runAI();
  S.aiBusy = F;
  const a = F.ai, q = a.pendingQ, prevText = a.text;
  a.pendingQ = null;
  a.status = "busy";
  const base = a.text ? a.text + "\n" + (q ? `Q: ${q}\n` : "") : (q ? `Q: ${q}\n` : "");
  let got = "", retry = false;
  renderAI(F);
  setAIDot();
  try {
    for await (const ev of stream("/api/advise", { id: F.d.id, q, history: a.history })) {
      if (ev.type === "wait") { retry = true; break; }
      if (ev.type === "error") throw new Error(ev.text);
      if (ev.type === "text") { got += ev.data; a.text = base + got; renderAIText(F); }
      if (ev.type === "best") {
        a.picks = ev.data || [];
        renderTargets(F);
        if (F.sel) $$(".chip", F.targetsEl).forEach((c) => c.classList.toggle("sel", c.dataset.id === F.sel));
      }
    }
    if (retry) {
      a.status = "wait"; a.tries++;
      if (a.tries < 60) { a.pendingQ = q; setTimeout(() => { S.aiQueue.unshift(F); runAI(); }, 3000); }
      else { a.status = "error"; a.error = "The AI model did not load. Check FastFlowLM."; }
    } else if (!got.trim()) {
      a.empty = (a.empty || 0) + 1;
      if (a.empty <= 2) { a.status = "queued"; a.pendingQ = q; S.aiQueue.unshift(F); }
      else { a.status = "error"; a.error = "The model gave an empty answer — ask again."; }
    } else {
      a.status = "done"; a.tries = 0; a.empty = 0;
      a.history.push({ role: "user", content: q || "Which formats should I use?" }, { role: "assistant", content: got });
    }
  } catch (e) {
    if (/FastFlowLM/.test(e.message) && a.tries < 60) {  // the AI server went away - wait for it to come back
      a.status = "wait"; a.tries++; a.pendingQ = q;
      a.text = prevText;  // drop the half-finished answer; it is asked again
      setTimeout(() => { S.aiQueue.unshift(F); runAI(); }, 3000);
    } else { a.status = "error"; a.error = e.message; }
  }
  S.aiBusy = null;
  renderAI(F);
  setAIDot();
  runAI();
}
function renderAIText(F) {
  if (!F.aiParts) return renderAI(F);
  patchHTML(F.aiParts.body, md(F.ai.text, F), true);
}

// ------------------------------------------------------------------ batch bar
function updateBatch() {
  $(".batch")?.remove();
  const live = [...S.files.values()].filter((F) => !F.d.error);
  if (live.length < 2) return;
  let common = null;
  for (const F of live) {
    const ids = new Set(F.d.targets.filter((t) => !t.compress).map((t) => t.id));
    common = common ? new Set([...common].filter((x) => ids.has(x))) : ids;
  }
  const first = live[0].d.targets;
  const sameKind = live.every((F) => F.d.cat === live[0].d.cat);
  const list = sameKind ? first.filter((t) => common.has(t.id) && !t.compress).slice(0, 10) : [];
  const mergeable = live.every((F) => F.d.cat === "image" || ["pdf", "svg", "epub", "xps"].includes(F.d.fid));
  const bar = h("div", { class: "batch" },
    h("span", { class: "lbl" }, `${live.length} files`),
    list.length ? h("span", { class: "lbl" }, "· all to") : null,
    h("div", { class: "chips" }, list.map((t, i) => h("button", { class: "chip", "--n": i, "--c": cc(t.cat), onclick: () => {
      live.forEach((F) => convert(F, t.id, { ...F.opts, quality: S.settings.quality }));
      toast(`Converting ${live.length} files to ${short(t.name)[0]}`);
    }, onmouseenter: (e) => showTip(e.currentTarget, t), onmouseleave: hideTip }, short(t.name)[0]))),
    mergeable ? h("button", { class: "btn small primary", onclick: mergeAll, title: "Combine into one PDF in the order shown (top first)" }, svg(I.merge), "Merge to PDF") : null,
    h("button", { class: "btn small ghost", onclick: () => [...S.files.values()].forEach(removeFile) }, "Clear"));
  document.body.append(bar);
}
async function mergeAll() {
  const ids = $$(".card", $("#files")).map((el) => [...S.files.values()].find((F) => F.el === el)).filter(Boolean).map((F) => F.d.id);
  try {
    const job = await api("/api/merge", { ids });
    const holder = h("div", { class: "jobs" });
    $("#files").prepend(holder);
    addJob({ jobsEl: holder }, job);
  } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ tooltip
const tip = $("#tip");
function showTip(el, t) {
  tip.replaceChildren(...[h("h5", {}, t.compress ? `Compress (${t.name})` : t.name), h("div", { class: "up" }, t.up), h("div", { class: "down" }, t.down),
    t.note ? h("div", { class: "note" }, t.note) : null].filter(Boolean));
  const r = el.getBoundingClientRect();
  tip.classList.add("on");
  const w = tip.offsetWidth, th = tip.offsetHeight;
  let x = Math.min(Math.max(10, r.left + r.width / 2 - w / 2), innerWidth - w - 10);
  let y = r.top - th - 10;
  if (y < 70) y = r.bottom + 10;
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
function hideTip() { tip.classList.remove("on"); }

// ------------------------------------------------------------------ settings, formats, status
// The AI advisor is on only where it can run: Ryzen AI NPU + FastFlowLM + the model, and switched on in Settings.
// Everywhere else (Intel PCs, older AMD) Morph is a converter with built-in format suggestions.
const aiOn = () => !!(S.settings.ai && S.ai?.ready);
async function refreshState() {
  try {
    const s = await api("/api/state");
    const wasOn = S.settings.ai === undefined ? undefined : aiOn();
    S.settings = s.settings; S.engines = s.engines; S.llm = s.llm; S.ai = s.ai; S.version = s.version;
    if (s.models?.length) S.models = s.models;
    setAIDot(s);
    if (wasOn !== undefined && wasOn !== aiOn()) S.files.forEach(renderAI);
  } catch (e) { /* closed */ }
}
function setAIDot(s) {
  const dot = $("#aiDot"), txt = $("#aiText");
  const st = S.llm, model = S.settings.model || "";
  dot.className = "dot";
  $("#aiPill").title = S.ai?.supported === false ? `Converter-only mode: ${S.ai.reason}` : "Format advisor running on the Ryzen AI NPU";
  if (S.ai && !S.ai.checked) { txt.textContent = "Checking for AI…"; return; }
  if (S.ai?.supported === false) { txt.textContent = "Converter mode"; return; }
  if (S.ai?.busy) { dot.classList.add("starting"); txt.textContent = "Setting up AI…"; return; }
  if (S.ai && !S.ai.ready) { txt.textContent = "AI not set up"; return; }
  if (!S.settings.ai) { txt.textContent = "AI off"; return; }
  if (S.aiBusy) { dot.classList.add("busy"); txt.textContent = "Thinking…"; return; }
  if (st === "online") { dot.classList.add("online"); txt.textContent = `AI ready · ${model}`; }
  else if (st === "starting") { dot.classList.add("starting"); txt.textContent = "Loading AI…"; }
  else if (st === "missing") txt.textContent = "FastFlowLM not found";
  else txt.textContent = "AI offline";
}
function openPanel(el) { $("#scrim").classList.add("on"); el.classList.add("on"); }
function closePanels() { $("#scrim").classList.remove("on"); $$(".drawer.on, .modal.on").forEach((e) => e.classList.remove("on")); }
async function openSettings() {
  await refreshState();
  const s = S.settings;
  $$("[data-set]").forEach((el) => {
    const k = el.dataset.set;
    if (el.classList.contains("toggle")) {
      el.classList.toggle("on", !!s[k]);
      el.onclick = async () => {
        S.settings = await api("/api/settings", { [k]: !s[k] });
        openSettings();
        if (k === "ai") { S.files.forEach(renderAI); setAIDot(); }
      };
    }
  });
  $("#qualSeg").replaceChildren(seg(QUAL, s.quality, async (v) => {
    S.settings = await api("/api/settings", { quality: v });
    S.files.forEach((F) => (F.opts.quality = v));
  }));
  $("#outDir").textContent = s.output_dir;
  $("#outDir").title = s.output_dir;
  renderEnabler(await api("/api/ai/status"));
  const sel = $("#model");
  const models = S.models.length ? S.models : [s.model];
  sel.replaceChildren(...models.map((m) => h("option", { value: m, selected: m === s.model }, m)));
  sel.onchange = async () => { S.settings = await api("/api/settings", { model: sel.value }); toast(`Switching to ${sel.value}`); };
  const e = S.engines;
  const rows = [["ffmpeg", "ffmpeg — audio & video"], ["pandoc", "pandoc — documents"], ["pymupdf", "PyMuPDF — PDF & e-books"],
    ["edge", "Microsoft Edge — HTML → PDF"], ["heif", "HEIC/HEIF pictures"], ["raw", "Camera RAW"], ["libreoffice", "LibreOffice — exact Office layouts, DOC/PPT/XLS"], ["7zip", "7-Zip — RAR archives"]];
  $("#engines").replaceChildren(...rows.map(([k, label]) => h("div", { class: "eng" },
    h("span", { class: e[k] ? "ok" : "no" }, e[k] ? "●" : "○"), label,
    !e[k] && k === "libreoffice" ? h("button", { class: "btn small", style: { marginLeft: "auto" }, onclick: installLO }, "Install") : null)));
  openPanel($("#settings"));
}
// ------------------------------------------------------------------ Ryzen AI NPU enabler
let enablerTimer = null;
function renderEnabler(st) {
  const card = $("#aiCard");
  const rows = $("#aiRows");
  rows.style.display = st.ready ? "" : "none";
  const step = (done, label, note, action) => h("div", { class: "estep" + (done ? " done" : "") },
    h("span", { class: "ei" }, done ? "✓" : "•"), h("div", { class: "grow" }, h("div", {}, label), note ? h("div", {}, note) : null), action || null);
  const job = st.job || {};
  const parts = [];
  if (!st.supported) {
    parts.push(h("div", { class: "ehead off" }, h("b", {}, "Converter-only mode"),
      h("div", {}, `${st.reason}. Every conversion works normally; format suggestions come from Morph's built-in rules instead of the AI.`)));
  } else {
    parts.push(h("div", { class: "ehead" }, h("b", {}, `Ryzen AI NPU found${st.cpu ? ` · ${st.cpu.replace(/\s+w\/.*$/i, "")}` : ""}`),
      h("div", {}, "The AI advisor needs FastFlowLM — a free engine that runs language models on the NPU. It is a prerequisite and installs separately (Windows asks for permission).")));
    const busy = !!job.task;
    parts.push(step(st.flm, "1 · FastFlowLM engine", st.flm ? "Installed" : "Not installed yet",
      st.flm ? null : h("div", { style: { display: "flex", gap: "6px" } },
        h("button", { class: "btn small ghost", onclick: () => api("/api/ai/open_flm_site") }, "About"),
        h("button", { class: "btn small primary", disabled: busy, onclick: () => runEnabler("/api/ai/install_flm") }, "Install"))));
    parts.push(step(st.has_model, `2 · AI model ${st.model}`, st.has_model ? "Downloaded" : `About ${st.model_gb} GB download`,
      st.has_model ? null : h("button", { class: "btn small primary", disabled: busy || !st.flm, onclick: () => runEnabler("/api/ai/pull") }, "Download")));
    if (busy) parts.push(h("div", { class: "ejob" }, h("div", {}, job.label + (job.detail ? ` — ${job.detail}` : "")),
      h("div", { class: "ebar" + (job.pct == null ? " indef" : "") }, h("i", { style: { width: (job.pct ?? 30) + "%" } }))));
    if (job.error) parts.push(h("div", { class: "error" }, job.error));
    if (st.ready) parts.push(h("div", { class: "eready" }, "✦ The AI advisor is ready on your NPU."));
  }
  card.replaceChildren(...parts);
  clearTimeout(enablerTimer);
  if (job.task) enablerTimer = setTimeout(async () => {
    const next = await api("/api/ai/status").catch(() => null);
    if (next) {
      renderEnabler(next);
      if (!next.job?.task) { await refreshState(); S.files.forEach(renderAI); if (next.ready) toast("AI advisor ready"); }
    }
  }, 1000);
}
async function runEnabler(path) {
  try { await api(path); } catch (e) { toast(e.message); }
  setTimeout(async () => renderEnabler(await api("/api/ai/status")), 400);
}
async function installLO() {
  await api("/api/install", { what: "libreoffice" });
  toast("Installing LibreOffice in a terminal window — Morph picks it up when it's done");
  const t0 = Date.now();
  const iv = setInterval(async () => {
    await refreshState();
    if (S.engines.libreoffice || Date.now() - t0 > 20 * 60e3) {
      clearInterval(iv);
      if (S.engines.libreoffice) {
        const list = await api("/api/refresh");
        for (const d of list) { const F = S.files.get(d.id); if (F) { F.d = d; } }
        toast("LibreOffice ready — more conversions unlocked");
        S.files.forEach((F) => { if (F.targetsEl) renderTargets(F); });
      }
    }
  }, 5000);
}
let catalog = null;
async function openFormats() {
  catalog = catalog || await api("/api/catalog");
  renderFormats("");
  openPanel($("#formats"));
  setTimeout(() => $("#fmtSearch").focus(), 200);
}
function renderFormats(q) {
  q = q.toLowerCase().trim();
  const parts = [];
  let total = 0;
  for (const g of catalog) {
    const list = g.formats.filter((f) => !q || f.name.toLowerCase().includes(q) || f.id.includes(q) || f.ext.includes(q));
    if (!list.length) continue;
    total += list.length;
    parts.push(h("div", { class: "group", "--c": cc(g.cat) }, h("h4", {}, `${g.label} · ${list.length}`),
      h("div", { class: "fgrid" }, list.map((f) => h("span", {
        class: "fmt" + (!f.read && !f.write ? " off" : !f.write ? " ro" : ""),
        onmouseenter: (e) => showTip(e.currentTarget, { name: f.name, up: f.up, down: f.down,
          note: f.read && f.write ? "Morph can open and create it" : f.read ? "Morph can open it" : f.write ? "Morph can create it" : "Needs an extra engine (see Settings)" }),
        onmouseleave: hideTip,
      }, f.name, h("em", {}, f.read && f.write ? "IN·OUT" : f.read ? "IN" : f.write ? "OUT" : "—"))))));
  }
  parts.unshift(h("p", { class: "legend" }, `${total} formats · IN = can open · OUT = can create`));
  $("#fmtList").replaceChildren(...parts);
}

// ------------------------------------------------------------------ wiring
function init() {
  $("#cats").replaceChildren(...Object.entries(CATS).map(([k, v], i) => h("span", { "--c": cc(k), "--n": i }, v)));
  $("#btnBrowse").onclick = browse;
  $("#fileInput").onchange = (e) => { addFiles(e.target.files); e.target.value = ""; };
  $("#btnSettings").onclick = openSettings;
  $("#btnFormats").onclick = openFormats;
  $("#btnFolder").onclick = () => api("/api/reveal", { folder: true });
  $("#btnOutDir").onclick = async () => { S.settings = await api("/api/pickdir"); $("#outDir").textContent = S.settings.output_dir; };
  $("#scrim").onclick = closePanels;
  $$("[data-close]").forEach((b) => (b.onclick = closePanels));
  $("#fmtSearch").oninput = (e) => renderFormats(e.target.value);
  $("#aiPill").onclick = openSettings;
  addEventListener("keydown", (e) => {
    if (e.key === "Escape") closePanels();
    if (e.ctrlKey && e.key.toLowerCase() === "o") { e.preventDefault(); browse(); }
  });
  addEventListener("scroll", () => { $("#hdr").classList.toggle("scrolled", scrollY > 8); hideTip(); }, { passive: true });
  addEventListener("pointerdown", hideTip);
  // settings first, so restored cards know whether the AI is on
  refreshState().then(() => api("/api/files")).then((list) => list.forEach((d, i) => addFile(d, i, true))).catch(() => {});

  let depth = 0;
  const ov = $("#overlay");
  addEventListener("dragenter", (e) => { if (e.dataTransfer?.types.includes("Files")) { e.preventDefault(); depth++; ov.classList.add("on"); } });
  addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; ov.classList.remove("on"); } });
  addEventListener("dragover", (e) => e.preventDefault());
  addEventListener("drop", (e) => {
    e.preventDefault(); depth = 0; ov.classList.remove("on");
    const items = [...(e.dataTransfer.items || [])];
    const dirs = items.filter((it) => it.webkitGetAsEntry?.()?.isDirectory).length;
    if (dirs) toast("Folders can't be converted — drop the files inside them");
    const files = [...e.dataTransfer.files].filter((f, i) => !(items[i]?.webkitGetAsEntry?.()?.isDirectory));
    addFiles(files);
  });
  addEventListener("paste", (e) => {
    if (e.target.tagName === "INPUT") return;
    const files = [...(e.clipboardData?.files || [])].map((f) =>
      f.name === "image.png" ? new File([f], `pasted-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.png`, { type: f.type }) : f);
    if (files.length) addFiles(files);
  });
  refreshState();
  setInterval(refreshState, 2500);
}
init();
