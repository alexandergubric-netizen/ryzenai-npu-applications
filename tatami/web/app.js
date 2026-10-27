// Tatami main window: wiring of drive picker, scan, folder tree, file list, types, treemap and actions.
import { get, post, bytes, num, pct, date, ago, esc, F, VERSION } from './api.js';
import { CATS, FOLDER_CAT, setExts, extName, extCat, extCss, logoSVG, AGE_STOPS, GROWTH, ageRgb } from './colors.js';
import { showMenu, hideMenu, dialog, toast, splitter, store } from './ui.js';
import { Grid } from './grid.js';
import { TreemapView } from './treemap.js';

const $ = id => document.getElementById(id);
const UNACC = -2;   // pseudo row: space used on the drive that the scan couldn't see

const S = {
  summary: null, sys: {}, drives: [],
  kids: new Map(),          // folder id -> child items (current sort)
  open: new Set([0]),       // expanded folders
  nodes: new Map(),         // id -> item (everything we have seen)
  root: 0,                  // treemap / types scope
  history: [],
  selected: 0,
  bySize: true,
  sort: 'size', dir: 'desc',
  tab: 'tree',
  typeFilter: null,         // {ext} | {cat}
  color: store.get('tmColor', 'type'),   // treemap colours: type | age | growth
  files: { q: '', ext: -1, cat: -1, min: 0, older: 0, sort: 'size', dir: 'desc', limit: 1000, dirs: false, dupes: false, dupMin: store.get('dupMin', 1 << 20) },
  dupes: null,              // last /api/dupes answer
};

// ======================================================================= boot
document.querySelectorAll('[data-logo]').forEach(e => e.innerHTML = logoSVG());
splash();
applyTheme(store.get('theme', 'system'));

const treeGrid = new Grid($('tree'), [
  { key: 'name', label: 'Name', flex: true, min: 220, sort: 'name', html: nameCell },
  { key: 'pct', label: '% of parent', w: 150, html: pctCell },
  { key: 'size', label: 'Size', w: 92, num: true, sort: 'size', html: r => r.id === UNACC ? bytes(r.s) : bytes(r.s) },
  { key: 'alloc', label: 'On disk', w: 92, num: true, sort: 'alloc', html: r => bytes(r.a) },
  { key: 'files', label: 'Files', w: 84, num: true, sort: 'files', html: r => r.f & F.DIR ? num(r.fi) : '' },
  { key: 'dirs', label: 'Folders', w: 74, num: true, sort: 'dirs', html: r => r.f & F.DIR ? num(r.di) : '' },
  { key: 'mod', label: 'Modified', w: 140, sort: 'modified', html: r => date(r.m) },
], {
  name: 'tree', sortKey: 'size', sortDir: 'desc',
  onSort: (k, d) => { S.sort = k; S.dir = d; S.kids.clear(); refreshTree(); },
  onToggle: row => toggle(row),
  onActivate: row => activate(row),
  onSelect: (rows, row) => selectNode(row, 'tree'),
  onContext: (row, x, y) => nodeMenu(row, x, y),
  onKey: treeKey,
});
treeGrid.empty = 'Nothing scanned yet.';

const fileGrid = new Grid($('files'), [
  { key: 'name', label: 'Name', flex: true, min: 200, sort: 'name', html: nameCellFlat },
  { key: 'path', label: 'Folder', w: 340, sort: 'path', cls: 'path-cell', html: pathCell },
  { key: 'size', label: 'Size', w: 92, num: true, sort: 'size', html: r => r.grp ? '' : bytes(r.s) },
  { key: 'alloc', label: 'On disk', w: 92, num: true, sort: 'alloc', html: r => r.grp ? '' : bytes(r.a) },
  { key: 'mod', label: 'Modified', w: 140, sort: 'modified', html: r => r.grp ? '' : date(r.m) },
  { key: 'type', label: 'Type', w: 110, sort: 'type', html: r => r.grp ? '' : r.f & F.DIR ? 'Folder' : esc(typeLabel(r.e)) },
], {
  name: 'files', sortKey: 'size', sortDir: 'desc',
  onSort: (k, d) => { S.files.sort = k === 'path' ? 'name' : k; S.files.dir = d; loadFiles(); },
  onActivate: row => { if (row.id >= 0) openItem(row); },
  onSelect: (rows, row) => selectNode(row, 'files'),
  onContext: (row, x, y) => nodeMenu(row, x, y),
  onKey: (e, row) => commonKeys(e, row, fileGrid),
});
fileGrid.empty = 'No files match.';

const tm = new TreemapView({
  stage: $('tmStage'), canvas: $('tm'), over: $('tmOver'),
  onHover: tmHover,
  onSelect: (id, chain) => revealInTree(id, chain),
  onZoom: id => navigate(id),
  onContext: (id, x, y) => { const n = S.nodes.get(id); if (n) nodeMenu(n, x, y); else get('node', { id }).then(r => { remember(r.node); nodeMenu(r.node, x, y); }); },
});
tm.color = S.color;
tm.onMode = () => { renderLegend(); syncColorButtons(); };

layoutSplitters();
wireCommands();
start();

async function start() {
  try { S.sys = await get('system'); } catch { }
  applyAccent();
  // a folder handed over by Tatami's own launch (Explorer menu, command line); never from the page's URL,
  // so a web page can't make Tatami scan something (e.g. a network share that asks for your Windows login)
  const p = (await get('startup').catch(() => ({}))).scan;
  if (p) { scan(p); return; }
  const st = await get('status').catch(() => ({ state: 'idle' }));
  if (st.state === 'done') { await loaded(); return; }
  if (st.state === 'scanning' || st.state === 'finishing' || st.state === 'elevating') { showScanning(st.path); poll(); return; }
  showHome();
}

function splash() {
  const sp = $('splash');
  $('splashRoom').outerHTML = logoSVG(true).replace('<svg ', '<svg class="splash-room" id="splashRoom" ');
  const done = () => { sp.classList.add('out'); setTimeout(() => sp.remove(), 400); };
  sp.onclick = done;
  setTimeout(done, matchMedia('(prefers-reduced-motion: reduce)').matches ? 50 : 1150);
}

// ======================================================================= theme
function applyTheme(t) {
  if (t === 'system') delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  store.set('theme', t);
  applyAccent();
  setTimeout(() => tm.paint && tm.paint(), 0);
}
function isDark() {
  const t = document.documentElement.dataset.theme;
  return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
}
function applyAccent() {
  const a = S.sys && S.sys.accent;
  const st = document.documentElement.style;
  if (!a) { st.removeProperty('--accent'); return; }
  // Windows uses a lighter tint of the accent in dark mode and a darker one in light mode
  st.setProperty('--accent', isDark() ? `color-mix(in srgb, ${a} 55%, white)` : `color-mix(in srgb, ${a} 82%, black)`);
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyAccent);

// ======================================================================= layout
function layoutSplitters() {
  const split = $('split'), top = $('top');
  const topH = store.get('topH', null), sideW = store.get('sideW', 330);
  if (topH) split.style.setProperty('--top-h', topH + 'px');
  top.style.setProperty('--side-w', sideW + 'px');
  splitter($('hsplit'), {
    axis: 'y', get: () => $('top').getBoundingClientRect().height,
    set: v => split.style.setProperty('--top-h', v + 'px'),
    min: () => 140, max: () => split.getBoundingClientRect().height - 120,
    done: () => store.set('topH', Math.round($('top').getBoundingClientRect().height)),
  });
  splitter($('vsplit'), {
    axis: 'x-rev', get: () => $('side').getBoundingClientRect().width,
    set: v => top.style.setProperty('--side-w', v + 'px'),
    min: () => 220, max: () => Math.max(240, top.getBoundingClientRect().width - 420),
    done: () => store.set('sideW', Math.round($('side').getBoundingClientRect().width)),
  });
}

// ======================================================================= home / drives
async function showHome() {
  $('home').hidden = false;
  $('scanning').hidden = true;
  syncAdmin();
  let drives = [];
  try { drives = await get('drives'); } catch (e) { toast(e.message, 'err'); }
  S.drives = drives;
  const sysDrive = (S.sys.user || 'C:').slice(0, 2).toUpperCase();
  $('driveCards').innerHTML = drives.map(d => {
    const used = d.total - d.free, f = d.total ? used / d.total : 0;
    const name = d.label || (d.type === 'removable' ? 'USB drive' : d.type === 'network' ? 'Network drive' : 'Local Disk');
    return `<button class="dcard" data-root="${esc(d.root)}">
      <span class="dico">${driveIcon(d, d.root.slice(0, 2).toUpperCase() === sysDrive)}</span>
      <span class="dt">${esc(name)} <small>(${esc(d.root.slice(0, 2))})</small></span>
      <span class="bar"><i class="${f > .9 ? 'full' : ''}" style="width:${(f * 100).toFixed(1)}%"></i></span>
      <span class="ds">${bytes(d.free)} free of ${bytes(d.total)} · ${esc(d.fs)}</span>
    </button>`;
  }).join('') || '<p class="muted">No drives found.</p>';
  $('driveCards').querySelectorAll('.dcard').forEach(c => c.onclick = () => scan(c.dataset.root));
}

function driveIcon(d, system) {
  const usb = d.type === 'removable', net = d.type === 'network';
  return `<svg viewBox="0 0 48 48" width="48" height="48">
    <rect x="4" y="${usb ? 14 : 12}" width="40" height="${usb ? 20 : 24}" rx="4" fill="${net ? '#6e7f96' : usb ? '#4a5568' : '#8a96a8'}"/>
    <rect x="4" y="${usb ? 14 : 12}" width="40" height="8" rx="4" fill="rgba(255,255,255,.25)"/>
    <rect x="9" y="${usb ? 27 : 29}" width="16" height="2.5" rx="1.2" fill="rgba(0,0,0,.35)"/>
    <circle cx="38" cy="${usb ? 28 : 30}" r="2" fill="${usb ? '#ffc53d' : '#46d160'}"/>
    ${system ? `<g transform="translate(28 3)"><rect width="7" height="7" fill="#0078d4"/><rect x="8" width="7" height="7" fill="#0078d4"/><rect y="8" width="7" height="7" fill="#0078d4"/><rect x="8" y="8" width="7" height="7" fill="#0078d4"/></g>` : ''}
    ${net ? '<path d="M24 36v6M14 42h20" stroke="#6e7f96" stroke-width="3" stroke-linecap="round"/>' : ''}
  </svg>`;
}

async function driveMenu(anchor) {
  let drives = S.drives;
  try { drives = S.drives = await get('drives'); } catch { }
  const items = drives.map(d => {
    const used = d.total - d.free, f = d.total ? used / d.total : 0;
    return {
      cls: 'drive-mi', action: () => scan(d.root),
      html: `<i class="ic">&#xEDA2;</i><div class="dm"><b>${esc(d.label || 'Local Disk')} (${esc(d.root.slice(0, 2))})</b>
        <small>${bytes(d.free)} free of ${bytes(d.total)}</small><div class="bar"><i style="width:${(f * 100).toFixed(1)}%"></i></div></div>`,
    };
  });
  items.push('-', { icon: '&#xE838;', label: 'Scan a folder…', key: 'Ctrl+O', action: pickFolder });
  if (!S.sys.admin) items.push({ icon: store.get('admin', false) ? '&#xE73E;' : '', label: 'Include protected folders (admin)', action: () => { store.set('admin', !store.get('admin', false)); syncAdmin(); } });
  showMenu(0, 0, items, anchor);
}

async function pickFolder() {
  try {
    const r = await post('pick-folder');
    if (r.path) scan(r.path);
  } catch (e) { toast(e.message, 'err'); }
}

// ======================================================================= scanning
let polling = false;
async function scan(path) {
  hideMenu();
  try {
    const r = await post('scan', { path, admin: !!store.get('admin', false) && !S.sys.admin });
    showScanning(r.path);
    poll();
  } catch (e) { toast(e.message, 'err'); }
}

function showScanning(path) {
  $('home').hidden = true;
  $('scanning').hidden = false;
  $('scanTitle').textContent = 'Scanning ' + path;
  $('scanRoom').innerHTML = '';
  roomMats = 0; roomCells = makeRoom();
}

// The scan animation: mats are laid into a room, one per chunk of files found.
let roomMats = 0, roomCells = [];
function makeRoom() {
  // a 6×4 room of 2:1 mats in a classic alternating layout (one cell = 20×20)
  const cells = [];
  const W = 12, H = 8;
  const used = Array.from({ length: H }, () => Array(W).fill(false));
  let flip = false;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    if (used[y][x]) continue;
    const horiz = ((x >> 1) + (y >> 1) + (flip ? 1 : 0)) % 2 === 0;
    if (horiz && x + 1 < W && !used[y][x + 1]) { used[y][x] = used[y][x + 1] = true; cells.push([x, y, 2, 1]); }
    else if (y + 1 < H && !used[y + 1][x]) { used[y][x] = used[y + 1][x] = true; cells.push([x, y, 1, 2]); }
    else { used[y][x] = true; cells.push([x, y, 1, 1]); }
  }
  // lay them in a pleasing order: from the doorway (bottom left) outward
  return cells.sort((a, b) => (a[0] + (H - a[1])) - (b[0] + (H - b[1])));
}
function addMats(n) {
  const svg = $('scanRoom');
  const cats = [1, 2, 3, 4, 6, 7, 8, 9, 10, 11];
  while (roomMats < n && roomMats < roomCells.length) {
    const [x, y, w, h] = roomCells[roomMats++];
    const c = CATS[cats[(roomMats * 7) % cats.length]].c;
    svg.insertAdjacentHTML('beforeend', `<g class="mat"><rect x="${x * 20 + 1}" y="${y * 20 + 1}" width="${w * 20 - 2}" height="${h * 20 - 2}" rx="2.5" fill="${c}"/>
      <rect x="${x * 20 + 2.5}" y="${y * 20 + 2.5}" width="${w * 20 - 5}" height="${h * 20 - 5}" rx="1.5" fill="none" stroke="rgba(255,255,255,.3)"/></g>`);
  }
  if (roomMats >= roomCells.length) { svg.innerHTML = ''; roomMats = 0; }
}

async function poll() {
  if (polling) return;
  polling = true;
  try {
    while (true) {
      let st;
      try { st = await get('status'); } catch (e) { toast(e.message, 'err'); break; }
      if (st.state === 'elevating') {
        $('scanTitle').textContent = 'Waiting for administrator permission…';
        $('scPath').textContent = 'Windows asks whether Tatami may read protected folders.';
        await sleep(250); continue;
      }
      if (st.state === 'scanning' || st.state === 'finishing') {
        $('scanTitle').textContent = (st.admin ? 'Scanning as administrator ' : 'Scanning ') + st.path;
        $('scFiles').textContent = num(st.files);
        $('scDirs').textContent = num(st.dirs);
        $('scBytes').textContent = bytes(st.bytes);
        $('scTime').textContent = (st.seconds || 0).toFixed(1) + ' s';
        $('scPath').textContent = st.state === 'finishing' ? 'Adding up folder sizes…' : (st.current || '');
        addMats(Math.floor((st.files || 0) / 20000) + Math.floor((st.seconds || 0) * 3));
        await sleep(160);
        continue;
      }
      if (st.state === 'done') { await loaded(); break; }
      if (st.state === 'error') { toast('Scan failed: ' + st.error, 'err'); showHome(); break; }
      if (st.state === 'cancelled') { if (st.error) toast(st.error, 'info'); if (S.summary) { $('scanning').hidden = true; } else showHome(); break; }
      break;
    }
  } finally { polling = false; }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ======================================================================= loaded
async function loaded() {
  const [sum, ex] = await Promise.all([get('summary'), get('exts')]);
  S.summary = sum;
  setExts(ex.names, ex.cats);
  S.bySize = sum.bySize;
  S.kids.clear(); S.nodes.clear(); S.open = new Set([0]); S.history = []; S.typeFilter = null;
  $('metric').querySelectorAll('button').forEach(b => b.classList.toggle('on', (b.dataset.m === 'size') === S.bySize));
  const rootNode = (await get('node', { id: 0 })).node;
  remember(rootNode);
  $('home').hidden = true; $('scanning').hidden = true;
  $('driveLabel').textContent = sum.wholeDrive ? sum.path.slice(0, 2) : 'Drives';
  document.title = 'Tatami — ' + sum.path;
  S.root = 0; S.selected = 0; S.dupes = null;
  syncColorButtons();
  if (sum.baselineLoading) watchBaseline();
  await refreshTree();
  treeGrid.selectId(0);
  await Promise.all([setRoot(0, false), drivebar()]);
  $('stLeft').textContent = `Scanned ${num(sum.files)} files and ${num(sum.dirs)} folders in ${sum.seconds.toFixed(2)} s`;
  if (sum.denied) $('stLeft').textContent += ` · ${num(sum.denied)} folders couldn't be opened`;
  if (S.tab === 'files') loadFiles();
  if (S.tab === 'insights') loadInsights();
}

function remember(n) { if (n) S.nodes.set(n.id, n); return n; }

async function drivebar() {
  const s = S.summary;
  $('dbName').textContent = s.path;
  $('dbSub').textContent = `${s.method} · ${s.scannedAt}`;
  // category totals for the capacity bar
  let types = [];
  try { types = await get('types', { id: 0 }); } catch { }
  const cat = new Array(CATS.length).fill(0);
  for (const t of types) cat[t.cat] += S.bySize ? t.s : t.a;
  const total = s.wholeDrive ? s.total : Math.max(1, S.bySize ? s.size : s.alloc);
  const parts = cat.map((v, i) => ({ i, v })).filter(p => p.v > 0).sort((a, b) => b.v - a.v);
  let html = parts.map(p => `<div title="${esc(CATS[p.i].name)}: ${bytes(p.v)}" style="width:${p.v / total * 100}%;background:${CATS[p.i].c}"></div>`).join('');
  if (s.wholeDrive && s.unaccounted > 0)
    html += `<div title="System &amp; protected: ${bytes(s.unaccounted)}" style="width:${s.unaccounted / total * 100}%;background:repeating-linear-gradient(135deg,#8b939e 0 3px,#6b737e 3px 6px)"></div>`;
  $('dbBar').innerHTML = html;
  $('dbLegend').innerHTML = parts.slice(0, 9).map(p =>
    `<span data-cat="${p.i}" class="${S.typeFilter && S.typeFilter.cat === p.i ? 'on' : ''}"><i style="background:${CATS[p.i].c}"></i>${esc(CATS[p.i].name)} ${bytes(p.v)}</span>`).join('')
    + (s.wholeDrive && s.unaccounted > 0 ? `<span title="Space Windows uses that a normal scan can't see: restore points, file system metadata, protected folders"><i style="background:#7b838e"></i>System &amp; protected ${bytes(s.unaccounted)}</span>` : '');
  $('dbLegend').querySelectorAll('[data-cat]').forEach(e => e.onclick = () => toggleTypeFilter({ cat: +e.dataset.cat }));
  $('dbStats').innerHTML = s.wholeDrive
    ? `<div><b>${bytes(s.used)}</b>used (${pct(s.used / s.total)})</div><div><b>${bytes(s.free)}</b>free of ${bytes(s.total)}</div><div><b>${num(s.files)}</b>files</div>`
    : `<div><b>${bytes(S.bySize ? s.size : s.alloc)}</b>in this folder</div><div><b>${num(s.files)}</b>files</div><div><b>${bytes(s.free)}</b>free on ${esc(s.volume)}</div>`;
}

// ======================================================================= folder tree
async function children(id) {
  if (S.kids.has(id)) return S.kids.get(id);
  const r = await get('children', { id, sort: S.sort, dir: S.dir });
  for (const it of r.items) remember(it);
  S.kids.set(id, r.items);
  return r.items;
}

async function refreshTree() {
  // load every expanded folder (in parallel), then flatten
  // (repeat: a folder deep in the chain becomes known only once its parent's children are loaded)
  for (let pass = 0; pass < 64; pass++) {
    const need = [...S.open].filter(id => S.nodes.has(id) && !S.kids.has(id));
    if (!need.length) break;
    await Promise.all(need.map(id => children(id).catch(() => { S.open.delete(id); })));
  }
  const rows = [];
  const visit = (node, depth, parentVal) => {
    const row = Object.assign({}, node, { depth, pv: parentVal });
    rows.push(row);
    if (!(node.f & F.DIR) || !S.open.has(node.id)) return;
    let kids = S.kids.get(node.id) || [];
    const v = metric(node);
    if (node.id === 0 && S.summary && S.summary.wholeDrive && S.summary.unaccounted > 0) {
      const un = { id: UNACC, n: 'System & protected space', f: 0, s: S.summary.unaccounted, a: S.summary.unaccounted, unacc: true, dim: true };
      kids = kids.slice();
      const at = S.sort === 'size' || S.sort === 'alloc' ? kids.findIndex(k => metric(k) < un.s) : -1;
      if (S.dir === 'asc' && at >= 0) kids.splice(kids.findIndex(k => metric(k) > un.s) < 0 ? kids.length : kids.findIndex(k => metric(k) > un.s), 0, un);
      else kids.splice(at < 0 ? kids.length : at, 0, un);
    }
    for (const k of kids) visit(k, depth + 1, v);
  };
  const root = S.nodes.get(0);
  if (root) visit(root, 0, metric(root));
  for (const r of rows) if (r.f & F.HARDLINK) r.dim = true;
  treeGrid.setRows(rows);
}

const metric = n => S.bySize ? n.s : n.a;

function nameCell(r) {
  const pad = r.depth * 18;
  const dir = r.f & F.DIR;
  const tw = dir && (r.c || r.id === 0) ? `<span class="tw">${S.open.has(r.id) ? '&#xE70D;' : '&#xE76C;'}</span>` : '<span class="tw"></span>';
  let icon;
  if (r.unacc) icon = '<span class="unk"></span>';
  else if (dir) icon = `<span class="fold${r.f & F.LINK ? ' link' : ''}${r.f & F.DENIED ? ' denied' : ''}"></span>`;
  else icon = `<span class="fil" style="--c:${extCss(r.e)}"></span>`;
  let badge = '';
  if (r.f & F.LINK) badge = '<span class="badge" title="Junction or link — points to a folder counted elsewhere">link</span>';
  else if (r.f & F.DENIED) badge = '<span class="badge" title="Windows didn\'t allow reading this folder">no access</span>';
  else if (r.f & F.HARDLINK) badge = '<span class="badge" title="Another name for a file already counted (hard link)">hard link</span>';
  else if (r.f & F.CLOUD) badge = '<span class="badge" title="Online-only file — takes no space on this PC">cloud</span>';
  return `<div class="g-name" style="padding-left:${pad}px">${tw}<span class="fi">${icon}</span><span class="nm" title="${esc(r.n)}">${esc(r.n)}</span>${badge}</div>`;
}

function nameCellFlat(r) {
  if (r.grp) return `<div class="g-name"><i class="ic">&#xE8C8;</i><span class="nm">${num(r.count)} identical files · ${bytes(r.size)} each</span></div>`;
  const dir = r.f & F.DIR;
  const icon = dir ? '<span class="fold"></span>' : `<span class="fil" style="--c:${extCss(r.e)}"></span>`;
  let badge = '';
  if (r.f & F.HARDLINK) badge = '<span class="badge">hard link</span>';
  else if (r.f & F.CLOUD) badge = '<span class="badge">cloud</span>';
  return `<div class="g-name"><span class="fi">${icon}</span><span class="nm" title="${esc(r.path)}">${esc(r.n)}</span>${badge}</div>`;
}

function pathCell(r) {
  if (r.grp) return `<span class="dup-w">${bytes(r.wasted)} in extra copies</span>`;
  if (!r.dup) return esc(parentPath(r.path));
  return `<div class="dup-path"><span class="pth" title="${esc(r.path)}">${esc(parentPath(r.path))}</span><span class="row-acts">
    <button data-act="reveal" data-id="${r.id}" title="Show in File Explorer">&#xEC50;</button>
    <button data-act="recycle" data-id="${r.id}" class="danger" title="Delete to Recycle Bin">&#xE74D;</button></span></div>`;
}

function pctCell(r) {
  if (r.depth === 0 && r.id === 0) return '';
  const f = r.pv > 0 ? metric(r) / r.pv : 0;
  const color = r.unacc ? '#8b939e' : (r.f & F.DIR) ? 'var(--accent)' : extCss(r.e);
  return `<div class="pct"><div class="bar"><i style="width:${Math.min(100, f * 100).toFixed(1)}%;background:${color}"></i></div><span>${pct(f)}</span></div>`;
}

function typeLabel(e) { const n = extName(e); return n ? n.toUpperCase() + ' file' : 'File'; }
function parentPath(p) { const i = (p || '').lastIndexOf('\\'); return i > 0 ? p.slice(0, i) : p; }

async function toggle(row, force) {
  if (!(row.f & F.DIR) || row.id < 0) return;
  const open = force ?? !S.open.has(row.id);
  if (open) S.open.add(row.id); else S.open.delete(row.id);
  await refreshTree();
}

function activate(row) {
  if (row.id < 0) return;
  if (row.f & F.DIR) navigate(row.id); else openItem(row);
}

function treeKey(e, row) {
  if (!row) return false;
  if (e.key === 'ArrowRight' && (row.f & F.DIR)) {
    if (!S.open.has(row.id)) { toggle(row, true); e.preventDefault(); return true; }
    return false;
  }
  if (e.key === 'ArrowLeft') {
    if ((row.f & F.DIR) && S.open.has(row.id)) { toggle(row, false); e.preventDefault(); return true; }
    const pi = treeGrid.rows.findIndex(r => r.id === parentOf(row));
    if (pi >= 0) { treeGrid.select(pi); e.preventDefault(); return true; }
    return false;
  }
  return commonKeys(e, row, treeGrid);
}

function parentOf(row) {
  const i = treeGrid.rows.indexOf(treeGrid.rows.find(r => r.id === row.id));
  for (let k = i - 1; k >= 0; k--) if (treeGrid.rows[k].depth < row.depth) return treeGrid.rows[k].id;
  return -1;
}

function commonKeys(e, row, grid) {
  if (e.key === 'Delete') { const sel = grid.selected().filter(r => r.id >= 0); if (sel.length) deleteItems(sel, e.shiftKey); e.preventDefault(); return true; }
  if (e.key === 'c' && e.ctrlKey) { copyPaths(grid.selected().filter(r => r.id >= 0)); e.preventDefault(); return true; }
  if (e.key === 'F10' && e.shiftKey || e.key === 'ContextMenu') {
    const el = grid.canvas.querySelector('.g-row.cur') || grid.el; const rc = el.getBoundingClientRect();
    nodeMenu(row, rc.left + 60, rc.bottom); e.preventDefault(); return true;
  }
  return false;
}

/** Expand the tree down to a node and select it (used by treemap clicks). */
async function revealInTree(id, chain) {
  if (S.tab !== 'tree') switchTab('tree');
  let ids = chain && chain.length ? chain.slice().reverse() : null;
  if (!ids || ids[0] !== 0) {
    const r = await get('node', { id }).catch(() => null);
    if (!r) return;
    remember(r.node);
    ids = r.node.chain.map(c => c.id);
  }
  // make sure the full chain from the scan root is known (the treemap may be zoomed in)
  if (ids[0] !== 0) {
    const r = await get('node', { id }).catch(() => null);
    if (!r) return;
    ids = r.node.chain.map(c => c.id);
  }
  for (const a of ids.slice(0, -1)) S.open.add(a);
  await refreshTree();
  treeGrid.selectId(id, false);
}

async function selectNode(row, from) {
  if (!row || row.id < 0) { tm.select(null); return; }
  S.selected = row.id;
  const r = await get('node', { id: row.id }).catch(() => null);
  if (!r) return;
  remember(Object.assign(S.nodes.get(row.id) || {}, r.node));
  const n = r.node;
  tm.select(n.chain.map(c => c.id).reverse());
  $('stRight').textContent = `${n.path} · ${bytes(metric(n))} · ${pct(n.pctRoot)} of scan`;
  if (from === 'files') { /* keep the treemap where it is */ }
}

// ======================================================================= navigation (treemap root)
async function navigate(id, push = true) {
  if (id === S.root) return;
  const n = S.nodes.get(id) || (await get('node', { id }).catch(() => null))?.node;
  if (!n || !(n.f & F.DIR)) return;
  if (push) S.history.push(S.root);
  await setRoot(id, true);
}

async function setRoot(id, reveal) {
  S.root = id;
  const r = await get('node', { id }).catch(() => null);
  if (!r) return;
  const n = remember(Object.assign(S.nodes.get(id) || {}, r.node));
  // breadcrumbs
  $('crumbs').innerHTML = r.node.chain.map((c, i) =>
    `${i ? '<span class="crumb-sep">&#xE76C;</span>' : ''}<span class="crumb" data-id="${c.id}" title="${esc(c.n)}">${esc(i === 0 ? c.n.replace(/\\$/, '') : c.n)}</span>`).join('');
  $('crumbs').querySelectorAll('.crumb').forEach(c => c.onclick = () => navigate(+c.dataset.id));
  $('crumbs').scrollLeft = 1e6;
  $('tmTitle').textContent = n.path;
  $('btnUp').disabled = id === 0;
  $('btnBack').disabled = !S.history.length;
  $('tmOut').disabled = id === 0;
  tm.bySize = S.bySize;
  await Promise.all([tm.show(id), loadTypes()]);
  if (reveal) { await revealInTree(id); }
  tm.select(S.selected != null ? [S.selected] : null);
  if (S.tab === 'files') loadFiles();
}

// ======================================================================= file types panel
async function loadTypes() {
  let types = [];
  try { types = await get('types', { id: S.root }); } catch { return; }
  const total = types.reduce((a, t) => a + (S.bySize ? t.s : t.a), 0) || 1;
  const n = S.nodes.get(S.root);
  $('typesScope').textContent = `${num(types.length)} types in ${n ? n.n : ''}`;
  $('types').innerHTML = types.slice(0, 400).map(t => {
    const v = S.bySize ? t.s : t.a, on = S.typeFilter && S.typeFilter.ext && S.typeFilter.ext.has(t.e);
    return `<div class="ty${on ? ' on' : ''}" data-e="${t.e}" title="${esc(CATS[t.cat].name)} · ${num(t.c)} files · double-click to list them">
      <span class="sw" style="background:${extCss(t.e)}"></span>
      <span class="tn">${t.n ? '.' + esc(t.n) : '(no extension)'}<small>${num(t.c)}</small></span>
      <span class="ts">${bytes(v)}</span>
      <span class="tb"><i style="width:${(v / total * 100).toFixed(2)}%;background:${extCss(t.e)}"></i></span>
    </div>`;
  }).join('') + (types.length > 400 ? `<div class="g-empty">${num(types.length - 400)} more small types</div>` : '');
  $('types').querySelectorAll('.ty').forEach(el => {
    el.onclick = () => toggleTypeFilter({ ext: +el.dataset.e });
    el.ondblclick = () => { S.files.ext = +el.dataset.e; S.files.cat = -1; switchTab('files'); };
  });
  renderLegend();
}

function toggleTypeFilter(f) {
  const cur = S.typeFilter;
  const same = cur && ((f.ext != null && cur.ext && cur.ext.has(f.ext) && cur.ext.size === 1) || (f.cat != null && cur.cat === f.cat));
  if (same) S.typeFilter = null;
  else S.typeFilter = f.ext != null ? { ext: new Set([f.ext]) } : { cat: f.cat };
  tm.setFilter(S.typeFilter);
  document.querySelectorAll('#types .ty').forEach(el => el.classList.toggle('on', !!(S.typeFilter && S.typeFilter.ext && S.typeFilter.ext.has(+el.dataset.e))));
  document.querySelectorAll('#dbLegend [data-cat]').forEach(el => el.classList.toggle('on', !!(S.typeFilter && S.typeFilter.cat === +el.dataset.cat)));
  renderLegend();
}

function renderLegend() {
  const f = S.typeFilter;
  if (f) {
    const label = f.ext ? [...f.ext].map(e => extName(e) ? '.' + extName(e) : '(no extension)').join(', ') : CATS[f.cat].name;
    $('tmLegend').innerHTML = `<span>Highlighting <b>${esc(label)}</b></span><button class="btn icon sm" id="tmClear" title="Clear highlight"><i class="ic">&#xE711;</i></button>`;
    $('tmClear').onclick = () => { S.typeFilter = null; tm.setFilter(null); loadTypes(); drivebar(); };
  } else if (tm.mode === 1) {
    const ramp = [];
    for (let k = 0; k <= 24; k++) { const d = Math.expm1(k / 24 * Math.log1p(3650)); const [r, g, b] = ageRgb(d).map(Math.round); ramp.push(`rgb(${r},${g},${b}) ${(k / 24 * 100).toFixed(0)}%`); }
    $('tmLegend').innerHTML = `<span>Modified</span><span>today</span><i class="ramp" style="background:linear-gradient(90deg,${ramp.join(',')})"></i><span>10+ years ago</span>`;
  } else if (tm.mode === 2) {
    const b = S.summary && S.summary.baseline;
    $('tmLegend').innerHTML = `<span title="Compared with the scan of ${esc(b || '')}">Since ${esc(b || 'last scan')}:</span>
      <span><i style="background:${GROWTH.fresh}"></i>New</span>
      <span><i style="background:linear-gradient(90deg,${GROWTH.grew1},${GROWTH.grew2})"></i>Grew</span>
      <span><i style="background:${GROWTH.same}"></i>Same</span>
      <span><i style="background:${GROWTH.shrank}"></i>Shrank</span>`;
  } else {
    $('tmLegend').innerHTML = CATS.slice(1, 11).map((c, i) => `<span><i style="background:${c.c}"></i>${esc(c.name)}</span>`).join('');
  }
}

// ======================================================================= treemap colour modes
function syncColorButtons() {
  const sum = S.summary || {};
  const shown = ['type', 'age', 'growth'][tm.mode];    // what the map really shows (growth falls back to type without a baseline)
  $('tmColor').querySelectorAll('button').forEach(b => {
    b.classList.toggle('on', b.dataset.c === shown);
    if (b.dataset.c === 'growth') {
      b.disabled = !sum.baseline;
      b.title = sum.baseline ? `What grew since the scan of ${sum.baseline}`
        : sum.baselineLoading ? 'Loading the previous scan…' : 'Needs an earlier scan of the same drive or folder — scan again later to compare';
    }
  });
}

async function setColor(c) {
  if (c === 'growth' && !(S.summary && S.summary.baseline)) {
    toast(S.summary && S.summary.baselineLoading ? 'Still loading the previous scan — try again in a moment.' : 'There is no earlier scan of this drive or folder to compare with yet.', 'info');
    return;
  }
  S.color = c; store.set('tmColor', c);
  syncColorButtons();
  await tm.setColor(c);
}

/** The previous scan loads in the background after a scan; enable "Growth" once it's there. */
async function watchBaseline() {
  for (let k = 0; k < 40 && S.summary && S.summary.baselineLoading; k++) {
    await sleep(1500);
    try { const s = await get('summary'); S.summary.baseline = s.baseline; S.summary.baselineLoading = s.baselineLoading; } catch { return; }
  }
  syncColorButtons();
  if (S.color === 'growth' && S.summary && S.summary.baseline && tm.mode !== 2) tm.reload();
}

// ======================================================================= treemap hover
let tipTimer = 0, tipId = -1;
function tmHover(h) {
  const tip = $('tmTip');
  if (!h) { tip.hidden = true; tipId = -1; return; }
  const place = () => {
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    tip.style.left = Math.min(h.w - tw - 6, h.x + 16) + 'px';
    tip.style.top = (h.y + 18 + th > h.h ? Math.max(4, h.y - th - 10) : h.y + 18) + 'px';
  };
  const key = h.id + (h.rest != null ? ':rest' : '');
  if (key === tipId && !tip.hidden) { place(); return; }
  tipId = key;
  clearTimeout(tipTimer);
  tipTimer = setTimeout(async () => {
    const r = await get('node', { id: h.id }).catch(() => null);
    if (!r || tipId !== key) return;
    const n = r.node, dir = n.f & F.DIR;
    const many = h.rest != null;
    const kind = many ? 'Items too small to draw, grouped together' : dir ? `Folder · ${num(n.fi)} files · ${num(n.di)} folders` : `${typeLabel(n.e)} · ${CATS[extCat(n.e)].name}`;
    tip.innerHTML = `<b>${esc(many ? 'Many small items in ' + n.n : n.n)}</b>
      <div class="row">${many ? `<span>${bytes(h.rest)}</span><span class="muted">of ${bytes(metric(n))} in this folder</span>` : `<span>${bytes(n.s)}</span><span class="muted">on disk ${bytes(n.a)}</span><span class="muted">${pct(n.pctRoot)} of all</span>`}</div>
      <div class="row muted"><span>${dir ? '' : `<i style="background:${extCss(n.e)}"></i>`}${esc(kind)}</span></div>
      ${n.m ? `<div class="muted">Modified ${date(n.m)} (${ago(n.m)})</div>` : ''}
      ${keyLine(tm.keyInfo(h.rec), dir || many)}
      <div class="p">${esc(n.path)}</div>`;
    tip.hidden = false;
    place();
  }, 60);
  place();
}

function keyLine(k, group) {
  if (!k) return '';
  if (k.mode === 1) {
    if (!(k.a >= 0)) return '';
    const ms = Date.now() - k.a * 86400000;
    return group ? `<div class="muted">Typical age (weighted by size): ${esc(ago(ms) || 'today')}</div>` : '';
  }
  const b = S.summary && S.summary.baseline;
  if (k.a !== k.a) return '';
  if (k.a > 1.5) return `<div class="row"><span><i style="background:${GROWTH.fresh}"></i>New since the scan of ${esc(b)}</span></div>`;
  if (Math.abs(k.b) < 1) return `<div class="row muted"><span><i style="background:${GROWTH.same}"></i>Unchanged since ${esc(b)}</span></div>`;
  const up = k.b > 0;
  return `<div class="row"><span><i style="background:${up ? GROWTH.grew2 : GROWTH.shrank}"></i>${up ? 'Grew' : 'Shrank'} by ${bytes(Math.abs(k.b))} since ${esc(b)}</span></div>`;
}

// ======================================================================= files tab
let filesSeq = 0, searchTimer = 0;
async function loadFiles() {
  const seq = ++filesSeq;
  const f = S.files;
  if (f.dupes) { renderDupesBar(); return loadDupes(seq); }
  fileGrid.empty = 'No files match.';
  renderFilterBar();
  const params = { id: S.root, q: f.q, ext: f.ext, cat: f.cat, min: f.min, older: f.older, sort: f.sort, dir: f.dir, limit: f.limit };
  if (f.dirs) params.dirs = 1;
  let r;
  try { r = await get('files', params); } catch (e) { toast(e.message, 'err'); return; }
  if (seq !== filesSeq) return;
  for (const it of r.items) remember(it);
  fileGrid.footer = r.total > r.items.length ? `Showing ${num(r.items.length)} of ${num(r.total)} · <a href="#" id="moreFiles">show more</a>` : '';
  fileGrid.setRows(r.items, false);
  const more = document.getElementById('moreFiles');
  if (more) more.onclick = e => { e.preventDefault(); S.files.limit *= 5; loadFiles(); };
  $('fbSum').textContent = `${num(r.total)} ${f.dirs ? 'folders' : 'files'} · ${bytes(r.sum)}`;
  $('tabNote').textContent = f.q ? `Search: ${f.q}` : '';
}

function renderFilterBar() {
  const f = S.files;
  const chips = [modeChips()];
  if (f.q) chips.push(`<span class="chip on" data-act="clearq">“${esc(f.q)}” <span class="x">&#xE711;</span></span>`);
  if (f.ext >= 0) chips.push(`<span class="chip on" data-act="clearext"><i class="sw" style="background:${extCss(f.ext)}"></i>.${esc(extName(f.ext) || '(none)')} <span class="x">&#xE711;</span></span>`);
  const catOpts = ['<option value="-1">All types</option>'].concat(CATS.slice(0, 11).map((c, i) => `<option value="${i}" ${f.cat === i ? 'selected' : ''}>${esc(c.name)}</option>`)).join('');
  const sizes = [[0, 'Any size'], [1 << 20, '≥ 1 MB'], [100 << 20, '≥ 100 MB'], [1 << 30, '≥ 1 GB'], [10 * 2 ** 30, '≥ 10 GB']];
  const ages = [[0, 'Any age'], [30, 'Older than 1 month'], [182, 'Older than 6 months'], [365, 'Older than 1 year'], [1095, 'Older than 3 years']];
  const ageDays = f.older ? Math.round((Date.now() - f.older) / 86400000) : 0;
  $('filterbar').innerHTML = chips.join('') +
    `<select id="fbCat" title="Type">${catOpts}</select>` +
    `<select id="fbMin" title="Size">${sizes.map(([v, l]) => `<option value="${v}" ${f.min === v ? 'selected' : ''}>${l}</option>`).join('')}</select>` +
    `<select id="fbAge" title="Last modified">${ages.map(([v, l]) => `<option value="${v}" ${Math.abs(ageDays - v) < 2 && (v > 0) === (f.older > 0) ? 'selected' : ''}>${l}</option>`).join('')}</select>` +
    `<span class="fb-sum" id="fbSum"></span>`;
  $('filterbar').querySelectorAll('[data-act]').forEach(c => c.onclick = () => {
    const a = c.dataset.act;
    if (a === 'clearq') { f.q = ''; $('search').value = ''; }
    if (a === 'clearext') f.ext = -1;
    if (modeChip(a)) return;
    f.limit = 1000;
    loadFiles();
  });
  $('fbCat').onchange = e => { f.cat = +e.target.value; f.ext = -1; f.limit = 1000; loadFiles(); };
  $('fbMin').onchange = e => { f.min = +e.target.value; f.limit = 1000; loadFiles(); };
  $('fbAge').onchange = e => { const d = +e.target.value; f.older = d ? Date.now() - d * 86400000 : 0; f.limit = 1000; loadFiles(); };
}

function modeChips() {
  const f = S.files, m = f.dupes ? 'dupes' : f.dirs ? 'dirs' : 'files';
  return [['files', 'Files'], ['dirs', 'Folders'], ['dupes', 'Duplicates']]
    .map(([k, l]) => `<span class="chip${m === k ? ' on' : ''}" data-act="${k}">${l}</span>`).join('');
}
/** Files | Folders | Duplicates chip clicked: switch the list. True when handled. */
function modeChip(a) {
  if (a !== 'files' && a !== 'dirs' && a !== 'dupes') return false;
  const f = S.files;
  f.dupes = a === 'dupes'; f.dirs = a === 'dirs'; f.limit = 1000;
  loadFiles();
  return true;
}

// ======================================================================= duplicates (Largest files tab)
let dupPoll = 0;
function renderDupesBar() {
  const f = S.files, d = S.dupes || { state: 'idle' };
  const mins = [[1 << 20, '≥ 1 MB'], [10 << 20, '≥ 10 MB'], [100 << 20, '≥ 100 MB'], [1 << 30, '≥ 1 GB']];
  const scope = S.nodes.get(S.root);
  let mid = '';
  if (d.state === 'hashing') {
    const p = d.bytesTotal ? d.bytesDone / d.bytesTotal : 0;
    mid = `<span class="fb-note">${esc(d.phase)}… ${num(d.filesDone)} of ${num(d.filesTotal)} files</span>
      <span class="fb-prog"><i style="width:${(p * 100).toFixed(1)}%"></i></span>
      <button class="btn" id="dupCancel">Cancel</button>`;
  } else {
    mid = `<select id="dupMin" title="Only compare files at least this big">${mins.map(([v, l]) => `<option value="${v}" ${f.dupMin === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <button class="btn${d.state === 'done' ? '' : ' primary'}" id="dupStart" title="Compares the contents of files that have the same size">${d.state === 'done' ? 'Search again' : 'Find duplicates'}${scope && S.root !== 0 ? ' in ' + esc(scope.n) : ''}</button>`;
    if (d.state === 'done' && d.groups) mid += `<button class="btn" id="dupSelect" title="Select every copy except the oldest one in each set">Select extra copies</button>
      <button class="btn danger" id="dupRecycle" title="Move every copy except the oldest one in each set to the Recycle Bin">Recycle extra copies…</button>`;
  }
  let sum = '';
  if (d.state === 'done') sum = d.groups ? `${num(d.groups)} ${d.groups === 1 ? 'set' : 'sets'} · ${num(d.files)} files · <b>${bytes(d.wasted)}</b> in extra copies` : 'No duplicates found';
  else if (d.state === 'cancelled') sum = 'Search cancelled';
  else if (d.state === 'error') sum = 'Search failed: ' + esc(d.error || '');
  $('filterbar').innerHTML = modeChips() + mid + `<span class="fb-sum" id="fbSum">${sum}</span>`;
  $('filterbar').querySelectorAll('[data-act]').forEach(c => c.onclick = () => modeChip(c.dataset.act));
  const on = (id, fn) => { const e = document.getElementById(id); if (e) e.onclick = fn; };
  on('dupStart', () => startDupes());
  on('dupCancel', () => post('dupes-cancel').catch(e => toast(e.message, 'err')));
  on('dupSelect', () => selectExtraCopies());
  on('dupRecycle', () => { const rows = selectExtraCopies(); if (rows.length) deleteItems(rows, false); });
  const sel = document.getElementById('dupMin');
  if (sel) sel.onchange = e => { f.dupMin = +e.target.value; store.set('dupMin', f.dupMin); };
}

async function startDupes() {
  try { await post('dupes-start', { id: S.root, min: S.files.dupMin }); }
  catch (e) { toast(e.message, 'err'); return; }
  S.files.dupes = true; S.files.dirs = false;
  if (S.tab !== 'files') switchTab('files'); else loadFiles();
}

async function loadDupes(seq) {
  let d;
  try { d = await get('dupes'); } catch (e) { toast(e.message, 'err'); return; }
  if (seq !== filesSeq) return;
  S.dupes = d;
  renderDupesBar();
  $('tabNote').textContent = d.state === 'done' || d.state === 'hashing' ? (d.scope === 0 ? '' : 'Duplicates in ' + d.scopePath) : '';
  if (d.state === 'hashing') {
    fileGrid.empty = d.candidates ? `Comparing ${num(d.candidates)} files that share a size with another file…` : 'Looking for files of the same size…';
    fileGrid.footer = '';
    fileGrid.setRows([], false);
    clearTimeout(dupPoll);
    dupPoll = setTimeout(() => { if (S.tab === 'files' && S.files.dupes && seq === filesSeq) loadDupes(seq); }, 400);
    return;
  }
  if (d.state !== 'done') {
    fileGrid.empty = `Find files that are stored more than once. Tatami groups files of the same size, then compares their contents (first 64 KB, then the whole file).
      <br><span class="muted">Hard links, online-only (cloud) files and the Windows folder are left out.</span>`;
    fileGrid.footer = '';
    fileGrid.setRows([], false);
    return;
  }
  const rows = [];
  d.items.forEach((g, gi) => {
    rows.push({ id: -1000 - gi, grp: true, count: g.files.length, size: g.size, wasted: g.wasted, cls: 'dup-h' });
    g.files.forEach((it, k) => { remember(it); rows.push(Object.assign({}, it, { dup: true, g: gi, cls: 'dup-f' + (k === 0 ? ' dup-keep' : '') })); });
  });
  fileGrid.empty = `No identical files of ${bytes(d.min)} or more${d.scope === 0 ? '' : ' in ' + esc(d.scopePath)}.`;
  fileGrid.footer = d.groups > d.items.length ? `Showing the ${num(d.items.length)} biggest of ${num(d.groups)} sets` : '';
  fileGrid.setRows(rows, true);
}

/** Select every copy but the first (oldest) of each set; returns those rows. */
function selectExtraCopies() {
  const rows = fileGrid.rows.filter(r => r.dup && !/\bdup-keep\b/.test(r.cls));
  fileGrid.sel = new Set(rows.map(r => r.id));
  fileGrid.render(true);
  const total = rows.reduce((a, r) => a + metric(r), 0);
  $('stRight').textContent = `${num(rows.length)} extra copies selected · ${bytes(total)}`;
  return rows;
}

// ======================================================================= tabs
function switchTab(t) {
  S.tab = t;
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('on', b.dataset.tab === t));
  document.querySelectorAll('.tabbody').forEach(b => b.hidden = b.dataset.body !== t);
  $('tabNote').textContent = '';
  if (!S.summary) return;
  if (t === 'files') loadFiles();
  if (t === 'insights') loadInsights();
  if (t === 'tree') treeGrid.render(true);
}

// ======================================================================= insights (filled in phase 6)
async function loadInsights() {
  const box = $('insights');
  box.innerHTML = '<div class="g-empty">Looking for things you can clean up…</div>';
  let ins;
  try { ins = await get('insights', { id: S.root }); }
  catch (e) { box.innerHTML = `<div class="g-empty">${esc(e.message)}</div>`; return; }
  box.innerHTML = ins.map((c, i) => `<div class="ins">
      <h4><i class="ic">${c.icon || '&#xE946;'}</i>${esc(c.title)}</h4>
      ${c.size != null ? `<div class="big">${c.signed ? signed(c.size) : bytes(c.size)}</div>` : ''}
      <p>${esc(c.text)}</p>
      ${c.items && c.items.length ? `<ul>${c.items.slice(0, 6).map(it => `<li data-id="${it.id}"><span title="${esc(it.path || it.n)}">${esc(it.n)}</span><span class="${it.delta ? (it.s > 0 ? 'up' : 'down') : ''}">${it.delta ? signed(it.s) : bytes(it.s)}</span></li>`).join('')}</ul>` : ''}
      <div class="acts">${(c.actions || []).map((a, k) => `<button class="btn" data-i="${i}" data-k="${k}">${esc(a.label)}</button>`).join('')}</div>
    </div>`).join('') || '<div class="g-empty">Nothing stands out — your disk looks tidy.</div>';
  box.querySelectorAll('li[data-id]').forEach(li => li.onclick = () => revealInTree(+li.dataset.id));
  box.querySelectorAll('.acts .btn').forEach(b => b.onclick = () => insightAction(ins[+b.dataset.i].actions[+b.dataset.k]));
}

const signed = v => (v > 0 ? '+' : v < 0 ? '−' : '') + bytes(Math.abs(v));

async function insightAction(a) {
  if (a.kind === 'files') {
    const f = a.filter || {};
    Object.assign(S.files, { q: f.q || '', ext: -1, cat: f.cat ?? -1, min: f.min || 0, older: f.olderDays ? Date.now() - f.olderDays * 86400000 : 0, dirs: !!f.dirs, dupes: false, limit: 1000 });
    if (f.q) $('search').value = f.q;
    if (a.root != null && a.root !== S.root) { S.history.push(S.root); await setRoot(a.root, false); }
    switchTab('files');
  }
  else if (a.kind === 'dupes') {
    if (a.start) { await startDupes(); return; }
    S.files.dupes = true; S.files.dirs = false;
    switchTab('files');
  }
  else if (a.kind === 'reveal') revealInTree(a.id);
  else if (a.kind === 'zoom') navigate(a.id);
  else if (a.kind === 'open') post('open-special', { what: a.what }).catch(e => toast(e.message, 'err'));
  else if (a.kind === 'zoom') navigate(a.id);
}

// ======================================================================= actions
function nodeMenu(row, x, y) {
  if (!row || row.id < 0) {
    if (row && row.unacc) showMenu(x, y, [{ head: 'System & protected space' },
      { icon: '&#xE946;', label: 'What is this?', action: explainUnaccounted }]);
    return;
  }
  const dir = row.f & F.DIR;
  const sel = (S.tab === 'files' ? fileGrid : treeGrid).selected().filter(r => r.id >= 0);
  const many = sel.length > 1 && sel.some(r => r.id === row.id);
  const targets = many ? sel : [row];
  showMenu(x, y, [
    { head: many ? `${sel.length} items · ${bytes(sel.reduce((a, r) => a + metric(r), 0))}` : row.n },
    dir ? { icon: '&#xE71E;', label: 'Zoom into folder', key: 'Enter', action: () => navigate(row.id) }
        : { icon: '&#xE8E5;', label: 'Open', key: 'Enter', action: () => openItem(row) },
    { icon: '&#xEC50;', label: 'Show in File Explorer', action: () => post('reveal', { id: row.id }).catch(e => toast(e.message, 'err')) },
    dir ? { icon: '&#xE8A5;', label: 'Largest files in here', action: () => { S.files.q = ''; S.files.ext = -1; setRoot(row.id, false).then(() => switchTab('files')); } } : null,
    '-',
    { icon: '&#xE8C8;', label: many ? 'Copy paths' : 'Copy path', key: 'Ctrl+C', action: () => copyPaths(targets) },
    { icon: '&#xE946;', label: 'Properties', action: () => post('props', { id: row.id }).catch(e => toast(e.message, 'err')) },
    dir ? { icon: '&#xE72C;', label: 'Rescan this folder', action: () => rescanFolder(row.id) } : null,
    '-',
    { icon: '&#xE74D;', label: 'Delete to Recycle Bin', key: 'Del', danger: true, action: () => deleteItems(targets, false) },
    { icon: '&#xE894;', label: 'Delete permanently…', key: 'Shift+Del', danger: true, action: () => deleteItems(targets, true) },
  ]);
}

function openItem(row) {
  if (row.f & F.DIR) { navigate(row.id); return; }
  post('open', { id: row.id }).catch(e => toast(e.message, 'err'));
}

async function copyPaths(rows) {
  if (!rows.length) return;
  const paths = [];
  for (const r of rows) {
    if (r.path) { paths.push(r.path); continue; }
    const n = await get('node', { id: r.id }).catch(() => null);
    if (n) paths.push(n.node.path);
  }
  try { await navigator.clipboard.writeText(paths.join('\r\n')); toast(paths.length > 1 ? `Copied ${paths.length} paths` : 'Copied ' + paths[0], 'ok', 2500); }
  catch { toast('Windows didn\'t allow copying to the clipboard.', 'err'); }
}

async function deleteItems(rows, permanent) {
  rows = rows.filter(r => r.id > 0);
  if (!rows.length) return;
  const total = rows.reduce((a, r) => a + (r.f & F.DIR ? r.s : r.s), 0);
  const paths = [];
  for (const r of rows.slice(0, 50)) {
    if (r.path) paths.push(r.path);
    else { const n = await get('node', { id: r.id }).catch(() => null); if (n) paths.push(n.node.path); }
  }
  const files = rows.reduce((a, r) => a + (r.f & F.DIR ? r.fi : 1), 0);
  // duplicates view: warn when every copy of a file would go
  let allCopies = 0;
  if (S.tab === 'files' && S.files.dupes) {
    const ids = new Set(rows.map(r => r.id)), left = new Map();
    for (const r of fileGrid.rows) if (r.dup && !ids.has(r.id)) left.set(r.g, true);
    allCopies = new Set(rows.filter(r => r.dup && !left.has(r.g)).map(r => r.g)).size;
  }
  const res = await dialog({
    title: permanent ? 'Delete permanently?' : 'Move to the Recycle Bin?',
    body: `<p>${rows.length === 1 ? `<b>${esc(rows[0].n)}</b>` : `<b>${rows.length} items</b>`} · ${bytes(total)}${files > 1 ? ` · ${num(files)} files` : ''}</p>
      <div class="d-list">${paths.map(esc).join('<br>')}${rows.length > 50 ? '<br>…' : ''}</div>
      ${allCopies ? `<p class="warn">This removes every copy of ${allCopies === 1 ? 'one file' : allCopies + ' files'} — no copy would be left.</p>` : ''}
      ${rows.some(r => r.f & F.LINK) ? '<p class="muted">For items marked <b>link</b>, only the link is removed. The folder it points to stays.</p>' : ''}
      ${permanent ? '<p class="warn">This can\'t be undone. The files won\'t go to the Recycle Bin.</p>'
                  : '<p class="muted">They go to the Recycle Bin, where you can restore them. If the Recycle Bin can\'t take an item (too big, or a drive without one), Tatami leaves it alone and tells you.</p>'}`,
    buttons: [{ label: permanent ? 'Delete permanently' : 'Move to Recycle Bin', danger: true, value: 'yes' }, { label: 'Cancel', focus: true }],
  });
  if (res !== 'yes') return;
  $('stLeft').textContent = 'Deleting…';
  let r;
  try { r = await post('delete', { ids: rows.map(x => x.id), permanent }); }
  catch (e) { toast(e.message, 'err'); return; }
  for (const e of r.errors) toast(e, 'err', 8000);
  if (r.deleted.length) {
    toast(`${permanent ? 'Deleted' : 'Moved to the Recycle Bin'}: ${r.deleted.length} item${r.deleted.length > 1 ? 's' : ''} (${bytes(total)})`, 'ok');
    await afterChange();
  }
  $('stLeft').textContent = 'Ready';
}

async function afterChange() {
  // sizes changed up the chain: drop caches and redraw everything visible
  const open = new Set(S.open);
  S.kids.clear(); S.nodes.clear();
  S.summary = await get('summary');
  remember((await get('node', { id: 0 })).node);
  S.open = open;
  let root = S.root;
  if (root !== 0 && !(await get('node', { id: root }).catch(() => null))) root = 0;
  await refreshTree();
  await Promise.all([setRoot(root, false), drivebar()]);
  if (S.tab === 'files') loadFiles();
  if (S.tab === 'insights') loadInsights();
}

async function rescanFolder(id) {
  try {
    $('stLeft').textContent = 'Rescanning…';
    const r = await post('rescan', { id });
    toast(`Rescanned in ${r.seconds.toFixed(1)} s`, 'ok', 2500);
    await afterChange();
  } catch (e) { toast(e.message, 'err'); }
  $('stLeft').textContent = 'Ready';
}

function explainUnaccounted() {
  dialog({
    title: 'System & protected space',
    body: `<p>This is space Windows reports as used, but that a normal scan can't open: System Restore points and shadow copies (in <i>System Volume Information</i>), the file system's own tables ($MFT), and folders your account isn't allowed to read.</p>
           <p class="muted">Run Tatami as administrator for a deeper scan. To shrink restore points, open <b>System Protection</b> in Windows settings.</p>`,
    buttons: [{ label: 'OK', primary: true }],
  });
}

// ======================================================================= commands
function wireCommands() {
  $('btnDrive').onclick = e => driveMenu($('btnDrive'));
  $('btnFolder').onclick = pickFolder;
  $('homeFolder').onclick = pickFolder;
  $('btnRescan').onclick = () => S.summary ? scan(S.summary.path) : showHome();
  $('scCancel').onclick = () => post('cancel');
  $('btnBack').onclick = () => { const id = S.history.pop(); if (id != null) navigate(id, false); };
  $('btnUp').onclick = up;
  $('tmOut').onclick = up;
  $('btnExport').onclick = exportCsv;
  $('btnMore').onclick = () => moreMenu($('btnMore'));
  document.querySelectorAll('.tab').forEach(b => b.onclick = () => switchTab(b.dataset.tab));
  $('tmColor').querySelectorAll('button').forEach(b => b.onclick = () => { if (b.dataset.c !== ['type', 'age', 'growth'][tm.mode]) setColor(b.dataset.c); });
  syncColorButtons();
  // inline actions on duplicate rows
  $('files').addEventListener('click', e => {
    const b = e.target.closest('.row-acts button'); if (!b) return;
    e.stopPropagation();
    const row = fileGrid.rows.find(r => r.id === +b.dataset.id); if (!row) return;
    if (b.dataset.act === 'reveal') post('reveal', { id: row.id }).catch(err => toast(err.message, 'err'));
    else deleteItems([row], false);
  });
  $('metric').querySelectorAll('button').forEach(b => b.onclick = async () => {
    const bySize = b.dataset.m === 'size';
    if (bySize === S.bySize || !S.summary) return;
    await post('metric', { bySize });
    S.bySize = bySize;
    $('metric').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    S.kids.clear();
    await refreshTree();
    await Promise.all([setRoot(S.root, false), drivebar()]);
  });
  $('search').addEventListener('input', e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      S.files.q = e.target.value.trim(); S.files.limit = 1000;
      if (S.files.q) S.files.dupes = false;
      if (S.files.q && S.tab !== 'files') switchTab('files'); else if (S.tab === 'files') loadFiles();
    }, 220);
  });
  $('search').addEventListener('keydown', e => { if (e.key === 'Escape') { e.target.value = ''; S.files.q = ''; if (S.tab === 'files') loadFiles(); e.target.blur(); } });
  addEventListener('keydown', e => {
    if (!$('dialogBack').hidden) return;
    const typing = e.target.matches('input, select, textarea');
    if (e.key === 'F5') { e.preventDefault(); $('btnRescan').click(); }
    else if (e.ctrlKey && e.key.toLowerCase() === 'o') { e.preventDefault(); pickFolder(); }
    else if (e.ctrlKey && e.key.toLowerCase() === 'f') { e.preventDefault(); $('search').focus(); $('search').select(); }
    else if (e.altKey && e.key === 'ArrowLeft') { e.preventDefault(); $('btnBack').click(); }
    else if (e.altKey && e.key === 'ArrowUp') { e.preventDefault(); up(); }
    else if (e.key === 'Backspace' && !typing) { e.preventDefault(); up(); }
    else if (e.ctrlKey && (e.key === 'r' || e.key === 'p' || e.key === 's')) e.preventDefault();
  });
  addEventListener('contextmenu', e => { if (!e.target.closest('input')) e.preventDefault(); });
  // keep the backend alive while the window is open
  setInterval(() => get('ping').catch(() => { }), 5000);
}

async function up() {
  if (S.root === 0) return;
  const r = await get('node', { id: S.root }).catch(() => null);
  if (r && r.node.parent >= 0) navigate(r.node.parent);
}

async function exportCsv() {
  if (!S.summary) return;
  const res = await dialog({
    title: 'Export to CSV',
    body: `<p>Save a spreadsheet of <b>${esc(S.nodes.get(S.root)?.n || '')}</b> with path, size, size on disk, counts and dates.</p>
      <label class="check"><input type="checkbox" id="exFiles"> Files only (no folder rows)</label>`,
    buttons: [{ label: 'Choose file…', primary: true, value: 'go' }, { label: 'Cancel' }],
    collect: d => ({ files: d.querySelector('#exFiles').checked }),
  });
  if (res.value !== 'go') return;
  try {
    $('stLeft').textContent = 'Exporting…';
    const r = await get('export', { id: S.root, files: res.data.files ? 1 : 0 });
    if (!r.cancelled) toast(`Exported ${num(r.rows)} rows to ${r.path}`, 'ok', 6000);
  } catch (e) { toast(e.message, 'err'); }
  $('stLeft').textContent = 'Ready';
}

function moreMenu(anchor) {
  const t = store.get('theme', 'system');
  showMenu(0, 0, [
    { head: 'Theme' },
    { icon: t === 'system' ? '&#xE73E;' : '', label: 'Use Windows setting', action: () => applyTheme('system') },
    { icon: t === 'light' ? '&#xE73E;' : '', label: 'Light', action: () => applyTheme('light') },
    { icon: t === 'dark' ? '&#xE73E;' : '', label: 'Dark', action: () => applyTheme('dark') },
    '-',
    { icon: '&#xE80F;', label: 'Start page (drives)', action: showHome },
    { icon: '&#xE896;', label: 'Export to CSV…', action: exportCsv, disabled: !S.summary },
    { icon: '&#xE8E5;', label: 'Open saved scan…', action: openScan },
    { icon: '&#xE74E;', label: 'Save this scan…', action: saveScan, disabled: !S.summary },
    { icon: '&#xE74D;', label: 'Clear scan history…', action: clearHistory },
    '-',
    { icon: '&#xE946;', label: 'About Tatami', action: about },
  ], anchor);
}

async function clearHistory() {
  const res = await dialog({
    title: 'Clear scan history?',
    body: `<p>Tatami keeps the last few scans of each drive or folder (for at most 90 days) to show what grew since.
      They list file and folder names and stay on this PC in your profile.</p><p class="muted">Clearing them only affects the "changed since last scan" view.</p>`,
    buttons: [{ label: 'Clear history', danger: true, value: 'yes' }, { label: 'Cancel', focus: true }],
  });
  if (res !== 'yes') return;
  try { const r = await post('history-clear'); toast(`Scan history cleared (${r.deleted} snapshot${r.deleted === 1 ? '' : 's'})`, 'ok'); }
  catch (e) { toast(e.message, 'err'); }
}

function about() {
  dialog({
    title: 'Tatami ' + VERSION,
    body: `<div style="display:flex;gap:16px;align-items:center"><span class="logo big">${logoSVG()}</span>
      <div><p><b>See what fills your disk.</b> A free disk space analyser for Windows.</p>
      <p class="muted">© 2026 Alexander Gubric · MIT License<br>Made with Claude.</p></div></div>
      <p class="muted" style="margin-top:12px">Keys: F5 rescan · Ctrl+O scan folder · Ctrl+F find · Enter zoom/open · Backspace up · Alt+← back · Del recycle · Shift+Del delete · Ctrl+C copy path</p>`,
    buttons: [{ label: 'Close', primary: true }],
  });
}

// ======================================================================= admin scans, saved scans
function syncAdmin() {
  const box = $('homeAdmin');
  if (S.sys.admin) { box.innerHTML = '<i class="ic">&#xE7EF;</i> Running as administrator — every folder is included.'; return; }
  const on = !!store.get('admin', false);
  box.innerHTML = `<label class="toggle" title="Reads folders your account can't open (WindowsApps, System Volume Information…). Windows asks for permission each scan.">
    <input type="checkbox" id="adminToggle" ${on ? 'checked' : ''}><span class="sw"></span>Include protected folders <span class="muted">(asks for administrator)</span></label>`;
  $('adminToggle').onchange = e => store.set('admin', e.target.checked);
}

async function openScan() {
  try {
    const r = await post('load');
    if (r.cancelled) return;
    $('home').hidden = true;
    await loaded();
  } catch (e) { toast(e.message, 'err'); }
}

async function saveScan() {
  try {
    const r = await post('save');
    if (!r.cancelled) toast('Saved to ' + r.path, 'ok', 5000);
  } catch (e) { toast(e.message, 'err'); }
}
