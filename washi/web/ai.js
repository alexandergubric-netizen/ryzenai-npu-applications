/* Washi AI panel: summaries, questions about the document, help with selected text and the app guide.
   Only shown on PCs that can run FastFlowLM on a Ryzen AI NPU. */
"use strict";
const AI = { mode: "doc", chats: {}, guide: [], busy: null, poll: null };
const LANGS = ["English", "Slovak", "Czech", "German", "French", "Spanish", "Italian", "Polish", "Hungarian", "Ukrainian", "Danish", "Japanese"];

function refreshAI() {
  const ai = S.ai;
  const btn = $("#aiBtn");
  btn.classList.toggle("hidden", !ai.supported);
  btn.classList.toggle("on", S.right === "ai");
  const dot = $(".ai-dot", btn);
  dot.className = "ai-dot" + (ai.enabled && ai.state === "online" ? " online" : ai.enabled && ["starting", "pulling"].includes(ai.state) ? " starting" : "");
  btn.title = ai.enabled ? `Washi AI — ${aiStatusText()} (Ctrl+Shift+A)` : "Washi AI is turned off (Settings)";
  const st = $("#stAi");
  st.classList.toggle("hidden", !ai.supported || !ai.enabled);
  st.innerHTML = `${icon("sparkle")}<span>${esc(aiStatusText())}</span>`;
  $$("[data-cmd^='ai.']").forEach((b) => b.classList.toggle("hidden", !ai.enabled));
  if ($("#home") && !$("#home").classList.contains("hidden")) renderHomeAI();
  if (S.right === "ai") renderAIHeader();
}
function aiStatusText() {
  const ai = S.ai;
  if (!ai.enabled) return "AI off";
  return { online: `${ai.model} on NPU${ai.tps ? ` · ${ai.tps} tok/s` : ""}`, starting: ai.detail || "Loading model…", missing: "FastFlowLM not installed",
    nomodel: "No model downloaded", pulling: ai.detail || "Downloading model…", offline: ai.detail || "AI engine stopped" }[ai.state] || ai.state;
}

function openAI(mode) {
  if (!S.ai.supported) return toast(S.ai.reason || "Local AI isn't available on this PC", { err: true });
  if (!S.ai.enabled) return toast("Turn on Local AI in Settings first", { action: { label: "Settings", fn: () => run("app.settings") } });
  if (mode) AI.mode = mode;
  if (!doc() && AI.mode === "doc") AI.mode = "guide";
  if (S.right !== "ai") {
    S.right = "ai";
    $("#right").classList.remove("hidden");
    if (doc() && view().fit !== "custom") setTimeout(() => setFit(view().fit), 30);
  }
  renderAI();
  refreshAI();
  if (S.ai.state !== "online" && !["starting", "pulling", "missing", "nomodel"].includes(S.ai.state)) api("ai/start").then((r) => { S.ai = r; refreshAI(); }).catch(() => {});
}
function closeAI() {
  S.right = null;
  $("#right").classList.add("hidden");
  refreshAI();
  if (doc() && view().fit !== "custom") setTimeout(() => setFit(view().fit), 30);
}

function chat() {
  if (AI.mode === "guide") return AI.guide;
  const id = S.active || "none";
  return (AI.chats[id] = AI.chats[id] || []);
}

function renderAI() {
  const host = $("#rightBody");
  host.innerHTML = `<div class="ai-panel"><div class="ai-head"><span class="orb">${icon("sparkle")}</span><div class="t"><b>Washi AI</b><span id="aiSub"></span></div>
      <button class="icon-btn sm" id="aiClear" title="New conversation">${icon("refresh")}</button><button class="icon-btn sm" id="aiClose" title="Close">${icon("x")}</button></div>
    <div class="seg"><button data-m="doc" ${!doc() ? "disabled style='opacity:.4'" : ""}>This document</button><button data-m="guide">How to use Washi</button></div>
    <div class="ai-msgs" id="aiMsgs"></div>
    <div class="ai-input"><div class="box"><textarea id="aiQ" rows="1" placeholder=""></textarea><button class="send" id="aiSend" title="Send (Enter)">${icon("send")}</button></div>
    <div class="hint">Runs privately on your NPU · answers can be wrong, check important facts</div></div></div>`;
  $$(".seg button", host).forEach((b) => { b.classList.toggle("on", b.dataset.m === AI.mode); b.onclick = () => { if (!b.disabled) { AI.mode = b.dataset.m; renderAI(); } }; });
  $("#aiClose").onclick = closeAI;
  $("#aiClear").onclick = () => { if (AI.busy) return; chat().length = 0; renderAI(); };
  const q = $("#aiQ");
  q.placeholder = AI.mode === "doc" ? "Ask about this document…" : "How do I…?";
  q.oninput = () => { q.style.height = "auto"; q.style.height = Math.min(q.scrollHeight, 140) + "px"; };
  q.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } };
  const send = () => { if (AI.busy) return stopAI(); const v = q.value.trim(); if (!v) return; q.value = ""; q.oninput(); aiAsk(v); };
  $("#aiSend").onclick = send;
  renderAIHeader();
  renderMsgs();
  setTimeout(() => q.focus(), 50);
}

function renderAIHeader() {
  const sub = $("#aiSub");
  if (!sub) return;
  const ai = S.ai;
  sub.innerHTML = `<span class="ai-dot ${ai.state === "online" ? "online" : ["starting", "pulling"].includes(ai.state) ? "starting" : ""}" style="width:6px;height:6px"></span>${esc(aiStatusText())}`;
  const send = $("#aiSend");
  if (send) { send.classList.toggle("stop", !!AI.busy); send.innerHTML = icon(AI.busy ? "stop" : "send"); send.title = AI.busy ? "Stop" : "Send (Enter)"; }
  if (!chat().length) renderMsgs();
}

function renderMsgs() {
  const box = $("#aiMsgs");
  if (!box) return;
  const ai = S.ai;
  box.innerHTML = "";
  if (ai.state === "missing" || ai.state === "nomodel" || ai.state === "pulling") {
    box.innerHTML = ai.state === "missing"
      ? `<div class="ai-card"><h3>Install FastFlowLM</h3><p>Your ${esc(ai.npu || "Ryzen AI NPU")} can run Washi's assistant. It needs the free FastFlowLM engine from AMD's partner project.</p><button class="btn primary" id="aiGet">${icon("external")}Get FastFlowLM</button><p class="muted" style="margin-top:10px;font-size:12px">After installing, restart Washi.</p></div>`
      : `<div class="ai-card"><h3>${ai.state === "pulling" ? "Downloading the model" : "Download the AI model"}</h3><p>Washi uses qwen3:4b (about 3 GB). It is downloaded once and stays on this PC.</p>
        ${ai.state === "pulling" ? `<div class="progress"><i style="width:${ai.pull || 0}%"></i></div><p class="muted">${esc(ai.detail)}</p>` : `<button class="btn primary" id="aiPull">${icon("download")}Download qwen3:4b</button>`}</div>`;
    $("#aiGet") && ($("#aiGet").onclick = () => api("open_url", { url: ai.flm_url }));
    $("#aiPull") && ($("#aiPull").onclick = () => api("ai/pull", {}).then((r) => { S.ai = r; refreshAI(); renderMsgs(); }).catch(fail));
    return;
  }
  const msgs = chat();
  if (!msgs.length) {
    const intro = document.createElement("div");
    intro.className = "ai-intro";
    if (AI.mode === "doc") {
      intro.innerHTML = `<h3>${esc(doc() ? doc().name : "")}</h3>Summarise it or ask anything — answers point to the pages they come from.
        <div class="chips"><button class="chip" data-sum="brief">${icon("sparkle")}Quick summary</button><button class="chip" data-sum="bullets">${icon("list")}Key points</button><button class="chip" data-sum="detailed">${icon("fileText")}Detailed summary</button></div>
        <div class="chips">${["What is this document about?", "List all dates and deadlines", "Who are the people or companies involved?", "What are the main numbers?"].map((s) => `<button class="chip" data-q="${esc(s)}">${esc(s)}</button>`).join("")}</div>`;
    } else {
      intro.innerHTML = `<h3>Find your way around Washi</h3>Ask how to do something and I'll show you where it is.
        <div class="chips">${["How do I highlight text?", "How do I sign a PDF?", "How do I edit text in a PDF?", "How do I merge two PDFs?", "How do I add a password?", "How do I reorder pages?"].map((s) => `<button class="chip" data-q="${esc(s)}">${esc(s)}</button>`).join("")}</div>`;
    }
    intro.onclick = (e) => { const c = e.target.closest(".chip"); if (!c) return; if (c.dataset.sum) aiSummary(c.dataset.sum); else aiAsk(c.dataset.q); };
    box.appendChild(intro);
  }
  for (const m of msgs) box.appendChild(msgEl(m));
  box.scrollTop = box.scrollHeight;
}

function msgEl(m) {
  const el = document.createElement("div");
  el.className = "msg " + (m.role === "user" ? "user" : "bot");
  m.el = el;
  if (m.role === "user") { el.textContent = m.text; return el; }
  drawBot(m);
  return el;
}

function drawBot(m) {
  const el = m.el;
  if (!el) return;
  let html = "";
  if (m.status && !m.text) html += `<div class="status">${m.pct != null ? `<div class="bar"><i style="width:${m.pct}%"></i></div>` : ""}<span>${esc(m.status)}</span></div>`;
  if (m.error) html += `<p style="color:var(--verm)">${esc(m.error)}</p>`;
  else if (m.text) html += `<div class="${m.done ? "" : "caret"}">${md(m.text)}</div>`;
  else if (!m.status) html += `<span class="typing"><i></i><i></i><i></i></span>`;
  const low = (m.text || "").toLowerCase();
  const acts = (m.actions || []).filter((a, i) => CMD[a.action] && (i === 0 || low.includes((CMD[a.action].short || CMD[a.action].label).toLowerCase())));
  if (acts.length && m.done) html += `<div class="acts">${acts.slice(0, 3).map((a) => `<button class="chip" data-show="${a.action}">${icon("eye")}Show me: ${esc(CMD[a.action].label)}</button>`).join("")}</div>`;
  if (m.done && m.text) html += `<div class="meta"><button data-copy>${icon("copy")}Copy</button>${m.kind === "summary" && doc() ? `<button data-note>${icon("note")}Add as note</button>` : ""}<span>${m.cancelled ? "Stopped" : m.secs ? `${m.secs} s${m.tps ? ` · ${m.tps} tok/s` : ""}` : ""}</span></div>`;
  el.innerHTML = html;
  el.onclick = (e) => {
    const pg = e.target.closest(".pg");
    if (pg && doc()) return gotoPage(+pg.dataset.page - 1, null, true);
    const sh = e.target.closest("[data-show]");
    if (sh) return showMe(sh.dataset.show);
    if (e.target.closest("[data-copy]")) { navigator.clipboard.writeText(m.text); toast("Copied"); }
    if (e.target.closest("[data-note]")) api("annot_add", { d: doc().id, p: 0, kind: "note", o: { point: [20, 20], content: "AI summary:\n\n" + m.text, color: "#ffd84d" } }).then(() => toast("Added as a note on page 1")).catch(fail);
  };
}

function push(role, text, extra = {}) {
  const m = { role, text, ...extra };
  chat().push(m);
  const box = $("#aiMsgs");
  if (box) { if (chat().length === 1) box.innerHTML = ""; box.appendChild(msgEl(m)); box.scrollTop = box.scrollHeight; }
  return m;
}

async function streamInto(m, path, body) {
  const ctl = new AbortController();
  AI.busy = ctl;
  renderAIHeader();
  let pending = false;
  const redraw = () => { if (pending) return; pending = true; requestAnimationFrame(() => { pending = false; drawBot(m); const b = $("#aiMsgs"); if (b && b.scrollHeight - b.scrollTop - b.clientHeight < 140) b.scrollTop = b.scrollHeight; }); };
  let waited = false;
  try {
    await apiStream(path, body, (ev) => {
      if (ev.type === "text") { m.text += ev.text; m.status = null; }
      else if (ev.type === "status") { m.status = ev.text; m.pct = ev.pct ?? null; }
      else if (ev.type === "reset") m.text = "";
      else if (ev.type === "cites") m.cites = ev.pages;
      else if (ev.type === "actions") m.actions = ev.items;
      else if (ev.type === "wait") { waited = true; m.status = ev.text; }
      else if (ev.type === "error") m.error = ev.text;
      else if (ev.type === "done") { m.done = true; m.tps = ev.tps; m.secs = ev.secs; m.cancelled = ev.cancelled; if (ev.tps) S.ai.tps = ev.tps; }
      redraw();
    }, ctl.signal);
  } catch (e) {
    if (e.name !== "AbortError") m.error = e.message;
    m.done = true;
  }
  AI.busy = null;
  if (waited && !m.text && !m.error) {
    // the model was still loading: wait until it is online, then ask again
    m.done = false;
    for (let i = 0; i < 120; i++) {
      await sleep(1500);
      S.ai = await api("ai/state").catch(() => S.ai);
      refreshAI();
      m.status = aiStatusText(); redraw();
      if (S.ai.state === "online") return streamInto(m, path, body);
      if (["offline", "missing", "nomodel"].includes(S.ai.state)) { m.error = S.ai.detail || "The AI engine could not start."; break; }
    }
    m.done = true;
  }
  if (!m.done) m.done = true;
  m.status = null;
  drawBot(m);
  renderAIHeader();
}

function history() {
  return chat().filter((m) => m.text && !m.error && (m.role === "user" || m.done)).slice(-6, -1).map((m) => ({ role: m.role === "user" ? "user" : "assistant", text: m.text }));
}

async function aiAsk(q) {
  if (AI.busy) return toast("Wait for the current answer, or press stop");
  if (AI.mode === "doc" && !doc()) AI.mode = "guide";
  if (S.right !== "ai") openAI();
  push("user", q);
  const m = push("bot", "", { kind: "answer" });
  if (AI.mode === "doc") await streamInto(m, "ai/ask", { d: doc().id, q, history: history() });
  else await streamInto(m, "ai/guide", { q, history: history(), context: { doc: !!doc(), tool: S.tool, tab: S.ribbonTab } });
}

async function aiSummary(style = "bullets") {
  if (!doc()) return toast("Open a PDF first");
  if (AI.busy) return toast("Wait for the current answer, or press stop");
  openAI("doc");
  push("user", { brief: "Quick summary", bullets: "Key points", detailed: "Detailed summary" }[style]);
  const m = push("bot", "", { kind: "summary" });
  await streamInto(m, "ai/summary", { d: doc().id, style });
}

async function aiSelection(text, mode, lang) {
  if (mode === "translate" && !lang) {
    const r = $("#floatbar").getBoundingClientRect();
    const guess = (() => { try { return new Intl.DisplayNames(["en"], { type: "language" }).of(navigator.language.split("-")[0]); } catch (e) { return "English"; } })();
    const langs = [...new Set([guess, ...LANGS])];
    showMenu(r.left + 40, r.top + 10, [{ header: "Translate into" }, ...langs.map((l) => ({ label: l, action: () => aiSelection(text, "translate", l) }))]);
    return;
  }
  if (AI.busy) return toast("Wait for the current answer, or press stop");
  openAI("doc");
  const label = { explain: "Explain", translate: `Translate into ${lang}`, simplify: "Simplify", keypoints: "Key points of", proofread: "Proofread" }[mode];
  push("user", `${label}: “${text.length > 220 ? text.slice(0, 220) + "…" : text}”`);
  const m = push("bot", "", { kind: "selection" });
  await streamInto(m, "ai/selection", { text, mode, lang });
}

function stopAI() {
  if (!AI.busy) return;
  api("ai/cancel").catch(() => {});
  setTimeout(() => AI.busy && AI.busy.abort(), 1500);
}
