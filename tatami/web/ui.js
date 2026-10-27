// Fluent-style building blocks: context menus, dialogs, toasts, splitters.
import { esc } from './api.js';

const $ = id => document.getElementById(id);

// ---------- context menu ----------
let menuClose = null;
/**
 * items: [{icon, label, key, action, danger, disabled}] | '-' | {head: 'text'} | {html, action}
 */
export function showMenu(x, y, items, anchor) {
  hideMenu();
  const m = $('menu');
  m.innerHTML = '';
  const actionable = [];
  for (const it of items) {
    if (!it) continue;
    if (it === '-') { m.insertAdjacentHTML('beforeend', '<div class="mi-sep"></div>'); continue; }
    if (it.head) { m.insertAdjacentHTML('beforeend', `<div class="mi-head">${esc(it.head)}</div>`); continue; }
    const d = document.createElement('div');
    d.className = 'mi' + (it.danger ? ' danger' : '') + (it.disabled ? ' disabled' : '') + (it.cls ? ' ' + it.cls : '');
    d.innerHTML = it.html ?? `<i class="ic">${it.icon || ''}</i><span>${esc(it.label)}</span>${it.key ? `<span class="key">${esc(it.key)}</span>` : ''}`;
    d.onclick = e => { e.stopPropagation(); hideMenu(); it.action && it.action(); };
    m.appendChild(d);
    actionable.push(d);
  }
  m.hidden = false;
  const r = m.getBoundingClientRect();
  if (anchor) { const a = anchor.getBoundingClientRect(); x = a.left; y = a.bottom + 4; }
  m.style.left = Math.max(4, Math.min(x, innerWidth - r.width - 4)) + 'px';
  m.style.top = Math.max(4, (y + r.height > innerHeight - 4 ? Math.max(4, y - r.height) : y)) + 'px';
  let kb = -1;
  const onKey = e => {
    if (e.key === 'Escape') { hideMenu(); e.preventDefault(); return; }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!actionable.length) return;
      if (kb >= 0) actionable[kb].classList.remove('kb');
      kb = (kb + (e.key === 'ArrowDown' ? 1 : -1) + actionable.length) % actionable.length;
      actionable[kb].classList.add('kb');
      e.preventDefault(); e.stopPropagation();
    } else if (e.key === 'Enter' && kb >= 0) { actionable[kb].click(); e.preventDefault(); e.stopPropagation(); }
  };
  const onDown = e => { if (!m.contains(e.target)) hideMenu(); };
  setTimeout(() => { addEventListener('mousedown', onDown, true); addEventListener('keydown', onKey, true); addEventListener('blur', hideMenu); }, 0);
  menuClose = () => { removeEventListener('mousedown', onDown, true); removeEventListener('keydown', onKey, true); removeEventListener('blur', hideMenu); };
}
export function hideMenu() {
  $('menu').hidden = true;
  if (menuClose) { menuClose(); menuClose = null; }
}

// ---------- dialog ----------
/**
 * html body + buttons [{label, primary, danger, value}] → Promise of the clicked value (null = cancelled).
 * onOpen(dialogEl) can wire inputs; collect(dialogEl) returns extra data merged as {value, data}.
 */
export function dialog({ title, body, buttons, onOpen, collect }) {
  return new Promise(resolve => {
    const back = $('dialogBack'), d = $('dialog');
    d.innerHTML = `<div class="d-body"><h3>${esc(title)}</h3>${body}</div><div class="d-foot"></div>`;
    const foot = d.querySelector('.d-foot');
    let first = null;
    const done = v => {
      back.hidden = true;
      removeEventListener('keydown', onKey, true);
      resolve(collect ? { value: v, data: v == null ? null : collect(d) } : v);
    };
    for (const b of buttons) {
      const el = document.createElement('button');
      el.className = 'btn' + (b.primary ? ' primary' : '') + (b.danger ? ' danger' : '');
      el.textContent = b.label;
      el.onclick = () => done(b.value ?? null);
      foot.appendChild(el);
      if (b.focus) first = el;   // e.g. Cancel on destructive questions, so Enter can't delete by accident
      else if ((b.primary || b.danger) && !buttons.some(x => x.focus)) first = first || el;
    }
    const onKey = e => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done(null); }
      e.stopPropagation();
    };
    addEventListener('keydown', onKey, true);
    back.hidden = false;
    back.onmousedown = e => { if (e.target === back) done(null); };
    onOpen && onOpen(d);
    (first || foot.lastChild).focus();
  });
}

// ---------- toasts ----------
export function toast(msg, kind = 'info', ms = 4200) {
  const icon = kind === 'err' ? '&#xE783;' : kind === 'ok' ? '&#xE73E;' : '&#xE946;';
  const t = document.createElement('div');
  t.className = 'toast ' + kind;
  t.innerHTML = `<i class="ic">${icon}</i><div>${esc(msg)}</div>`;
  $('toasts').appendChild(t);
  setTimeout(() => { t.style.transition = 'opacity .3s'; t.style.opacity = 0; setTimeout(() => t.remove(), 300); }, ms);
}

// ---------- splitters ----------
export function splitter(handle, { axis, get, set, min, max, done }) {
  handle.addEventListener('pointerdown', e => {
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);
    const start = axis === 'y' ? e.clientY : e.clientX, base = get();
    const move = ev => {
      const d = (axis === 'y' ? ev.clientY : ev.clientX) - start;
      set(Math.max(min(), Math.min(max(), base + (axis === 'x-rev' ? -d : d))));
    };
    const up = () => { handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', up); done && done(); };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', up);
  });
}

// ---------- settings (per-viewer conveniences) ----------
export const store = {
  get(k, d) { try { const v = localStorage.getItem('tatami.' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('tatami.' + k, JSON.stringify(v)); } catch { } },
};
