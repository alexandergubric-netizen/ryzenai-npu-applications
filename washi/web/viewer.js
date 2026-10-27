/* Washi viewer: pages, zoom, layouts, lazy rendering and the text / link / form / search layers. */
"use strict";
const V = {
  els: [],            // page elements of the active document
  observer: null,
  visible: new Set(),
  renderTimer: null,
  measure: document.createElement("canvas").getContext("2d"),
};

function scale(v = view()) { return v.zoom * PX; }
function dpr() { return Math.min(window.devicePixelRatio || 1, 3); }

function fitZoom(v, d, mode) {
  const el = $("#viewer");
  const bar = el.offsetWidth - el.clientWidth;   // reserve room for the vertical scrollbar before it appears
  const vw = el.clientWidth - 64 - (bar ? 0 : 12), vh = el.clientHeight - 44;
  const maxW = Math.max(...d.pages.map((p) => p.w)), maxH = Math.max(...d.pages.map((p) => p.h));
  const w = v.layout === "two" ? maxW * 2 + 10 / PX : maxW;
  if (mode === "fit-page") return clamp(Math.min(vw / (w * PX), vh / (maxH * PX)), 0.1, 8);
  return clamp(vw / (w * PX), 0.1, 8);
}

/* (Re)build every page box for the active document. Images and layers fill in lazily. */
function buildPages() {
  const d = doc(), v = view();
  const host = $("#pages");
  if (V.observer) V.observer.disconnect();
  host.innerHTML = "";
  V.els = [];
  V.visible.clear();
  if (!d) return;
  if (v.fit !== "custom") v.zoom = fitZoom(v, d, v.fit);
  host.className = v.layout === "two" ? "two" : v.layout === "single" ? "single" : "";
  V.observer = new IntersectionObserver(onIntersect, { root: $("#viewer"), rootMargin: "900px 0px" });
  d.pages.forEach((pg, i) => {
    const el = document.createElement("div");
    el.className = "page placeholder";
    el.dataset.p = i;
    el.innerHTML = `<img class="pimg loading" alt="" draggable="false"><div class="layer text-layer"></div><div class="layer hit-layer"></div>
      <div class="layer link-layer"></div><div class="layer form-layer"></div><div class="layer ann-layer"></div>
      <div class="layer draw-layer"></div><div class="layer edit-layer"></div><div class="pnum">${esc(pg.label)}</div>`;
    const img = el.firstElementChild;
    img.onload = () => { img.classList.remove("loading"); el.classList.remove("placeholder", "broken"); img.dataset.tries = 0; };
    img.onerror = () => {
      const tries = +(img.dataset.tries || 0);
      if (!img.dataset.src) return;
      if (tries < 2) {   // a busy moment or a closed connection: try again
        img.dataset.tries = tries + 1;
        setTimeout(() => { if (img.dataset.src) img.src = img.dataset.src + "&retry=" + (tries + 1); }, 700 * (tries + 1));
      } else { el.classList.remove("placeholder"); el.classList.add("broken"); }
    };
    host.appendChild(el);
    V.els.push(el);
    V.observer.observe(el);
  });
  sizePages();
  applyLayoutVisibility();
  document.dispatchEvent(new Event("pages-built"));
}

function sizePages() {
  const d = doc(), v = view();
  if (!d) return;
  const s = scale(v);
  V.els.forEach((el, i) => {
    const pg = d.pages[i];
    el.style.width = Math.round(pg.w * s) + "px";
    el.style.height = Math.round(pg.h * s) + "px";
    el.style.setProperty("--s", s);
  });
  $("#zoomLabel").textContent = Math.round(v.zoom * 100) + "%";
  $$("#stNav [data-cmd^='view.']").forEach((b) => b.classList.toggle("on",
    b.dataset.cmd === "view." + (v.layout === "continuous" ? "continuous" : v.layout) ||
    (b.dataset.cmd === "view.fitwidth" && v.fit === "fit-width") || (b.dataset.cmd === "view.fitpage" && v.fit === "fit-page")));
}

function onIntersect(entries) {
  for (const e of entries) {
    const p = +e.target.dataset.p;
    if (e.isIntersecting) { V.visible.add(p); loadPage(p); } else V.visible.delete(p);
  }
}

/* Request the image for the current zoom and fetch text/links/forms/annotations once per page version. */
function loadPage(p) {
  const d = doc(), v = view(), el = V.els[p];
  if (!d || !el || !d.pages[p]) return;
  const pg = d.pages[p];
  const sc = Math.round(scale(v) * dpr() * 100) / 100;
  const img = el.firstElementChild;
  const want = pageURL(d.id, p, sc, pg.pv);
  if (img.dataset.src !== want) { img.dataset.src = want; img.dataset.tries = 0; img.src = want; }
  const key = pg.pv + ":" + pg.rot;
  if (v.pinfo[p] && v.pinfo[p].key === key) {
    if (el.dataset.layers !== key) drawLayers(p);
    return;
  }
  if (v.pinfo[p] && v.pinfo[p].loading === key) return;
  v.pinfo[p] = { loading: key };
  const id = d.id;
  api("pageinfo", { d: id, p }).then((info) => {
    if (!S.docs[id] || S.docs[id].pages[p]?.pv !== pg.pv) return;
    view(id).pinfo[p] = { key, ...info };
    view(id).annots[p] = info.annots;
    if (S.active === id) drawLayers(p);
  }).catch(() => { delete view(id).pinfo[p]; });
}

function rerenderVisible() {
  clearTimeout(V.renderTimer);
  V.renderTimer = setTimeout(() => V.visible.forEach(loadPage), 140);
}

/* ------------------------------------------------------------------ layers (positioned in % so zoom needs no rebuild) */
const pct = (v, total) => (v / total * 100).toFixed(4) + "%";
function place(el, r, pg) {
  el.style.left = pct(r[0], pg.w); el.style.top = pct(r[1], pg.h);
  el.style.width = pct(r[2] - r[0], pg.w); el.style.height = pct(r[3] - r[1], pg.h);
}

function drawLayers(p) {
  const d = doc(), v = view(), el = V.els[p];
  const info = v.pinfo[p];
  if (!el || !info || !info.text) return;
  const pg = d.pages[p];
  el.dataset.layers = info.key;
  drawText(el.querySelector(".text-layer"), info.text, pg);
  drawLinks(el.querySelector(".link-layer"), info.links || [], pg);
  drawForms(el.querySelector(".form-layer"), info.widgets || [], pg, p);
  drawHits(p);
  if (S.sel && S.sel.p === p) drawSelection();
}

function drawText(layer, lines, pg) {
  const frag = document.createDocumentFragment();
  const ctx = V.measure;
  for (const l of lines) {
    const span = document.createElement("span");
    span.textContent = l.t;
    const [x0, y0, x1, y1] = l.r;
    let ang = Math.round((Math.atan2(l.dir[1], l.dir[0]) * 180 / Math.PI + pg.rot) / 90) * 90;
    ang = ((ang % 360) + 360) % 360;
    const horiz = ang === 0 || ang === 180;
    const len = horiz ? x1 - x0 : y1 - y0;
    const thick = horiz ? y1 - y0 : x1 - x0;
    const fz = Math.min(l.s, thick * 1.05) || l.s;
    ctx.font = `10px Arial`;
    const natural = ctx.measureText(l.t).width / 10 * fz;
    const k = natural > 0 ? len / natural : 1;
    const [lx, ty] = ang === 0 ? [x0, y0] : ang === 90 ? [x1, y0] : ang === 180 ? [x1, y1] : [x0, y1];
    span.style.left = pct(lx, pg.w);
    span.style.top = pct(ty, pg.h);
    span.style.fontSize = `calc(var(--s) * ${fz.toFixed(2)}px)`;
    span.style.transform = `${ang ? `rotate(${ang}deg) ` : ""}scaleX(${k.toFixed(4)})`;
    frag.appendChild(span);
    frag.appendChild(document.createTextNode("\n"));
  }
  layer.innerHTML = "";
  layer.appendChild(frag);
}

function drawLinks(layer, links, pg) {
  layer.innerHTML = "";
  for (const l of links) {
    const a = document.createElement("a");
    place(a, l.r, pg);
    a.title = l.uri ? l.uri : `Go to page ${l.page + 1}`;
    a.onclick = (e) => {
      if (S.tool !== "select" && S.tool !== "hand") return;
      e.preventDefault();
      if (l.uri) confirmBox("Open link?", l.uri, "Open in browser").then((ok) => ok && api("open_url", { url: l.uri }));
      else gotoPage(l.page);
    };
    layer.appendChild(a);
  }
}

function drawForms(layer, widgets, pg, p) {
  layer.innerHTML = "";
  const d = doc();
  for (const w of widgets) {
    let el;
    const t = w.type;
    if (t === "CheckBox" || t === "RadioButton") {
      el = document.createElement("input");
      el.type = "checkbox";
      el.checked = w.value && w.value !== "Off" && w.value !== false;
      el.onchange = () => setField(d.id, p, w, el.checked);
    } else if (t === "ComboBox" || t === "ListBox") {
      el = document.createElement("select");
      for (const o of w.options) {
        const opt = document.createElement("option");
        const [val, label] = Array.isArray(o) ? o : [o, o];
        opt.value = val; opt.textContent = label;
        el.appendChild(opt);
      }
      el.value = w.value;
      el.onchange = () => setField(d.id, p, w, el.value);
    } else if (t === "Text") {
      el = document.createElement(w.multiline ? "textarea" : "input");
      el.value = w.value || "";
      if (w.max) el.maxLength = w.max;
      el.onchange = () => setField(d.id, p, w, el.value);
      el.style.fontSize = `calc(var(--s) * ${(w.size || Math.min(12, (w.r[3] - w.r[1]) * 0.7)).toFixed(1)}px)`;
    } else continue;
    el.className = "fw";
    el.title = w.label || w.name;
    if (w.readonly) { el.readOnly = true; el.disabled = el.type === "checkbox" || el.tagName === "SELECT"; }
    place(el, w.r, pg);
    layer.appendChild(el);
  }
}

async function setField(id, p, w, value) {
  try { await api("field_set", { d: id, p, xref: w.xref, value }); } catch (e) { fail(e); }
}

function drawHits(p) {
  const v = view(), el = V.els[p];
  if (!el) return;
  const layer = el.querySelector(".hit-layer");
  layer.innerHTML = "";
  const pg = doc().pages[p];
  v.hits.forEach((h, i) => {
    if (h.p !== p) return;
    const div = document.createElement("div");
    place(div, [h.r[0] - 1, h.r[1] - 1, h.r[2] + 1, h.r[3] + 1], pg);
    if (i === v.hitIdx) div.className = "cur";
    layer.appendChild(div);
  });
}
function drawAllHits() { V.els.forEach((_, p) => drawHits(p)); }

/* ------------------------------------------------------------------ navigation */
function currentPage() {
  const v = view();
  return v ? v.page : 0;
}

function trackPage() {
  const v = view(), d = doc();
  if (!d || !V.els.length || v.layout === "single") return;
  const vr = $("#viewer").getBoundingClientRect();
  const mid = vr.top + vr.height * 0.35;
  let best = 0, bestDist = Infinity;
  for (let i = 0; i < V.els.length; i++) {
    const r = V.els[i].getBoundingClientRect();
    if (r.top <= mid && r.bottom >= mid) { best = i; bestDist = 0; break; }
    const dist = Math.min(Math.abs(r.top - mid), Math.abs(r.bottom - mid));
    if (dist < bestDist) { bestDist = dist; best = i; }
  }
  if (best !== v.page) { v.page = best; onPageChange(); }
}

function onPageChange() {
  const v = view(), d = doc();
  if (!d) return;
  $("#pageInput").value = d.pages[v.page]?.label || v.page + 1;
  $("#pageCount").textContent = `/ ${d.pages.length}`;
  document.dispatchEvent(new Event("page-changed"));
}

function gotoPage(p, yPt = null, smooth = false) {
  const d = doc(), v = view();
  if (!d) return;
  p = clamp(p, 0, d.pages.length - 1);
  if (v.layout === "single") {
    v.page = p;
    applyLayoutVisibility();
    $("#viewer").scrollTop = yPt != null ? Math.max(0, yPt * scale() - 40) : 0;
    onPageChange();
    return;
  }
  const el = V.els[p];
  if (!el) return;
  const top = el.offsetTop - 14 + (yPt != null ? yPt * scale() - 60 : 0);
  $("#viewer").scrollTo({ top: Math.max(0, top), behavior: smooth ? "smooth" : "auto" });
  v.page = p;
  onPageChange();
}

function applyLayoutVisibility() {
  const v = view();
  V.els.forEach((el, i) => { el.style.display = v.layout === "single" && i !== v.page ? "none" : ""; });
  if (v.layout === "single") { loadPage(v.page); }
}

function setZoom(z, anchor) {
  const v = view(), d = doc();
  if (!d) return;
  const vw = $("#viewer");
  const old = scale(v);
  z = clamp(z, 0.1, 8);
  const ax = anchor ? anchor.x : vw.clientWidth / 2, ay = anchor ? anchor.y : vw.clientHeight / 2;
  const cx = vw.scrollLeft + ax, cy = vw.scrollTop + ay;
  v.zoom = z;
  sizePages();
  const k = scale(v) / old;
  vw.scrollLeft = cx * k - ax;
  vw.scrollTop = cy * k - ay;
  rerenderVisible();
  document.dispatchEvent(new Event("zoom-changed"));
}

function setFit(mode) {
  const v = view(), d = doc();
  if (!d) return;
  v.fit = mode;
  const p = v.page;
  v.zoom = fitZoom(v, d, mode);
  sizePages();
  rerenderVisible();
  gotoPage(p);
}

function setLayout(layout) {
  const v = view();
  if (!doc()) return;
  v.layout = layout;
  const p = v.page;
  buildPages();
  gotoPage(p);
  api("settings", { set: { layout } }).catch(() => {});
}

/* page under a client point, with the point in page points */
function pageAt(clientX, clientY) {
  for (let i = 0; i < V.els.length; i++) {
    const el = V.els[i];
    if (el.style.display === "none") continue;
    const r = el.getBoundingClientRect();
    if (clientX >= r.left && clientX <= r.right && clientY >= r.top && clientY <= r.bottom) {
      const s = scale();
      return { p: i, x: (clientX - r.left) / s, y: (clientY - r.top) / s, el };
    }
  }
  return null;
}
function toPage(el, clientX, clientY) {
  const r = el.getBoundingClientRect(), s = scale();
  return { x: (clientX - r.left) / s, y: (clientY - r.top) / s };
}

/* Text selection -> {page: [rects in points]} */
function selectionRects() {
  const sel = getSelection();
  if (!sel.rangeCount || sel.isCollapsed) return null;
  const out = {};
  const s = scale();
  for (let i = 0; i < sel.rangeCount; i++) {
    for (const cr of sel.getRangeAt(i).getClientRects()) {
      if (cr.width < 1 || cr.height < 1) continue;
      const hit = pageAt(cr.left + cr.width / 2, cr.top + cr.height / 2);
      if (!hit) continue;
      const pr = hit.el.getBoundingClientRect();
      (out[hit.p] = out[hit.p] || []).push([(cr.left - pr.left) / s, (cr.top - pr.top) / s, (cr.right - pr.left) / s, (cr.bottom - pr.top) / s]);
    }
  }
  return Object.keys(out).length ? out : null;
}

/* A refreshed document: re-request changed pages only. */
document.addEventListener("doc-changed", (e) => {
  const { id, old } = e.detail;
  if (id !== S.active) return;
  const d = S.docs[id];
  if (!old || old.pages.length !== d.pages.length || old.pages.some((p, i) => p.w !== d.pages[i].w || p.h !== d.pages[i].h || p.rot !== d.pages[i].rot)) {
    const p = view().page;
    const top = $("#viewer").scrollTop;
    buildPages();
    if (old && old.pages.length === d.pages.length) $("#viewer").scrollTop = top; else gotoPage(Math.min(p, d.pages.length - 1));
    return;
  }
  d.pages.forEach((pg, i) => {
    if (old.pages[i].pv !== pg.pv) {
      const el = V.els[i];
      if (el) el.dataset.layers = "";
      if (V.visible.has(i) || view().layout === "single") loadPage(i);
    }
  });
});

addEventListener("resize", () => {
  const v = view();
  if (!doc() || v.fit === "custom") return;
  clearTimeout(V.resizeT);
  V.resizeT = setTimeout(() => { v.zoom = fitZoom(v, doc(), v.fit); sizePages(); rerenderVisible(); }, 120);
});
