// Virtualised list/tree grid in the style of Windows 11 Explorer's details view.
import { store } from './ui.js';

export class Grid {
  /**
   * cols: [{key, label, w (px), min, num, sort, html(row) }]
   * opts: {name, rowH, onActivate(row), onSelect(rows), onContext(row, x, y), onToggle(row), onKey(e), sortKey, sortDir, onSort(key, dir)}
   */
  constructor(el, cols, opts) {
    this.el = el; this.cols = cols; this.o = opts;
    this.rowH = opts.rowH || 30;
    this.rows = [];
    this.sel = new Set();
    this.cur = -1; this.anchor = -1;
    this.sortKey = opts.sortKey || 'size'; this.sortDir = opts.sortDir || 'desc';
    const saved = store.get('cols.' + opts.name, null);
    if (saved) for (const c of cols) if (saved[c.key]) c.w = saved[c.key];
    el.tabIndex = 0;
    el.innerHTML = '<div class="g-head"></div><div class="g-scroll"><div class="g-canvas"></div></div>';
    this.head = el.querySelector('.g-head');
    this.scroll = el.querySelector('.g-scroll');
    this.canvas = el.querySelector('.g-canvas');
    this.pool = [];
    this.renderHead();
    this.scroll.addEventListener('scroll', () => this.render());
    new ResizeObserver(() => this.render()).observe(this.scroll);
    el.addEventListener('keydown', e => this.key(e));
    this.canvas.addEventListener('mousedown', e => this.mouse(e));
    this.canvas.addEventListener('dblclick', e => {
      const i = this.indexAt(e); if (i < 0) return;
      if (e.target.classList.contains('tw')) return;
      this.o.onActivate && this.o.onActivate(this.rows[i]);
    });
    this.canvas.addEventListener('contextmenu', e => {
      e.preventDefault();
      const i = this.indexAt(e); if (i < 0) return;
      if (!this.sel.has(this.rows[i].id)) this.select(i, false, false);
      this.o.onContext && this.o.onContext(this.rows[i], e.clientX, e.clientY);
    });
  }

  template() { return this.cols.map(c => c.flex ? `minmax(${c.min || 120}px, 1fr)` : c.w + 'px').join(' '); }

  renderHead() {
    this.head.style.gridTemplateColumns = this.template();
    this.head.innerHTML = this.cols.map(c => {
      const s = this.sortKey === c.sort;
      const arrow = s ? `<i class="ic">${this.sortDir === 'asc' ? '&#xE70E;' : '&#xE70D;'}</i>` : '';
      return `<div class="${c.num ? 'num' : ''} ${s ? 'sorted' : ''}" data-k="${c.key}">${c.num ? arrow : ''}${c.label}${c.num ? '' : arrow}${c.flex ? '' : '<span class="rz"></span>'}</div>`;
    }).join('');
    this.head.querySelectorAll('[data-k]').forEach(h => {
      const col = this.cols.find(c => c.key === h.dataset.k);
      h.onclick = e => {
        if (e.target.classList.contains('rz') || !col.sort || !this.o.onSort) return;
        if (this.sortKey === col.sort) this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
        else { this.sortKey = col.sort; this.sortDir = col.sort === 'name' || col.sort === 'type' || col.sort === 'path' ? 'asc' : 'desc'; }
        this.renderHead();
        this.o.onSort(this.sortKey, this.sortDir);
      };
      const rz = h.querySelector('.rz');
      if (rz) rz.onpointerdown = e => {
        e.preventDefault(); e.stopPropagation();
        rz.setPointerCapture(e.pointerId);
        const x0 = e.clientX, w0 = col.w;
        rz.onpointermove = ev => { col.w = Math.max(col.min || 50, w0 + ev.clientX - x0); this.layout(); };
        rz.onpointerup = () => {
          rz.onpointermove = null;
          const s = {}; for (const c of this.cols) if (!c.flex) s[c.key] = c.w;
          store.set('cols.' + this.o.name, s);
        };
      };
    });
  }

  layout() {
    const t = this.template();
    this.head.style.gridTemplateColumns = t;
    for (const r of this.pool) r.style.gridTemplateColumns = t;
    this.render(true);
  }

  setRows(rows, keepScroll = true) {
    this.rows = rows;
    if (!keepScroll) this.scroll.scrollTop = 0;
    const ids = new Set(rows.map(r => r.id));
    for (const id of [...this.sel]) if (!ids.has(id)) this.sel.delete(id);
    if (this.cur >= rows.length) this.cur = rows.length - 1;
    this.render(true);
  }

  render(force) {
    const n = this.rows.length, h = this.rowH;
    this.canvas.style.height = (n * h + (this.footer ? h : 0)) + 'px';
    const top = this.scroll.scrollTop, vh = this.scroll.clientHeight;
    const a = Math.max(0, Math.floor(top / h) - 4), b = Math.min(n, Math.ceil((top + vh) / h) + 4);
    if (!force && a === this.a && b === this.b) return;
    this.a = a; this.b = b;
    const need = b - a, t = this.template();
    while (this.pool.length < need) {
      const d = document.createElement('div');
      d.className = 'g-row'; d.style.gridTemplateColumns = t;
      this.canvas.appendChild(d); this.pool.push(d);
    }
    for (let k = 0; k < this.pool.length; k++) {
      const d = this.pool[k];
      if (k >= need) { d.style.display = 'none'; continue; }
      const i = a + k, row = this.rows[i];
      d.style.display = '';
      d.style.top = (i * h) + 'px';
      d.dataset.i = i;
      const cls = 'g-row' + (this.sel.has(row.id) ? ' sel' : '') + (i === this.cur ? ' cur' : '') + (row.dim ? ' dim' : '') + (row.cls ? ' ' + row.cls : '');
      if (d.className !== cls) d.className = cls;
      const html = this.cols.map(c => `<div class="${c.num ? 'num' : ''} ${c.cls || ''}">${c.html(row)}</div>`).join('');
      if (d._html !== html) { d.innerHTML = html; d._html = html; }
    }
    if (this.footer) {
      if (!this.footEl) { this.footEl = document.createElement('div'); this.footEl.className = 'g-more'; this.canvas.appendChild(this.footEl); }
      this.footEl.style.top = (n * h) + 'px'; this.footEl.innerHTML = this.footer; this.footEl.hidden = false;
    } else if (this.footEl) this.footEl.hidden = true;
    if (!n && this.empty) {
      if (!this.emptyEl) { this.emptyEl = document.createElement('div'); this.emptyEl.className = 'g-empty'; this.canvas.appendChild(this.emptyEl); }
      this.emptyEl.innerHTML = this.empty; this.emptyEl.hidden = false;
    } else if (this.emptyEl) this.emptyEl.hidden = true;
  }

  indexAt(e) {
    const r = e.target.closest('.g-row');
    return r ? +r.dataset.i : -1;
  }

  mouse(e) {
    if (e.button !== 0) return;
    const i = this.indexAt(e);
    if (i < 0) return;
    if (e.target.classList.contains('tw')) { this.cur = i; this.o.onToggle && this.o.onToggle(this.rows[i]); return; }
    this.select(i, e.ctrlKey, e.shiftKey);
  }

  select(i, ctrl, shift) {
    if (i < 0 || i >= this.rows.length) return;
    const id = this.rows[i].id;
    if (shift && this.anchor >= 0) {
      if (!ctrl) this.sel.clear();
      const [a, b] = this.anchor < i ? [this.anchor, i] : [i, this.anchor];
      for (let k = a; k <= b; k++) this.sel.add(this.rows[k].id);
    } else if (ctrl) {
      if (this.sel.has(id)) this.sel.delete(id); else this.sel.add(id);
      this.anchor = i;
    } else {
      this.sel.clear(); this.sel.add(id); this.anchor = i;
    }
    this.cur = i;
    this.ensureVisible(i);
    this.render(true);
    this.o.onSelect && this.o.onSelect(this.selected(), this.rows[i]);
  }

  selectId(id, focus = true) {
    const i = this.rows.findIndex(r => r.id === id);
    if (i >= 0) { this.select(i, false, false); if (focus) this.el.focus({ preventScroll: true }); }
    return i;
  }

  selected() { return this.rows.filter(r => this.sel.has(r.id)); }

  ensureVisible(i) {
    const h = this.rowH, top = this.scroll.scrollTop, vh = this.scroll.clientHeight;
    if (i * h < top) this.scroll.scrollTop = i * h;
    else if ((i + 1) * h > top + vh) this.scroll.scrollTop = (i + 1) * h - vh;
  }

  key(e) {
    if (this.o.onKey && this.o.onKey(e, this.rows[this.cur])) return;
    const page = Math.max(1, Math.floor(this.scroll.clientHeight / this.rowH) - 1);
    let i = this.cur;
    switch (e.key) {
      case 'ArrowDown': i++; break;
      case 'ArrowUp': i--; break;
      case 'PageDown': i += page; break;
      case 'PageUp': i -= page; break;
      case 'Home': i = 0; break;
      case 'End': i = this.rows.length - 1; break;
      case 'Enter': if (this.cur >= 0) this.o.onActivate && this.o.onActivate(this.rows[this.cur]); e.preventDefault(); return;
      case 'a': if (e.ctrlKey) { this.rows.forEach(r => this.sel.add(r.id)); this.render(true); this.o.onSelect && this.o.onSelect(this.selected(), this.rows[this.cur]); e.preventDefault(); } return;
      default: return;
    }
    e.preventDefault();
    this.select(Math.max(0, Math.min(this.rows.length - 1, i)), false, e.shiftKey);
  }
}
