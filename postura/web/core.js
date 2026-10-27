// Shared state, helpers and navigation for the pages.
import { get, post } from './api.js';
export { get, post };
export { EDITION, ASSISTANT } from './logo.js';

export const S = { state: null };
const listeners = new Set();

/** Subscribe to state refreshes; returns an unsubscribe function. */
export function onState(fn) { listeners.add(fn); if (S.state) fn(S.state); return () => listeners.delete(fn); }

export async function refresh() {
  try {
    S.state = await get('state');
    S.lastFetch = Date.now();
    listeners.forEach(fn => { try { fn(S.state); } catch (e) { console.error(e); } });
    if (S.state.goto) location.hash = S.state.goto;
  } catch (e) { /* tray app restarting */ }
  return S.state;
}

/** Seconds until the next eye break, counting down locally between polls. */
export function liveNextEye() {
  const st = S.state;
  if (!st) return 0;
  if (st.paused || st.away || !st.settings.eyeEnabled || st.breakOpen) return st.nextEye;
  return Math.max(0, st.nextEye - Math.floor((Date.now() - S.lastFetch) / 1000));
}

export async function setSettings(patch) {
  S.state = await post('settings', patch);
  S.lastFetch = Date.now();
  listeners.forEach(fn => fn(S.state));
  applyLook();
}

export async function setUi(patch) {
  if (S.state) Object.assign(S.state.ui, patch);
  await post('ui', patch).catch(e => toast(e.message));
}

export function ui(key, def) {
  const v = S.state && S.state.ui ? S.state.ui[key] : undefined;
  return v === undefined ? def : v;
}

export function applyLook() {
  const s = S.state && S.state.settings;
  if (!s) return;
  const root = document.documentElement;
  if (s.theme === 'system') delete root.dataset.theme; else root.dataset.theme = s.theme;
  root.classList.toggle('reduce', s.motion === 'reduced');
}

export const reduced = () => document.documentElement.classList.contains('reduce') || matchMedia('(prefers-reduced-motion: reduce)').matches;

export function go(page) { location.hash = page; }

export function toast(msg) {
  document.querySelectorAll('.ptoast').forEach(t => t.remove());
  const t = document.createElement('div');
  t.className = 'ptoast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2600);
}

export const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export function clock(secs) {
  secs = Math.max(0, Math.round(secs));
  const m = Math.floor(secs / 60), s = secs % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function duration(secs) {
  const m = Math.round(secs / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

export function el(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

/** Ease a set of numeric values towards targets; calls draw(current) each frame. */
export function tween(cur, target, draw, ms = 650) {
  if (reduced()) { Object.assign(cur, target); draw(cur); return; }
  const from = { ...cur }, t0 = performance.now();
  const ease = t => 1 - Math.pow(1 - t, 3);
  if (cur._raf) cancelAnimationFrame(cur._raf);
  const step = now => {
    const k = Math.min(1, (now - t0) / ms), e = ease(k);
    for (const key in target) cur[key] = from[key] + (target[key] - from[key]) * e;
    draw(cur);
    if (k < 1) cur._raf = requestAnimationFrame(step); else cur._raf = 0;
  };
  cur._raf = requestAnimationFrame(step);
}

/** Wire a range input so its filled track follows the value. */
export function paintRange(input) {
  const f = () => input.style.setProperty('--p', ((input.value - input.min) / (input.max - input.min) * 100) + '%');
  input.addEventListener('input', f);
  f();
}

export function toggleHTML(id, checked) {
  return `<label class="toggle"><input type="checkbox" id="${id}" ${checked ? 'checked' : ''}><span class="sw"></span></label>`;
}

export function segHTML(id, options, value) {
  return `<div class="seg" id="${id}">${options.map(([v, l]) => `<button data-v="${v}" class="${String(v) === String(value) ? 'on' : ''}">${l}</button>`).join('')}</div>`;
}

export function wireSeg(root, id, onPick) {
  const seg = root.querySelector('#' + id);
  seg.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    seg.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    onPick(b.dataset.v);
  });
  return seg;
}

export function ringSVG(frac, { size = 150, stroke = 10, color = 'var(--accent)', track = 'var(--line-2)' } = {}) {
  const r = 50 - stroke / 2 - 1, c = 2 * Math.PI * r;
  return `<svg viewBox="0 0 100 100" width="${size}" height="${size}" style="transform:rotate(-90deg)">
    <circle cx="50" cy="50" r="${r}" fill="none" stroke="${track}" stroke-width="${stroke}"/>
    <circle class="ring-fg" cx="50" cy="50" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round"
      stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - frac)}" style="transition:stroke-dashoffset .8s var(--ease)"/>
  </svg>`;
}

export function setRing(svg, frac) {
  const c = svg.querySelector('.ring-fg');
  if (!c) return;
  const len = parseFloat(c.getAttribute('stroke-dasharray'));
  c.setAttribute('stroke-dashoffset', len * (1 - Math.max(0, Math.min(1, frac))));
}
