/* Washi panels: ribbon, side panels, dialogs, command palette and the start page. */
"use strict";
const RIBBON = [
  { id: "home", label: "Home", groups: [["file.open", "file.save", "file.saveas", "file.print"], ["edit.undo", "edit.redo"], ["tool.select", "tool.hand"],
    ["tool.highlight", "tool.note", "tool.textbox", "tool.edittext"], ["view.zoomin", "view.zoomout", "view.fitwidth", "view.fitpage", "view.ebooktext"], ["nav.find", "ai.summary"]] },
  { id: "comment", label: "Comment", groups: [["tool.highlight", "tool.underline", "tool.strikeout", "tool.squiggly", "tool.area"], ["tool.note", "tool.textbox", "tool.stamp"],
    ["tool.rect", "tool.ellipse", "tool.line", "tool.arrow", "tool.ink"], ["side.comments", "doc.flatten"]] },
  { id: "edit", label: "Edit", groups: [["tool.edittext", "tool.addtext", "tool.whiteout"], ["tool.image", "tool.sign", "tool.link"], ["page.watermark", "page.numbers"], ["doc.properties"]] },
  { id: "pages", label: "Pages", groups: [["page.rotateccw", "page.rotatecw"], ["page.blank", "page.insertfile", "page.duplicate"], ["page.extract", "page.split", "page.delete"], ["tool.crop", "page.uncrop"], ["page.numbers", "page.watermark"]] },
  { id: "forms", label: "Forms", groups: [["tool.field", "tool.fieldcheck", "tool.fieldcombo"], ["doc.flatten"]] },
  { id: "protect", label: "Protect", groups: [["tool.redact", "doc.redactapply"], ["doc.protect", "doc.unprotect"], ["doc.properties"]] },
  { id: "convert", label: "Convert", groups: [["export.docx", "export.txt", "export.md", "export.html", "export.png"], ["export.pdf", "doc.optimize"], ["file.merge", "file.fromimages"], ["side.attachments"]] },
];
const STYLE_TOOLS = { markup: ["highlight", "area"], ink: ["rect", "ellipse", "line", "arrow", "ink"], text: ["textbox"] };

function renderRibbon() {
  const tabs = $(".ribbon-tabs");
  tabs.innerHTML = RIBBON.map((t) => `<button class="rtab${t.id === S.ribbonTab ? " active" : ""}" data-tab="${t.id}">${t.label}</button>`).join("") +
    `<span class="spacer"></span><button class="icon-btn sm" data-cmd="edit.undo" title="Undo (Ctrl Z)">${icon("undo")}</button><button class="icon-btn sm" data-cmd="edit.redo" title="Redo (Ctrl Y)">${icon("redo")}</button><button class="icon-btn sm" data-cmd="file.save" title="Save (Ctrl S)">${icon("save")}</button><button class="icon-btn sm" data-cmd="file.saveas" title="Save as… (Ctrl Shift S)">${icon("saveAs")}</button>`;
  tabs.onclick = (e) => { const b = e.target.closest("[data-tab]"); if (b) setRibbonTab(b.dataset.tab); };
  setRibbonTab(S.ribbonTab);
}

function setRibbonTab(id) {
  S.ribbonTab = id;
  $$(".rtab").forEach((b) => b.classList.toggle("active", b.dataset.tab === id));
  const t = RIBBON.find((r) => r.id === id) || RIBBON[0];
  // every button is drawn; refreshState() shows/hides the conditional ones (e-book text size, AI) as things change
  $(".ribbon-body").innerHTML = t.groups.map((g) => `<div class="rgroup">${g.filter((c) => CMD[c]).map(rbtn).join("")}</div>`).join("");
  refreshState();
}
function rbtn(id) {
  const c = CMD[id];
  const k = c.keys ? ` (${kbdLabel(c.keys)})` : "";
  return `<button class="rbtn${S.tool && id === "tool." + S.tool ? " on" : ""}${c.hidden && c.hidden() ? " hidden" : ""}" data-cmd="${id}" title="${esc(c.label + k)}${c.tip ? "\n" + esc(c.tip) : ""}">${icon(c.icon)}<span>${esc(c.short || c.label)}</span></button>`;
}

/* colour / width / fill for the active drawing tool, inside the floating tool pill above the page */
function renderStyleGroup() {
  const g = $("#styleGroup");
  if (!g) return;
  const t = S.tool;
  let html = "";
  if (STYLE_TOOLS.markup.includes(t)) {
    html = `<div class="rstack"><span class="muted" style="font-size:11px;padding-left:2px">Colour</span><div class="swatches">${MARK_COLORS.map((c) => `<button class="swatch${c === S.style.color ? " on" : ""}" data-sc="color" data-v="${c}" style="background:${c}"></button>`).join("")}</div></div>`;
  } else if (STYLE_TOOLS.ink.includes(t) || t === "textbox") {
    html = `<div class="rstack"><span class="muted" style="font-size:11px;padding-left:2px">${t === "textbox" ? "Fill" : "Colour"}</span><div class="swatches">${(t === "textbox" ? [null, "#ffffff", "#fff3b0", "#d6ecff", "#ffe0e8"] : INK_COLORS.slice(0, 7)).map((c) =>
      `<button class="swatch${c === null ? " none" : ""}${(t === "textbox" ? S.style.fill : S.style.stroke) === c ? " on" : ""}" data-sc="${t === "textbox" ? "fill" : "stroke"}" data-v="${c ?? ""}" style="background:${c || "transparent"}"></button>`).join("")}
      <span class="swatch custom" title="Custom colour"><input type="color" data-sc="${t === "textbox" ? "fill" : "stroke"}"></span></div></div>`;
    if (t !== "textbox") html += `<div class="rstack"><span class="muted" style="font-size:11px">Width</span><select data-sw>${[0.5, 1, 1.5, 2, 3, 4, 6, 8].map((w) => `<option${w === S.style.width ? " selected" : ""}>${w}</option>`).join("")}</select></div>`;
    if (t === "rect" || t === "ellipse") html += `<div class="rstack"><span class="muted" style="font-size:11px">Fill</span><div class="swatches">${[null, "#ffffff", "#fff3b0", "#d6ecff", "#ffe0e8"].map((c) => `<button class="swatch${c === null ? " none" : ""}${S.style.fill === c ? " on" : ""}" data-sc="fill" data-v="${c ?? ""}" style="background:${c || "transparent"}"></button>`).join("")}</div></div>`;
  }
  g.innerHTML = html;
  g.classList.toggle("hidden", !html);
  g.onclick = (e) => {
    const b = e.target.closest("[data-sc]");
    if (!b || b.tagName === "INPUT") return;
    S.style[b.dataset.sc] = b.dataset.v || null;
    renderStyleGroup();
  };
  g.oninput = (e) => {
    if (e.target.dataset.sw !== undefined) S.style.width = Number(e.target.value);
    else if (e.target.type === "color") { S.style[e.target.dataset.sc] = e.target.value; }
  };
  g.onchange = (e) => { if (e.target.type === "color") renderStyleGroup(); };
}

/* ------------------------------------------------------------------ side panels */
const SIDE = {
  thumbs: { title: "Pages", render: renderThumbs },
  outline: { title: "Bookmarks", render: renderOutline },
  search: { title: "Find", render: renderSearch },
  comments: { title: "Comments", render: renderComments },
  attachments: { title: "Attachments", render: renderAttachments },
  help: { title: "Help", render: renderHelp },
};

function openSide(name, toggle) {
  if (toggle && S.side === name && S.sideOpen) { S.sideOpen = false; }
  else { S.side = name; S.sideOpen = true; }
  $("#side").classList.toggle("collapsed", !S.sideOpen);
  $$("#rail [data-side]").forEach((b) => b.classList.toggle("on", S.sideOpen && b.dataset.side === S.side));
  if (S.sideOpen) renderSide();
  setTimeout(() => { if (doc() && view().fit !== "custom") { view().zoom = fitZoom(view(), doc(), view().fit); sizePages(); rerenderVisible(); } }, 10);
}
function renderSide() {
  if (!S.sideOpen || !doc()) return;
  const p = SIDE[S.side];
  const body = $("#sideBody");
  // each panel installs its own handlers; drop the previous panel's first
  for (const ev of ["onclick", "ondblclick", "oncontextmenu", "oninput", "ondragstart", "ondragover", "ondrop", "ondragend"]) body[ev] = null;
  $("#side").onclick = null;
  if (body._io) { body._io.disconnect(); body._io = null; }
  $("#sideTitle").textContent = p.title;
  $("#sideTools").innerHTML = "";
  p.render(body);
}

/* Pages panel: thumbnails, multi-select, drag to reorder, right-click actions */
function renderThumbs(body) {
  const d = doc(), v = view();
  $("#sideTools").innerHTML = `<button class="icon-btn sm" title="Rotate selected" data-cmd="page.rotatecw">${icon("rotateCw")}</button><button class="icon-btn sm" title="Insert blank page" data-cmd="page.blank">${icon("pagePlus")}</button><button class="icon-btn sm" title="Delete selected" data-cmd="page.delete">${icon("trash")}</button>`;
  body.innerHTML = `<div class="thumbs">${d.pages.map((pg, i) => `<div class="thumb-item${i === v.page ? " cur" : ""}${v.selPages.has(i) ? " sel" : ""}" data-p="${i}" draggable="true">
    <div class="tframe" style="aspect-ratio:${pg.w}/${pg.h}"><img loading="lazy" draggable="false" alt=""></div><span>${esc(pg.label)}</span></div>`).join("")}</div>`;
  const io = new IntersectionObserver((ents) => ents.forEach((e) => {
    if (!e.isIntersecting) return;
    const i = +e.target.dataset.p, pg = doc().pages[i], img = e.target.querySelector("img");
    if (!pg) return;
    const want = pageURL(doc().id, i, Math.round(200 / Math.max(pg.w, pg.h) * dpr() * 100) / 100, pg.pv, "jpg");
    if (img.dataset.src !== want) { img.dataset.src = want; img.src = want; }
  }), { root: body, rootMargin: "300px" });
  $$(".thumb-item", body).forEach((el) => io.observe(el));
  body._io && body._io.disconnect();
  body._io = io;
  let anchor = v.page;
  body.onclick = (e) => {
    const it = e.target.closest(".thumb-item");
    if (!it) return;
    const i = +it.dataset.p;
    if (e.ctrlKey) { v.selPages.has(i) ? v.selPages.delete(i) : v.selPages.add(i); anchor = i; }
    else if (e.shiftKey) { v.selPages = new Set(); for (let k = Math.min(anchor, i); k <= Math.max(anchor, i); k++) v.selPages.add(k); }
    else { v.selPages = new Set([i]); anchor = i; gotoPage(i); }
    markThumbs();
  };
  body.oncontextmenu = (e) => {
    const it = e.target.closest(".thumb-item");
    if (!it) return;
    e.preventDefault();
    const i = +it.dataset.p;
    if (!v.selPages.has(i)) { v.selPages = new Set([i]); markThumbs(); }
    const n = v.selPages.size;
    showMenu(e.clientX, e.clientY, [
      { header: n > 1 ? `${n} pages` : `Page ${i + 1}` },
      { label: "Rotate right", icon: "rotateCw", action: () => run("page.rotatecw") },
      { label: "Rotate left", icon: "rotateCcw", action: () => run("page.rotateccw") },
      { label: "Duplicate", icon: "duplicate", action: () => run("page.duplicate") },
      { label: "Insert blank page after", icon: "pagePlus", action: () => api("pages_blank", { d: doc().id, at: Math.max(...v.selPages) + 1 }).catch(fail) },
      { label: "Insert pages from file after…", icon: "insertFile", action: () => api("pages_insert_file", { d: doc().id, at: Math.max(...v.selPages) + 1 }).catch(fail) },
      { label: "Extract to new PDF…", icon: "extract", action: () => run("page.extract") },
      "-",
      { label: n > 1 ? `Delete ${n} pages` : "Delete page", icon: "trash", danger: true, action: () => run("page.delete") },
    ]);
  };
  // drag & drop reordering
  let dragFrom = null;
  body.ondragstart = (e) => {
    const it = e.target.closest(".thumb-item");
    if (!it) return;
    const i = +it.dataset.p;
    if (!v.selPages.has(i)) { v.selPages = new Set([i]); markThumbs(); }
    dragFrom = [...v.selPages];
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/washi-pages", dragFrom.join(","));
  };
  body.ondragover = (e) => {
    if (!dragFrom) return;
    e.preventDefault();
    $$(".drop-before, .drop-after", body).forEach((x) => x.classList.remove("drop-before", "drop-after"));
    const it = e.target.closest(".thumb-item");
    if (!it) return;
    const r = it.getBoundingClientRect();
    it.classList.add(e.clientX < r.left + r.width / 2 ? "drop-before" : "drop-after");
  };
  body.ondrop = async (e) => {
    if (!dragFrom) return;
    e.preventDefault();
    const it = $(".drop-before, .drop-after", body);
    const pages = dragFrom;
    dragFrom = null;
    if (!it) return;
    const to = +it.dataset.p + (it.classList.contains("drop-after") ? 1 : 0);
    it.classList.remove("drop-before", "drop-after");
    try {
      await api("pages_move", { d: doc().id, pages, to });
      const before = to - pages.filter((p) => p < to).length;
      v.selPages = new Set(pages.map((_, k) => before + k));
      renderSide();
    } catch (err) { fail(err); }
  };
  body.ondragend = () => { dragFrom = null; $$(".drop-before, .drop-after", body).forEach((x) => x.classList.remove("drop-before", "drop-after")); };
  setTimeout(() => { const cur = $(".thumb-item.cur", body); cur && cur.scrollIntoView({ block: "nearest" }); }, 30);
}
function markThumbs() {
  const v = view();
  $$("#sideBody .thumb-item").forEach((el) => { const i = +el.dataset.p; el.classList.toggle("cur", i === v.page); el.classList.toggle("sel", v.selPages.has(i)); });
}
const selectedPages = () => { const v = view(); return v.selPages.size ? [...v.selPages].sort((a, b) => a - b) : [v.page]; };

/* Bookmarks */
async function renderOutline(body) {
  const d = doc();
  $("#sideTools").innerHTML = `<button class="icon-btn sm" title="Add a bookmark for this page" data-a="add">${icon("bookmarkPlus")}</button>`;
  body.innerHTML = `<div class="panel-pad muted">Loading…</div>`;
  let items = await api("outline", { d: d.id }).catch(() => []);
  const collapsed = view().collapsed || (view().collapsed = new Set());
  let selIdx = -1;
  const save = async (next) => { const r = await api("outline_set", { d: d.id, items: next }); items = r.outline; draw(); };
  const draw = () => {
    if (!items.length) {
      body.innerHTML = `<div class="panel-empty">${icon("bookmark")}<div>No bookmarks yet.</div><button class="btn sm" style="margin-top:12px" data-a="add">${icon("bookmarkPlus")}Bookmark this page</button></div>`;
      return;
    }
    let hideBelow = 99;
    body.innerHTML = items.map((it, i) => {
      if (it.lvl > hideBelow) return "";
      hideBelow = 99;
      const kids = items[i + 1] && items[i + 1].lvl > it.lvl;
      if (kids && collapsed.has(i)) hideBelow = it.lvl;
      return `<div class="tree-item${kids && !collapsed.has(i) ? " open" : ""}${i === selIdx ? " sel" : ""}" data-i="${i}" style="padding-left:${(it.lvl - 1) * 14 + 4}px">
        <span class="tw">${kids ? icon("chevRight") : ""}</span><span class="tt">${esc(it.title)}</span><span class="tp">${it.p + 1}</span></div>`;
    }).join("") + `<div class="panel-pad muted" style="font-size:11.5px">Double-click to rename · right-click for more</div>`;
  };
  draw();
  const panel = $("#side");
  panel.onclick = async (e) => {
    const a = e.target.closest("[data-a]");
    if (a && a.dataset.a === "add") {
      const title = await promptBox("New bookmark", "Title", `Page ${view().page + 1}`, { icon: "bookmarkPlus" });
      if (title) await save([...items, { lvl: 1, title, p: view().page }]).catch(fail);
    }
  };
  body.onclick = (e) => {
    const it = e.target.closest(".tree-item");
    if (!it) return;
    const i = +it.dataset.i;
    if (e.target.closest(".tw") && it.querySelector(".tw svg")) { collapsed.has(i) ? collapsed.delete(i) : collapsed.add(i); draw(); return; }
    selIdx = i; draw();
    gotoPage(items[i].p);
  };
  body.ondblclick = async (e) => {
    const it = e.target.closest(".tree-item");
    if (!it) return;
    const i = +it.dataset.i;
    const title = await promptBox("Rename bookmark", "Title", items[i].title, { icon: "bookmark" });
    if (title) { items[i].title = title; await save(items).catch(fail); }
  };
  body.oncontextmenu = (e) => {
    const it = e.target.closest(".tree-item");
    if (!it) return;
    e.preventDefault();
    const i = +it.dataset.i;
    const kidsEnd = () => { let j = i + 1; while (j < items.length && items[j].lvl > items[i].lvl) j++; return j; };
    showMenu(e.clientX, e.clientY, [
      { label: "Rename", icon: "pencil", action: () => body.ondblclick({ target: it }) },
      { label: "Point to the current page", icon: "bookmark", action: () => { items[i].p = view().page; save(items).catch(fail); } },
      { label: "Add child bookmark here", icon: "bookmarkPlus", action: async () => { const t = await promptBox("New bookmark", "Title", `Page ${view().page + 1}`); if (t) { items.splice(kidsEnd(), 0, { lvl: items[i].lvl + 1, title: t, p: view().page }); save(items).catch(fail); } } },
      { label: "Indent", icon: "indent", disabled: i === 0 || items[i - 1].lvl < items[i].lvl, action: () => { for (let j = i; j < kidsEnd(); j++) items[j].lvl++; save(items).catch(fail); } },
      { label: "Outdent", icon: "outdent", disabled: items[i].lvl === 1, action: () => { const end = kidsEnd(); for (let j = i; j < end; j++) items[j].lvl--; save(items).catch(fail); } },
      "-",
      { label: "Delete", icon: "trash", danger: true, action: () => { items.splice(i, kidsEnd() - i); save(items).catch(fail); } },
    ]);
  };
}

/* Find */
function renderSearch(body) {
  const v = view();
  body.innerHTML = `<div class="search-box"><input id="findInput" placeholder="Find in document…" value="${esc(v.query)}">
    <div class="row"><label><input type="checkbox" id="findCase" ${v.findCase ? "checked" : ""}> Match case</label><label><input type="checkbox" id="findWhole" ${v.findWhole ? "checked" : ""}> Whole words</label>
    <span class="nav"><button class="icon-btn sm" id="findPrev" title="Previous (Shift Enter)">${icon("chevUp")}</button><button class="icon-btn sm" id="findNext" title="Next (Enter)">${icon("chevDown")}</button></span></div>
    <div class="muted" id="findCount" style="font-size:12px"></div></div><div id="findResults"></div>`;
  const inp = $("#findInput");
  let timer;
  const go = () => { clearTimeout(timer); timer = setTimeout(() => doSearch(inp.value), 220); };
  inp.oninput = go;
  $("#findCase").onchange = (e) => { v.findCase = e.target.checked; doSearch(inp.value, true); };
  $("#findWhole").onchange = (e) => { v.findWhole = e.target.checked; doSearch(inp.value, true); };
  inp.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); stepHit(e.shiftKey ? -1 : 1); } };
  $("#findPrev").onclick = () => stepHit(-1);
  $("#findNext").onclick = () => stepHit(1);
  setTimeout(() => { inp.focus(); inp.select(); }, 30);
  drawResults();
}
async function doSearch(q, force) {
  const v = view(), d = doc();
  if (!force && q === v.query) return;
  v.query = q;
  if (!q.trim()) { v.hits = []; v.hitIdx = -1; drawAllHits(); drawResults(); return; }
  $("#findCount") && ($("#findCount").textContent = "Searching…");
  v.hits = await api("search", { d: d.id, q, case: !!v.findCase, whole: !!v.findWhole }).catch((e) => (fail(e), []));
  v.hitIdx = v.hits.findIndex((h) => h.p >= v.page);
  if (v.hitIdx < 0 && v.hits.length) v.hitIdx = 0;
  drawAllHits();
  drawResults();
  if (v.hitIdx >= 0) showHit();
}
function drawResults() {
  const v = view(), box = $("#findResults");
  if (!box) return;
  $("#findCount").textContent = v.query ? (v.hits.length ? `${v.hitIdx + 1} of ${v.hits.length}${v.hits.length >= 2000 ? "+" : ""} matches` : "No matches") : "";
  const q = v.query.trim();
  const re = q ? new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), v.findCase ? "g" : "gi") : null;
  let last = -1;
  box.innerHTML = v.hits.slice(0, 600).map((h, i) => {
    const head = h.p !== last ? `<div class="group-head">Page ${doc().pages[h.p]?.label || h.p + 1}</div>` : "";
    last = h.p;
    return head + `<div class="result${i === v.hitIdx ? " cur" : ""}" data-i="${i}"><div class="rs">${re ? esc(h.snippet).replace(new RegExp(re.source.replace(/&/g, "&amp;"), re.flags), (m) => `<mark>${m}</mark>`) : esc(h.snippet)}</div></div>`;
  }).join("");
  box.onclick = (e) => { const r = e.target.closest(".result"); if (r) { v.hitIdx = +r.dataset.i; showHit(); drawResults(); } };
}
function stepHit(dir) {
  const v = view();
  if (!v.hits.length) return;
  v.hitIdx = (v.hitIdx + dir + v.hits.length) % v.hits.length;
  showHit();
  drawResults();
  const cur = $("#findResults .result.cur");
  cur && cur.scrollIntoView({ block: "nearest" });
}
function showHit() {
  const v = view(), h = v.hits[v.hitIdx];
  if (!h) return;
  gotoPage(h.p, h.r[1]);
  drawAllHits();
}

/* Comments */
async function renderComments(body) {
  const d = doc();
  body.innerHTML = `<div class="panel-pad muted">Loading…</div>`;
  const all = await api("annots", { d: d.id }).catch(() => []);
  const authors = [...new Set(all.map((a) => a.author).filter(Boolean))];
  const kinds = [...new Set(all.map((a) => a.kind))];
  const draw = () => {
    const q = ($("#cmtFilter")?.value || "").toLowerCase(), kind = $("#cmtKind")?.value || "", who = $("#cmtWho")?.value || "";
    const list = all.filter((a) => (!kind || a.kind === kind) && (!who || a.author === who) && (!q || (a.content + " " + a.kind + " " + a.author).toLowerCase().includes(q)));
    let last = -1;
    $("#cmtList").innerHTML = list.length ? list.map((a) => {
      const head = a.p !== last ? `<div class="group-head">Page ${a.p + 1}</div>` : "";
      last = a.p;
      return head + `<div class="cmt${S.sel && S.sel.id === a.id ? " sel" : ""}" data-id="${a.id}" data-p="${a.p}"><span class="cdot" style="background:${a.stroke || a.fill || "#999"}"></span>
        <div class="cbody"><div class="ckind">${esc(a.kind)}</div><div class="cmeta">${esc(a.author || "")}${a.date ? " · " + esc(pdfDate(a.date)) : ""}</div>${a.content ? `<div class="ctext">${esc(a.content)}</div>` : ""}</div></div>`;
    }).join("") : `<div class="panel-empty">${icon("comments")}<div>${all.length ? "Nothing matches the filter." : "No comments or markup yet. Use the Comment tab to add some."}</div></div>`;
  };
  body.innerHTML = all.length ? `<div class="filter-row"><input id="cmtFilter" placeholder="Filter…"><select id="cmtKind"><option value="">All types</option>${kinds.map((k) => `<option>${esc(k)}</option>`).join("")}</select>
    ${authors.length > 1 ? `<select id="cmtWho"><option value="">Everyone</option>${authors.map((k) => `<option>${esc(k)}</option>`).join("")}</select>` : ""}</div><div id="cmtList"></div>` : `<div id="cmtList"></div>`;
  draw();
  body.oninput = draw;
  body.onclick = (e) => {
    const c = e.target.closest(".cmt");
    if (!c) return;
    const a = all.find((x) => x.id === +c.dataset.id && x.p === +c.dataset.p);
    gotoPage(a.p, a.r[1]);
    setTool("select");
    setTimeout(() => selectAnnot(a), 120);
  };
  body.ondblclick = (e) => { const c = e.target.closest(".cmt"); if (c) openComment(all.find((x) => x.id === +c.dataset.id)); };
  $("#sideTools").innerHTML = `<span class="muted" style="font-size:12px;padding-right:6px">${all.length}</span>`;
}

/* Attachments */
async function renderAttachments(body) {
  const d = doc();
  $("#sideTools").innerHTML = `<button class="icon-btn sm" title="Attach a file" data-a="add">${icon("plus")}</button>`;
  const draw = (items) => {
    body.innerHTML = items.length ? items.map((a) => `<div class="att">${icon("clip")}<div><b>${esc(a.name)}</b><span>${fmtBytes(a.size)}${a.desc ? " · " + esc(a.desc) : ""}</span></div>
      <button class="icon-btn sm" data-save="${esc(a.name)}" title="Save to disk">${icon("download")}</button><button class="icon-btn sm" data-del="${esc(a.name)}" title="Remove">${icon("trash")}</button></div>`).join("")
      : `<div class="panel-empty">${icon("clip")}<div>No files are attached to this PDF.</div><button class="btn sm" style="margin-top:12px" data-a="add">${icon("plus")}Attach a file</button></div>`;
  };
  draw(await api("attachments", { d: d.id }).catch(() => []));
  $("#side").onclick = async (e) => {
    const b = e.target.closest("button");
    if (!b || !$("#side").contains(b)) return;
    try {
      if (b.dataset.a === "add") { const r = await api("attachment_add", { d: d.id }); if (r) draw(r.items); }
      if (b.dataset.save) { const r = await api("attachment_save", { d: d.id, name: b.dataset.save }); if (r) toast("Saved " + r.saved.split("\\").pop(), { action: { label: "Show", fn: () => api("reveal", { path: r.saved }) } }); }
      if (b.dataset.del && await confirmBox("Remove attachment?", b.dataset.del, "Remove", true)) { const r = await api("attachment_delete", { d: d.id, name: b.dataset.del }); draw(r.items); }
    } catch (err) { fail(err); }
  };
}

/* Help (works without AI) */
async function renderHelp(body) {
  body.innerHTML = `<div class="search-box"><input id="helpQ" placeholder="How do I…?"></div><div id="helpList"></div>
    ${S.ai.enabled ? `<div class="panel-pad"><button class="btn sm" id="helpAi" style="width:100%">${icon("sparkle")}Ask the AI guide</button></div>` : ""}`;
  const list = $("#helpList");
  const draw = async (q) => {
    const items = await api("help_search", { q });
    list.innerHTML = items.map((t) => `<div class="help-topic"><b>${esc(t.title)}</b><p>${esc(t.how)}</p>${t.where ? `<div class="where">${esc(t.where)}${t.keys ? ` · <kbd>${esc(t.keys)}</kbd>` : ""}</div>` : ""}
      ${t.action && CMD[t.action] ? `<button class="showme" data-act="${t.action}">${icon("eye")}Show me</button>` : ""}</div>`).join("") || `<div class="panel-empty">No topic matches. Try other words.</div>`;
  };
  let timer;
  $("#helpQ").oninput = (e) => { clearTimeout(timer); timer = setTimeout(() => draw(e.target.value), 150); };
  list.onclick = (e) => { const b = e.target.closest("[data-act]"); if (b) showMe(b.dataset.act); };
  if ($("#helpAi")) $("#helpAi").onclick = () => { openAI("guide"); const q = $("#helpQ").value.trim(); if (q) aiAsk(q); };
  draw("");
}
function showMe(action) {
  const c = CMD[action];
  if (!c) return;
  if (action.startsWith("tool.") || action.startsWith("side.") || action.startsWith("view.") || action.startsWith("nav.")) { if (!c.needsDoc || doc()) run(action); }
  spotlight(action);
}

/* ------------------------------------------------------------------ dialogs */
async function watermarkDialog() {
  const r = await modal({ title: "Watermark", icon: "watermark", wide: true,
    body: `<div class="wm-preview"><span id="wmP">CONFIDENTIAL</span></div>
      <div class="fld"><label>Text</label><input name="text" value="CONFIDENTIAL" id="wmT"></div>
      <div class="fld-row3"><div class="fld"><label>Size</label><input type="number" name="size" value="64" min="8" max="300" id="wmS"></div>
      <div class="fld"><label>Angle</label><input type="number" name="angle" value="45" min="-90" max="90" id="wmA"></div>
      <div class="fld"><label>Colour</label><input type="color" name="color" value="#c0392b" id="wmC" style="width:100%;height:34px;padding:3px"></div></div>
      <div class="fld"><label>Opacity <span class="muted" id="wmOv">20 %</span></label><input type="range" name="opacity" min="0.05" max="1" step="0.05" value="0.2" id="wmO" style="width:100%"></div>
      <div class="fld"><label>Pages</label><input name="pages" value="all" placeholder="all, or e.g. 1-3, 7"></div>`,
    onOpen: (b) => {
      const upd = () => { const p = $("#wmP", b); p.textContent = $("#wmT", b).value; p.style.transform = `rotate(${-$("#wmA", b).value}deg)`; p.style.color = $("#wmC", b).value; p.style.opacity = $("#wmO", b).value; p.style.fontSize = $("#wmS", b).value * 0.4 + "px"; $("#wmOv", b).textContent = Math.round($("#wmO", b).value * 100) + " %"; };
      b.oninput = upd; upd();
    },
    buttons: [{ label: "Cancel", value: null, ghost: true }, { label: "Add watermark", value: "form", primary: true }] });
  if (r) await api("watermark", { d: doc().id, ...r });
}

async function numbersDialog() {
  const r = await modal({ title: "Page numbers, header & footer", icon: "hash",
    body: `<div class="fld"><label>Text</label><input name="text" value="Page {page} of {pages}"><div class="note">Use {page}, {pages}, {date} and {name} (file name).</div></div>
      <div class="fld-row"><div class="fld"><label>Position</label><select name="position">${["bottom-center", "bottom-right", "bottom-left", "top-center", "top-right", "top-left"].map((p) => `<option value="${p}">${p.replace("-", " ").replace(/^./, (c) => c.toUpperCase())}</option>`).join("")}</select></div>
      <div class="fld"><label>Size</label><input type="number" name="size" value="10" min="5" max="40"></div></div>
      <div class="fld-row"><div class="fld"><label>Start numbering at</label><input type="number" name="start" value="1" min="0"></div><div class="fld"><label>Pages</label><input name="pages" value="all"></div></div>`,
    buttons: [{ label: "Cancel", value: null, ghost: true }, { label: "Add", value: "form", primary: true }] });
  if (r) await api("header_footer", { d: doc().id, ...r });
}

async function protectDialog() {
  const r = await modal({ title: "Password protection", icon: "lock",
    body: `<p>Washi encrypts the PDF with AES-256 when you save it.</p>
      <div class="fld"><label>Password to open</label><input type="password" name="user" autocomplete="new-password"><div class="note">Leave empty to let anyone open it but restrict what they can do.</div></div>
      <div class="fld"><label>Owner password (to change permissions)</label><input type="password" name="owner" autocomplete="new-password"></div>
      <div class="fld"><label>Allow people to</label><div class="checks"><label><input type="checkbox" name="print" checked> Print</label><label><input type="checkbox" name="copy" checked> Copy text</label>
      <label><input type="checkbox" name="annotate" checked> Comment & fill forms</label><label><input type="checkbox" name="edit"> Edit pages</label></div></div>`,
    validate: (v) => (!v.user && !v.owner ? "Set at least one password" : null),
    buttons: [{ label: "Cancel", value: null, ghost: true }, { label: "Protect", value: "form", primary: true }] });
  if (!r) return;
  await api("protect", { d: doc().id, ...r });
  toast("Protection will be applied when you save", { icon: "lock", action: { label: "Save now", fn: () => run("file.save") } });
}

async function optimizeDialog() {
  const r = await modal({ title: "Reduce file size", icon: "compress",
    body: `<p>Images are resampled and the file is recompressed. You can undo this.</p><div class="radio-cards">
      <label><input type="radio" name="level" value="light"><b>Light</b><span>Images ≤ 200 dpi, best quality</span></label>
      <label><input type="radio" name="level" value="balanced" checked><b>Balanced</b><span>Images ≤ 150 dpi</span></label>
      <label><input type="radio" name="level" value="strong"><b>Strong</b><span>Images ≤ 100 dpi, smallest</span></label></div>`,
    buttons: [{ label: "Cancel", value: null, ghost: true }, { label: "Optimise", value: "form", primary: true }] });
  if (!r) return;
  const t = toast("Optimising…", { icon: "compress", ms: 60000 });
  try {
    const res = await api("optimize", { d: doc().id, level: r.level });
    t.remove();
    const pctv = Math.round((1 - res.after / res.before) * 100);
    toast(`${fmtBytes(res.before)} → ${fmtBytes(res.after)} (${pctv > 0 ? "−" + pctv : "+" + -pctv} %). Save to keep it.`, { icon: "compress", ms: 6000 });
  } catch (e) { t.remove(); throw e; }
}

async function propertiesDialog() {
  const d = doc(), m = d.meta;
  const r = await modal({ title: "Document properties", icon: "info", wide: true,
    body: `<div class="fld-row"><div class="fld"><label>Title</label><input name="title" value="${esc(m.title)}"></div><div class="fld"><label>Author</label><input name="author" value="${esc(m.author)}"></div></div>
      <div class="fld-row"><div class="fld"><label>Subject</label><input name="subject" value="${esc(m.subject)}"></div><div class="fld"><label>Keywords</label><input name="keywords" value="${esc(m.keywords)}"></div></div>
      <div class="kv" style="margin-top:6px"><span>File</span><span>${esc(d.path || "Not saved yet")}</span><span>Pages</span><span>${d.pages.length} · ${Math.round(d.pages[0].w / 72 * 25.4)} × ${Math.round(d.pages[0].h / 72 * 25.4)} mm</span>
      <span>PDF</span><span>${esc(m.format)}</span><span>Created</span><span>${esc(pdfDate(m.creationDate))}</span><span>Modified</span><span>${esc(pdfDate(m.modDate))}</span>
      <span>Producer</span><span>${esc([m.creator, m.producer].filter(Boolean).join(" · "))}</span><span>Security</span><span>${esc(m.encryption || (d.encrypted ? "Encrypted" : "None"))}${d.security ? " (changes on save)" : ""}</span>
      <span>Forms</span><span>${d.forms ? "Yes" : "No"}</span><span>Bookmarks</span><span>${d.outline}</span><span>Attachments</span><span>${d.attachments}</span></div>`,
    buttons: [{ label: "Close", value: null, ghost: true }, { label: "Save properties", value: "form", primary: true }] });
  if (r) await api("meta_set", { d: d.id, meta: r });
}

async function exportDialog(kind) {
  const kinds = { docx: "Word document (.docx)", txt: "Plain text (.txt)", md: "Markdown (.md)", html: "Web page (.html)", png: "PNG images", jpg: "JPEG images", pdf: "PDF copy (selected pages)" };
  const n = doc().pages.length;
  const r = await modal({ title: "Export", icon: "export",
    body: `<div class="fld"><label>Format</label><select name="kind" id="exK">${Object.entries(kinds).map(([k, l]) => `<option value="${k}"${k === kind ? " selected" : ""}>${l}</option>`).join("")}</select></div>
      <div class="fld"><label>Pages</label><input name="pages" value="${n > 1 ? "1-" + n : "1"}"><div class="note">For example 1-3, 7, 10-</div></div>
      <div class="fld" id="exDpi"><label>Resolution</label><select name="dpi"><option value="96">96 dpi (screen)</option><option value="150" selected>150 dpi</option><option value="300">300 dpi (print)</option></select></div>`,
    onOpen: (b) => { const t = () => $("#exDpi", b).classList.toggle("hidden", !["png", "jpg"].includes($("#exK", b).value)); $("#exK", b).onchange = t; t(); },
    buttons: [{ label: "Cancel", value: null, ghost: true }, { label: "Export…", value: "form", primary: true }] });
  if (!r) return;
  const t = r.kind === "docx" ? toast("Converting to Word… this can take a moment", { icon: "word", ms: 120000 }) : null;
  try {
    const res = await api("export", { d: doc().id, kind: r.kind, pages: r.pages, dpi: r.dpi });
    t && t.remove();
    if (res) toast(res.files.length > 1 ? `Exported ${res.files.length} files` : "Exported " + res.files[0].split("\\").pop(), { action: { label: "Show", fn: () => api("reveal", { path: res.files[0] }) } });
  } catch (e) { t && t.remove(); throw e; }
}

async function splitDialog() {
  const d = doc();
  const r = await modal({ title: "Split document", icon: "split",
    body: `<div class="radio-cards" style="margin-bottom:12px"><label><input type="radio" name="mode" value="every" checked><b>Every N pages</b><span>Equal parts</span></label>
      <label><input type="radio" name="mode" value="bookmarks"><b>By bookmarks</b><span>One file per chapter</span></label><label><input type="radio" name="mode" value="ranges"><b>Page ranges</b><span>You choose</span></label></div>
      <div class="fld-row"><div class="fld"><label>N (pages per file)</label><input type="number" name="n" value="1" min="1" max="${d.pages.length}"></div>
      <div class="fld"><label>Ranges</label><input name="ranges" placeholder="1-3; 4-8; 9-"><div class="note">Separate files with ;</div></div></div>`,
    buttons: [{ label: "Cancel", value: null, ghost: true }, { label: "Split…", value: "form", primary: true }] });
  if (!r) return;
  const res = await api("split", { d: d.id, ...r });
  if (res) toast(`Saved ${res.files.length} files`, { icon: "split", action: { label: "Show", fn: () => api("reveal", { path: res.files[0] }) } });
}

async function settingsDialog() {
  const s = S.settings, ai = S.ai;
  const aiHtml = ai.supported
    ? `<div class="fld"><label>Local AI</label><div class="checks"><label><input type="checkbox" name="ai" ${s.ai ? "checked" : ""}> Use the AI assistant on the NPU (${esc(ai.npu || "Ryzen AI")})</label></div>
       ${ai.models && ai.models.length ? `<div class="fld" style="margin-top:8px"><label>Model</label><select name="model">${ai.models.map((m) => `<option${m === ai.model ? " selected" : ""}>${esc(m)}</option>`).join("")}</select><div class="note">qwen3:4b is the fastest; larger models answer more carefully.</div></div>` : ""}
       <div class="fld"><label>NPU power mode</label><select name="pmode">${["powersaver", "balanced", "performance", "turbo"].map((m) => `<option${m === s.pmode ? " selected" : ""}>${m}</option>`).join("")}</select><div class="note">Takes effect the next time FastFlowLM starts.</div></div></div>`
    : `<div class="fld"><label>Local AI</label><p class="muted" style="margin:0">Not available on this PC — ${esc(ai.reason || "no compatible NPU")}. Everything else in Washi works normally.</p></div>`;
  const r = await modal({ title: "Settings", icon: "settings", wide: true,
    body: `<div class="fld"><label>Appearance</label><div class="radio-cards"><label><input type="radio" name="theme" value="auto" ${s.theme === "auto" ? "checked" : ""}><b>System</b><span>Follow Windows</span></label>
      <label><input type="radio" name="theme" value="light" ${s.theme === "light" ? "checked" : ""}><b>Light</b><span>Warm paper</span></label><label><input type="radio" name="theme" value="dark" ${s.theme === "dark" ? "checked" : ""}><b>Dark</b><span>Ink</span></label></div></div>
      <div class="fld"><label>Accent colour</label><div class="swatches" id="accentPick">${[["indigo", "#27407a"], ["vermilion", "#e2452f"], ["matcha", "#6f9a33"], ["gold", "#d99a17"]].map(([k, c]) => `<button type="button" class="swatch${(s.accent || "indigo") === k ? " on" : ""}" data-acc="${k}" style="background:${c};width:30px;height:30px" title="${k}"></button>`).join("")}</div><input type="hidden" name="accent" value="${esc(s.accent || "indigo")}" id="accentVal"></div>
      <div class="fld"><div class="checks"><label><input type="checkbox" name="page_dark" ${s.page_dark ? "checked" : ""}> Dark pages in the dark theme (reading mode)</label><label><input type="checkbox" name="splash" ${s.splash ? "checked" : ""}> Play the intro animation</label></div></div>
      <div class="fld-row"><div class="fld"><label>Your name (on comments and stamps)</label><input name="author" value="${esc(s.author)}"></div>
      <div class="fld"><label>Open documents at</label><select name="zoom"><option value="fit-width"${s.zoom === "fit-width" ? " selected" : ""}>Fit width</option><option value="fit-page"${s.zoom === "fit-page" ? " selected" : ""}>Fit page</option></select></div></div>
      ${aiHtml}
      <div class="fld"><label>Default PDF app</label>
        <div style="display:flex;gap:12px;align-items:center"><button type="button" class="btn sm" id="defBtn">${icon("pdf")}Make Washi the default PDF app</button><span class="muted" id="defState" style="font-size:12.5px"></span></div>
        <div class="note">Windows asks you to confirm: in the page that opens, set Washi for “.pdf”.</div></div>`,
    onOpen: (b) => {
      $("#accentPick", b).onclick = (e) => { const x = e.target.closest("[data-acc]"); if (!x) return; $$("[data-acc]", b).forEach((y) => y.classList.toggle("on", y === x)); $("#accentVal", b).value = x.dataset.acc; applyTheme({ ...S.settings, accent: x.dataset.acc }); };
      const show = (st) => { $("#defState", b).textContent = st.default ? "✓ Washi opens your PDFs" : st.registered ? "Washi is in “Open with”, not the default yet" : ""; };
      api("default_app").then(show).catch(() => {});
      $("#defBtn", b).onclick = async () => {
        try {
          const st = await api("default_app", { make: true });
          show(st);
          toast(st.opened ? "In Windows Settings, choose Washi for .pdf (and .xps/.epub if you like)." : "Washi is registered. Choose it under Settings > Apps > Default apps.", { icon: "pdf", ms: 9000 });
          // the choice is made in Windows; check again when the person comes back
          const again = () => { removeEventListener("focus", again); setTimeout(() => api("default_app").then(show).catch(() => {}), 300); };
          addEventListener("focus", again);
        } catch (e) { fail(e); }
      };
    },
    buttons: [{ label: "About Washi", value: "about", ghost: true }, { label: "Cancel", value: null, ghost: true }, { label: "Save", value: "form", primary: true }] });
  if (r === "about") return aboutDialog();
  if (!r) { applyTheme(S.settings); return; }
  const res = await api("settings", { set: r });
  S.settings = res.settings; S.ai = res.ai;
  applyTheme(S.settings);
  refreshAI();
}

function aboutDialog() {
  return modal({ title: "About Washi", icon: "info",
    body: `<div style="display:flex;gap:16px;align-items:center;margin-bottom:12px">${logoSVG(64)}<div><b style="font-size:18px">Washi ${esc(WASHI.version)}</b><div class="muted">A PDF editor with a local AI assistant</div></div></div>
      <p>Washi (和紙) is Japanese hand-made paper: light, strong and made to last.</p>
      <p>© 2026 Alexander Gubric · MIT License. Washi uses PyMuPDF / MuPDF (AGPL-3.0, © Artifex Software). The AI runs on your own PC with FastFlowLM; your documents never leave it.</p>
      <div class="kv"><span>AI</span><span>${S.ai.supported ? esc(`${S.ai.state} · ${S.ai.model || ""}${S.ai.tps ? ` · ${S.ai.tps} tokens/s` : ""}`) : esc(S.ai.reason)}</span><span>Processor</span><span>${esc(S.ai.cpu || "")}</span></div>`,
    buttons: [{ label: "Keyboard shortcuts", value: "keys", ghost: true }, { label: "Close", value: true, primary: true }] }).then((v) => v === "keys" && shortcutsDialog());
}

function shortcutsDialog() {
  const rows = Object.values(CMD).filter((c) => c.keys).map((c) => `<span>${esc(c.label)}</span><span><kbd>${esc(kbdLabel(c.keys))}</kbd></span>`).join("");
  return modal({ title: "Keyboard shortcuts", icon: "keyboard", wide: true, body: `<div class="kv" style="grid-template-columns:1fr auto;gap:7px 20px">${rows}<span>Pan while held</span><span><kbd>Space</kbd></span><span>Zoom</span><span><kbd>Ctrl</kbd> + wheel</span></div>`, buttons: [{ label: "Close", value: true, primary: true }] });
}

async function passwordFlow(errOrItem) {
  const name = (errOrItem.name || errOrItem.path || "This PDF").split("\\").pop();
  const text = errOrItem.wrong ? `That password didn't open ${name}. Try again (passwords are case-sensitive).` : `${name} is protected. Enter its password to open it.`;
  const pw = await promptBox("Password needed", text, "", { type: "password", icon: "lock", ok: "Open" });
  if (!pw) return;
  try {
    if (errOrItem.path) handleOpened(await api("open", { path: errOrItem.path, password: pw }));
    else if (errOrItem.file) {
      const res = await upload(errOrItem.file, "open", pw);
      if (res.password) passwordFlow({ ...errOrItem, wrong: true });
      else showDoc(res.doc.id);
    }
  } catch (e) { fail(e); }
}

/* ------------------------------------------------------------------ command palette */
function openPalette(prefill = "") {
  closeMenu();
  $(".palette")?.remove();
  const el = document.createElement("div");
  el.className = "palette";
  el.innerHTML = `<input placeholder="Type a command, a question or a page number…" value="${esc(prefill)}"><div class="list"></div>`;
  document.body.appendChild(el);
  const inp = $("input", el), list = $(".list", el);
  let items = [], hot = 0, helpTopics = [];
  const close = () => { el.remove(); removeEventListener("pointerdown", away, true); };
  const away = (e) => { if (!el.contains(e.target)) close(); };
  setTimeout(() => addEventListener("pointerdown", away, true));
  const score = (q, c) => {
    const l = (c.label + " " + (c.tags || "") + " " + (c.group || "")).toLowerCase();
    if (!q) return c.palette === false ? 0 : 1;
    let s = 0;
    for (const w of q.toLowerCase().split(/\s+/).filter(Boolean)) { if (c.label.toLowerCase().startsWith(w)) s += 3; else if (l.includes(w)) s += 1; else return 0; }
    return s;
  };
  const draw = () => {
    const q = inp.value.trim();
    items = [];
    if (/^\d+$/.test(q) && doc()) items.push({ label: `Go to page ${q}`, icon: "page", group: "Navigate", go: () => gotoPage(+q - 1) });
    items.push(...Object.values(CMD).filter((c) => !c.hidden?.() && (!doc() ? !c.enabled : enabled(c.id))).map((c) => ({ c, s: score(q, c) })).filter((x) => x.s > 0).sort((a, b) => b.s - a.s).slice(0, q ? 12 : 40)
      .map(({ c }) => ({ label: c.label, icon: c.icon, group: c.needsDoc && !doc() ? c.group + " · open a PDF first" : c.group, keys: c.keys, go: () => run(c.id) })));
    for (const t of helpTopics.slice(0, 4)) items.push({ label: t.title, icon: "help", group: "Help", go: () => { openSide("help"); if (t.action) showMe(t.action); } });
    if (q && S.ai.enabled && q.length > 3) {
      items.push({ label: `Ask AI: “${q}”`, icon: "sparkle", group: doc() ? "About this document" : "Washi guide", cls: "ask-ai", go: () => { openAI(doc() ? "doc" : "guide"); aiAsk(q); } });
      if (doc()) items.push({ label: `Ask the guide: “${q}”`, icon: "sparkle", group: "How to use Washi", cls: "ask-ai", go: () => { openAI("guide"); aiAsk(q); } });
    }
    hot = clamp(hot, 0, items.length - 1);
    list.innerHTML = items.map((it, i) => `<div class="item ${it.cls || ""}${i === hot ? " hot" : ""}" data-i="${i}">${icon(it.icon)}<span class="lbl">${esc(it.label)}</span><span class="grp">${esc(it.group || "")}</span>${it.keys ? `<kbd>${esc(kbdLabel(it.keys))}</kbd>` : ""}</div>`).join("");
  };
  let ht;
  inp.oninput = () => { hot = 0; draw(); clearTimeout(ht); ht = setTimeout(async () => { helpTopics = inp.value.trim().length > 2 ? await api("help_search", { q: inp.value }) : []; draw(); }, 200); };
  inp.onkeydown = (e) => {
    if (e.key === "ArrowDown") { hot = Math.min(hot + 1, items.length - 1); draw(); e.preventDefault(); $(".item.hot", list)?.scrollIntoView({ block: "nearest" }); }
    else if (e.key === "ArrowUp") { hot = Math.max(hot - 1, 0); draw(); e.preventDefault(); $(".item.hot", list)?.scrollIntoView({ block: "nearest" }); }
    else if (e.key === "Enter") { e.preventDefault(); const it = items[hot]; close(); it && it.go(); }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
  };
  list.onclick = (e) => { const r = e.target.closest(".item"); if (r) { const it = items[+r.dataset.i]; close(); it.go(); } };
  draw();
  if (prefill.trim().length > 2) inp.oninput();
  inp.focus();
  inp.setSelectionRange(inp.value.length, inp.value.length);
}

/* ------------------------------------------------------------------ start page */
async function renderHome() {
  const items = await api("recent").catch(() => []);
  const box = $("#recent");
  $("#recentCount").textContent = items.length ? `${items.length} file${items.length > 1 ? "s" : ""}` : "";
  box.innerHTML = items.length ? items.map((r, i) => `<button class="recent" data-i="${i}" title="${esc(r.path)}"><div class="thumb" data-thumb="${i}">${icon("pdf")}</div><b>${esc(r.name)}</b>
      <span>${r.pages ? r.pages + " pages · " : ""}${new Date(r.opened * 1000).toLocaleDateString()}</span><span class="forget" data-forget="${i}" title="Remove from list">${icon("x")}</span></button>`).join("")
    : `<div class="empty-recent">Files you open will appear here.</div>`;
  $$("[data-thumb]", box).forEach((el) => {
    const r = items[+el.dataset.thumb];
    const img = new Image();
    img.onload = () => { el.innerHTML = ""; el.style.backgroundImage = `url("${img.src}")`; };
    img.src = `/api/thumb?path=${encodeURIComponent(r.path)}&t=${encodeURIComponent(WASHI.token)}`;
  });
  box.onclick = async (e) => {
    const f = e.target.closest("[data-forget]");
    if (f) { e.stopPropagation(); await api("forget", { path: items[+f.dataset.forget].path }); return renderHome(); }
    const b = e.target.closest(".recent");
    if (b) openPaths([items[+b.dataset.i].path]);
  };
  renderHomeAI();
}
function renderHomeAI() {
  const box = $("#homeAi"), ai = S.ai;
  if (!ai.supported) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  const msg = !S.settings.ai ? ["Local AI is turned off", "Turn it on in Settings to summarise documents and ask questions."]
    : ai.state === "online" ? ["Washi AI is ready on your NPU", `${ai.model} runs privately on ${ai.npu || "the Ryzen AI NPU"} — open a PDF and press Summarise, or ask how to do anything.`]
    : ai.state === "missing" ? ["Add local AI to Washi", "This PC has a Ryzen AI NPU. Install the free FastFlowLM engine to summarise documents on it."]
    : ai.state === "nomodel" ? ["Download the AI model", "FastFlowLM is installed. Washi needs the qwen3:4b model (about 3 GB) once."]
    : ["Washi AI is warming up", ai.detail || "Loading the model onto the NPU…"];
  box.innerHTML = `${icon("sparkle")}<div><b>${esc(msg[0])}</b><span class="muted">${esc(msg[1])}</span></div>` +
    (ai.state === "online" && S.settings.ai ? `<button class="btn sm" data-cmd="ai.guide">${icon("help")}Ask the guide</button>` : ai.state === "missing" ? `<button class="btn sm primary" id="getFlm">Get FastFlowLM</button>` : ai.state === "nomodel" ? `<button class="btn sm primary" id="pullModel">Download model</button>` : "");
  $("#getFlm") && ($("#getFlm").onclick = () => api("open_url", { url: ai.flm_url }));
  $("#pullModel") && ($("#pullModel").onclick = () => api("ai/pull", {}).then((r) => { S.ai = r; refreshAI(); }).catch(fail));
}
