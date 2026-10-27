/* Washi tools: everything the pointer does on a page. */
"use strict";
const TOOLS = {
  select: { kind: "select", hint: "" },
  hand: { kind: "hand", hint: "Drag to move around the page" },
  highlight: { kind: "markup", hint: "Select text to highlight it" },
  underline: { kind: "markup", hint: "Select text to underline it" },
  strikeout: { kind: "markup", hint: "Select text to strike it out" },
  squiggly: { kind: "markup", hint: "Select text to mark it with a wavy line" },
  area: { kind: "rect", hint: "Drag over any area to highlight it" },
  note: { kind: "click", hint: "Click where the sticky note should go" },
  textbox: { kind: "rect", hint: "Drag a box, then type your comment" },
  rect: { kind: "rect", hint: "Drag to draw a rectangle (Shift = square)" },
  ellipse: { kind: "rect", hint: "Drag to draw an ellipse (Shift = circle)" },
  line: { kind: "line", hint: "Drag to draw a line (Shift = straight)" },
  arrow: { kind: "line", hint: "Drag to draw an arrow (Shift = straight)" },
  ink: { kind: "ink", hint: "Draw freely with the pen" },
  stamp: { kind: "rect", hint: "Click or drag to place the stamp" },
  sign: { kind: "rect", hint: "Click or drag to place your signature" },
  image: { kind: "rect", hint: "Click or drag to place the image" },
  edittext: { kind: "edittext", hint: "Click a line of text to change it" },
  addtext: { kind: "click", hint: "Click where you want to type" },
  whiteout: { kind: "rect", hint: "Drag over content to erase it" },
  redact: { kind: "rect", hint: "Drag over content to mark it for redaction" },
  link: { kind: "rect", hint: "Drag over the area that should become a link" },
  crop: { kind: "rect", hint: "Drag the area to keep" },
  field: { kind: "rect", hint: "Drag to add a text field" },
  fieldcheck: { kind: "rect", hint: "Click or drag to add a checkbox" },
  fieldcombo: { kind: "rect", hint: "Drag to add a dropdown" },
};
const T = { pending: null, ink: null, inkTimer: null, drag: null, editor: null };
const MARKUP_KINDS = new Set(["Highlight", "Underline", "Strikeout", "Squiggly"]);

function setTool(name, pending) {
  if (!TOOLS[name]) name = "select";
  commitInk();
  closeEditor(true);
  if (pending !== undefined) T.pending = pending;
  else if (name !== S.tool) T.pending = null;
  S.tool = name;
  const t = TOOLS[name];
  const vw = $("#viewer");
  vw.className = "";
  vw.classList.add("t-" + (t.kind === "rect" || t.kind === "line" || t.kind === "ink" ? "draw" : name === "note" ? "note" : name === "addtext" ? "addtext" : name === "edittext" ? "edittext" : name));
  $$(".text-layer").forEach((l) => l.classList.toggle("off", !(t.kind === "select" || t.kind === "markup")));
  if (t.kind !== "select") selectAnnot(null);
  hideFloat();
  const hint = $("#toolHint");
  if (t.hint && doc()) {
    hint.innerHTML = `${icon(TOOL_ICON[name] || "select")}<span>${esc(t.hint)}</span><span id="styleGroup"></span><button class="done">Done <kbd style="background:none;border:0;color:inherit">Esc</kbd></button>`;
    hint.querySelector(".done").onclick = () => setTool("select");
    hint.classList.remove("hidden");
    renderStyleGroup();
  } else hint.classList.add("hidden");
  $$("[data-cmd^='tool.']").forEach((b) => b.classList.toggle("on", b.dataset.cmd === "tool." + name));
}
const TOOL_ICON = { hand: "hand", highlight: "highlight", underline: "underline", strikeout: "strike", squiggly: "squiggly", area: "area", note: "note",
  textbox: "textbox", rect: "rect", ellipse: "ellipse", line: "line", arrow: "arrow", ink: "pen", stamp: "stamp", sign: "sign", image: "image",
  edittext: "editText", addtext: "addText", whiteout: "whiteout", redact: "redact", link: "link", crop: "crop", field: "field", fieldcheck: "checkbox", fieldcombo: "dropdown" };

/* ------------------------------------------------------------------ pointer routing */
function initPointer() {
  const pages = $("#pages");
  pages.addEventListener("pointerdown", onDown);
  pages.addEventListener("pointermove", onHover);
  pages.addEventListener("pointerleave", () => $$(".line-hover").forEach((e) => e.remove()));
  pages.addEventListener("dblclick", onDouble);
  document.addEventListener("pointerup", onTextUp);
  const vw = $("#viewer");
  vw.addEventListener("scroll", () => { trackPage(); hideFloat(true); }, { passive: true });
  vw.addEventListener("wheel", (e) => {
    if (e.ctrlKey) {
      e.preventDefault();
      const r = vw.getBoundingClientRect();
      view().fit = "custom";
      setZoom(view().zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12), { x: e.clientX - r.left, y: e.clientY - r.top });
    } else if (view() && view().layout === "single") {
      const atTop = vw.scrollTop <= 0, atBottom = vw.scrollTop + vw.clientHeight >= vw.scrollHeight - 2;
      if (e.deltaY > 0 && atBottom) { e.preventDefault(); if (!V.flip) { V.flip = setTimeout(() => (V.flip = null), 350); run("nav.next"); } }
      else if (e.deltaY < 0 && atTop) { e.preventDefault(); if (!V.flip) { V.flip = setTimeout(() => (V.flip = null), 350); gotoPage(view().page - 1, doc().pages[view().page - 1]?.h); } }
    }
  }, { passive: false });
  // hand tool + space-bar panning
  let pan = null;
  vw.addEventListener("pointerdown", (e) => {
    if (!(S.tool === "hand" || T.space) || e.button !== 0) return;
    pan = { x: e.clientX, y: e.clientY, l: vw.scrollLeft, t: vw.scrollTop };
    vw.classList.add("panning");
    vw.setPointerCapture(e.pointerId);
    e.preventDefault();
  }, true);
  vw.addEventListener("pointermove", (e) => { if (pan) { vw.scrollLeft = pan.l - (e.clientX - pan.x); vw.scrollTop = pan.t - (e.clientY - pan.y); } });
  vw.addEventListener("pointerup", () => { pan = null; vw.classList.remove("panning"); });
}

function pageOf(e) {
  const el = e.target.closest(".page");
  if (!el) return null;
  const p = +el.dataset.p;
  return { p, el, pt: toPage(el, e.clientX, e.clientY) };
}

function onDown(e) {
  if (e.button !== 0 || S.tool === "hand" || T.space) return;
  if (e.target.closest(".inline-editor, .edit-style, .form-layer .fw, .sel-box")) return;
  const hit = pageOf(e);
  if (!hit) return;
  const t = TOOLS[S.tool];
  if (t.kind === "select") {
    const a = annotAt(hit.p, hit.pt);
    if (a) { e.preventDefault(); selectAnnot({ ...a, p: hit.p }); startMove(e, hit, "move"); return; }
    if (S.sel) selectAnnot(null);
    return;   // text selection proceeds natively
  }
  if (t.kind === "markup") return;
  e.preventDefault();
  if (t.kind === "click") return clickTool(hit);
  if (t.kind === "edittext") return editTextAt(hit);
  if (t.kind === "rect") return dragRect(e, hit);
  if (t.kind === "line") return dragLine(e, hit);
  if (t.kind === "ink") return drawInk(e, hit);
}

function onDouble(e) {
  if (S.tool !== "select") return;
  const hit = pageOf(e);
  if (!hit) return;
  const a = annotAt(hit.p, hit.pt);
  if (a && a.type === 2) editFreeText({ ...a, p: hit.p });   // FreeText: edit in place
  else if (a) openComment({ ...a, p: hit.p });
}

function annotAt(p, pt) {
  const list = view().annots[p] || [];
  let best = null;
  const tol = 4 + 4 / scale();   // a few screen pixels, whatever the zoom
  for (const a of list) {
    const [x0, y0, x1, y1] = a.r;
    if (!(pt.x >= x0 - 3 && pt.x <= x1 + 3 && pt.y >= y0 - 3 && pt.y <= y1 + 3)) continue;
    if (!a.fill && a.kind === "Rectangle") {          // hollow: only the frame is "the shape"
      const inside = pt.x > x0 + tol && pt.x < x1 - tol && pt.y > y0 + tol && pt.y < y1 - tol;
      if (inside) continue;
    } else if (!a.fill && a.kind === "Ellipse") {
      const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, rx = Math.max((x1 - x0) / 2, 1), ry = Math.max((y1 - y0) / 2, 1);
      const d = Math.hypot((pt.x - cx) / rx, (pt.y - cy) / ry);
      if (Math.abs(d - 1) * Math.min(rx, ry) > tol) continue;
    }
    const area = (x1 - x0) * (y1 - y0);
    if (!best || area < best.area) best = { ...a, area };
  }
  return best;
}

/* ------------------------------------------------------------------ text selection -> markup / float bar */
async function onTextUp(e) {
  if (!doc() || T.drag) return;
  if (!e.target.closest || !e.target.closest("#pages")) { if (!e.target.closest("#floatbar")) hideFloat(); return; }
  await sleep(10);
  const rects = selectionRects();
  const t = TOOLS[S.tool];
  if (!rects) { if (!S.sel) hideFloat(); return; }
  if (t.kind === "markup") {
    getSelection().removeAllRanges();
    await markup(S.tool, rects);
    return;
  }
  if (t.kind === "select") showTextFloat(e.clientX, e.clientY, rects);
}

async function markup(kind, rects, color) {
  const d = doc();
  const c = color || (kind === "highlight" ? S.style.color : kind === "underline" ? "#3d8fd1" : kind === "squiggly" ? "#e0a526" : "#e2452f");
  for (const [p, rs] of Object.entries(rects)) {
    await api("annot_add", { d: d.id, p: +p, kind, o: { rects: rs, color: c } });
  }
}

function showTextFloat(x, y, rects) {
  const bar = $("#floatbar");
  const ai = S.ai.enabled;
  bar.innerHTML = `
    <button data-a="highlight" title="Highlight">${icon("highlight")}</button>
    <button data-a="underline" title="Underline">${icon("underline")}</button>
    <button data-a="strikeout" title="Strike out">${icon("strike")}</button>
    <button data-a="copy" title="Copy (Ctrl C)">${icon("copy")}Copy</button>
    ${ai ? `<span class="sep"></span><button class="ai" data-a="explain">${icon("sparkle")}Explain</button>
    <button class="ai" data-a="translate">${icon("translate")}Translate</button><button class="ai" data-a="more" title="More AI">${icon("more")}</button>` : ""}`;
  const text = getSelection().toString();
  bar.onclick = async (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    const a = b.dataset.a;
    if (["highlight", "underline", "strikeout"].includes(a)) { getSelection().removeAllRanges(); hideFloat(); await markup(a, rects).catch(fail); }
    else if (a === "copy") { await navigator.clipboard.writeText(text.replace(/\n(?!\n)/g, " ")); toast("Copied"); hideFloat(); }
    else if (a === "explain" || a === "translate") { hideFloat(); aiSelection(text, a); }
    else if (a === "more") menuAt(b, [
      { label: "Explain", icon: "sparkle", action: () => aiSelection(text, "explain") },
      { label: "Translate", icon: "translate", action: () => aiSelection(text, "translate") },
      { label: "Simplify", icon: "wand", action: () => aiSelection(text, "simplify") },
      { label: "Key points", icon: "list", action: () => aiSelection(text, "keypoints") },
      { label: "Proofread", icon: "check", action: () => aiSelection(text, "proofread") },
    ]);
  };
  positionFloat(x, y - 52);
}

function positionFloat(x, y) {
  const bar = $("#floatbar"), wrap = $("#viewerWrap").getBoundingClientRect();
  bar.classList.remove("hidden");
  const r = bar.getBoundingClientRect();
  bar.style.left = clamp(x - wrap.left - r.width / 2, 8, wrap.width - r.width - 8) + "px";
  bar.style.top = clamp(y - wrap.top, 8, wrap.height - r.height - 8) + "px";
}
function hideFloat(onlyText) {
  if (onlyText && S.sel) { if (S.sel) placeAnnotBar(); return; }
  $("#floatbar").classList.add("hidden");
}

/* ------------------------------------------------------------------ drawing */
function draftEl(hit, cls) {
  const d = document.createElement("div");
  d.className = "draft" + (cls ? " " + cls : "");
  hit.el.querySelector(".draw-layer").appendChild(d);
  return d;
}

function dragRect(e, hit) {
  const pg = doc().pages[hit.p];
  const start = hit.pt;
  const cls = { redact: "redact", whiteout: "whiteout", crop: "crop" }[S.tool] || "";
  const el = draftEl(hit, cls);
  if (T.pending && T.pending.preview) el.innerHTML = `<img src="${T.pending.preview}">`;
  let r = [start.x, start.y, start.x, start.y];
  const move = (ev) => {
    const pt = toPage(hit.el, ev.clientX, ev.clientY);
    let x1 = clamp(pt.x, 0, pg.w), y1 = clamp(pt.y, 0, pg.h);
    if (ev.shiftKey || T.pending?.ratio) {
      const ratio = T.pending?.ratio || 1;
      const w = Math.abs(x1 - start.x), h = Math.abs(y1 - start.y);
      const s = Math.max(w, h * ratio);
      x1 = start.x + Math.sign(x1 - start.x || 1) * s;
      y1 = start.y + Math.sign(y1 - start.y || 1) * s / ratio;
    }
    r = [Math.min(start.x, x1), Math.min(start.y, y1), Math.max(start.x, x1), Math.max(start.y, y1)];
    place(el, r, pg);
  };
  const up = async () => {
    removeEventListener("pointermove", move);
    removeEventListener("pointerup", up);
    T.drag = null;
    el.remove();
    const small = r[2] - r[0] < 5 && r[3] - r[1] < 5;
    if (small) r = defaultRect(start, pg);
    if (!r) return;
    try { await commitRect(hit.p, r); } catch (err) { fail(err); }
  };
  T.drag = true;
  addEventListener("pointermove", move);
  addEventListener("pointerup", up);
}

function defaultRect(pt, pg) {
  const sizes = { stamp: [170, 170 / (T.pending?.ratio || 3)], sign: [150, 150 / (T.pending?.ratio || 3)], fieldcheck: [14, 14], field: [180, 22], fieldcombo: [150, 22], textbox: [200, 60],
    rect: [80, 60], ellipse: [80, 60], area: null, redact: null, whiteout: null, crop: null, link: null };
  if (S.tool === "image" && T.pending) {
    const w = Math.min(T.pending.w * 0.75, pg.w * 0.45);
    return [pt.x, pt.y, pt.x + w, pt.y + w * T.pending.h / T.pending.w];
  }
  const s = sizes[S.tool];
  if (!s) return null;
  const x = clamp(pt.x - (S.tool === "stamp" || S.tool === "sign" ? s[0] / 2 : 0), 0, pg.w - s[0]);
  const y = clamp(pt.y - (S.tool === "stamp" || S.tool === "sign" ? s[1] / 2 : 0), 0, pg.h - s[1]);
  return [x, y, x + s[0], y + s[1]];
}

async function commitRect(p, rect) {
  const d = doc(), st = S.style;
  switch (S.tool) {
    case "area": return api("annot_add", { d: d.id, p, kind: "area", o: { rect, color: st.color } });
    case "rect": case "ellipse":
      return api("annot_add", { d: d.id, p, kind: S.tool, o: { rect, color: st.stroke, fill: st.fill, width: st.width } }).then(afterAdd);
    case "textbox": return textboxEditor(p, rect);
    case "stamp": return api("annot_add", { d: d.id, p, kind: "stamp", o: { rect, label: st.stamp } }).then(afterAdd);
    case "redact":
      await api("annot_add", { d: d.id, p, kind: "redact", o: { rect } });
      return toast("Marked for redaction. Nothing is removed until you apply it.", { icon: "redact", action: { label: "Apply now", fn: () => run("doc.redactapply") }, ms: 6000 });
    case "whiteout": return api("whiteout", { d: d.id, p, rect });
    case "image":
      if (!T.pending) return run("tool.image");
      await api("image_add", { d: d.id, p, rect, img: T.pending.img });
      return setTool("select");
    case "sign":
      if (!T.pending) return run("tool.sign");
      await api("signature_add", { d: d.id, p, rect, png: T.pending.png }).then(afterAdd);
      return setTool("select");
    case "link": return linkDialog(p, rect);
    case "crop": return cropDialog(p, rect);
    case "field": case "fieldcheck": case "fieldcombo": {
      const kind = { field: "text", fieldcheck: "check", fieldcombo: "combo" }[S.tool];
      const name = await promptBox("Field name", "Name (used when the form data is exported)", `${kind}_${Date.now() % 10000}`, { icon: "field" });
      if (name === null) return;
      await api("field_add", { d: d.id, p, kind, rect, name });
      delete view().pinfo[p];
      return loadPage(p);
    }
  }
}
function afterAdd(res) { if (res && res.annot && S.tool === "select") selectAnnot(res.annot); return res; }

function dragLine(e, hit) {
  const pg = doc().pages[hit.p];
  const a = hit.pt;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "draft-svg");
  svg.setAttribute("viewBox", `0 0 ${pg.w} ${pg.h}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.innerHTML = `<line stroke="${S.style.stroke}" stroke-width="${S.style.width}" stroke-linecap="round"/>`;
  hit.el.querySelector(".draw-layer").appendChild(svg);
  const line = svg.firstChild;
  let b = a;
  const move = (ev) => {
    let pt = toPage(hit.el, ev.clientX, ev.clientY);
    if (ev.shiftKey) {
      const ang = Math.round(Math.atan2(pt.y - a.y, pt.x - a.x) / (Math.PI / 4)) * (Math.PI / 4);
      const len = Math.hypot(pt.x - a.x, pt.y - a.y);
      pt = { x: a.x + Math.cos(ang) * len, y: a.y + Math.sin(ang) * len };
    }
    b = pt;
    line.setAttribute("x1", a.x); line.setAttribute("y1", a.y); line.setAttribute("x2", b.x); line.setAttribute("y2", b.y);
  };
  const up = async () => {
    removeEventListener("pointermove", move); removeEventListener("pointerup", up);
    T.drag = null;
    svg.remove();
    if (Math.hypot(b.x - a.x, b.y - a.y) < 4) return;
    await api("annot_add", { d: doc().id, p: hit.p, kind: S.tool, o: { points: [[a.x, a.y], [b.x, b.y]], color: S.style.stroke, width: S.style.width } }).catch(fail);
  };
  T.drag = true;
  addEventListener("pointermove", move); addEventListener("pointerup", up);
}

function drawInk(e, hit) {
  if (T.ink && (T.ink.p !== hit.p || T.ink.d !== doc().id || T.ink.color !== S.style.stroke || T.ink.width !== S.style.width)) commitInk();
  clearTimeout(T.inkTimer);
  const pg = doc().pages[hit.p];
  if (!T.ink) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "draft-svg");
    svg.setAttribute("viewBox", `0 0 ${pg.w} ${pg.h}`);
    svg.setAttribute("preserveAspectRatio", "none");
    hit.el.querySelector(".draw-layer").appendChild(svg);
    T.ink = { d: doc().id, p: hit.p, paths: [], svg, color: S.style.stroke, width: S.style.width };
  }
  const path = [[hit.pt.x, hit.pt.y]];
  T.ink.paths.push(path);
  const pl = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  pl.setAttribute("fill", "none"); pl.setAttribute("stroke", S.style.stroke); pl.setAttribute("stroke-width", S.style.width);
  pl.setAttribute("stroke-linecap", "round"); pl.setAttribute("stroke-linejoin", "round");
  T.ink.svg.appendChild(pl);
  const move = (ev) => {
    const evs = ev.getCoalescedEvents ? ev.getCoalescedEvents() : [ev];
    for (const ce of evs) {
      const pt = toPage(hit.el, ce.clientX, ce.clientY);
      const last = path[path.length - 1];
      if (Math.hypot(pt.x - last[0], pt.y - last[1]) > 0.6) path.push([clamp(pt.x, 0, pg.w), clamp(pt.y, 0, pg.h)]);
    }
    pl.setAttribute("points", path.map((q) => q.join(",")).join(" "));
  };
  const up = () => {
    removeEventListener("pointermove", move); removeEventListener("pointerup", up);
    T.drag = null;
    T.inkTimer = setTimeout(commitInk, 1100);
  };
  T.drag = true;
  addEventListener("pointermove", move); addEventListener("pointerup", up);
}

/* Stores the pen strokes drawn so far (into the document they were drawn on). Returns a promise. */
function commitInk() {
  clearTimeout(T.inkTimer);
  const ink = T.ink;
  T.ink = null;
  if (!ink) return Promise.resolve();
  const paths = ink.paths.filter((p) => p.length > 1).map(simplify);
  if (!paths.length || !S.docs[ink.d]) { ink.svg.remove(); return Promise.resolve(); }
  return api("annot_add", { d: ink.d, p: ink.p, kind: "ink", o: { paths, color: ink.color, width: ink.width } })
    .catch(fail).finally(() => setTimeout(() => ink.svg.remove(), 250));
}
function simplify(path) {   // drop points closer than 0.8 pt to the line through their neighbours
  if (path.length < 4) return path;
  const out = [path[0]];
  for (let i = 1; i < path.length - 1; i++) {
    const [a, b, c] = [out[out.length - 1], path[i], path[i + 1]];
    const area = Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / (Math.hypot(c[0] - a[0], c[1] - a[1]) || 1);
    if (area > 0.35) out.push(b);
  }
  out.push(path[path.length - 1]);
  return out.map((p) => [Math.round(p[0] * 100) / 100, Math.round(p[1] * 100) / 100]);
}

/* ------------------------------------------------------------------ click tools: note, typewriter */
async function clickTool(hit) {
  if (S.tool === "note") {
    const res = await api("annot_add", { d: doc().id, p: hit.p, kind: "note", o: { point: [hit.pt.x, hit.pt.y], content: "" } });
    setTool("select");
    selectAnnot(res.annot);
    openComment(res.annot, true);
    return;
  }
  if (S.tool === "addtext") return typewriter(hit);
}

function editorBox(hit, r, opts) {
  closeEditor(true);
  const pg = doc().pages[hit.p];
  const ta = document.createElement("textarea");
  ta.className = "inline-editor" + (opts.wrap ? " wrap" : "");
  ta.spellcheck = true;
  ta.value = opts.text || "";
  place(ta, r, pg);
  if (!opts.fixedSize) { ta.style.width = "auto"; ta.style.height = "auto"; }
  hit.el.querySelector(".edit-layer").appendChild(ta);
  const bar = document.createElement("div");
  bar.className = "edit-style";
  hit.el.querySelector(".edit-layer").appendChild(bar);
  const st = { size: opts.size || 12, family: opts.family || "sans", bold: !!opts.bold, italic: !!opts.italic, color: opts.color || "#1b2130", changed: false };
  const apply = () => {
    ta.style.fontSize = `calc(var(--s) * ${st.size}px)`;
    ta.style.fontFamily = { sans: "Arial, sans-serif", serif: "'Times New Roman', serif", mono: "'Courier New', monospace" }[st.family];
    ta.style.fontWeight = st.bold ? 700 : 400;
    ta.style.fontStyle = st.italic ? "italic" : "normal";
    ta.style.color = st.color;
    if (!opts.fixedSize) { ta.style.height = "auto"; ta.style.height = ta.scrollHeight + 2 + "px"; ta.style.width = "auto"; ta.style.width = Math.max(ta.scrollWidth + 6, 60) + "px"; }
  };
  bar.innerHTML = `<select data-k="family" title="Font"><option value="sans">Sans</option><option value="serif">Serif</option><option value="mono">Mono</option></select>
    <input type="number" data-k="size" min="4" max="200" step="0.5" title="Size (pt)">
    ${opts.noStyle ? "" : `<button class="tbtn" data-k="bold" title="Bold">B</button><button class="tbtn" data-k="italic" title="Italic"><i>I</i></button>`}
    <input type="color" data-k="color" title="Colour"><button class="ok">${esc(opts.ok || "Done")}</button>`;
  bar.querySelector("[data-k=family]").value = st.family;
  bar.querySelector("[data-k=size]").value = st.size;
  bar.querySelector("[data-k=color]").value = st.color;
  $$(".tbtn", bar).forEach((b) => b.classList.toggle("on", st[b.dataset.k]));
  bar.addEventListener("input", (e) => {
    const k = e.target.dataset.k;
    if (!k) return;
    st[k] = k === "size" ? Number(e.target.value) || st.size : e.target.value;
    if (k === "family") st.familyChanged = true;
    st.changed = true; apply(); ta.focus();
  });
  bar.addEventListener("pointerdown", (e) => { if (e.target.tagName === "BUTTON") e.preventDefault(); });
  bar.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.classList.contains("ok")) return finish(true);
    st[b.dataset.k] = !st[b.dataset.k];
    b.classList.toggle("on", st[b.dataset.k]);
    st.changed = true; apply(); ta.focus();
  });
  const s = scale();
  bar.style.left = r[0] * s + "px";
  bar.style.top = Math.max(0, r[1] * s - 42) + "px";
  if (r[1] * s < 44) bar.style.top = (r[3] * s + 6) + "px";
  let done = false;
  let committed = Promise.resolve();
  const did = S.active;   // commit to this document even if another tab is shown by then
  const finish = (ok) => {
    if (done) return committed;
    done = true;
    T.editor = null;
    ta.remove(); bar.remove();
    if (ok) committed = Promise.resolve().then(() => opts.commit(ta.value, st, did)).catch(fail);
    else opts.cancel && opts.cancel();
    return committed;
  };
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish(false); }
    if (e.key === "Enter" && (e.ctrlKey || opts.enterCommits && !e.shiftKey)) { e.preventDefault(); finish(true); }
  });
  ta.addEventListener("input", apply);
  ta.addEventListener("blur", () => setTimeout(() => { if (!done && !bar.contains(document.activeElement) && document.activeElement !== ta) finish(true); }, 120));
  T.editor = { finish };
  apply();
  setTimeout(() => { ta.focus(); if (opts.selectAll) ta.select(); else ta.setSelectionRange(ta.value.length, ta.value.length); }, 20);
  return ta;
}
/* Ends an open in-place editor; the returned promise settles once its change has reached the document. */
function closeEditor(commit) { return T.editor ? T.editor.finish(commit) : Promise.resolve(); }

function typewriter(hit) {
  editorBox(hit, [hit.pt.x, hit.pt.y, hit.pt.x + 60, hit.pt.y + 16], {
    size: S.style.textSize || 12, family: S.style.font, color: S.style.textColor || "#1b2130", ok: "Add",
    commit: async (text, st, did) => {
      if (!text.trim()) return;
      S.style.textSize = st.size; S.style.font = st.family; S.style.textColor = st.color;
      await api("add_text", { d: did, p: hit.p, point: [hit.pt.x, hit.pt.y], text, size: st.size, family: st.family, bold: st.bold, italic: st.italic, color: st.color });
    },
  });
}

function textboxEditor(p, rect) {
  const el = V.els[p];
  editorBox({ p, el }, rect, {
    fixedSize: true, wrap: true, size: S.style.size || 12, color: "#1b2130", noStyle: true, ok: "Add",
    commit: async (text, st, did) => {
      if (!text.trim()) return;
      const res = await api("annot_add", { d: did, p, kind: "freetext", o: { rect, text, size: st.size, textcolor: st.color, font: st.family, fill: S.style.fill } });
      S.style.size = st.size;
      return res;
    },
  });
}

function editFreeText(a) {
  const el = V.els[a.p];
  selectAnnot(null);
  editorBox({ p: a.p, el }, a.r, {
    fixedSize: true, wrap: true, text: a.content, size: a.size || 12, color: a.textcolor || "#1b2130", noStyle: true, selectAll: true,
    commit: async (text, st, did) => { await api("annot_update", { d: did, p: a.p, id: a.id, o: { text, size: st.size, textcolor: st.color } }); },
  });
}

/* Edit text: hover shows the line, click opens it in place. */
function onHover(e) {
  if (S.tool !== "edittext" || T.editor) return;
  const hit = pageOf(e);
  $$(".line-hover").forEach((x) => x.remove());
  if (!hit) return;
  const info = view().pinfo[hit.p];
  if (!info || !info.text) return;
  const l = info.text.find((l) => hit.pt.x >= l.r[0] - 1 && hit.pt.x <= l.r[2] + 1 && hit.pt.y >= l.r[1] - 1 && hit.pt.y <= l.r[3] + 1);
  if (!l) return;
  const box = document.createElement("div");
  box.className = "line-hover";
  place(box, [l.r[0] - 1.5, l.r[1] - 1, l.r[2] + 1.5, l.r[3] + 1], doc().pages[hit.p]);
  hit.el.querySelector(".edit-layer").appendChild(box);
}

async function editTextAt(hit) {
  $$(".line-hover").forEach((x) => x.remove());
  const line = await api("line_at", { d: doc().id, p: hit.p, pt: [hit.pt.x, hit.pt.y] });
  if (!line) return toast("There is no text here. Use Add text to type something new.", { icon: "editText" });
  const pt = [hit.pt.x, hit.pt.y];
  editorBox(hit, [line.r[0] - 1, line.r[1] - 1, line.r[2] + 1, line.r[3] + 1], {
    text: line.text.replace(/\s+$/, ""), size: line.size, family: line.family, bold: line.bold, italic: line.italic, color: line.color || "#000000",
    enterCommits: true, ok: "Apply",
    commit: async (text, st, did) => {
      if (text === line.text.replace(/\s+$/, "") && !st.changed) return;
      const body = { d: did, p: hit.p, point: pt, text, size: st.size, color: st.color };
      if (st.changed) Object.assign(body, { bold: st.bold, italic: st.italic });
      if (st.familyChanged) body.family = st.family;
      await api("edit_line", body);
    },
  });
}

/* ------------------------------------------------------------------ annotation selection, move, resize */
function selectAnnot(a) {
  S.sel = a ? { ...a } : null;
  $$(".sel-box").forEach((x) => x.remove());
  if (!a) { hideFloat(); document.dispatchEvent(new Event("annot-selected")); return; }
  getSelection().removeAllRanges();
  drawSelection();
  placeAnnotBar();
  document.dispatchEvent(new Event("annot-selected"));
}

function drawSelection() {
  $$(".sel-box").forEach((x) => x.remove());
  const a = S.sel;
  if (!a || !V.els[a.p]) return;
  const pg = doc().pages[a.p];
  const box = document.createElement("div");
  const fixed = MARKUP_KINDS.has(a.kind);
  box.className = "sel-box" + (fixed ? " fixed" : "");
  place(box, [a.r[0] - 2, a.r[1] - 2, a.r[2] + 2, a.r[3] + 2], pg);
  if (!fixed && a.kind !== "Note") box.innerHTML = ["nw", "n", "ne", "e", "se", "s", "sw", "w"].map((h) => `<i class="h" data-h="${h}"></i>`).join("");
  box.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault(); e.stopPropagation();
    if (fixed) return;
    startMove(e, { p: a.p, el: V.els[a.p], pt: toPage(V.els[a.p], e.clientX, e.clientY) }, e.target.dataset.h || "move");
  });
  box.addEventListener("dblclick", (e) => { e.stopPropagation(); if (a.type === 2) editFreeText(a); else openComment(a); });
  V.els[a.p].querySelector(".ann-layer").appendChild(box);
  V.els[a.p].querySelector(".ann-layer").style.pointerEvents = "none";
  box.style.pointerEvents = "auto";
}

function startMove(e, hit, handle) {
  const a = S.sel;
  if (!a || MARKUP_KINDS.has(a.kind)) return;
  const pg = doc().pages[a.p];
  const start = hit.pt, r0 = [...a.r];
  let r = r0, moved = false;
  const box = $(".sel-box");
  hideFloat();
  const move = (ev) => {
    const pt = toPage(hit.el, ev.clientX, ev.clientY);
    const dx = pt.x - start.x, dy = pt.y - start.y;
    if (!moved && Math.hypot(dx, dy) < 2) return;
    moved = true;
    let [x0, y0, x1, y1] = r0;
    if (handle === "move") { x0 += dx; x1 += dx; y0 += dy; y1 += dy; }
    else {
      if (handle.includes("w")) x0 += dx;
      if (handle.includes("e")) x1 += dx;
      if (handle.includes("n")) y0 += dy;
      if (handle.includes("s")) y1 += dy;
      if (ev.shiftKey && handle.length === 2) { const k = (r0[3] - r0[1]) / (r0[2] - r0[0]); if (handle.includes("n")) y0 = y1 - (x1 - x0) * k; else y1 = y0 + (x1 - x0) * k; }
    }
    r = [Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)];
    if (r[2] - r[0] < 4) r[2] = r[0] + 4;
    if (r[3] - r[1] < 4) r[3] = r[1] + 4;
    place(box, [r[0] - 2, r[1] - 2, r[2] + 2, r[3] + 2], pg);
  };
  const up = async () => {
    removeEventListener("pointermove", move); removeEventListener("pointerup", up);
    T.drag = null;
    if (!moved) { placeAnnotBar(); return; }
    try {
      const res = await api("annot_update", { d: doc().id, p: a.p, id: a.id, o: { rect: r } });
      selectAnnot(res.annot);
    } catch (err) { fail(err); selectAnnot(a); }
  };
  T.drag = true;
  addEventListener("pointermove", move); addEventListener("pointerup", up);
}

/* the floating bar for a selected annotation: colour, fill, width, opacity, comment, delete */
function placeAnnotBar() {
  const a = S.sel;
  if (!a || !V.els[a.p]) return;
  const bar = $("#floatbar");
  const shape = ["Rectangle", "Ellipse", "Polygon"].includes(a.kind);
  const stroked = ["Rectangle", "Ellipse", "Polygon", "Line", "Drawing", "Polyline"].includes(a.kind);
  const colors = MARKUP_KINDS.has(a.kind) || a.kind === "Note" ? MARK_COLORS.concat(["#e2452f"]) : INK_COLORS;
  const canColor = !["Stamp", "Signature", "Text box", "Redaction mark"].includes(a.kind);
  bar.innerHTML = `${canColor ? colors.map((c) => `<button class="sw-btn" data-c="${c}" title="${c}"><span class="swatch${(a.stroke || "").toLowerCase() === c ? " on" : ""}" style="background:${c};width:18px;height:18px;border-radius:5px"></span></button>`).join("") + '<span class="sep"></span>' : ""}
    ${shape ? `<button data-a="fill" title="Fill">${icon("palette")}Fill</button>` : ""}
    ${stroked ? `<button data-a="width" title="Line width">${icon("minus")}${a.width || 1}pt</button>` : ""}
    <button data-a="opacity" title="Opacity">${icon("eye")}${Math.round((a.opacity ?? 1) * 100)}%</button>
    ${a.type === 2 ? `<button data-a="edit" title="Edit text">${icon("pencil")}Edit</button>` : ""}
    <button data-a="comment" title="Comment">${icon("note")}${a.content && a.type !== 2 ? "1" : ""}</button>
    <button data-a="delete" title="Delete (Del)">${icon("trash")}</button>`;
  bar.onclick = async (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.dataset.c) return updateSel({ color: b.dataset.c });
    const act = b.dataset.a;
    if (act === "delete") return deleteSel();
    if (act === "comment") return openComment(a);
    if (act === "edit") return editFreeText(a);
    if (act === "fill") return menuAt(b, [{ label: "No fill", action: () => updateSel({ fill: null }) }, ...["#ffffff", "#fff3b0", "#d9f2d0", "#d6ecff", "#ffe0e8", "#1b2130"].map((c) => ({ label: c, icon: "palette", action: () => updateSel({ fill: c }) }))]);
    if (act === "width") return menuAt(b, [0.5, 1, 1.5, 2, 3, 4, 6, 8].map((w) => ({ label: w + " pt", check: w === a.width, action: () => updateSel({ width: w }) })));
    if (act === "opacity") return menuAt(b, [100, 80, 60, 40, 25].map((o) => ({ label: o + " %", action: () => updateSel({ opacity: o / 100 }) })));
  };
  const el = V.els[a.p], r = el.getBoundingClientRect(), s = scale();
  positionFloat(r.left + (a.r[0] + a.r[2]) / 2 * s, r.top + a.r[1] * s - 54 < 70 ? r.top + a.r[3] * s + 12 : r.top + a.r[1] * s - 54);
}

async function updateSel(o) {
  const a = S.sel;
  if (!a) return;
  try {
    const res = await api("annot_update", { d: doc().id, p: a.p, id: a.id, o });
    selectAnnot(res.annot);
    if (o.color && !MARKUP_KINDS.has(a.kind)) S.style.stroke = o.color;
  } catch (e) { fail(e); }
}
async function deleteSel() {
  const a = S.sel;
  if (!a) return;
  selectAnnot(null);
  await api("annot_delete", { d: doc().id, p: a.p, id: a.id }).catch(fail);
}

async function openComment(a, isNew) {
  const r = await modal({
    title: isNew ? "New note" : `${a.kind} comment`, icon: "note",
    body: `<div class="fld"><textarea name="content" rows="6" placeholder="Write a comment…">${esc(a.content || "")}</textarea></div>
      <p class="muted" style="font-size:12px">${esc(a.author || S.settings.author || "")}${a.date ? " · " + esc(pdfDate(a.date)) : ""} · page ${a.p + 1}</p>`,
    buttons: [isNew ? { label: "Remove note", value: "delete", ghost: true } : { label: "Cancel", value: null, ghost: true }, { label: "Save", value: "form", primary: true }],
  });
  if (r === "delete") { S.sel = a; return deleteSel(); }
  if (!r) return;
  try {
    const res = await api("annot_update", { d: doc().id, p: a.p, id: a.id, o: { content: r.content } });
    if (S.sel && S.sel.id === a.id) selectAnnot(res.annot);
  } catch (e) { fail(e); }
}

/* ------------------------------------------------------------------ tool set-up dialogs: stamp, signature, image, link, crop */
const stampCache = {};
async function stampPreview(label) {
  if (!stampCache[label]) stampCache[label] = await api("stamp_preview", { label });
  return stampCache[label];
}

async function pickStamp(anchor) {
  const labels = ["Approved", "Reviewed", "Final", "Draft", "For comment", "Confidential", "Not approved", "Void", "Sign here"];
  const grid = document.createElement("div");
  grid.innerHTML = `<div class="mh" style="padding:6px 8px 2px;font-size:11px;font-weight:600;color:var(--text-3);text-transform:uppercase;letter-spacing:.5px">Stamps</div>
    <div class="stamp-grid">${labels.map((l) => `<button data-l="${esc(l)}" title="${esc(l)}"></button>`).join("")}</div>
    <div class="stamp-custom"><input placeholder="Your own stamp text…" maxlength="28"><button class="btn sm primary">Use</button></div>`;
  const m = anchor ? menuAt(anchor, [], { node: grid }) : showMenu(innerWidth / 2 - 210, 120, [], { node: grid });
  const choose = async (label) => {
    closeMenu();
    S.style.stamp = label;
    const pv = await stampPreview(label);
    setTool("stamp", { preview: pv.img, ratio: pv.ratio });
  };
  for (const b of $$(".stamp-grid button", m)) {
    b.onclick = () => choose(b.dataset.l);
    stampPreview(b.dataset.l).then((pv) => { b.innerHTML = `<img src="${pv.img}" alt="${esc(b.dataset.l)}">`; }).catch(() => (b.textContent = b.dataset.l));
  }
  const inp = $(".stamp-custom input", m);
  const useCustom = () => inp.value.trim() && choose(inp.value.trim());
  $(".stamp-custom button", m).onclick = useCustom;
  inp.onkeydown = (e) => e.key === "Enter" && useCustom();
}

async function signatureDialog() {
  // the remembered signature lives on the server, encrypted for this Windows user (DPAPI); an older copy in the
  // window's storage moves there once and is removed
  let saved = null;
  try {
    const old = localStorage.getItem("washi.signature");
    if (old) { await api("signature_remember", { png: old }); localStorage.removeItem("washi.signature"); }
  } catch (e) { /* empty */ }
  try { saved = (await api("signature_saved")).png; } catch (e) { /* empty */ }
  const body = document.createElement("div");
  body.innerHTML = `<div class="seg" style="margin:0 0 12px"><button class="on" data-m="draw">Draw</button><button data-m="type">Type</button><button data-m="image">Image</button>${saved ? '<button data-m="saved">Saved</button>' : ""}</div>
    <div data-p="draw"><canvas class="sig-pad" width="900" height="300"></canvas>
      <div class="sig-tools"><span class="muted" style="flex:1">Sign with mouse, pen or finger</span>
      <button class="swatch on" data-ink="#111111" style="background:#111"></button><button class="swatch" data-ink="#1c3faa" style="background:#1c3faa"></button>
      <button class="btn sm ghost" data-clear>Clear</button></div></div>
    <div data-p="type" class="hidden"><div class="fld"><input data-type placeholder="Your name" value="${esc(S.settings.author || "")}" style="font-size:16px"></div>
      <div class="fld"><select data-font><option value="'Ink Free'">Ink Free</option><option value="'Segoe Script'">Segoe Script</option><option value="'Lucida Handwriting'">Lucida Handwriting</option><option value="'Segoe Print'">Segoe Print</option></select></div>
      <canvas class="sig-pad" data-typed width="900" height="300" style="border-style:solid"></canvas></div>
    <div data-p="image" class="hidden"><p>Use a scan or photo of your signature (a PNG with a transparent background looks best).</p><button class="btn" data-pick>${icon("image")}Choose image…</button><div data-img style="margin-top:10px"></div></div>
    <div data-p="saved" class="hidden"><img data-saved style="max-width:100%;max-height:160px;background:#fff;border-radius:8px;padding:6px">
      <div style="margin-top:8px"><button class="btn sm ghost" data-forget>Forget the saved signature</button></div></div>
    <label class="checks" style="margin-top:12px"><label><input type="checkbox" data-remember> Remember this signature on this PC (encrypted for your Windows account)</label></label>`;
  let mode = "draw", ink = "#111111", imgData = null;
  const pad = $("canvas.sig-pad", body), ctx = pad.getContext("2d");
  let drawing = false, dirty = false;
  ctx.lineCap = ctx.lineJoin = "round";
  const pos = (e) => { const r = pad.getBoundingClientRect(); return [(e.clientX - r.left) * pad.width / r.width, (e.clientY - r.top) * pad.height / r.height]; };
  pad.onpointerdown = (e) => { drawing = true; dirty = true; pad.setPointerCapture(e.pointerId); const [x, y] = pos(e); ctx.beginPath(); ctx.moveTo(x, y); ctx.strokeStyle = ink; ctx.lineWidth = 5 * (e.pressure && e.pointerType === "pen" ? 0.5 + e.pressure : 1); };
  pad.onpointermove = (e) => { if (!drawing) return; const [x, y] = pos(e); ctx.lineTo(x, y); ctx.stroke(); };
  pad.onpointerup = () => { drawing = false; };
  const typed = $("canvas[data-typed]", body), tctx = typed.getContext("2d");
  const drawTyped = () => {
    tctx.clearRect(0, 0, typed.width, typed.height);
    tctx.fillStyle = ink;
    tctx.font = `110px ${$("[data-font]", body).value}`;
    tctx.textBaseline = "middle";
    const t = $("[data-type]", body).value;
    const w = tctx.measureText(t).width;
    if (w > typed.width - 40) tctx.font = `${110 * (typed.width - 40) / w}px ${$("[data-font]", body).value}`;
    tctx.fillText(t, 20, typed.height / 2);
  };
  $("[data-type]", body).oninput = drawTyped;
  $("[data-font]", body).onchange = drawTyped;
  body.addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.m) {
      mode = b.dataset.m;
      $$(".seg button", body).forEach((x) => x.classList.toggle("on", x === b));
      $$("[data-p]", body).forEach((p) => p.classList.toggle("hidden", p.dataset.p !== mode));
      if (mode === "type") setTimeout(drawTyped, 50);
      if (mode === "saved") $("[data-saved]", body).src = saved;
    }
    if (b.dataset.ink) { ink = b.dataset.ink; $$("[data-ink]", body).forEach((x) => x.classList.toggle("on", x === b)); drawTyped(); }
    if (b.hasAttribute("data-clear")) { ctx.clearRect(0, 0, pad.width, pad.height); dirty = false; }
    if (b.hasAttribute("data-forget")) {
      await api("signature_remember", { png: null });
      saved = null;
      $('[data-m="saved"]', body)?.remove();
      $('[data-m="draw"]', body).click();
      toast("The saved signature was removed");
    }
    if (b.hasAttribute("data-pick")) {
      const r = await api("pick_image");
      if (r && r.preview) { imgData = r.preview; $("[data-img]", body).innerHTML = `<img src="${r.preview}" style="max-width:100%;max-height:150px;background:#fff;border-radius:8px">`; }
      else if (r) toast("That image is too large to use as a signature", { err: true });
    }
  });
  setTimeout(() => $$(".swatch", body).forEach((s) => (s.style.width = s.style.height = "22px")));
  const ok = await modal({ title: "Your signature", icon: "sign", body, wide: true,
    buttons: [{ label: "Cancel", value: null, ghost: true }, { label: "Place signature", value: true, primary: true }] });
  if (!ok) return null;
  let url = null;
  if (mode === "draw") { if (!dirty) return toast("Draw your signature first", { err: true }), null; url = trimCanvas(pad); }
  else if (mode === "type") { if (!$("[data-type]", body).value.trim()) return null; url = trimCanvas(typed); }
  else if (mode === "image") url = imgData;
  else url = saved;
  if (!url) return null;
  if ($("[data-remember]", body).checked && url !== saved) { try { await api("signature_remember", { png: url }); } catch (e) { /* empty */ } }
  const img = new Image();
  await new Promise((r) => { img.onload = r; img.src = url; });
  return { png: url, ratio: img.width / img.height, preview: url };
}

function trimCanvas(c) {
  const ctx = c.getContext("2d");
  const { data, width, height } = ctx.getImageData(0, 0, c.width, c.height);
  let x0 = width, y0 = height, x1 = 0, y1 = 0;
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) if (data[(y * width + x) * 4 + 3] > 8) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  if (x1 <= x0) return c.toDataURL("image/png");
  const pad = 8, out = document.createElement("canvas");
  out.width = x1 - x0 + pad * 2; out.height = y1 - y0 + pad * 2;
  out.getContext("2d").drawImage(c, x0 - pad, y0 - pad, out.width, out.height, 0, 0, out.width, out.height);
  return out.toDataURL("image/png");
}

async function linkDialog(p, rect) {
  const r = await modal({ title: "Add link", icon: "link",
    body: `<div class="radio-cards" style="grid-template-columns:1fr 1fr;margin-bottom:12px"><label><input type="radio" name="kind" value="web" checked><b>Web address</b><span>Opens a website or e-mail</span></label>
      <label><input type="radio" name="kind" value="page"><b>Page in this PDF</b><span>Jumps to a page</span></label></div>
      <div class="fld"><label>Web address or page number</label><input name="target" placeholder="https://… or 3"></div>`,
    buttons: [{ label: "Cancel", value: null, ghost: true }, { label: "Add link", value: "form", primary: true }] });
  if (!r || !r.target.trim()) return;
  const body = { d: doc().id, p, rect };
  if (r.kind === "page") body.page = clamp(parseInt(r.target, 10) - 1 || 0, 0, doc().pages.length - 1);
  else body.uri = r.target.trim();
  await api("link_add", body);
}

async function cropDialog(p, rect) {
  const n = doc().pages.length;
  const r = await modal({ title: "Crop pages", icon: "crop",
    body: `<p>Keep the area you drew (${Math.round(rect[2] - rect[0])} × ${Math.round(rect[3] - rect[1])} pt). Content outside is hidden, not deleted, so you can undo the crop later.</p>
      <div class="radio-cards"><label><input type="radio" name="which" value="this" checked><b>This page</b><span>Page ${p + 1}</span></label>
      <label><input type="radio" name="which" value="all"><b>All pages</b><span>${n} pages</span></label><label><input type="radio" name="which" value="sel"><b>Selected</b><span>In the page panel</span></label></div>`,
    buttons: [{ label: "Cancel", value: null, ghost: true }, { label: "Crop", value: "form", primary: true }] });
  if (!r) return;
  const pages = r.which === "all" ? [...Array(n).keys()] : r.which === "sel" && view().selPages.size ? [...view().selPages] : [p];
  await api("crop", { d: doc().id, p, rect, pages });
  setTool("select");
}
