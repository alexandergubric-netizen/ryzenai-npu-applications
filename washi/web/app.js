/* Washi app shell: commands, tabs, opening & saving, keyboard, drag & drop, printing, theme, intro. */
"use strict";

/* ------------------------------------------------------------------ commands */
const D = () => doc().id;
const toolCmd = (name, label, ic, keys, tab, extra = {}) => cmd("tool." + name, { label, icon: ic, keys, tab, group: "Tools", needsDoc: true, run: () => setTool(S.tool === name && !extra.always ? "select" : name), ...extra });

cmd("file.open", { label: "Open…", short: "Open", icon: "open", keys: "Mod+O", tab: "home", group: "File", run: () => api("open").then(handleOpened) });
cmd("file.new", { label: "New blank PDF", short: "New", icon: "filePlus", keys: "Mod+N", group: "File", run: () => api("new", { size: "a4", pages: 1 }).then((r) => showDoc(r.doc.id)) });
cmd("file.merge", { label: "Combine files into one PDF…", short: "Combine", icon: "layers", tab: "convert", group: "File", tags: "merge join", run: () => api("merge").then((r) => r && showDoc(r.doc.id)) });
cmd("file.fromimages", { label: "Create PDF from images…", short: "From images", icon: "image", tab: "convert", group: "File", tags: "scan photo jpg png", run: () => api("from_images").then((r) => r && showDoc(r.doc.id)) });
cmd("file.save", { label: "Save", icon: "save", keys: "Mod+S", tab: "home", group: "File", needsDoc: true, run: () => saveDoc(false) });
cmd("file.saveas", { label: "Save as…", short: "Save as", icon: "saveAs", keys: "Mod+Shift+S", tab: "home", group: "File", needsDoc: true, tags: "copy new name another folder", run: () => saveDoc(true) });
cmd("file.close", { label: "Close document", icon: "x", keys: "Mod+W", group: "File", needsDoc: true, run: () => closeDoc(S.active) });
cmd("file.print", { label: "Print…", short: "Print", icon: "print", keys: "Mod+P", tab: "home", group: "File", needsDoc: true, run: printDoc });
cmd("file.home", { label: "Start page", icon: "home", group: "File", run: showHome });
cmd("file.reveal", { label: "Show file in Explorer", icon: "folder", group: "File", needsDoc: true, enabled: () => !!(doc()?.path || doc()?.source_path), run: () => api("reveal", { path: doc().path || doc().source_path }) });

cmd("edit.undo", { label: "Undo", icon: "undo", keys: "Mod+Z", tab: "home", group: "Edit", needsDoc: true, enabled: () => doc()?.undo > 0, run: () => api("undo", { d: D() }).then(() => selectAnnot(null)) });
cmd("edit.redo", { label: "Redo", icon: "redo", keys: "Mod+Y", tab: "home", group: "Edit", needsDoc: true, enabled: () => doc()?.redo > 0, run: () => api("redo", { d: D() }).then(() => selectAnnot(null)) });

cmd("view.zoomin", { label: "Zoom in", short: "Zoom in", icon: "zoomIn", keys: "Mod+=", tab: "home", group: "View", needsDoc: true, run: () => { view().fit = "custom"; setZoom(nextZoom(1)); } });
cmd("view.zoomout", { label: "Zoom out", short: "Zoom out", icon: "zoomOut", keys: "Mod+-", tab: "home", group: "View", needsDoc: true, run: () => { view().fit = "custom"; setZoom(nextZoom(-1)); } });
cmd("view.fitwidth", { label: "Fit width", icon: "fitWidth", keys: "Mod+2", tab: "home", group: "View", needsDoc: true, run: () => setFit("fit-width") });
cmd("view.fitpage", { label: "Fit page", icon: "fitPage", keys: "Mod+0", tab: "home", group: "View", needsDoc: true, run: () => setFit("fit-page") });
cmd("view.actual", { label: "Actual size (100 %)", icon: "page", keys: "Mod+1", group: "View", needsDoc: true, run: () => { view().fit = "custom"; setZoom(1); } });
cmd("view.continuous", { label: "Continuous scrolling", icon: "scroll", group: "View", needsDoc: true, run: () => setLayout("continuous") });
cmd("view.single", { label: "Single page", icon: "page", group: "View", needsDoc: true, run: () => setLayout("single") });
cmd("view.two", { label: "Two pages side by side", icon: "book", group: "View", needsDoc: true, run: () => setLayout("two") });
cmd("view.theme", { label: "Switch light / dark theme", icon: "moon", group: "View", tags: "dark mode night", run: toggleTheme });
cmd("view.pagedark", { label: "Dark pages (reading mode)", icon: "eye", group: "View", tags: "night invert", run: () => api("settings", { set: { page_dark: !S.settings.page_dark } }).then((r) => { S.settings = r.settings; applyTheme(S.settings); }) });
cmd("view.ebooktext", { label: "E-book text size…", short: "Text size", icon: "editText", group: "View", needsDoc: true, tags: "epub mobi fb2 font bigger smaller reading",
  hidden: () => !doc()?.reflowable, enabled: () => !!doc()?.reflowable,
  run: () => {
    const cur = doc().fontsize || 11;
    const el = $("[data-cmd='view.ebooktext']:not(.hidden)") || $("#zoomLabel");
    menuAt(el, [{ header: "E-book text size" }, ...[[9, "Small"], [11, "Normal"], [13, "Large"], [16, "Larger"], [20, "Huge"]].map(([s, l]) => ({
      label: `${l} (${s} pt)`, check: Math.abs(cur - s) < 0.1,
      action: async () => {
        const p = view().page / Math.max(doc().pages.length, 1);
        try { await api("reflow", { d: D(), size: s }); gotoPage(Math.round(p * doc().pages.length)); } catch (e) { fail(e); }
      },
    }))]);
  } });
cmd("view.sidebar", { label: "Show / hide side panel", icon: "grid", keys: "F4", group: "View", needsDoc: true, run: () => openSide(S.side, true) });

cmd("nav.find", { label: "Find text", short: "Find", icon: "search", keys: "Mod+F", tab: "home", group: "Navigate", needsDoc: true, run: () => openSide("search") });
cmd("nav.next", { label: "Next page", icon: "chevDown", group: "Navigate", needsDoc: true, run: () => gotoPage(view().page + 1) });
cmd("nav.prev", { label: "Previous page", icon: "chevUp", group: "Navigate", needsDoc: true, run: () => gotoPage(view().page - 1) });
cmd("nav.first", { label: "First page", icon: "chevUp", keys: "Home", group: "Navigate", needsDoc: true, palette: false, run: () => gotoPage(0) });
cmd("nav.last", { label: "Last page", icon: "chevDown", keys: "End", group: "Navigate", needsDoc: true, palette: false, run: () => gotoPage(doc().pages.length - 1) });
cmd("nav.goto", { label: "Go to page…", icon: "page", keys: "Mod+G", group: "Navigate", needsDoc: true, run: () => { $("#pageInput").focus(); $("#pageInput").select(); } });

toolCmd("select", "Select", "select", "V", "home", { always: true, tip: "Select text and comments" });
toolCmd("hand", "Hand", "hand", "H", "home", { tip: "Drag to scroll (or hold Space)" });
toolCmd("highlight", "Highlight", "highlight", "M", "comment", { tip: "Select text to highlight it", tags: "marker" });
toolCmd("underline", "Underline", "underline", null, "comment");
toolCmd("strikeout", "Strike out", "strike", null, "comment", { short: "Strike" });
toolCmd("squiggly", "Squiggly underline", "squiggly", null, "comment", { short: "Squiggly" });
toolCmd("area", "Area highlight", "area", null, "comment", { short: "Area" });
toolCmd("note", "Sticky note", "note", "N", "comment", { short: "Note", tags: "comment" });
toolCmd("textbox", "Text box comment", "textbox", "T", "comment", { short: "Text box", tags: "typewriter free text" });
toolCmd("rect", "Rectangle", "rect", "R", "comment", { tags: "shape square box" });
toolCmd("ellipse", "Ellipse", "ellipse", "O", "comment", { tags: "shape circle oval" });
toolCmd("line", "Line", "line", "L", "comment", { tags: "shape" });
toolCmd("arrow", "Arrow", "arrow", "A", "comment", { tags: "shape pointer" });
toolCmd("ink", "Pen (freehand drawing)", "pen", "P", "comment", { short: "Pen", tags: "draw ink pencil" });
cmd("tool.stamp", { label: "Stamp", icon: "stamp", keys: "S", tab: "comment", group: "Tools", needsDoc: true, tags: "approved draft confidential", run: () => pickStamp($("[data-cmd='tool.stamp']:not(.hidden)")) });
cmd("tool.sign", { label: "Sign (add signature)", short: "Sign", icon: "sign", tab: "edit", group: "Tools", needsDoc: true, tags: "signature", run: async () => { const s = await signatureDialog(); if (s) setTool("sign", s); } });
cmd("tool.image", { label: "Add image", short: "Image", icon: "image", tab: "edit", group: "Tools", needsDoc: true, tags: "picture photo logo", run: async () => { const r = await api("pick_image"); if (r) setTool("image", r); } });
toolCmd("edittext", "Edit text", "editText", "E", "edit", { tip: "Click a line of text to change it", tags: "change modify correct typo" });
toolCmd("addtext", "Add text", "addText", "X", "edit", { tip: "Click anywhere to type new text", tags: "typewriter write" });
toolCmd("whiteout", "Erase area (whiteout)", "whiteout", null, "edit", { short: "Erase", tags: "remove delete content white" });
toolCmd("link", "Add link", "link", null, "edit", { short: "Link", tags: "url hyperlink" });
toolCmd("redact", "Mark for redaction", "redact", null, "protect", { short: "Redact", tags: "black out censor hide" });
toolCmd("crop", "Crop pages", "crop", null, "pages", { short: "Crop", tags: "trim margins" });
toolCmd("field", "Text field", "field", null, "forms", { tags: "form input" });
toolCmd("fieldcheck", "Checkbox field", "checkbox", null, "forms", { short: "Checkbox", tags: "form" });
toolCmd("fieldcombo", "Dropdown field", "dropdown", null, "forms", { short: "Dropdown", tags: "form combo choice" });

const pagesCmd = (id, label, ic, fn, extra = {}) => cmd("page." + id, { label, icon: ic, tab: "pages", group: "Pages", needsDoc: true, run: fn, ...extra });
pagesCmd("rotatecw", "Rotate pages right", "rotateCw", () => api("pages_rotate", { d: D(), pages: selectedPages(), angle: 90 }), { short: "Right", keys: "Mod+R" });
pagesCmd("rotateccw", "Rotate pages left", "rotateCcw", () => api("pages_rotate", { d: D(), pages: selectedPages(), angle: -90 }), { short: "Left", keys: "Mod+Shift+R" });
pagesCmd("delete", "Delete pages", "trash", async () => {
  const p = selectedPages();
  if (!(await confirmBox("Delete pages?", p.length > 1 ? `Delete ${p.length} pages (${p.map((x) => x + 1).join(", ")})? You can undo this.` : `Delete page ${p[0] + 1}? You can undo this.`, "Delete", true))) return;
  await api("pages_delete", { d: D(), pages: p }); view().selPages.clear(); renderSide();
}, { short: "Delete" });
pagesCmd("blank", "Insert blank page", "pagePlus", () => api("pages_blank", { d: D(), at: view().page + 1 }).then(() => gotoPage(view().page + 1)), { short: "Blank page" });
pagesCmd("insertfile", "Insert pages from file…", "insertFile", () => api("pages_insert_file", { d: D(), at: view().page + 1 }).then((r) => r && toast(`Inserted ${r.added} page${r.added > 1 ? "s" : ""}`)), { short: "From file", tags: "merge add" });
pagesCmd("duplicate", "Duplicate pages", "duplicate", () => api("pages_duplicate", { d: D(), pages: selectedPages() }), { short: "Duplicate", tags: "copy" });
pagesCmd("extract", "Extract pages to new PDF…", "extract", async () => {
  const r = await api("pages_extract", { d: D(), pages: selectedPages() });
  if (r) toast("Saved " + r.saved.split("\\").pop(), { action: { label: "Open", fn: () => openPaths([r.saved]) } });
}, { short: "Extract" });
pagesCmd("split", "Split document…", "split", splitDialog, { short: "Split" });
pagesCmd("uncrop", "Remove crop", "fitPage", () => api("uncrop", { d: D(), pages: selectedPages() }), { short: "Uncrop" });
pagesCmd("numbers", "Page numbers, header & footer…", "hash", numbersDialog, { short: "Numbers", tags: "bates footer header" });
pagesCmd("watermark", "Watermark…", "watermark", watermarkDialog, { short: "Watermark" });

cmd("doc.redactapply", { label: "Apply redactions", short: "Apply", icon: "check", tab: "protect", group: "Protect", needsDoc: true, run: async () => {
  if (!(await confirmBox("Apply redactions?", "Everything under the redaction marks is permanently removed (text, images and drawings) and replaced by black boxes. You can still undo before you save.", "Apply redactions", true))) return;
  const r = await api("redact_apply", { d: D() }); toast(`Redacted on ${r.pages} page${r.pages > 1 ? "s" : ""}. Save to make it permanent.`, { icon: "redact" });
} });
cmd("doc.flatten", { label: "Flatten comments and forms", short: "Flatten", icon: "flatten", tab: "comment", group: "Document", needsDoc: true, run: async () => {
  if (await confirmBox("Flatten?", "Comments, stamps and form fields become part of the page and can no longer be edited.", "Flatten")) await api("flatten", { d: D() });
} });
cmd("doc.protect", { label: "Password protect…", short: "Password", icon: "lock", tab: "protect", group: "Protect", needsDoc: true, tags: "encrypt security", run: protectDialog });
cmd("doc.unprotect", { label: "Remove password", short: "Unlock", icon: "unlock", tab: "protect", group: "Protect", needsDoc: true, tags: "decrypt security", run: async () => { await api("protect", { d: D(), remove: true }); toast("The password is removed when you save", { action: { label: "Save now", fn: () => run("file.save") } }); } });
cmd("doc.optimize", { label: "Reduce file size…", short: "Optimise", icon: "compress", tab: "convert", group: "Document", needsDoc: true, tags: "compress smaller shrink optimize", run: optimizeDialog });
cmd("doc.properties", { label: "Document properties…", short: "Properties", icon: "info", keys: "Mod+D", tab: "protect", group: "Document", needsDoc: true, tags: "metadata title author", run: propertiesDialog });

const exp = (k, label, ic) => cmd("export." + k, { label: `Export to ${label}…`, short: label, icon: ic, tab: "convert", group: "Export", needsDoc: true, run: () => exportDialog(k) });
exp("docx", "Word", "word"); exp("txt", "Text", "fileText"); exp("md", "Markdown", "fileText"); exp("html", "HTML", "file"); exp("png", "Images", "image");
cmd("export.pdf", { label: "Save selected pages as PDF…", short: "PDF copy", icon: "pdf", tab: "convert", group: "Export", needsDoc: true, run: () => exportDialog("pdf") });

const sideCmd = (k, label, ic, keys) => cmd("side." + k, { label, short: label, icon: ic, keys, group: "Panels", needsDoc: true, run: () => openSide(k) });
sideCmd("thumbs", "Pages panel", "grid"); sideCmd("outline", "Bookmarks", "bookmark", "Mod+B"); sideCmd("comments", "Comments list", "comments"); sideCmd("attachments", "Attachments", "clip");
CMD["side.comments"].short = "List"; CMD["side.comments"].tab = "comment"; CMD["side.attachments"].tab = "convert";

cmd("ai.summary", { label: "Summarise with AI", short: "Summarise", icon: "sparkle", tab: "home", group: "AI", needsDoc: true, hidden: () => !S.ai.enabled, run: () => aiSummary("bullets") });
cmd("ai.panel", { label: "Open Washi AI", icon: "sparkle", keys: "Mod+Shift+A", group: "AI", hidden: () => !S.ai.enabled, run: () => (S.right === "ai" ? closeAI() : openAI()) });
cmd("ai.guide", { label: "Ask the AI guide how to do something", icon: "help", group: "AI", hidden: () => !S.ai.enabled, run: () => openAI("guide") });

cmd("app.palette", { label: "Search commands", icon: "command", keys: "Mod+K", group: "Washi", palette: false, run: () => openPalette() });
cmd("app.settings", { label: "Settings", icon: "settings", keys: "Mod+,", group: "Washi", run: settingsDialog });
cmd("app.help", { label: "Help", icon: "help", keys: "F1", group: "Washi", run: () => (doc() ? openSide("help") : openPalette("how ")) });
cmd("app.about", { label: "About Washi", icon: "info", group: "Washi", run: aboutDialog });
cmd("app.shortcuts", { label: "Keyboard shortcuts", icon: "keyboard", group: "Washi", run: shortcutsDialog });

const ZOOMS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4, 5, 6, 8];
function nextZoom(dir) { const z = view().zoom; return dir > 0 ? ZOOMS.find((x) => x > z + 0.001) || 8 : [...ZOOMS].reverse().find((x) => x < z - 0.001) || 0.25; }

/* ------------------------------------------------------------------ tabs and documents */
function renderTabs() {
  $("#tabs").innerHTML = S.order.map((id) => {
    const d = S.docs[id];
    return `<div class="tab${id === S.active ? " active" : ""}" data-id="${id}" title="${esc(d.path || d.name)}">${icon("pdf")}<span class="name">${esc(d.name)}</span>${d.dirty ? '<span class="dirty" title="Unsaved changes"></span>' : ""}<button class="close" title="Close (Ctrl W)">${icon("x")}</button></div>`;
  }).join("");
}
$("#tabs").addEventListener("click", (e) => {
  const t = e.target.closest(".tab");
  if (!t) return;
  if (e.target.closest(".close")) closeDoc(t.dataset.id); else showDoc(t.dataset.id);
});
$("#tabs").addEventListener("auxclick", (e) => { const t = e.target.closest(".tab"); if (t && e.button === 1) closeDoc(t.dataset.id); });
$("#tabs").addEventListener("contextmenu", (e) => {
  const t = e.target.closest(".tab");
  if (!t) return;
  e.preventDefault();
  const id = t.dataset.id, d = S.docs[id];
  const others = S.order.filter((x) => x !== id);
  const go = (fn) => async () => { if (S.active !== id) showDoc(id); try { await fn(); } catch (err) { fail(err); } };
  showMenu(e.clientX, e.clientY, [
    { label: "Save", icon: "save", kbd: "Ctrl S", action: go(() => saveDoc(false)) },
    { label: "Save as…", icon: "saveAs", kbd: "Ctrl Shift S", action: go(() => saveDoc(true)) },
    { label: "Show in Explorer", icon: "folder", disabled: !(d.path || d.source_path), action: () => api("reveal", { path: d.path || d.source_path }).catch(fail) },
    { label: "Copy file path", icon: "copy", disabled: !(d.path || d.source_path), action: () => navigator.clipboard.writeText(d.path || d.source_path).then(() => toast("Path copied")) },
    "-",
    { label: "Close", icon: "x", kbd: "Ctrl W", action: () => closeDoc(id).catch(fail) },
    { label: "Close other tabs", icon: "x", disabled: !others.length, action: async () => { for (const o of others) { if (S.docs[o]) await closeDoc(o).catch(fail); } } },
  ]);
});

function showDoc(id) {
  if (!S.docs[id]) return;
  if (S.active && S.active !== id && view()) view().scroll = $("#viewer").scrollTop;
  if (!S.order.includes(id)) S.order.push(id);
  closeEditor(true);
  selectAnnot(null);
  S.active = id;
  $("#home").classList.add("hidden");
  $("#work").classList.remove("hidden");
  $("#ribbon").classList.remove("hidden");
  $("#stNav").classList.remove("hidden");
  renderTabs();
  buildPages();
  const v = view();
  if (v.scroll != null) $("#viewer").scrollTop = v.scroll; else gotoPage(v.page || 0);
  onPageChange();
  setTool(S.tool);
  openSide(S.side, false);
  if (!S.sideOpen) $("#side").classList.add("collapsed");
  refreshState();
  if (S.right === "ai") renderAI();
  $("#viewer").focus({ preventScroll: true });
}

function showHome() {
  if (S.active && view()) view().scroll = $("#viewer").scrollTop;
  S.active = null;
  $("#home").classList.remove("hidden");
  $("#work").classList.add("hidden");
  $("#ribbon").classList.add("hidden");
  $("#stNav").classList.add("hidden");
  renderTabs();
  refreshState();
  renderHome();
}

async function closeDoc(id) {
  const d = S.docs[id];
  if (!d) return;
  if (d.dirty) {
    if (S.active !== id) showDoc(id);
    const r = await modal({ title: "Save changes?", icon: "save", body: `<p>${esc(d.name)} has changes that are not saved.</p>`,
      buttons: [{ label: "Cancel", value: null, ghost: true }, { label: "Don't save", value: "discard" }, { label: "Save", value: "save", primary: true }] });
    if (!r) return;
    if (r === "save") {
      try { if (!(await saveDoc(false))) return; } catch (e) { fail(e); return; }
    }
  }
  await api("close", { d: id }).catch(() => {});
  const i = S.order.indexOf(id);
  S.order.splice(i, 1);
  delete S.docs[id]; delete S.views[id]; delete AI.chats[id];
  if (S.active === id) {
    S.active = null;
    const next = S.order[Math.min(i, S.order.length - 1)];
    if (next) showDoc(next); else showHome();
  } else renderTabs();
}

let saving = null;
function saveDoc(as, elsewhere) {
  if (saving) return saving;   // a second Ctrl+S / click while saving joins the same save
  saving = doSave(as, elsewhere).finally(() => { saving = null; });
  return saving;
}
async function doSave(as, elsewhere) {
  const d = doc();
  if (!d) return false;
  await closeEditor(true);   // an open text editor / pen stroke must be in the file that gets written
  await commitInk();
  let r;
  try {
    r = await api("save", { d: d.id, as: !!as, elsewhere: !!elsewhere });
  } catch (e) {
    if (!e.data || !e.data.save_as) throw e;
    const choice = await modal({ title: "Couldn't save here", icon: "save", body: `<p>${esc(e.message)}</p>`,
      buttons: [{ label: "Cancel", value: null, ghost: true }, { label: "Save a copy as…", value: "as", primary: true, icon: "saveAs" }] });
    if (choice !== "as") return false;
    return doSave(true, true);
  }
  if (!r) return false;
  toast(`Saved ${r.saved.split("\\").pop()} · ${fmtBytes(r.size)}`, { icon: "save" });
  renderTabs();
  refreshState();
  return true;
}

function handleOpened(list) {
  if (!list) return;
  let last = null;
  for (const it of list) {
    if (it.doc) { updateDoc(it.doc); S.order.includes(it.doc.id) || S.order.push(it.doc.id); last = it.doc.id; }
    else if (it.password) passwordFlow(it);
    else if (it.error) toast(it.error, { err: true });
  }
  if (last) showDoc(last);
}
async function openPaths(paths) {
  for (const p of paths) {
    try { handleOpened(await api("open", { path: p })); } catch (e) { fail(e); }
  }
}

function refreshState() {
  const d = doc();
  $$("[data-cmd]").forEach((b) => {
    const c = CMD[b.dataset.cmd];
    if (!c) return;
    b.disabled = !enabled(b.dataset.cmd);
    if (c.hidden) b.classList.toggle("hidden", !!c.hidden());
  });
  $("#stDoc").textContent = d ? `${d.path || d.source_path || d.name}${d.dirty ? " · edited" : ""}${d.security ? " · protection changes on save" : ""}` +
    `${d.converted ? ` · ${d.source || "file"} shown as PDF — Save as keeps a PDF copy` : ""}` : `Washi ${WASHI.version}`;
  document.title = d ? `${d.dirty ? "• " : ""}${d.name} — Washi` : "Washi";
}

document.addEventListener("doc-changed", (e) => {
  if (S.order.includes(e.detail.id)) renderTabs();
  if (e.detail.id === S.active) {
    refreshState();
    if (S.sideOpen && ["thumbs", "comments", "attachments"].includes(S.side)) { clearTimeout(S.sideT); S.sideT = setTimeout(renderSide, 150); }
    if (S.sel) { const list = view().annots[S.sel.p]; if (!list) { /* refreshed later */ } }
  }
});
document.addEventListener("page-changed", () => { if (S.sideOpen && S.side === "thumbs") markThumbs(); });

/* ------------------------------------------------------------------ status bar */
$("#pageInput").addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  const d = doc(), v = e.target.value.trim();
  const byLabel = d.pages.findIndex((p) => p.label === v);
  gotoPage(byLabel >= 0 ? byLabel : (parseInt(v, 10) || 1) - 1);
  $("#viewer").focus();
});
$("#zoomLabel").addEventListener("click", (e) => menuAt(e.currentTarget, [
  { label: "Fit width", icon: "fitWidth", action: () => run("view.fitwidth") }, { label: "Fit page", icon: "fitPage", action: () => run("view.fitpage") }, "-",
  ...[0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4].map((z) => ({ label: Math.round(z * 100) + " %", action: () => { view().fit = "custom"; setZoom(z); } })),
]));

/* ------------------------------------------------------------------ keyboard */
function keyName(e) {
  let k = e.key.length === 1 ? e.key.toUpperCase() : e.key;
  let shift = e.shiftKey;
  // physical digit keys, so Ctrl+1/2/0 work on layouts where the number row types letters (Slovak, Czech, French…)
  if (/^Digit\d$/.test(e.code || "") && (e.ctrlKey || e.metaKey)) { k = e.code.slice(5); shift = false; }
  if (k === "+" || (e.code === "Equal" && (e.ctrlKey || e.metaKey)) || e.code === "NumpadAdd") { k = "="; shift = false; }
  if (e.code === "Minus" && (e.ctrlKey || e.metaKey) || e.code === "NumpadSubtract") { k = "-"; shift = false; }
  if (k === "_") { k = "-"; shift = false; }
  return (e.ctrlKey || e.metaKey ? "Mod+" : "") + (shift && (e.key.length > 1 || e.ctrlKey || e.metaKey) ? "Shift+" : "") + (e.altKey ? "Alt+" : "") + k;
}
addEventListener("keydown", (e) => {
  if ($(".modal-back") || $(".palette")) return;
  const typing = e.target.closest && e.target.closest("input, textarea, select, [contenteditable]");
  const k = keyName(e);
  if (e.key === " " && !typing && doc()) { if (!T.space) { T.space = true; $("#viewer").classList.add("t-hand"); } e.preventDefault(); return; }
  if (e.key === "Escape" && !typing) {
    closeMenu();
    if (S.sel) selectAnnot(null); else if (S.tool !== "select") setTool("select"); else { getSelection().removeAllRanges(); hideFloat(); }
    return;
  }
  if ((e.key === "Delete" || e.key === "Backspace") && !typing && S.sel) { e.preventDefault(); deleteSel(); return; }
  if (!typing && doc() && view().layout === "single" && ["PageDown", "PageUp", "ArrowRight", "ArrowLeft"].includes(e.key)) { e.preventDefault(); run(e.key === "PageDown" || e.key === "ArrowRight" ? "nav.next" : "nav.prev"); return; }
  if (k === "Mod+Shift+Z" && !typing) { e.preventDefault(); if (doc()) run("edit.redo"); return; }
  if (e.ctrlKey && e.altKey && !e.metaKey) return;   // AltGr on European keyboards types characters
  const c = Object.values(CMD).find((c) => c.keys === k);
  if (!c) return;
  const plain = !k.startsWith("Mod+") && !k.startsWith("F") && !["Home", "End"].includes(k);
  if (typing && (plain || ["Home", "End"].includes(k))) return;
  if (typing && ["Mod+Z", "Mod+Y", "Mod+A"].includes(k)) return;   // let text fields undo their own typing
  if (c.needsDoc && !doc()) return;
  e.preventDefault();
  run(c.id);
}, true);
addEventListener("keyup", (e) => { if (e.key === " " && T.space) { T.space = false; setTool(S.tool); } });

/* ------------------------------------------------------------------ drag & drop of files */
let dragDepth = 0;
const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
addEventListener("dragenter", (e) => { if (!hasFiles(e)) return; dragDepth++; $("#drop").classList.remove("hidden"); $("#dropHint").textContent = doc() ? "PDFs and e-books open in a new tab · images are placed on the page" : "PDFs, e-books (EPUB, MOBI, FB2) or images"; });
addEventListener("dragleave", (e) => { if (!hasFiles(e)) return; if (--dragDepth <= 0) { dragDepth = 0; $("#drop").classList.add("hidden"); } });
addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
addEventListener("drop", async (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  dragDepth = 0;
  $("#drop").classList.add("hidden");
  const files = [...e.dataTransfer.files];
  const images = files.filter((f) => /^image\//.test(f.type));
  const others = files.filter((f) => !/^image\//.test(f.type));
  if (images.length && doc()) {
    try {
      const r = await upload(images[0], "image");
      setTool("image", r);
      const hit = pageAt(e.clientX, e.clientY);
      if (hit) { const pg = doc().pages[hit.p]; const w = Math.min(r.w * 0.75, pg.w * 0.45), h = w * r.h / r.w; await commitRect(hit.p, [hit.x - w / 2, hit.y - h / 2, hit.x + w / 2, hit.y + h / 2]); }
    } catch (err) { fail(err); }
  } else others.push(...images);
  for (const f of others) {
    const t = toast(`Opening ${f.name}…`, { icon: "open", ms: 60000 });
    try {
      const r = await upload(f);
      t.remove();
      if (r.password) passwordFlow({ name: f.name, file: f });
      else { S.order.includes(r.doc.id) || S.order.push(r.doc.id); showDoc(r.doc.id); }
    } catch (err) { t.remove(); fail(err); }
  }
});

/* ------------------------------------------------------------------ printing: pages rendered at print resolution */
async function printDoc() {
  const d = doc(), root = $("#printRoot");
  const big = d.pages.length > 40;
  const sc = big ? 1.6 : 2.2;   // ~115 / 160 dpi
  const t = toast("Preparing pages for printing…", { icon: "print", ms: 600000 });
  root.innerHTML = "";
  const imgs = d.pages.map(() => root.appendChild(new Image()));
  for (let i = 0; i < d.pages.length; i += 6) {   // a few at a time, so huge files don't flood the server
    await Promise.all(imgs.slice(i, i + 6).map((img, k) => new Promise((res) => {
      img.onload = img.onerror = res;
      img.src = pageURL(d.id, i + k, sc, d.pages[i + k].pv, big ? "jpg" : undefined);
    })));
    t.querySelector("span").textContent = `Preparing pages for printing… ${Math.min(i + 6, d.pages.length)} / ${d.pages.length}`;
  }
  t.remove();
  addEventListener("afterprint", () => (root.innerHTML = ""), { once: true });
  window.print();
}

/* ------------------------------------------------------------------ theme */
function applyTheme(s) {
  const dark = s.theme === "dark" || (s.theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  if (s.accent && s.accent !== "indigo") document.documentElement.dataset.accent = s.accent; else delete document.documentElement.dataset.accent;
  document.body.classList.toggle("page-dark", dark && !!s.page_dark);
  $("#themeBtn").innerHTML = icon(dark ? "sun" : "moon");
  try { localStorage.setItem("washi.theme", JSON.stringify({ theme: s.theme, accent: s.accent, splash: s.splash })); } catch (e) { /* empty */ }
}
async function toggleTheme() {
  const dark = document.documentElement.dataset.theme === "dark";
  const r = await api("settings", { set: { theme: dark ? "light" : "dark" } });
  S.settings = r.settings;
  applyTheme(S.settings);
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyTheme(S.settings));

/* ------------------------------------------------------------------ intro */
function splash() {
  let cfg = {};
  try { cfg = JSON.parse(localStorage.getItem("washi.theme") || "{}"); } catch (e) { /* empty */ }
  const el = $("#splash");
  if (cfg.splash === false) { el.remove(); return Promise.resolve(); }
  document.body.classList.add("splashing");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  return new Promise((resolve) => {
    let done = false;
    const end = () => {
      if (done) return;
      done = true;
      el.classList.add("done");
      document.body.classList.remove("splashing");
      setTimeout(() => el.remove(), 600);
      removeEventListener("keydown", end, true);
      resolve();
    };
    el.addEventListener("click", end);
    addEventListener("keydown", end, true);
    setTimeout(end, reduced ? 500 : 2700);
  });
}

/* ------------------------------------------------------------------ start-up */
let pollFails = 0, deadToast = null;
async function poll() {
  try {
    const r = await api("ping");
    pollFails = 0;
    if (deadToast) { deadToast.remove(); deadToast = null; }
    if (r.pending && r.pending.length) openPaths(r.pending);
    const before = JSON.stringify([S.ai.state, S.ai.detail, S.ai.pull, S.ai.tps, S.ai.models]);
    S.ai = r.ai;
    if (before !== JSON.stringify([S.ai.state, S.ai.detail, S.ai.pull, S.ai.tps, S.ai.models])) { refreshAI(); if (S.right === "ai" && ["pulling", "online", "nomodel"].includes(S.ai.state) && !chat().length) renderMsgs(); }
  } catch (e) {
    // a few misses can be a busy moment; after that the engine has stopped (and the window can't save)
    if (++pollFails >= 4 && !deadToast) {
      deadToast = toast("Washi's engine stopped unexpectedly. Close this window and start Washi again — your files on disk are safe.", { err: true, ms: 3600000 });
    }
  }
  setTimeout(poll, S.ai.state === "starting" || S.ai.state === "pulling" ? 1200 : 2500);
}

async function init() {
  hydrateIcons();
  $$("[data-logo]").forEach((el) => (el.innerHTML = logoSVG(el.dataset.logo === "lg" ? 76 : 26)));
  const intro = splash();
  const st = await api("state", { full: true });
  S.settings = st.settings;
  S.ai = st.ai;
  applyTheme(S.settings);
  S.side = S.settings.sidebar || "thumbs";
  renderRibbon();
  initPointer();
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-cmd]");
    if (b && !b.disabled && !e.defaultPrevented) run(b.dataset.cmd);
  });
  $("#homeBtn").onclick = () => run("file.home");
  $("#paletteBtn").onclick = () => openPalette();
  $("#aiBtn").onclick = () => (S.right === "ai" ? closeAI() : openAI());
  $("#helpBtn").onclick = () => run("app.help");
  $("#themeBtn").onclick = toggleTheme;
  $("#settingsBtn").onclick = () => run("app.settings");
  $("#rail").onclick = (e) => { const b = e.target.closest("[data-side]"); if (b) { openSide(b.dataset.side, true); api("settings", { set: { sidebar: S.side } }).catch(() => {}); } };
  // side panel resizing
  const rs = $("#sideResize");
  rs.onpointerdown = (e) => {
    rs.setPointerCapture(e.pointerId); rs.classList.add("dragging");
    const x0 = e.clientX, w0 = $("#side").offsetWidth;
    rs.onpointermove = (ev) => { $("#side").style.width = clamp(w0 + ev.clientX - x0, 200, 520) + "px"; };
    rs.onpointerup = () => { rs.onpointermove = null; rs.classList.remove("dragging"); if (doc() && view().fit !== "custom") setFit(view().fit); if (S.side === "thumbs") renderSide(); };
  };
  addEventListener("beforeunload", (e) => { if (Object.values(S.docs).some((d) => d.dirty)) { e.preventDefault(); e.returnValue = ""; } });
  for (const d of st.open || []) { S.docs[d.id] = d; S.order.push(d.id); }
  refreshAI();
  if (S.order.length) showDoc(S.order[S.order.length - 1]); else showHome();
  if (st.pending && st.pending.length) openPaths(st.pending);
  await intro;
  setTimeout(poll, 1500);
}
init().catch(fail);
