"use strict";
/* Kaizen 5S — front end. Plain JS, no frameworks, no network access beyond 127.0.0.1. */

const TOKEN = window.KAIZEN_TOKEN;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const sleep = ms => new Promise(r => setTimeout(r, ms));

const PATHS = {
  overview: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  map: '<rect x="3" y="3" width="18" height="18" rx="2.5"/><path d="M12 3v18M12 10h9M3 15h9"/>',
  files: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  programs: '<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M3 9h18"/><path d="M6.5 6.5h.01M9 6.5h.01"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12z"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  auto: '<circle cx="12" cy="12" r="9"/><path d="M12 3v18" /><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor"/>',
  scan: '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/><path d="M10 11v5M14 11v5"/>',
  move: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M10 13h6M13 10l3 3-3 3"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 17l.6 1.4L21 19l-1.4.6L19 21l-.6-1.4L17 19l1.4-.6z"/>',
  open: '<path d="M14 4h6v6M20 4l-9 9M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  pen: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
  send: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  chip: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
  undo: '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  shield: '<path d="M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6z"/>',
  keep: '<path d="M12 21s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.6-7 10-7 10z"/>',
  app: '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M9 12h6M12 9v6"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  cloud: '<path d="M7 18h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6.1 9.5 4.25 4.25 0 0 0 7 18z"/>',
  usb: '<path d="M12 3v13M9 6l3-3 3 3M8 10v2l4 3 4-3v-2"/><circle cx="12" cy="19" r="2"/>',
  pc: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
};
const icon = n => `<i data-icon="${n}"><svg viewBox="0 0 24 24">${PATHS[n] || ''}</svg></i>`;
const hydrateIcons = (root = document) =>
  $$('i[data-icon]', root).forEach(i => { if (!i.firstChild) i.innerHTML = `<svg viewBox="0 0 24 24">${PATHS[i.dataset.icon] || ''}</svg>`; });

const S = {
  sort:    { kanji: '整理', romaji: 'Seiri',    en: 'Sort',         desc: 'Let go of what you no longer use: long-forgotten files and duplicates.' },
  order:   { kanji: '整頓', romaji: 'Seiton',   en: 'Set in order', desc: 'A place for everything: files lingering in Downloads or loose on the Desktop.' },
  shine:   { kanji: '清掃', romaji: 'Seiso',    en: 'Shine',        desc: 'Clear the dust: temp files, old installers, empty folders, broken shortcuts.' },
  std:     { kanji: '清潔', romaji: 'Seiketsu', en: 'Standardize',  desc: 'One naming habit: no more “final (2)”, “copy” or “untitled”.' },
  sustain: { kanji: '躾',   romaji: 'Shitsuke', en: 'Sustain',      desc: 'Folders that stay clean, and a regular 5S check to keep it that way.' },
};
const NEED = { ...S, app: { kanji: '他', romaji: 'App data', en: 'Managed by programs' } };
const SUGGEST = [
  'What can I safely clean up first?',
  'Which programs haven’t I used in ages?',
  'What are my biggest files that I don’t use?',
  'How can I improve my Seiton score?',
];

const state = { view: null, params: {}, status: null, overview: null, list: null, sel: new Map(), chat: [], queue: [],
  describing: false, chatBusy: false };

/* ---------------------------------------------------------------- helpers */
async function api(path, body) {
  const opt = { headers: { 'X-Kaizen': TOKEN } };
  if (body !== undefined) {
    opt.method = 'POST';
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(body);
  }
  const r = await fetch(path, opt);
  if (r.status === 403) { location.reload(); throw new Error('Kaizen restarted, reloading…'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(data.error || r.statusText), { status: r.status });
  return data;
}
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function fmtBytes(n) {
  if (!n) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0;
  while (n >= 1024 && i < 4) { n /= 1024; i++; }
  return (i < 2 ? Math.round(n) : n.toFixed(n < 10 ? 1 : 0)) + ' ' + u[i];
}
function ago(ts) {
  if (!ts) return 'never';
  const d = (Date.now() / 1000 - ts) / 86400;
  if (d < 1) return 'today';
  if (d < 2) return 'yesterday';
  if (d < 14) return `${Math.floor(d)} days ago`;
  if (d < 60) return `${Math.floor(d / 7)} weeks ago`;
  if (d < 730) return `${Math.floor(d / 30.4)} months ago`;
  return `${Math.round(d / 365)} years ago`;
}
const fmtDate = ts => ts ? new Date(ts * 1000).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : '—';
const thumbUrl = (path, size = 256, mode = '') =>
  `/api/thumb?t=${encodeURIComponent(TOKEN)}&size=${size}&mode=${mode}&path=${encodeURIComponent(path)}`;
const tail = p => { const parts = (p || '').split('\\'); return parts.slice(-2).join('\\'); };
const extOf = n => (n.split('.').length > 1 ? n.split('.').pop() : 'file').slice(0, 5);

function ring(value, size, stroke, col, label = '') {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(1, value || 0));
  return `<div class="ring" style="width:${size}px;height:${size}px">
    <svg width="${size}" height="${size}"><circle class="track" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${stroke}"/>
    <circle class="bar" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${stroke}" stroke="${col}"
      stroke-dasharray="${c}" stroke-dashoffset="${c}" data-target="${c * (1 - v)}"/></svg>
    <div class="val"><b data-count="${Math.round(v * 100)}">0%</b>${label ? `<small>${label}</small>` : ''}</div></div>`;
}
function animateIn(root) {
  requestAnimationFrame(() => requestAnimationFrame(() => {
    $$('.ring .bar', root).forEach(b => { b.style.strokeDashoffset = b.dataset.target; });
    $$('[data-count]', root).forEach(countUp);
  }));
}
function countUp(el) {
  const to = +el.dataset.count, t0 = performance.now(), dur = 1300;
  const step = t => {
    const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(to * e) + '%';
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
function setTitle(t, sub) { $('#viewTitle').textContent = t; $('#viewSub').textContent = sub || ''; document.title = `${t} · Kaizen 5S`; }

/* ---------------------------------------------------------------- toasts, modal, sheet */
function toast(msg, { undo, ms = 6000 } = {}) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.innerHTML = `<span>${msg}</span>${undo ? `<button class="btn sm">${icon('undo')} Undo</button>` : ''}`;
  $('#toasts').appendChild(t);
  const close = () => { t.classList.add('out'); setTimeout(() => t.remove(), 400); };
  if (undo) $('button', t).onclick = async () => {
    close();
    const r = await api('/api/action', { op: 'undo', batch: undo });
    const lost = (r.failed || []).length;
    toast(`Restored ${r.restored} item${r.restored === 1 ? '' : 's'}${lost ? ` · ${lost} not found in the Recycle Bin any more` : ''}`);
    state.overview = null;
    route();
  };
  setTimeout(close, ms);
}
function openModal(html, cls = '') {
  const m = $('#modal');
  m.className = 'modal ' + cls;
  m.innerHTML = html;
  hydrateIcons(m);
  $('#scrim').classList.add('on');
  requestAnimationFrame(() => m.classList.add('on'));
  return m;
}
function closeModal() {
  $('#modal').classList.remove('on');
  if (!$('#sheet').classList.contains('on')) $('#scrim').classList.remove('on');
}
function confirmBox({ title, text, ok = 'Confirm', danger = false }) {
  return new Promise(resolve => {
    const m = openModal(`<h2>${title}</h2><p>${text}</p><div class="foot">
      <button class="btn ghost" data-no>Cancel</button><button class="btn ${danger ? 'danger' : 'primary'}" data-yes>${ok}</button></div>`);
    $('[data-no]', m).onclick = () => { closeModal(); resolve(false); };
    $('[data-yes]', m).onclick = () => { closeModal(); resolve(true); };
  });
}
function openSheet(html) {
  const s = $('#sheet');
  s.innerHTML = html;
  hydrateIcons(s);
  s.scrollTop = 0;
  $('#scrim').classList.add('on');
  requestAnimationFrame(() => s.classList.add('on'));
  return s;
}
function closeSheet() {
  $('#sheet').classList.remove('on');
  if (!$('#modal').classList.contains('on')) $('#scrim').classList.remove('on');
}
$('#scrim').onclick = () => { closeModal(); closeSheet(); };

/* ---------------------------------------------------------------- router */
const VIEWS = { overview: viewOverview, map: viewMap, files: viewFiles, programs: viewPrograms };
function parseHash() {
  const h = location.hash.replace(/^#\/?/, '') || 'overview';
  const [v, q] = h.split('?');
  return { view: VIEWS[v] ? v : 'overview', params: Object.fromEntries(new URLSearchParams(q || '')) };
}
async function route() {
  const { view, params } = parseHash();
  tooltipOff();
  if (view === 'map' && state.view === 'map' && $('#tm')) {
    state.params = params;
    return drawMap(params.path || '');
  }
  state.view = view;
  state.params = params;
  clearSel();
  closeSheet();
  $$('.rail-nav a').forEach(a => a.classList.toggle('active', a.dataset.view === view));
  const v = $('#view');
  v.innerHTML = '';
  $('#main').scrollTop = 0;
  try {
    await VIEWS[view](v, params);
  } catch (e) {
    v.innerHTML = `<div class="empty"><h2>Something went wrong</h2><p>${esc(e.message)}</p></div>`;
  }
  hydrateIcons(v);
}
window.addEventListener('hashchange', route);
document.addEventListener('click', e => {
  const go = e.target.closest('[data-go]');
  if (go) { location.hash = go.dataset.go; return; }
  const ask = e.target.closest('[data-chat]');
  if (ask) openChat(ask.dataset.chat);
  if (e.target.closest('[data-close]')) { closeSheet(); closeModal(); }
});

/* ---------------------------------------------------------------- overview */
function emptyState() {
  const scanning = state.status?.scan?.running;
  return `<div class="empty">
    <svg class="enso" viewBox="0 0 120 120"><path d="M100 62a40 40 0 1 1-16.5-32.4"/></svg>
    <h2>${scanning ? 'Looking through your folders…' : 'Begin with a 5S check'}</h2>
    <p>Kaizen looks through Desktop, Documents, Downloads, Pictures, Videos and Music,<br>plus your installed programs. It only reads and never changes anything on its own.</p>
    ${scanning ? '' : `<button class="btn primary" onclick="startScan()" style="margin-top:14px">${icon('scan')} Run my first 5S check</button>`}
  </div>`;
}
function sparkline(h) {
  if (!h || h.length < 2) return `<div class="spark"><h4>Trend</h4><p class="note">Your 5S trend appears after your second check. Regular checks are the heart of Shitsuke.</p></div>`;
  const W = 220, H = 60, vals = h.map(x => x.overall);
  const mn = Math.min(...vals) - 0.05, mx = Math.max(...vals) + 0.02;
  const xs = vals.map((_, i) => i / (vals.length - 1) * W), ys = vals.map(v => H - (v - mn) / (mx - mn || 1) * H);
  const d = xs.map((x, i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${ys[i].toFixed(1)}`).join('');
  return `<div class="spark"><h4>Trend · ${h.length} checks</h4><svg viewBox="0 0 ${W} ${H}">
    <path class="area" d="${d}L${W},${H}L0,${H}Z"/><path class="line" d="${d}"/>
    <circle cx="${xs.at(-1)}" cy="${ys.at(-1)}" r="3.5" fill="var(--ink)"/></svg></div>`;
}
async function viewOverview(v) {
  setTitle('Overview', 'Your PC through the lens of 5S' + (edition().name ? ` · ${edition().name}` : ''));
  const o = await api('/api/overview');
  state.overview = o;
  const sc = o.scores;
  if (!sc) { v.innerHTML = emptyState(); return; }
  const pc = o.program_counts || {};
  const pct = Math.round(sc.overall * 100);
  const mood = pct >= 90 ? 'Beautifully in order' : pct >= 75 ? 'Mostly in order' : pct >= 55 ? 'Some tidying will help' : 'Time for a good 5S session';
  const toReview = sc.counts.sort + sc.counts.order + sc.counts.shine + sc.counts.std;
  const stackBar = f => {
    const total = f.sort_n + f.order_n + f.shine_n + f.std_n || 1;
    return `<div class="stack">${['sort', 'order', 'shine', 'std'].map(k => `<span style="width:${f[k + '_n'] / total * 100}%;background:var(--${k})"></span>`).join('')}</div>`;
  };
  v.innerHTML = `
  <section class="hero">
    ${ring(sc.overall, 150, 12, 'var(--ink)', '5S score')}
    <div>
      <h2>${mood}</h2>
      <p>Kaizen checked <b>${sc.files.toLocaleString()}</b> of your own files and <b>${(pc.n || 0) - (pc.lo || 0)}</b> programs.
      ${o.managed.n ? `${o.managed.n.toLocaleString()} game and app files (${fmtBytes(o.managed.b)}) were left alone because programs manage them.` : ''}</p>
      <div class="facts">
        <div class="fact"><b>${fmtBytes(sc.reclaim)}</b><span>could be freed</span></div>
        <div class="fact"><b>${toReview}</b><span>files to review</span></div>
        <div class="fact"><b>${pc.unused || 0}</b><span>programs gathering dust</span></div>
        <div class="fact"><b>${ago(state.status?.last_scan)}</b><span>last 5S check</span></div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn primary" data-go="#/files">Review files</button>
        <button class="btn" data-go="#/programs">Review programs</button>
        <button class="btn ghost" data-chat="What should I clean up first?">${icon('spark')} Ask what to do first</button>
      </div>
    </div>
    ${sparkline(o.history)}
  </section>
  <div class="section-h"><h3>The five S</h3><span>Tap one to see exactly what it found</span></div>
  <section class="s-grid">${Object.entries(S).map(([k, m]) => `
    <button class="s-card" style="--c:var(--${k})" data-go="#/files?s=${k}">
      <span class="kanji">${m.kanji}</span>
      <div class="top">${ring(sc.scores[k], 54, 6, `var(--${k})`)}<h4>${m.romaji}<small>${m.en}</small></h4></div>
      <p>${m.desc}</p>
      <div class="count"><span><b>${sc.counts[k]}</b> ${k === 'sustain' ? 'files in good shape' : 'to review'}</span>
        <span>${k === 'sustain' ? `${sc.scans_30d} checks / 30 days` : (sc.bytes[k] ? fmtBytes(sc.bytes[k]) : '')}</span></div>
    </button>`).join('')}
  </section>
  <section class="two-col">
    <div class="panel"><h3>Folders that need attention</h3><p>Colour shows which S each folder needs.</p>
      ${o.folders.length ? o.folders.map(f => `
        <div class="row-item" data-go="#/map?path=${encodeURIComponent(f.path)}">
          <div class="ico" style="color:var(--${f.need})">${icon('folder')}</div>
          <div><div class="name">${esc(f.name)}</div><div class="sub">${esc(tail(f.path))} · ${f.files} files</div>${stackBar(f)}</div>
          <div class="right" style="color:var(--${f.need})">${NEED[f.need].romaji}</div>
        </div>`).join('') : `<p class="note">Every folder is in good shape. That is Shitsuke.</p>`}
    </div>
    <div class="panel"><h3>Programs gathering dust</h3><p>Installed, but Windows hasn’t seen you use them in a long time.</p>
      ${o.programs.length ? o.programs.map(p => `
        <div class="row-item" data-go="#/programs">
          <div class="ico">${p.exe ? `<img src="${thumbUrl(p.exe, 64, 'icon')}" alt="" onerror="this.remove()">` : icon('app')}</div>
          <div><div class="name">${esc(p.name)}</div><div class="sub">${p.last_run ? 'Last used ' + ago(p.last_run) : 'No record of use'}</div></div>
          <div class="right">${p.size ? fmtBytes(p.size) : ''}</div>
        </div>`).join('') : `<p class="note">No unused programs found.</p>`}
    </div>
  </section>
  <p class="copyright">${editionLine()}</p>`;
  animateIn(v);
}

/* ---------------------------------------------------------------- map */
function squarify(items, x, y, w, h) {
  const out = [], rest = items.slice();
  const total = rest.reduce((a, b) => a + b.value, 0);
  if (!total) return out;
  const scale = (w * h) / total;
  const worst = (row, side) => {
    const s = row.reduce((a, b) => a + b.value * scale, 0);
    const mx = Math.max(...row.map(r => r.value * scale)), mn = Math.min(...row.map(r => r.value * scale));
    return Math.max(side * side * mx / (s * s), (s * s) / (side * side * mn));
  };
  while (rest.length) {
    const side = Math.min(w, h);
    let row = [], best = Infinity;
    while (rest.length) {
      const cand = row.concat([rest[0]]);
      const wr = worst(cand, side);
      if (wr > best) break;
      best = wr; row = cand; rest.shift();
    }
    const area = row.reduce((a, b) => a + b.value * scale, 0);
    if (w >= h) {
      const cw = area / h; let cy = y;
      for (const it of row) { const ih = it.value * scale / cw; out.push({ ...it, x, y: cy, w: cw, h: ih }); cy += ih; }
      x += cw; w -= cw;
    } else {
      const ch = area / w; let cx = x;
      for (const it of row) { const iw = it.value * scale / ch; out.push({ ...it, x: cx, y, w: iw, h: ch }); cx += iw; }
      y += ch; h -= ch;
    }
  }
  return out;
}
async function viewMap(v, params) {
  setTitle('Folder map', 'Size = space used · colour = which S the folder needs most');
  v.innerHTML = `<div class="map-head"><div class="crumbs" id="crumbs"></div>
    <div class="legend">${Object.entries(S).map(([k, m]) => `<span><i class="sw" style="background:var(--${k})"></i>${m.en}</span>`).join('')}
      <label style="display:inline-flex;gap:8px;align-items:center;cursor:pointer"><span>Show game &amp; app data</span>
      <span class="switch" style="transform:scale(.8)"><input type="checkbox" id="showApp" ${showApp() ? 'checked' : ''}><span></span></span></label></div></div>
    <div class="treemap" id="tm"></div>`;
  $('#showApp').onchange = e => {
    try { localStorage.setItem('kaizen-show-app', e.target.checked ? '1' : ''); } catch { /* ignore */ }
    drawMap(state.params.path || '');
  };
  await drawMap(params.path || '');
}
function showApp() { try { return !!localStorage.getItem('kaizen-show-app'); } catch { return false; } }
async function drawMap(path) {
  const tm = $('#tm');
  if (!tm) return;
  const t = await api('/api/tree?path=' + encodeURIComponent(path));
  const crumbs = [{ path: '', name: 'This PC' }, ...(t.crumbs || [])];
  $('#crumbs').innerHTML = crumbs.map((c, i) => `${i ? '<span class="sep">/</span>' : ''}<button data-path="${esc(c.path)}">${esc(c.name)}</button>`).join('')
    + (path ? `<span class="sep"></span><button class="btn sm" data-files="${esc(path)}">${icon('files')} Show files</button>` : '');
  hydrateIcons($('#crumbs'));
  $$('#crumbs [data-path]').forEach(b => b.onclick = () => { location.hash = '#/map' + (b.dataset.path ? '?path=' + encodeURIComponent(b.dataset.path) : ''); });
  const fb = $('#crumbs [data-files]');
  if (fb) fb.onclick = () => { location.hash = `#/files?s=everything&path=${encodeURIComponent(fb.dataset.files)}`; };

  const withApp = showApp();
  const kids = (t.children || []).map(c => withApp ? c : {
    ...c, bytes: c.bytes - (c.managed_bytes || 0), files: c.files - (c.managed_n || 0), app_bytes: c.managed_bytes || 0,
  }).filter(c => (c.bytes > 0 || c.files > 0) && (withApp || c.need !== 'app'));
  if (!kids.length) {
    tm.innerHTML = `<div class="empty"><p>${t.children?.length ? 'Only game and app data here. Switch on “Show game & app data” to see it.' : 'No scan data yet. Run a 5S check first.'}</p></div>`;
    return;
  }
  const W = tm.clientWidth, H = tm.clientHeight;
  const total = kids.reduce((a, c) => a + c.bytes, 0) || 1;
  const items = kids.map(c => ({ ...c, value: Math.max(c.bytes, total * 0.008) })).sort((a, b) => b.value - a.value);
  const rects = squarify(items, 0, 0, W, H);
  state.tiles = rects;
  tm.innerHTML = rects.map((r, i) => {
    const k = r.need || 'sustain';
    const a = k === 'sustain' ? 16 : k === 'app' ? 22 : Math.round(24 + Math.min(1, r.severity * 1.6) * 40);
    const small = r.w < 96 || r.h < 56;
    return `<div class="tile ${small ? 'small' : ''} ${r.files_here ? 'files' : ''}" data-i="${i}"
      style="left:${r.x / W * 100}%;top:${r.y / H * 100}%;width:${r.w / W * 100}%;height:${r.h / H * 100}%;animation-delay:${Math.min(i * 22, 480)}ms">
      <div style="--c:var(--${k});--a:${a}%"><div><div class="tn">${esc(r.name)}</div>
      <div class="ts">${fmtBytes(r.bytes)} · ${r.files.toLocaleString()} files</div></div><span class="tk">${NEED[k].kanji}</span></div></div>`;
  }).join('');
  $$('.tile', tm).forEach(el => {
    const r = rects[+el.dataset.i];
    el.onmousemove = e => tooltipOn(e, tileTip(r));
    el.onmouseleave = tooltipOff;
    el.onclick = () => {
      tooltipOff();
      if (r.files_here) { location.hash = `#/files?s=everything&here=1&path=${encodeURIComponent(r.path)}`; return; }
      if (!r.subdirs) { location.hash = `#/files?s=everything&path=${encodeURIComponent(r.path)}`; return; }
      const z = document.createElement('div');
      const inner = el.firstElementChild;
      z.className = 'zoomer';
      z.style.cssText = `left:${el.offsetLeft + 3}px;top:${el.offsetTop + 3}px;width:${el.offsetWidth - 6}px;height:${el.offsetHeight - 6}px;background:${getComputedStyle(inner).backgroundColor}`;
      tm.appendChild(z);
      requestAnimationFrame(() => { z.style.cssText += ';left:0;top:0;width:100%;height:100%;border-radius:0'; });
      setTimeout(() => { location.hash = '#/map?path=' + encodeURIComponent(r.path); }, 380);
    };
  });
}
function tileTip(r) {
  const k = r.need || 'sustain';
  const label = k === 'sustain' ? `<span style="color:var(--sustain)">躾 In good shape</span>`
    : k === 'app' ? `<span style="color:var(--muted)">Managed by programs, left alone</span>`
    : `<span style="color:var(--${k})">${NEED[k].kanji} Needs ${NEED[k].romaji} · ${NEED[k].en}</span>`;
  const issues = ['sort', 'order', 'shine', 'std'].filter(s => r[s + '_n'] > 0)
    .map(s => `<div class="tl"><span style="color:var(--${s})">${S[s].romaji}</span><b>${r[s + '_n']}</b></div>`).join('');
  return `<h5>${esc(r.name)}</h5><div class="tl"><span>Size</span><b>${fmtBytes(r.bytes)}</b></div>
    <div class="tl"><span>Files</span><b>${r.files.toLocaleString()}</b></div>
    <div class="tl"><span>Last activity</span><b>${ago(r.last_used)}</b></div>
    ${r.app_bytes ? `<div class="tl"><span>Game/app data (hidden)</span><b>${fmtBytes(r.app_bytes)}</b></div>` : ''}
    <div class="need">${label}</div>${issues}
    <div class="tl" style="margin-top:6px;color:var(--muted)"><span>${r.files_here ? 'Click to see these files' : r.subdirs ? 'Click to zoom in' : 'Click to see files'}</span></div>`;
}
function tooltipOn(e, html) {
  const t = $('#tooltip');
  if (t.dataset.html !== html) { t.innerHTML = html; t.dataset.html = html; }
  const x = Math.min(e.clientX + 16, innerWidth - t.offsetWidth - 12);
  const y = Math.min(e.clientY + 16, innerHeight - t.offsetHeight - 12);
  t.style.left = x + 'px'; t.style.top = y + 'px';
  t.classList.add('on');
}
function tooltipOff() { $('#tooltip').classList.remove('on'); }

/* ---------------------------------------------------------------- AI descriptions */
const describeObs = new IntersectionObserver(entries => {
  for (const e of entries) if (e.isIntersecting) { describeObs.unobserve(e.target); state.queue.push(e.target); pump(); }
}, { rootMargin: '120px' });
function aiLine(item, kind) {
  if (item.ai) return `<div class="ai-line">${icon('spark')}<span>${esc(item.ai)}</span></div>`;
  if (!state.status?.settings?.auto_describe || ['missing'].includes(state.status?.ai?.state)) return '';
  return `<div class="ai-line loading" data-describe="${kind}:${item.id}">${icon('spark')}<span></span></div>`;
}
function watchDescribe(root) { $$('[data-describe]', root).forEach(el => describeObs.observe(el)); }
async function pump() {
  if (state.describing) return;
  state.describing = true;
  try {
    while (state.queue.length) {
      const ai = state.status?.ai?.state;
      if (ai === 'missing') { state.queue.forEach(el => el.remove()); state.queue = []; break; }
      if (ai !== 'online' || state.chatBusy) { await sleep(1500); continue; }
      const el = state.queue.shift();
      if (!el.isConnected) continue;
      const [kind, id] = el.dataset.describe.split(':');
      try {
        const r = await api('/api/describe', { kind, id: +id });
        if (r.text) {
          el.classList.remove('loading');
          el.classList.add('fresh');
          $('span', el).textContent = r.text;
          const list = state.list?.items || [];
          const it = list.find(x => x.id === +id);
          if (it) it.ai = r.text;
        } else el.remove();
      } catch (e) {
        if (e.status === 503) { state.queue.unshift(el); await sleep(2000); } else el.remove();
      }
    }
  } finally { state.describing = false; }
}

/* ---------------------------------------------------------------- files */
const FILE_TABS = [['all', 'All to review'], ['sort'], ['order'], ['shine'], ['std'], ['sustain', 'In good shape'], ['app', 'App data'], ['everything', 'Everything']];
async function viewFiles(v, params) {
  const s = params.s || 'all';
  const sub = S[s] && s !== 'sustain' ? `${S[s].kanji} ${S[s].romaji}: ${S[s].desc}` : s === 'sustain' ? 'Recently used and without issues. Keep it up.'
    : s === 'app' ? 'Files that games and programs manage. Kaizen never suggests touching them.' : 'Everything Kaizen suggests you look at, biggest first';
  setTitle('Files', sub);
  if (!state.overview) state.overview = await api('/api/overview').catch(() => null);
  const counts = state.overview?.scores?.counts || {};
  const appN = state.overview?.managed?.n;
  v.innerHTML = `
    <div class="toolbar">
      <div class="seg">${FILE_TABS.map(([k, label]) => `<button class="${k === s ? 'on' : ''}" data-s="${k}" style="--c:var(--${k})">
        ${S[k] ? `<span class="k">${S[k].kanji}</span>${label || S[k].en}` : label}
        ${counts[k] != null && k !== 'sustain' ? `<span class="n">${counts[k]}</span>` : k === 'app' && appN ? `<span class="n">${appN}</span>` : ''}</button>`).join('')}</div>
      <label class="search">${icon('search')}<input id="q" placeholder="Search files" value="${esc(params.q || '')}"></label>
      <select id="sort"><option value="size">Biggest first</option><option value="old">Longest unused</option><option value="new">Recently used</option><option value="name">Name</option></select>
      ${params.path ? `<span class="chip">in ${esc(tail(params.path))}<button id="clearPath" title="Clear">${icon('x')}</button></span>` : ''}
      ${params.ids ? `<span class="chip">From your chat<button id="clearPath" title="Clear">${icon('x')}</button></span>` : ''}
    </div>
    <div class="summary" id="summary"></div>
    <div class="grid" id="grid"></div>
    <div class="sentinel" id="sentinel"></div>`;
  $('#sort').value = params.sort || (s === 'sort' ? 'old' : 'size');
  $$('.seg [data-s]', v).forEach(b => b.onclick = () => { location.hash = '#/files?' + new URLSearchParams({ ...pick(params, ['path', 'here']), s: b.dataset.s }); });
  const cp = $('#clearPath');
  if (cp) cp.onclick = () => { location.hash = '#/files?s=' + s; };
  let deb;
  $('#q').oninput = e => { clearTimeout(deb); deb = setTimeout(() => { params.q = e.target.value; loadFiles(true); }, 280); };
  $('#sort').onchange = e => { params.sort = e.target.value; loadFiles(true); };
  const grid = $('#grid');
  grid.addEventListener('load', e => { if (e.target.tagName === 'IMG') e.target.parentElement.classList.add('loaded'); }, true);
  grid.addEventListener('error', e => {
    if (e.target.tagName !== 'IMG') return;
    const th = e.target.parentElement;
    th.classList.add('loaded');
    th.innerHTML = `<span class="glyph">${esc(th.dataset.ext || 'file')}</span>`;
  }, true);
  grid.onclick = e => {
    const card = e.target.closest('.card');
    if (!card) return;
    const item = state.list.items.find(x => x.id === +card.dataset.id);
    if (e.target.closest('.check') || e.ctrlKey || state.sel.size) toggleSel(item, card);
    else openFileSheet(item);
  };
  new IntersectionObserver(es => { if (es[0].isIntersecting) loadFiles(false); }, { rootMargin: '400px' }).observe($('#sentinel'));
  await loadFiles(true);
}
const pick = (o, keys) => Object.fromEntries(keys.filter(k => o[k]).map(k => [k, o[k]]));
async function loadFiles(reset) {
  const params = state.params;
  if (reset) state.list = { items: [], total: 0, offset: 0, done: false, loading: false };
  const L = state.list;
  if (L.loading || L.done) return;
  L.loading = true;
  const q = new URLSearchParams({ s: params.s || 'all', sort: $('#sort')?.value || 'size', offset: L.offset, limit: 60,
    ...pick(params, ['path', 'here', 'q', 'ids']) });
  const d = await api('/api/files?' + q);
  if (state.list !== L) return;
  const grid = $('#grid');
  if (reset) { grid.innerHTML = ''; clearSel(); }
  L.items.push(...d.items);
  L.total = d.total;
  L.offset += d.items.length;
  L.done = d.items.length < 60;
  L.loading = false;
  const start = grid.children.length;
  grid.insertAdjacentHTML('beforeend', d.items.map((f, i) => fileCard(f, start + i)).join(''));
  hydrateIcons(grid);
  watchDescribe(grid);
  $('#summary').innerHTML = L.total ? `<span><b>${L.total.toLocaleString()}</b> files · ${fmtBytes(d.total_bytes)}</span>
      <button class="btn sm ghost" id="selAll">${icon('check')} Select all shown</button>`
    : `<span>${params.s === 'all' || !params.s ? 'Nothing to review here. Your files are in order.' : 'No files in this view.'}</span>`;
  hydrateIcons($('#summary'));
  const sa = $('#selAll');
  if (sa) sa.onclick = () => { $$('#grid .card').forEach(c => { const it = L.items.find(x => x.id === +c.dataset.id); if (!state.sel.has(it.id)) toggleSel(it, c); }); };
  if (!L.items.length && reset) grid.innerHTML = `<div class="empty" style="grid-column:1/-1">
      <svg class="enso" viewBox="0 0 120 120"><path d="M100 62a40 40 0 1 1-16.5-32.4"/></svg><h2>All clear</h2><p>Nothing here needs your attention.</p></div>`;
}
function fileCard(f, i) {
  const media = ['image', 'video'].includes(f.category) && !f.cloud;
  const dots = [...new Set(f.reasons.map(r => r.s))].map(s => `<span style="background:var(--${s})"></span>`).join('');
  const thumb = f.category === 'folder'
    ? `<div class="thumb icon loaded" style="color:var(--muted)">${icon('folder')}</div>`
    : `<div class="thumb ${media ? 'cover' : 'icon'}" data-ext="${esc(extOf(f.name))}"><img loading="lazy" src="${thumbUrl(f.path, media ? 320 : 128)}" alt=""></div>`;
  return `<div class="card ${state.sel.has(f.id) ? 'sel' : ''}" data-id="${f.id}" style="--i:${i % 24}">
    <div class="check">${icon('check')}</div><div class="dots">${dots}</div>${thumb}
    <div class="body"><div class="nm" title="${esc(f.name)}">${esc(f.name)}</div>
      <div class="mt"><span title="${esc(f.dir)}">${esc(tail(f.dir))}</span><span>${f.category === 'folder' ? '' : fmtBytes(f.size)}</span></div>
      <div class="mt"><span>${f.category === 'folder' ? 'Empty folder' : 'Used ' + ago(f.last_used)}</span>${f.remote ? '<span title="Network or removable drive: no Recycle Bin">🌐 network</span>' : f.cloud ? '<span>☁ cloud</span>' : ''}</div>
      ${f.managed ? `<div class="ai-line"><span>${esc(f.managed)}, left alone</span></div>` : aiLine(f, 'file')}
      <div class="reasons">${f.reasons.map(r => `<span class="tag" style="--c:var(--${r.s})">${esc(r.t)}</span>`).join('')}</div>
    </div></div>`;
}
function toggleSel(item, card) {
  if (!item) return;
  if (state.sel.has(item.id)) state.sel.delete(item.id); else state.sel.set(item.id, item);
  card?.classList.toggle('sel', state.sel.has(item.id));
  renderSelbar();
}
function clearSel() { state.sel.clear(); $$('.card.sel').forEach(c => c.classList.remove('sel')); renderSelbar(); }
function renderSelbar() {
  const bar = $('#selbar'), items = [...state.sel.values()];
  $('#grid')?.classList.toggle('selecting', items.length > 0);
  document.body.classList.toggle('sel-open', items.length > 0);
  if (!items.length) { bar.classList.remove('on'); return; }
  const bytes = items.reduce((a, f) => a + (f.size || 0), 0);
  const canMove = items.some(f => f.target), canRename = items.some(f => f.new_name);
  const managed = items.some(f => f.managed || f.remote);  // app data, or a drive without a Recycle Bin
  bar.innerHTML = `<div class="info"><b>${items.length}</b> selected · ${fmtBytes(bytes)}</div>
    <button class="btn sm" data-a="keep">${icon('keep')} Keep</button>
    ${canMove ? `<button class="btn sm" data-a="move">${icon('move')} Move to suggested place</button>` : ''}
    ${canRename ? `<button class="btn sm" data-a="rename">${icon('pen')} Apply clean names</button>` : ''}
    ${managed ? '' : `<button class="btn sm danger" data-a="recycle">${icon('trash')} Recycle</button>`}
    <button class="icon-btn" data-a="clear" style="color:inherit">${icon('x')}</button>`;
  bar.classList.add('on');
  $$('[data-a]', bar).forEach(b => b.onclick = () => {
    const a = b.dataset.a, ids = items.map(f => f.id);
    if (a === 'clear') clearSel();
    else if (a === 'recycle') recycleFiles(items);
    else fileAction(a, ids);
  });
}
function removeCards(ids) {
  ids.forEach(id => {
    const c = $(`#grid .card[data-id="${id}"]`);
    if (c) { c.classList.add('gone'); setTimeout(() => c.remove(), 380); }
    state.sel.delete(id);
    if (state.list) state.list.items = state.list.items.filter(x => x.id !== id);
  });
  renderSelbar();
}
async function recycleFiles(items) {
  const bytes = items.reduce((a, f) => a + (f.size || 0), 0);
  const ok = await confirmBox({
    title: `Move ${items.length} item${items.length > 1 ? 's' : ''} to the Recycle Bin?`,
    text: `This frees ${fmtBytes(bytes)} once you empty the Recycle Bin, and you can undo right after. Kaizen checks first that the Recycle Bin can take each item; anything it can't take (too big, or on a drive without one) stays where it is.`,
    ok: 'Move to Recycle Bin', danger: true });
  if (!ok) return;
  const r = await api('/api/action', { op: 'recycle', kind: 'file', ids: items.map(f => f.id) });
  const failed = new Set((r.failed || []).map(x => x[0]));
  removeCards(items.filter(f => !failed.has(f.path)).map(f => f.id));
  closeSheet();
  state.overview = null;
  toast(`${r.done} item${r.done === 1 ? '' : 's'} moved to the Recycle Bin · ${fmtBytes(r.freed)}`, { undo: r.batch });
  if (failed.size) toast(`${failed.size} not moved: ${esc((r.failed[0] || [])[1] || 'in use or protected')}${failed.size > 1 ? ' (and others)' : ''}`, { ms: 9000 });
}
async function fileAction(op, ids, extra = {}) {
  const r = await api('/api/action', { op, kind: 'file', ids, ...extra });
  const s = state.params.s || 'all';
  if (s !== 'everything') removeCards(ids); else { clearSel(); loadFiles(true); }
  closeSheet();
  state.overview = null;
  const verb = { keep: 'Marked as fine, Kaizen won’t flag', move: 'Moved', rename: 'Renamed' }[op];
  toast(`${verb} ${r.done} item${r.done === 1 ? '' : 's'}`, { undo: r.batch });
  if (r.failed?.length) toast(`${r.failed.length} could not be changed: ${esc(r.failed[0][1])}`);
}
async function openFileSheet(f) {
  const media = ['image', 'video'].includes(f.category) && !f.cloud;
  const s = openSheet(`
    <div class="preview">${f.category === 'folder' ? `<div style="width:80px;color:var(--muted)">${icon('folder')}</div>`
      : `<img src="${thumbUrl(f.path, media ? 512 : 256)}" alt="" ${media ? '' : 'style="width:128px;height:128px"'} onerror="this.remove()">`}
      <button class="icon-btn" data-close>${icon('x')}</button></div>
    <div class="content">
      <h2>${esc(f.name)}</h2><div class="path">${esc(f.path)}</div>
      <div class="facts-grid">
        <div><span>Size</span><b>${f.category === 'folder' ? '—' : fmtBytes(f.size)}</b></div>
        <div><span>Type</span><b style="text-transform:capitalize">${esc(f.category)}${f.ext ? ' · ' + esc(f.ext) : ''}</b></div>
        <div><span>Last used</span><b>${ago(f.last_used)}</b></div>
        <div><span>Modified</span><b>${fmtDate(f.mtime)}</b></div>
        <div><span>Created / arrived</span><b>${fmtDate(f.ctime)}</b></div>
        <div><span>Library</span><b>${esc(f.root_name)}</b></div>
      </div>
      ${f.managed ? `<div class="note">${esc(f.managed)}. Kaizen leaves these alone because a program relies on them.</div>`
        : `<div class="ai-box" id="sheetAi">${icon('spark')}<span>${f.ai ? esc(f.ai) : '<span class="ai-line loading" style="display:block;width:220px"><span></span></span>'}</span></div>`}
      <div class="why">${f.reasons.length ? f.reasons.map(r => `<div style="--c:var(--${r.s})"><span class="sd"></span><span><b>${S[r.s].romaji}</b> · ${esc(r.t)}</span></div>`).join('')
        : `<div style="--c:var(--sustain)"><span class="sd"></span><span><b>Shitsuke</b> · No issues. This file is in good shape.</span></div>`}</div>
      ${f.target ? `<label>Suggested place (Seiton)</label><div class="note">${esc(f.target)}</div>` : ''}
      ${f.new_name ? `<label>Suggested name (Seiketsu), you can edit it</label><input class="input" id="newName" value="${esc(f.new_name)}">` : ''}
      <div class="actions">
        ${f.category !== 'folder' ? `<button class="btn sm" data-a="open">${icon('open')} Open</button>` : ''}
        <button class="btn sm" data-a="reveal">${icon('folder')} Show in folder</button>
        ${f.reasons.length ? `<button class="btn sm" data-a="keep">${icon('keep')} Keep</button>` : ''}
        ${f.target ? `<button class="btn sm" data-a="move">${icon('move')} Move</button>` : ''}
        ${f.new_name ? `<button class="btn sm" data-a="rename">${icon('pen')} Rename</button>` : ''}
        ${f.managed || f.remote ? '' : `<button class="btn sm danger" data-a="recycle">${icon('trash')} Recycle</button>`}
      </div>
      ${f.remote ? `<p class="note" style="margin-top:14px">${icon('globe')} This file is on a network or removable drive. There’s no Recycle Bin there, so Kaizen never deletes it. Open the folder if you want to remove it yourself.</p>` : ''}
    </div>`);
  $$('[data-a]', s).forEach(b => b.onclick = () => {
    const a = b.dataset.a;
    if (a === 'open' || a === 'reveal') api('/api/action', { op: a, kind: 'file', ids: [f.id] });
    else if (a === 'recycle') recycleFiles([f]);
    else if (a === 'rename') fileAction('rename', [f.id], { names: { [f.id]: $('#newName').value } });
    else fileAction(a, [f.id]);
  });
  if (!f.ai && !f.managed) {
    for (let i = 0; i < 20 && $('#sheetAi'); i++) {
      try {
        const r = await api('/api/describe', { kind: 'file', id: f.id });
        f.ai = r.text;
        if ($('#sheetAi')) $('#sheetAi span').textContent = r.text || 'No description available.';
        break;
      } catch (e) {
        if (e.status !== 503) { if ($('#sheetAi')) $('#sheetAi').remove(); break; }
        await sleep(2500);
      }
    }
  }
}

/* ---------------------------------------------------------------- programs */
const edition = () => state.status?.edition || { id: 'public', allow_uninstall: true };
const canUninstall = () => edition().allow_uninstall !== false;
const editionLine = () => edition().name
  ? `Kaizen 5S · ${esc(edition().name)} · © 2026 Alexander Gubric · ${esc(edition().grant)}`
  : 'Kaizen 5S · © 2026 Alexander Gubric · Free and open source (MIT License)';
const PROG_TABS =[['unused', 'Unused for ages', 'sort'], ['dupes', 'Doing the same job', 'std'], ['leftovers', 'Leftovers', 'shine'],
  ['active', 'Used recently', 'sustain'], ['protected', 'Protected', 'app'], ['all', 'All programs', '']];
async function viewPrograms(v, params) {
  const tab = params.tab || 'unused';
  setTitle('Programs', canUninstall() ? 'Based on Windows’ own record of the programs you start. Nothing is removed without you.'
    : 'Based on Windows’ own record of the programs you start. On this company PC only IT can remove programs.');
  const d = await api('/api/programs?' + new URLSearchParams({ tab, ...pick(params, ['q']) }));
  state.list = d;
  const desc = {
    unused: 'Seiri for software: installed, but you haven’t opened them in a long time.',
    dupes: 'Seiketsu: several programs doing the same job. Keep the one you actually use.',
    leftovers: 'Seiso: folders in Program Files that no installed program uses any more.',
    active: 'Shitsuke: the tools you rely on. Nothing to do here.',
    protected: 'Drivers, runtimes and security software. Other programs depend on them, so Kaizen never suggests removing them.',
    all: 'Everything installed on this PC.',
  }[tab];
  v.innerHTML = `
    <div class="toolbar">
      <div class="seg">${PROG_TABS.map(([k, label, c]) => `<button class="${k === tab ? 'on' : ''}" data-tab="${k}" style="--c:var(--${c || 'muted'})">
        ${S[c] ? `<span class="k">${S[c].kanji}</span>` : ''}${label}<span class="n">${d.counts[k]}</span></button>`).join('')}</div>
      <label class="search">${icon('search')}<input id="pq" placeholder="Search programs" value="${esc(params.q || '')}"></label>
    </div>
    <p class="summary">${desc}</p>
    ${canUninstall() ? '' : `<div class="policy">${icon('lock')}<span>${esc(edition().uninstall_note)}</span></div>`}
    <div class="plist" id="plist"></div>`;
  $$('[data-tab]', v).forEach(b => b.onclick = () => { location.hash = '#/programs?tab=' + b.dataset.tab; });
  let deb;
  $('#pq').oninput = e => { clearTimeout(deb); deb = setTimeout(() => { location.hash = '#/programs?' + new URLSearchParams({ tab, q: e.target.value }); }, 400); };
  const list = $('#plist');
  if (!d.items.length) {
    list.innerHTML = `<div class="empty"><svg class="enso" viewBox="0 0 120 120"><path d="M100 62a40 40 0 1 1-16.5-32.4"/></svg><h2>Nothing here</h2><p>Your programs are in order.</p></div>`;
    return;
  }
  let html = '', group = null;
  d.items.forEach((p, i) => {
    if (tab === 'dupes' && p.dup_group !== group) { group = p.dup_group; html += `<div class="group-h">${icon('app')} ${esc(group)}</div>`; }
    html += progRow(p, i);
  });
  list.innerHTML = html;
  hydrateIcons(list);
  watchDescribe(list);
  list.onclick = e => {
    const b = e.target.closest('[data-a]');
    if (!b) return;
    const p = d.items.find(x => x.id === +b.closest('.prog').dataset.id);
    progAction(b.dataset.a, p, b.closest('.prog'));
  };
}
function progRow(p, i) {
  const used = p.kind === 'leftover' ? `Unchanged since <b>${fmtDate(p.last_run)}</b>`
    : p.last_run ? `Last used <b>${ago(p.last_run)}</b>` : `<b>No record of use</b> · installed ${ago(p.installed)}`;
  const ev = p.evidence?.length ? ` · <span style="color:var(--muted)">${esc(p.evidence.join(', '))}</span>` : '';
  const runs = p.run_count ? ` · ${p.run_count} launches` : '';
  const ico = p.exe ? `<img src="${thumbUrl(p.exe, 96, 'icon')}" alt="" onerror="this.remove()">`
    : icon(p.kind === 'leftover' ? 'folder' : 'app');
  const acts = p.protected
    ? `<span class="tag" style="--c:var(--app)" title="${esc(p.protect_reason)}">Protected</span>${p.location ? `<button class="btn sm ghost" data-a="reveal" title="Show folder">${icon('folder')}</button>` : ''}`
    : p.kind === 'leftover'
      ? `<button class="btn sm" data-a="keep">${icon('keep')} Keep</button><button class="btn sm" data-a="reveal">${icon('folder')} Show folder</button>`
      : `${p.i_sort || p.i_std ? `<button class="btn sm" data-a="keep">${icon('keep')} Keep</button>` : ''}
         ${p.location ? `<button class="btn sm ghost" data-a="reveal" title="Show install folder">${icon('folder')}</button>` : ''}
         ${canUninstall()
           ? `<button class="btn sm ${p.i_sort || p.i_std ? 'danger' : ''}" data-a="uninstall">${icon('trash')} Uninstall…</button>`
           : `<span class="btn sm locked" title="${esc(edition().uninstall_note)}" aria-disabled="true">${icon('lock')} Uninstall</span>`}`;
  return `<div class="prog ${p.protected ? 'protected' : ''}" data-id="${p.id}" style="--i:${i % 20}">
    <div class="ico">${ico}</div>
    <div><div class="nm" title="${esc(p.name)}">${esc(p.name)}</div>
      <div class="pub">${esc([p.publisher, p.version].filter(Boolean).join(' · ') || (p.kind === 'leftover' ? esc(p.location) : ''))}</div></div>
    <div><div class="use">${used}${runs}${ev}</div>
      ${p.protected ? `<div class="ai-line"><span>${esc(p.protect_reason)}</span></div>` : aiLine(p, 'program')}
      <div class="reasons">${p.reasons.map(r => `<span class="tag" style="--c:var(--${r.s})">${esc(r.t)}</span>`).join('')}</div></div>
    <div class="acts"><span class="size">${p.size ? fmtBytes(p.size) : ''}</span>${acts}</div>
  </div>`;
}
async function progAction(a, p, row) {
  if (a === 'reveal') return api('/api/action', { op: 'reveal', kind: 'program', ids: [p.id] });
  if (a === 'keep') {
    const r = await api('/api/action', { op: 'keep', kind: 'program', ids: [p.id] });
    row.classList.add('gone');
    setTimeout(() => row.remove(), 400);
    state.overview = null;
    return toast(`Kaizen won’t suggest removing ${esc(p.name)} again`, { undo: r.batch });
  }
  if (a === 'uninstall') {
    if (!canUninstall()) return toast(esc(edition().uninstall_note));
    const ok = await confirmBox({
      title: `Uninstall ${esc(p.name)}?`,
      text: `Kaizen will open ${esc(p.name)}’s own uninstaller. Windows may ask for permission. Nothing is removed until you confirm in that window. Run a new 5S check afterwards to update this list.`,
      ok: 'Open uninstaller', danger: true });
    if (!ok) return;
    const r = await api('/api/action', { op: 'uninstall', kind: 'program', ids: [p.id] });
    toast(r.launched ? 'Uninstaller opened. Follow the steps in its window.' : (r.error || 'Opened Windows Settings → Apps so you can remove it there.'));
  }
}

/* ---------------------------------------------------------------- chat */
const chatLog = $('#chatLog');
function renderChatEmpty() {
  if (state.status?.ai?.state === 'missing') {
    chatLog.innerHTML = `<div class="chat-empty"><svg viewBox="0 0 64 64"><path d="M54 33a22 22 0 1 1-9-17.8"/></svg>
      <p><b>No local AI is installed</b>, so chat is switched off. Everything else in Kaizen still works: scans, 5S scores,
      the map and all clean-up actions.</p>
      <p style="font-size:12.5px">To add AI, install <b>LM Studio</b> (any PC) or <b>FastFlowLM</b> (AMD Ryzen AI) with a
      Qwen3 4B model, then restart Kaizen.</p></div>`;
    $('#chatText').disabled = true;
    $('#chatText').placeholder = 'Chat needs a local AI';
    return;
  }
  $('#chatText').disabled = false;
  $('#chatText').placeholder = 'Ask about your files or programs…';
  chatLog.innerHTML = `<div class="chat-empty"><svg viewBox="0 0 64 64"><path d="M54 33a22 22 0 1 1-9-17.8"/></svg>
    <p>I run entirely on this PC${state.status?.ai?.kind === 'flm' ? ', on your Ryzen AI NPU' : ''}. Nothing you ask leaves it.</p>
    <div class="suggest">${SUGGEST.map(s => `<button>${esc(s)}</button>`).join('')}</div></div>`;
  $$('.suggest button', chatLog).forEach(b => b.onclick = () => send(b.textContent));
}
function openChat(prefill) {
  if (!state.chat.length) renderChatEmpty();
  if (state.status?.ai?.state === 'missing') prefill = null;
  $('#chat').classList.add('on');
  $('#chat').setAttribute('aria-hidden', 'false');
  $('#askFab').classList.add('hide');
  if (prefill) send(prefill); else setTimeout(() => $('#chatText').focus(), 300);
}
function closeChat() {
  $('#chat').classList.remove('on');
  $('#chat').setAttribute('aria-hidden', 'true');
  $('#askFab').classList.remove('hide');
}
function md(text, refs) {
  // safety net: a line that cites an item which isn't in this answer's data was made up - drop it
  text = text.split('\n').filter(l => [...l.matchAll(/\[([FP]\d+)\]/g)].every(m => refs[m[1]])).join('\n');
  let h = esc(text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>');
  h = h.replace(/\[([FP]\d+)\]/g, (m, ref) => refs[ref] ? `<span class="ref" data-ref="${ref}">${esc(refs[ref].name.length > 34 ? refs[ref].name.slice(0, 32) + '…' : refs[ref].name)}</span>` : '');
  let out = '', inList = false;
  for (const line of h.split('\n')) {
    const m = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)/);
    if (m) { if (!inList) { out += '<ul>'; inList = true; } out += `<li>${m[1]}</li>`; }
    else { if (inList) { out += '</ul>'; inList = false; } if (line.trim()) out += `<p>${line}</p>`; }
  }
  return out + (inList ? '</ul>' : '');
}
function miniCard(it) {
  const media = it.kind === 'file' && ['image', 'video'].includes(it.category) && !it.cloud;
  const src = it.kind === 'file' ? thumbUrl(it.path, media ? 200 : 96) : it.exe ? thumbUrl(it.exe, 64, 'icon') : '';
  return `<div class="mini" data-ref="${it.ref}"><div class="t">${src ? `<img class="${media ? '' : 'icon'}" src="${src}" alt="" onerror="this.remove()">` : icon(it.kind === 'file' ? 'files' : 'app')}</div>
    <div class="n" title="${esc(it.name)}">${esc(it.name)}</div></div>`;
}
async function openRef(it) {
  if (!it) return;
  if (it.kind === 'file') {
    const d = await api('/api/files?' + new URLSearchParams({ ids: String(it.id), s: 'everything' }));
    if (d.items[0]) openFileSheet(d.items[0]);
  } else {
    closeChat();
    location.hash = '#/programs?' + new URLSearchParams({ tab: 'all', q: it.name });
  }
}
async function send(text) {
  text = text.trim();
  if (!text || state.chatBusy) return;
  if (!state.chat.length) chatLog.innerHTML = '';
  state.chat.push({ role: 'user', content: text });
  chatLog.insertAdjacentHTML('beforeend', `<div class="msg user">${esc(text)}</div>`);
  const bot = document.createElement('div');
  bot.className = 'msg bot';
  bot.innerHTML = '<div class="txt"><span class="caret"></span></div>';
  chatLog.appendChild(bot);
  chatLog.scrollTop = chatLog.scrollHeight;
  state.chatBusy = true;
  let acc = '', items = [], refs = {};
  const txt = $('.txt', bot);
  try {
    const r = await fetch('/api/chat', { method: 'POST', headers: { 'X-Kaizen': TOKEN, 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: state.chat }) });
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.error || 'The local AI is not ready yet.'); }
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf = '', meta = null;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const line = buf.slice(0, i).trim();
        buf = buf.slice(i + 2);
        if (!line.startsWith('data:')) continue;
        const ev = JSON.parse(line.slice(5));
        if (ev.items) { items = ev.items; refs = Object.fromEntries(items.map(x => [x.ref, x])); }
        if (ev.t) { acc += ev.t; txt.innerHTML = md(acc, refs) + '<span class="caret"></span>'; chatLog.scrollTop = chatLog.scrollHeight; }
        if (ev.error) throw new Error(ev.error);
        if (ev.done) meta = ev;
      }
    }
    txt.innerHTML = md(acc, refs) || '<p>(no answer)</p>';
    const mentioned = [...new Set([...acc.matchAll(/\[([FP]\d+)\]/g)].map(m => m[1]))].filter(r => refs[r]);
    const show = (mentioned.length ? mentioned.map(r => refs[r]) : items).slice(0, 8);
    const fileIds = show.filter(x => x.kind === 'file').map(x => x.id);
    if (show.length) bot.insertAdjacentHTML('beforeend', `<div class="mini-cards">${show.map(miniCard).join('')}</div>
      ${fileIds.length > 1 ? `<button class="btn sm" data-go="#/files?s=everything&ids=${fileIds.join(',')}">${icon('files')} Open these ${fileIds.length} files</button>` : ''}`);
    bot.insertAdjacentHTML('beforeend', `<div class="meta">${icon('chip')} ${esc(meta?.engine || 'Local AI')}${meta?.tps ? ` · ${meta.tps} tok/s` : ''}${meta?.ttft ? ` · first word in ${meta.ttft}s` : ''}</div>`);
    state.chat.push({ role: 'assistant', content: acc });
  } catch (e) {
    txt.innerHTML = `<p style="color:var(--sort)">${esc(e.message)}</p>`;
    state.chat.pop();
  } finally {
    state.chatBusy = false;
    hydrateIcons(bot);
    $$('[data-ref]', bot).forEach(el => el.onclick = () => openRef(refs[el.dataset.ref]));
    chatLog.scrollTop = chatLog.scrollHeight;
  }
}
$('#chatForm').onsubmit = e => { e.preventDefault(); const t = $('#chatText'); send(t.value); t.value = ''; t.style.height = ''; };
$('#chatText').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#chatForm').requestSubmit(); } });
$('#chatText').addEventListener('input', e => { e.target.style.height = ''; e.target.style.height = e.target.scrollHeight + 'px'; });
$('#askFab').onclick = () => openChat();
$('#chatClose').onclick = closeChat;

/* ---------------------------------------------------------------- status, scan, settings, theme */
function renderStatus(s) {
  const btn = $('#scanBtn'), sc = s.scan;
  btn.classList.toggle('busy', !!sc.running);
  btn.disabled = !!(sc.running && sc.cancel);
  $('span', btn).textContent = sc.running
    ? (sc.cancel ? 'Stopping…' : `${sc.phase || 'Scanning'} · ${sc.files.toLocaleString()} files · Stop`) : 'Run 5S check';
  btn.title = sc.running ? `Click to stop. Now reading: ${sc.current || '…'}` : 'Look through your folders and programs';
  $('#scanline').classList.toggle('on', !!sc.running);
  const pill = $('#aiPill'), ai = s.ai;
  pill.className = 'ai-pill ' + ai.state;
  const eng = ai.engine || 'AI';
  $('.txt', pill).textContent = ai.state === 'online' ? `${eng} · ${ai.model}${ai.tps ? ` · ${ai.tps} tok/s` : ''}`
    : ai.state === 'starting' ? (ai.kind === 'flm' ? 'Waking the NPU…' : `Starting ${eng}…`)
    : ai.state === 'missing' ? 'No local AI installed' : `${eng} offline · start`;
  pill.title = ai.detail || (ai.kind === 'flm' ? 'Local AI on the Ryzen AI NPU (FastFlowLM)' : 'Local AI through LM Studio');
  $('#chatMeta').textContent = ai.state === 'online'
    ? `${ai.model} ${ai.kind === 'flm' ? 'on your Ryzen AI NPU' : 'in LM Studio'} · private, nothing leaves this PC`
    : ai.state === 'starting' ? (ai.detail || 'Starting the local AI…')
    : ai.state === 'missing' ? 'No local AI installed' : (ai.detail || 'The local AI is not running');
}
async function poll() {
  try {
    const s = await api('/api/status');
    const was = state.status?.scan?.running;
    state.status = s;
    renderStatus(s);
    if (was && !s.scan.running) {
      state.overview = null;
      if (s.scan.error) toast('The 5S check hit a problem: ' + esc(s.scan.error));
      else if (s.scan.stopped) toast('5S check stopped. Your previous results are kept.');
      else toast('5S check complete');
      if (s.scan.skipped?.length) toast(`Couldn’t reach ${s.scan.skipped.map(esc).join(', ')}, so it was skipped. Check it in Settings → Manage folders.`, { ms: 10000 });
      route();
    }
    if (!was && s.scan.running && state.view === 'overview' && !$('.hero')) route();
  } catch { /* server restarting */ }
  setTimeout(poll, state.status?.scan?.running || state.status?.ai?.state === 'starting' ? 900 : 4000);
}
async function startScan() {
  if (state.status?.scan?.running) {
    await api('/api/scan/stop', {});
    state.status.scan.cancel = true;
    renderStatus(state.status);
    return;
  }
  await api('/api/scan', {});
  const s = await api('/api/status');
  state.status = s;
  renderStatus(s);
  setTimeout(poll, 600);
  if (state.view === 'overview' && !$('.hero')) route();
}
window.startScan = startScan;
$('#scanBtn').onclick = startScan;
$('#aiPill').onclick = () => {
  const st = state.status?.ai?.state;
  if (st === 'offline') api('/api/ai/start', {}).then(() => toast('Starting the local AI…'));
  else openChat();
};
setInterval(() => api('/api/ping', {}).catch(() => {}), 5000);
api('/api/ping', {}).catch(() => {});

function applyTheme(t) {
  if (t === 'auto') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.dataset.theme = t;
  $('#themeBtn').innerHTML = icon(t === 'dark' ? 'moon' : t === 'light' ? 'sun' : 'auto');
  $('#themeBtn').title = `Theme: ${t}`;
  try { localStorage.setItem('kaizen-theme', t); } catch { /* storage unavailable */ }
}
$('#themeBtn').onclick = () => {
  const cur = state.status?.settings?.theme || 'auto';
  const next = { auto: 'dark', dark: 'light', light: 'auto' }[cur];
  applyTheme(next);
  if (state.status) state.status.settings.theme = next;
  api('/api/settings', { theme: next });
};

async function openSettings() {
  const st = await api('/api/status');
  const s = st.settings;
  const models = (await api('/api/models').catch(() => ({ models: [] }))).models;
  const flm = st.ai.kind !== 'lmstudio';
  const roots = ['Desktop', 'Documents', 'Downloads', 'Pictures', 'Videos', 'Music'];
  const months = d => Math.round(d / 30.4);
  // model ids come from local AI servers: escaped like everything else (a rogue service must not inject markup)
  const opt = (vals, cur, fmt) => vals.map(v => `<option value="${esc(v)}" ${String(v) === String(cur) ? 'selected' : ''}>${esc(fmt(v))}</option>`).join('');
  const m = openModal(`
    <h2>Settings</h2>
    <div class="form-h">5S rules</div>
    <div class="form-row"><div><b>Files count as unused after</b><small>Seiri: older than this and not opened → suggested for review</small></div>
      <select id="st_stale">${opt([90, 182, 365, 548, 730, 1095], s.stale_days, d => months(d) + ' months')}</select></div>
    <div class="form-row"><div><b>Programs count as unused after</b><small>Based on Windows’ record of programs you start</small></div>
      <select id="st_pstale">${opt([90, 182, 365, 730], s.program_stale_days, d => months(d) + ' months')}</select></div>
    <div class="form-row"><div><b>Downloads grace period</b><small>Seiton: how long a file may sit in Downloads</small></div>
      <select id="st_dl">${opt([7, 14, 30, 60], s.downloads_days, d => d + ' days')}</select></div>
    <div class="form-row"><div><b>Protect photo, video and music libraries</b><small>Memories are not clutter: never flag them for age alone</small></div>
      <label class="switch"><input type="checkbox" id="st_media" ${s.protect_media ? 'checked' : ''}><span></span></label></div>
    <div class="form-h">Folders to check</div>
    <div class="form-row"><div><b>${roots.length - s.skip_roots.length} Windows libraries${s.extra_roots.length ? ` + ${s.extra_roots.length} extra folder${s.extra_roots.length > 1 ? 's' : ''}` : ''}</b>
      <small>Choose exactly which folders the 5S check looks through, including network drives</small></div>
      <button class="btn sm" id="st_folders">${icon('folder')} Manage folders…</button></div>
    <div class="form-h">Local AI</div>
    <div class="form-row"><div><b>AI engine</b><small>FastFlowLM runs on the AMD Ryzen AI NPU. LM Studio works on any PC.</small></div>
      <select id="st_engine">${opt(['auto', 'flm', 'lmstudio'], s.engine, v => ({ auto: 'Automatic', flm: 'FastFlowLM (NPU)', lmstudio: 'LM Studio' })[v])}</select></div>
    <div class="form-row"><div><b>Chat model</b><small>Models downloaded in ${flm ? 'FastFlowLM' : 'LM Studio'}</small></div>
      <select id="st_model">${opt(models.length ? models : [flm ? s.model : (s.lms_model || st.ai.model || '')], flm ? s.model : (s.lms_model || st.ai.model), v => v || 'Automatic')}</select></div>
    ${flm ? `<div class="form-row"><div><b>Photo descriptions</b><small>A vision model lets Kaizen describe what a picture shows</small></div>
      <select id="st_vision"><option value="">Off</option>${opt(models.filter(x => /vl|gemma3:4b/.test(x)), s.vision_model, v => v)}</select></div>
    <div class="form-row"><div><b>NPU power mode</b><small>Turbo is fastest, Power saver is easiest on battery</small></div>
      <select id="st_pmode">${opt(['powersaver', 'balanced', 'performance', 'turbo'], s.pmode, v => v[0].toUpperCase() + v.slice(1))}</select></div>` : ''}
    <div class="form-row"><div><b>Describe items automatically</b><small>Kaizen explains each visible file and program in one line</small></div>
      <label class="switch"><input type="checkbox" id="st_auto" ${s.auto_describe ? 'checked' : ''}><span></span></label></div>
    <p class="note" style="margin-top:18px">Kaizen 5S ${esc(st.version)}${st.edition?.name ? ` · ${esc(st.edition.name)} · ${esc(st.edition.grant)}` : ''}
      · © 2026 Alexander Gubric · Free and open source software under the MIT License.</p>
    <div class="foot"><button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="st_save">Save</button></div>`, 'wide');
  $('#st_folders').onclick = () => openFolders();
  $('#st_save').onclick = async () => {
    const payload = {
      stale_days: +$('#st_stale').value, program_stale_days: +$('#st_pstale').value, downloads_days: +$('#st_dl').value,
      protect_media: $('#st_media').checked, auto_describe: $('#st_auto').checked, engine: $('#st_engine').value,
      ...(flm ? { model: $('#st_model').value, vision_model: $('#st_vision').value, pmode: $('#st_pmode').value }
        : { lms_model: $('#st_model').value }),
    };
    const rescan = ['stale_days', 'program_stale_days', 'downloads_days', 'protect_media'].some(k => payload[k] !== s[k]);
    await api('/api/settings', payload);
    closeModal();
    state.status.settings = { ...s, ...payload };
    if (rescan) toast('Saved. Run a new 5S check to apply the new rules.');
    else toast('Settings saved');
  };
}
$('#settingsBtn').onclick = openSettings;

/* ---------------------------------------------------------------- folder manager */
const KIND = {
  local: { icon: 'pc', label: 'This PC' }, network: { icon: 'globe', label: 'Network' },
  cloud: { icon: 'cloud', label: 'Cloud drive' }, removable: { icon: 'usb', label: 'Removable' },
  optical: { icon: 'usb', label: 'Disc' }, ramdisk: { icon: 'pc', label: 'RAM disk' },
};
const kindChip = k => `<span class="kind k-${k || 'local'}">${icon((KIND[k] || KIND.local).icon)}${(KIND[k] || KIND.local).label}</span>`;
function accessBadges(c) {
  if (!c) return `<span class="acc wait">checking…</span>`;
  if (c.error) return `<span class="acc no" title="${esc(c.error)}">✕ ${esc(c.error.length > 46 ? c.error.slice(0, 44) + '…' : c.error)}</span>`;
  const noBin = ['network', 'removable', 'optical'].includes(c.kind);
  return `<span class="acc ${c.read ? 'ok' : 'no'}">${c.read ? '✓' : '✕'} Can see files</span>
    <span class="acc ${c.write ? 'ok' : 'no'}">${c.write ? '✓' : '✕'} Can move & rename</span>
    ${noBin ? '<span class="acc info">Never deletes here</span>' : `<span class="acc ${c.delete ? 'ok' : 'no'}">${c.delete ? '✓' : '✕'} Can recycle</span>`}`;
}
async function openFolders() {
  const data = await api('/api/folders');
  let libs = data.libraries.map(l => ({ ...l })), extra = data.extra.map(e => ({ ...e, check: null }));
  let pending = null;  // result of "Check access" for the folder being added
  const m = openModal(`
    <h2>Folders to check</h2>
    <p>A 5S check looks through these folders. Kaizen only reads them, and nothing changes until you click a button.</p>
    <div class="form-h">Windows libraries</div><div id="fl_libs"></div>
    <div class="form-h">Extra folders and drives</div><div id="fl_extra"></div>
    <div class="form-h">Add a folder</div>
    <div class="row-add"><input class="input" id="fl_path" placeholder="D:\\Projects  or  \\\\server\\share\\folder">
      <button class="btn sm" id="fl_browse">${icon('folder')} Browse…</button>
      <button class="btn sm" id="fl_check">Check access</button></div>
    <p class="hint">Network folders work too: pick them under Network in Browse, use a mapped drive (Z:\\), or type the path.</p>
    <div id="fl_result"></div>
    <div class="foot"><button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="fl_save">Save</button></div>`, 'wide');

  const drawLibs = () => {
    $('#fl_libs').innerHTML = libs.map((l, i) => `<div class="frow ${l.exists ? '' : 'off'}">
      <div class="fico">${icon('folder')}</div><div><b>${esc(l.name)}</b><small>${esc(l.path || 'not found')}</small></div>
      <div>${kindChip(l.kind)}</div>
      <label class="switch"><input type="checkbox" data-lib="${i}" ${l.enabled ? 'checked' : ''} ${l.exists ? '' : 'disabled'}><span></span></label></div>`).join('');
    hydrateIcons($('#fl_libs'));
    $$('[data-lib]', m).forEach(c => c.onchange = () => { libs[+c.dataset.lib].enabled = c.checked; });
  };
  const drawExtra = () => {
    $('#fl_extra').innerHTML = extra.length ? extra.map((e, i) => `<div class="frow">
      <div class="fico">${icon((KIND[e.kind] || KIND.local).icon)}</div>
      <div><b title="${esc(e.path)}">${esc(e.path)}</b><div class="accs">${accessBadges(e.check)}</div></div>
      <div>${kindChip(e.kind)}</div>
      <div style="display:flex;gap:4px"><button class="icon-btn" data-recheck="${i}" title="Check again">${icon('scan')}</button>
      <button class="icon-btn" data-rm="${i}" title="Remove from the list">${icon('x')}</button></div></div>`).join('')
      : `<p class="note">No extra folders yet. Add a project folder, a second drive or a network share below.</p>`;
    hydrateIcons($('#fl_extra'));
    $$('[data-rm]', m).forEach(b => b.onclick = () => { extra.splice(+b.dataset.rm, 1); drawExtra(); });
    $$('[data-recheck]', m).forEach(b => b.onclick = () => recheck(+b.dataset.recheck));
  };
  const recheck = async i => {
    extra[i].check = null;
    drawExtra();
    const c = await api('/api/folders/check', { path: extra[i].path }).catch(e => ({ error: e.message }));
    if (extra[i]) { extra[i].check = c; extra[i].kind = c.kind || extra[i].kind; drawExtra(); }
  };
  const showResult = c => {
    pending = c;
    const box = $('#fl_result');
    if (!c) { box.innerHTML = ''; return; }
    const risky = ['network', 'cloud', 'removable', 'optical'].includes(c.kind);
    const usable = !c.error && c.read;
    box.innerHTML = `<div class="fcheck ${usable ? '' : 'bad'}">
      <div class="fc-head">${kindChip(c.kind)}<b>${esc(c.path)}</b>${c.label || c.fs ? `<small>${esc([c.label, c.fs].filter(Boolean).join(' · '))}</small>` : ''}</div>
      ${c.error ? `<p class="err">✕ ${esc(c.error)}</p>` : `<div class="accs">${accessBadges(c)}</div>
        <p class="meta">${c.dirs} folders and ${c.files} files at the top level${c.files + c.dirs >= 2000 ? ' (or more)' : ''} · answered in ${c.ms} ms</p>`}
      ${c.warnings?.length ? `<ul class="warns">${c.warnings.map(w => `<li>${esc(w)}</li>`).join('')}</ul>` : ''}
      ${usable && risky ? `<label class="consent"><input type="checkbox" id="fl_ok"> I’m allowed to access this folder and I understand the notes above.</label>` : ''}
      ${usable ? `<button class="btn primary sm" id="fl_add" ${risky ? 'disabled' : ''}>${icon('plus')} Add this folder</button>` : ''}
    </div>`;
    hydrateIcons(box);
    const ok = $('#fl_ok');
    if (ok) ok.onchange = () => { $('#fl_add').disabled = !ok.checked; };
    const add = $('#fl_add');
    if (add) add.onclick = () => {
      const key = c.path.toLowerCase().replace(/\\+$/, '');
      const clash = extra.find(e => { const k = e.path.toLowerCase().replace(/\\+$/, ''); return key === k || key.startsWith(k + '\\'); })
        || libs.find(l => l.enabled && l.path && key.startsWith(l.path.toLowerCase().replace(/\\+$/, '') + '\\'));
      if (clash) { toast(`Already covered by ${esc(clash.path || clash.name)}`); return; }
      extra.push({ path: c.path, kind: c.kind, check: c });
      $('#fl_path').value = '';
      showResult(null);
      drawExtra();
    };
  };
  const runCheck = async () => {
    const path = $('#fl_path').value.trim();
    $('#fl_result').innerHTML = `<div class="fcheck"><p class="meta">Checking ${esc(path)}…</p></div>`;
    showResult(await api('/api/folders/check', { path }).catch(e => ({ path, error: e.message, warnings: [] })));
  };
  $('#fl_check').onclick = runCheck;
  $('#fl_path').onkeydown = e => { if (e.key === 'Enter') runCheck(); };
  $('#fl_browse').onclick = async () => {
    const r = await api('/api/folders/pick', {});
    if (r.path) { $('#fl_path').value = r.path; runCheck(); }
  };
  $('#fl_save').onclick = async () => {
    const payload = { skip_roots: libs.filter(l => !l.enabled).map(l => l.name), extra_roots: extra.map(e => e.path) };
    await api('/api/settings', payload);
    if (state.status) Object.assign(state.status.settings, payload);
    closeModal();
    toast('Folders saved. Run a 5S check to scan them.');
  };
  drawLibs();
  drawExtra();
  extra.forEach((_, i) => recheck(i));
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeModal(); closeSheet(); closeChat(); clearSel(); }
  if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); openChat(); }
});

/* ---------------------------------------------------------------- boot */
(async function boot() {
  hydrateIcons();
  try { applyTheme(localStorage.getItem('kaizen-theme') || 'auto'); } catch { applyTheme('auto'); }
  renderChatEmpty();
  try {
    state.status = await api('/api/status');
    renderStatus(state.status);
    applyTheme(state.status.settings.theme || 'auto');
  } catch { /* first paint without status */ }
  await route();
  setTimeout(poll, 1500);
})();
