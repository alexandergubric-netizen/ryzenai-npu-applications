// Cushion treemap: the server lays out rectangles (Treemap.cs), this file shades them per pixel and handles
// hover, selection and type highlighting. Record layout (40 bytes): f32 x,y,w,h | i32 id | u16 ext | u8 kind |
// u8 depth | f32 s1x,s2x,s1y,s2y.
import { getBin, post } from './api.js';
import { extRgb, extCat, ageRgb, growthRgb } from './colors.js';

const K_FILE = 0, K_FRAME = 1, K_REST = 2, K_HEADER = 3;
const REC = 10; // 32-bit words per record

export class TreemapView {
  constructor({ stage, canvas, over, onHover, onSelect, onZoom, onContext }) {
    this.stage = stage; this.cv = canvas; this.ov = over;
    this.ctx = canvas.getContext('2d'); this.octx = over.getContext('2d');
    this.cb = { onHover, onSelect, onZoom, onContext };
    this.root = null; this.n = 0; this.hover = -1; this.selRec = -1; this.filter = null; this.gen = 0;
    this.color = 'type';      // requested colour mode; this.mode = what the server could deliver (0 type, 1 age, 2 growth)
    this.mode = 0;
    this.labels = new Map();
    new ResizeObserver(() => { clearTimeout(this.rt); this.rt = setTimeout(() => this.reload(), 120); }).observe(stage);
    over.addEventListener('mousemove', e => this.move(e));
    over.addEventListener('mouseleave', () => { this.setHover(-1); this.cb.onHover(null); });
    over.addEventListener('click', e => { const r = this.recAt(e); if (r >= 0) this.cb.onSelect(this.id(r), this.chainIds(r)); });
    over.addEventListener('dblclick', e => {
      const r = this.recAt(e); if (r < 0) return;
      // drill down one level: zoom into the folder under the cursor that sits directly in the current view
      for (let p = r; p >= 0; p = this.par[p]) {
        if (this.depth(p) !== 1) continue;
        if (this.kind(p) !== K_FILE && !this.restSize.has(p)) this.cb.onZoom(this.id(p));
        return;
      }
    });
    over.addEventListener('contextmenu', e => {
      e.preventDefault();
      const r = this.recAt(e); if (r < 0) return;
      this.cb.onSelect(this.id(r), this.chainIds(r));
      this.cb.onContext(this.id(r), e.clientX, e.clientY);
    });
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => this.paint());
  }

  // ---- record accessors
  id(r) { return this.i32[r * REC + 4]; }
  ext(r) { return this.u16[(r * REC + 5) * 2]; }
  kind(r) { return this.u8[(r * REC + 5) * 4 + 2]; }
  depth(r) { return this.u8[(r * REC + 5) * 4 + 3]; }

  async show(rootId) { this.root = rootId; await this.reload(); }

  /** 'type' | 'age' | 'growth' — age and growth need per-record keys from the server, so this reloads. */
  async setColor(c) { this.color = c; await this.reload(); }

  /** Colour key of a record: {mode, a, b} (age: a = days; growth: a = relative change, b = bytes). */
  keyInfo(r) { return this.mode ? { mode: this.mode, a: this.keyA[r], b: this.keyB ? this.keyB[r] : 0 } : null; }

  rgb(r) {
    if (this.mode === 1) return ageRgb(this.keyA[r]);
    if (this.mode === 2) return growthRgb(this.keyA[r]);
    return extRgb(this.ext(r));
  }

  async reload() {
    const w = this.stage.clientWidth, h = this.stage.clientHeight;
    if (w < 4 || h < 4 || this.root == null) return;
    const dpr = devicePixelRatio || 1;
    const W = Math.round(w * dpr), H = Math.round(h * dpr);
    const gen = ++this.gen;
    this.cb.onHover(null);
    this.stage.classList.add('tm-busy');
    let buf;
    try { buf = await getBin('treemap', { id: this.root, w: W, h: H, dpr, color: this.color }); }
    catch (e) { this.stage.classList.remove('tm-busy'); if (gen === this.gen) this.clear(); return; }
    if (gen !== this.gen) return;
    this.stage.classList.remove('tm-busy');
    this.W = W; this.H = H; this.dpr = dpr;
    this.buf = buf;
    const dv = new DataView(buf);
    const n = dv.getInt32(0, true);
    this.f32 = new Float32Array(buf, 4, n * REC); this.i32 = new Int32Array(buf, 4, n * REC);
    this.u16 = new Uint16Array(buf, 4, n * REC * 2); this.u8 = new Uint8Array(buf, 4, n * 40);
    this.n = n;
    this.restSize = new Map();
    let o = 4 + n * 40;
    const nr = dv.getInt32(o, true); o += 4;
    for (let k = 0; k < nr; k++, o += 12) this.restSize.set(dv.getInt32(o, true), dv.getFloat64(o + 4, true));
    // colour keys (Treemap.cs): mode, then float32[n] (age days | growth ratio) and for growth float32[n] bytes
    this.mode = o + 4 <= buf.byteLength ? dv.getInt32(o, true) : 0; o += 4;
    this.keyA = this.keyB = null;
    if (this.mode) { this.keyA = new Float32Array(buf, o, n); o += n * 4; }
    if (this.mode === 2) this.keyB = new Float32Array(buf, o, n);
    if (this.onMode) this.onMode(this.mode);
    // parent record of each record (records come in depth-first order)
    this.par = new Int32Array(this.n);
    this.byId = new Map();
    const stack = [];
    for (let r = 0; r < this.n; r++) {
      const d = this.depth(r), k = this.kind(r);
      while (stack.length && this.depth(stack[stack.length - 1]) >= d && !(k === K_REST && this.id(stack[stack.length - 1]) === this.id(r))) stack.pop();
      // a "small items" block belongs to the folder frame with the same id
      this.par[r] = stack.length ? stack[stack.length - 1] : -1;
      if (k === K_FRAME || k === K_HEADER) stack.push(r);
      const id = this.id(r);
      if (!this.byId.has(id)) this.byId.set(id, r);
    }
    this.cv.width = this.ov.width = W; this.cv.height = this.ov.height = H;
    this.hover = -1;
    const tp = performance.now();
    this.paint();
    if (window.TATAMI_DEBUG) console.log(`treemap ${n} recs, paint ${Math.round(performance.now() - tp)} ms`);
    this.fetchLabels(gen);
  }

  clear() {
    this.n = 0; this.ctx.clearRect(0, 0, this.cv.width, this.cv.height); this.octx.clearRect(0, 0, this.ov.width, this.ov.height);
  }

  setFilter(f) { this.filter = f; this.paint(); }   // f: {ext:Set} | {cat:number} | null

  passes(r) {
    const f = this.filter; if (!f) return true;
    const e = this.ext(r);
    if (f.ext) return f.ext.has(e);
    if (f.cat != null) return extCat(e) === f.cat;
    if (f.ids) { for (let p = r; p >= 0; p = this.par[p]) if (f.ids.has(this.id(p))) return true; return false; }
    return true;
  }

  paint() {
    if (!this.n) return;
    const W = this.W, H = this.H, f32 = this.f32;
    const img = this.ctx.createImageData(W, H);
    const px = new Uint32Array(img.data.buffer);
    this.hit = new Int32Array(W * H).fill(-1);
    const css = getComputedStyle(document.documentElement);
    const headRgb = parseColor(css.getPropertyValue('--tm-head')), bgRgb = parseColor(css.getPropertyValue('--tm-bg'));
    const bgPix = (255 << 24) | (bgRgb[2] << 16) | (bgRgb[1] << 8) | bgRgb[0];
    px.fill(bgPix);
    const headPix = (255 << 24) | (headRgb[2] << 16) | (headRgb[1] << 8) | headRgb[0];
    const dark = (headRgb[0] + headRgb[1] + headRgb[2]) < 300;
    // light from the top-left, slightly in front (van Wijk / WinDirStat)
    const Lx = -1, Ly = -1, Lz = 10, Ln = Math.hypot(Lx, Ly, Lz);
    const lx = Lx / Ln, ly = Ly / Ln, lz = Lz / Ln;
    const Ia = 0.32, Is = 0.78;
    const filter = this.filter;
    const pad = Math.max(1, Math.round(this.dpr));
    for (let r = 0; r < this.n; r++) {
      const b = r * REC, k = this.kind(r);
      if (k === K_FRAME) continue;
      const x0 = Math.round(f32[b]), y0 = Math.round(f32[b + 1]);
      const x1 = Math.min(W, Math.round(f32[b] + f32[b + 2])), y1 = Math.min(H, Math.round(f32[b + 1] + f32[b + 3]));
      if (x1 <= x0 || y1 <= y0) continue;
      if (k === K_HEADER) {
        for (let y = y0; y < y1; y++) { const o = y * W; px.fill(headPix, o + x0, o + x1); }
        // a hairline around the folder so neighbouring folders separate cleanly
        const edge = dark ? 0xff3a3a3a : 0xffcfcfcf;
        for (let x = x0; x < x1; x++) { px[y0 * W + x] = edge; px[(y1 - 1) * W + x] = edge; }
        for (let y = y0; y < y1; y++) { px[y * W + x0] = edge; px[y * W + x1 - 1] = edge; }
        for (let y = y0; y < y1; y++) this.hit.fill(r, y * W + x0, y * W + x1);
        continue;
      }
      let [cr, cg, cb] = this.rgb(r);
      if (filter && !this.passes(r)) {
        const g = (cr * .3 + cg * .59 + cb * .11);
        const m = dark ? .22 : .5;
        cr = cg = cb = dark ? g * m : g * m + 255 * (1 - m) * .8;
      }
      const s1x = f32[b + 6], s2x = f32[b + 7], s1y = f32[b + 8], s2y = f32[b + 9];
      for (let y = y0; y < y1; y++) {
        const ny = -(2 * s2y * (y + .5) + s1y), o = y * W;
        const nyl = ny * ly, ny2 = ny * ny + 1;
        for (let x = x0; x < x1; x++) {
          const nx = -(2 * s2x * (x + .5) + s1x);
          let c = (nx * lx + nyl + lz) / Math.sqrt(nx * nx + ny2);
          if (c < 0) c = 0;
          const i = Ia + Is * c;
          let R = cr * i, G = cg * i, B = cb * i;
          if (R > 255) R = 255; if (G > 255) G = 255; if (B > 255) B = 255;
          px[o + x] = (255 << 24) | (B << 16) | (G << 8) | R;
        }
        this.hit.fill(r, o + x0, o + x1);
      }
    }
    this.ctx.putImageData(img, 0, 0);
    this.drawLabels();
    this.drawOverlay();
  }

  async fetchLabels(gen) {
    const want = [];
    const d = this.dpr, hh = Math.round(17 * d);
    for (let r = 0; r < this.n; r++) {
      const b = r * REC, k = this.kind(r), w = this.f32[b + 2], h = this.f32[b + 3];
      if ((k === K_HEADER && w > 40 * d) || ((k === K_FILE || k === K_REST) && w > 70 * d && h > 22 * d)) want.push(this.id(r));
      if (want.length > 1500) break;
    }
    const missing = [...new Set(want)].filter(id => !this.labels.has(id));
    if (missing.length) {
      try {
        const res = await post('names', { ids: missing });
        for (const it of res) this.labels.set(it.id, it);
      } catch { return; }
    }
    if (gen === this.gen) this.drawLabels(true);
  }

  drawLabels(repaint) {
    if (repaint) { this.paint(); return; }
    const ctx = this.ctx, d = this.dpr, hh = Math.round(17 * d);
    const css = getComputedStyle(document.documentElement);
    const headText = css.getPropertyValue('--tm-head-text').trim() || '#000';
    const bySize = this.bySize !== false;
    ctx.save();
    ctx.textBaseline = 'middle';
    for (let r = 0; r < this.n; r++) {
      const b = r * REC, k = this.kind(r);
      const x = this.f32[b], y = this.f32[b + 1], w = this.f32[b + 2], h = this.f32[b + 3];
      const lab = this.labels.get(this.id(r));
      if (!lab) continue;
      if (k === K_HEADER && w > 40 * d) {
        ctx.font = `${600} ${Math.round(11.5 * d)}px "Segoe UI Variable Text","Segoe UI",sans-serif`;
        ctx.fillStyle = headText;
        clipText(ctx, lab.n + '   ' + fmtBytes(bySize ? lab.s : lab.a), x + 6 * d, y + hh / 2 + .5 * d, w - 10 * d);
      } else if ((k === K_FILE || k === K_REST) && w > 70 * d && h > 22 * d) {
        ctx.font = `${Math.round(11 * d)}px "Segoe UI Variable Text","Segoe UI",sans-serif`;
        ctx.fillStyle = 'rgba(255,255,255,.95)';
        ctx.shadowColor = 'rgba(0,0,0,.55)'; ctx.shadowBlur = 3 * d;
        const many = this.restSize.has(r);
        clipText(ctx, many ? 'Many small items' : lab.n, x + 5 * d, y + 10 * d, w - 10 * d);
        if (h > 36 * d) {
          ctx.fillStyle = 'rgba(255,255,255,.8)';
          clipText(ctx, fmtBytes(many ? this.restSize.get(r) : bySize ? lab.s : lab.a), x + 5 * d, y + 24 * d, w - 10 * d);
        }
        ctx.shadowBlur = 0;
      }
    }
    ctx.restore();
  }

  recAt(e) {
    if (!this.hit) return -1;
    const rc = this.ov.getBoundingClientRect();
    const x = Math.floor((e.clientX - rc.left) * this.W / rc.width), y = Math.floor((e.clientY - rc.top) * this.H / rc.height);
    if (x < 0 || y < 0 || x >= this.W || y >= this.H) return -1;
    return this.hit[y * this.W + x];
  }

  chainIds(r) { const c = []; for (let p = r; p >= 0; p = this.par[p]) c.push(this.id(p)); return c; }

  move(e) {
    const r = this.recAt(e);
    if (r !== this.hover) this.setHover(r);
    const rc = this.stage.getBoundingClientRect();
    this.cb.onHover(r < 0 ? null : { id: this.id(r), rec: r, rest: this.restSize.has(r) ? this.restSize.get(r) : null, ext: this.ext(r), x: e.clientX - rc.left, y: e.clientY - rc.top, w: rc.width, h: rc.height });
  }

  setHover(r) { this.hover = r; this.drawOverlay(); }

  /** Highlight a node; chain = its ids from itself up to the root (first one present in the map wins). */
  select(chain) {
    this.selRec = -1;
    if (!this.byId) return;
    if (chain) for (const id of chain) { const r = this.byId.get(id); if (r != null) { this.selRec = r; break; } }
    this.drawOverlay();
  }

  drawOverlay() {
    const c = this.octx, d = this.dpr || 1;
    c.clearRect(0, 0, this.ov.width, this.ov.height);
    if (!this.n) return;
    const rect = (r, color, lw, dash) => {
      const b = r * REC;
      c.setLineDash(dash || []);
      c.strokeStyle = color; c.lineWidth = lw;
      c.strokeRect(Math.round(this.f32[b]) + lw / 2, Math.round(this.f32[b + 1]) + lw / 2,
        Math.max(1, Math.round(this.f32[b + 2]) - lw), Math.max(1, Math.round(this.f32[b + 3]) - lw));
    };
    if (this.hover >= 0) {
      const p = this.par[this.hover];
      if (p >= 0 && this.kind(this.hover) !== K_HEADER) rect(p, 'rgba(255,255,255,.55)', 1 * d, [4 * d, 3 * d]);
      rect(this.hover, 'rgba(255,255,255,.95)', 1.5 * d);
    }
    if (this.selRec >= 0) {
      const acc = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
      rect(this.selRec, 'rgba(0,0,0,.6)', 4 * d);
      rect(this.selRec, acc || '#60cdff', 2.5 * d);
    }
  }
}

function clipText(ctx, s, x, y, max) {
  if (max < 12) return;
  if (ctx.measureText(s).width <= max) { ctx.fillText(s, x, y); return; }
  let lo = 0, hi = s.length;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (ctx.measureText(s.slice(0, m) + '…').width <= max) lo = m; else hi = m - 1; }
  if (lo > 0) ctx.fillText(s.slice(0, lo) + '…', x, y);
}

function parseColor(s) {
  s = s.trim();
  if (s.startsWith('#')) { const n = parseInt(s.slice(1, 7), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
  const m = s.match(/[\d.]+/g); return m ? m.slice(0, 3).map(Number) : [128, 128, 128];
}

function fmtBytes(b) {
  const u = ['B', 'KB', 'MB', 'GB', 'TB']; let v = b, k = 0;
  while (v >= 1024 && k < u.length - 1) { v /= 1024; k++; }
  return k === 0 ? b + ' B' : v.toLocaleString(undefined, { maximumFractionDigits: v >= 100 ? 0 : 1 }) + ' ' + u[k];
}
