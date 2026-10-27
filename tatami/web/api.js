// Talking to Tatami.exe and formatting numbers.
const TOKEN = document.querySelector('meta[name="tatami-token"]').content;
export const VERSION = document.querySelector('meta[name="tatami-version"]').content;

export class ApiError extends Error {
  constructor(msg, status) { super(msg); this.status = status; }
}

async function call(url, opts = {}) {
  opts.headers = Object.assign({ 'X-Tatami': TOKEN }, opts.headers || {});
  let r;
  try { r = await fetch(url, opts); }
  catch (e) { throw new ApiError('Tatami stopped responding. Close this window and start Tatami again.', 0); }
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).error || msg; } catch { }
    throw new ApiError(msg, r.status);
  }
  return r;
}

export async function get(path, params) {
  const q = params ? '?' + new URLSearchParams(params) : '';
  return (await call('/api/' + path + q)).json();
}

export async function getBin(path, params) {
  const q = params ? '?' + new URLSearchParams(params) : '';
  return (await call('/api/' + path + q)).arrayBuffer();
}

export async function post(path, body) {
  return (await call('/api/' + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {})
  })).json();
}

// ---------- formatting (uses the Windows locale of the window, e.g. decimal comma) ----------
const nf1 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
const pf = new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1, minimumFractionDigits: 1 });
const df = new Intl.DateTimeFormat(undefined, { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });

export function bytes(b) {
  if (b == null) return '';
  const u = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let v = b, k = 0;
  while (Math.abs(v) >= 1024 && k < u.length - 1) { v /= 1024; k++; }
  if (k === 0) return nf0.format(b) + ' B';
  return (v >= 100 ? nf0.format(v) : nf1.format(v)) + ' ' + u[k];
}
export const num = n => nf0.format(n || 0);
export const pct = f => pf.format(isFinite(f) ? f : 0);
export const date = ms => ms > 0 ? df.format(new Date(ms)) : '';
export function ago(ms) {
  if (!ms) return '';
  const d = (Date.now() - ms) / 86400000;
  if (d < 1) return 'today';
  if (d < 2) return 'yesterday';
  if (d < 60) return Math.floor(d) + ' days ago';
  if (d < 730) return Math.floor(d / 30.4) + ' months ago';
  return Math.floor(d / 365.25) + ' years ago';
}
export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// node flags (Tree.cs)
export const F = { DIR: 1, DENIED: 2, HARDLINK: 4, LINK: 8, DELETED: 16, CLOUD: 32 };
