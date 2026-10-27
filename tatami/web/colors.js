// Colours of file categories (index = ExtTable.Categories in Ext.cs) and the Tatami logo.
export const CATS = [
  { name: 'Other', c: '#8b939e' },
  { name: 'Video', c: '#e5484d' },
  { name: 'Audio', c: '#d6409f' },
  { name: 'Pictures', c: '#f76b15' },
  { name: 'Archives', c: '#f5b82e' },
  { name: 'Disk images', c: '#a8754f' },
  { name: 'Programs', c: '#3e63dd' },
  { name: 'Documents', c: '#30a46c' },
  { name: 'Code', c: '#12a594' },
  { name: 'Game data', c: '#8e4ec6' },
  { name: 'System & cache', c: '#0090ff' },
  { name: 'Folders', c: '#c9b27c' },
];
export const FOLDER_CAT = 11;

let extNames = [''], extCats = [0];
const cache = new Map();

export function setExts(names, cats) { extNames = names; extCats = cats; cache.clear(); }
export const extName = e => extNames[e] ?? '';
export const extCat = e => (e == null || e < 0 || e >= extCats.length) ? (e === 65535 ? FOLDER_CAT : 0) : extCats[e];

function hexRgb(h) { const n = parseInt(h.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
function rgbHsl([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
  let h = 0, s = 0;
  if (mx !== mn) {
    const d = mx - mn;
    s = l > .5 ? d / (2 - mx - mn) : d / (mx + mn);
    h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    h /= 6;
  }
  return [h, s, l];
}
function hslRgb([h, s, l]) {
  if (s === 0) return [l * 255, l * 255, l * 255];
  const q = l < .5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
  const f = t => { if (t < 0) t += 1; if (t > 1) t -= 1; return t < 1 / 6 ? p + (q - p) * 6 * t : t < 1 / 2 ? q : t < 2 / 3 ? p + (q - p) * (2 / 3 - t) * 6 : p; };
  return [f(h + 1 / 3) * 255, f(h) * 255, f(h - 1 / 3) * 255];
}
function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }

/** [r,g,b] for an extension index: the category colour, nudged per extension so types stay distinguishable. */
export function extRgb(e) {
  let v = cache.get(e);
  if (v) return v;
  const cat = extCat(e);
  const base = rgbHsl(hexRgb(CATS[cat].c));
  if (e > 0 && e !== 65535 && cat !== FOLDER_CAT) {
    const hs = hash(extName(e));
    base[0] = (base[0] + ((hs & 255) / 255 - .5) * 0.07 + 1) % 1;
    base[2] = Math.min(.78, Math.max(.3, base[2] + (((hs >> 8) & 255) / 255 - .5) * 0.22));
    base[1] = Math.min(1, Math.max(.35, base[1] + (((hs >> 16) & 255) / 255 - .5) * 0.2));
  }
  v = hslRgb(base).map(Math.round);
  cache.set(e, v);
  return v;
}
export const extCss = e => { const [r, g, b] = extRgb(e); return `rgb(${r},${g},${b})`; };

// ---------- treemap colour modes ----------
const NONE = [139, 147, 158];
/** Age heat map: hot colours for files changed recently, cool for ones untouched for years (log scale). */
export const AGE_STOPS = [
  [0, '#e5484d', 'Today'], [7, '#f76b15', '1 week'], [30, '#f5b82e', '1 month'], [182, '#46a758', '6 months'],
  [365, '#12a594', '1 year'], [1095, '#3e63dd', '3 years'], [3650, '#6e56cf', '10 years'],
];
const ageStops = AGE_STOPS.map(([d, c]) => [Math.log1p(d), hexRgb(c)]);
const mix = (a, b, f) => [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
export function ageRgb(days) {
  if (!(days >= 0)) return days < 0 ? ageStops[0][1] : NONE;   // NaN: nothing dated; < 0: clock skew → newest
  const t = Math.log1p(days);
  for (let i = 1; i < ageStops.length; i++)
    if (t <= ageStops[i][0]) return mix(ageStops[i - 1][1], ageStops[i][1], (t - ageStops[i - 1][0]) / (ageStops[i][0] - ageStops[i - 1][0]));
  return ageStops[ageStops.length - 1][1];
}

/** Growth since the previous scan: rel = change / max(old, new) in -1…1, 2 = new, NaN = nothing to compare. */
export const GROWTH = { same: '#9aa1ab', grew1: '#f5b82e', grew2: '#e5484d', fresh: '#d6409f', shrank: '#0090ff' };
const G = Object.fromEntries(Object.entries(GROWTH).map(([k, v]) => [k, hexRgb(v)]));
export function growthRgb(rel) {
  if (rel !== rel) return NONE;
  if (rel > 1.5) return G.fresh;
  if (Math.abs(rel) < 0.005) return G.same;
  if (rel < 0) return mix(G.same, G.shrank, Math.min(1, Math.sqrt(-rel) * 1.2));
  const f = Math.min(1, Math.sqrt(rel));
  return f < .5 ? mix(G.same, G.grew1, f * 2) : mix(G.grew1, G.grew2, (f - .5) * 2);
}

/**
 * Logo: a 4½-mat tatami room seen from above — four mats pinwheel around a half mat, each mat a file-type
 * colour, bound with dark heri (cloth borders) on a straw floor.
 */
export function logoSVG(animate = false) {
  const mats = [
    // x, y, w, h, colour
    [4, 4, 74, 37, '#e5484d'],
    [82, 4, 37, 74, '#3e63dd'],
    [45, 82, 74, 37, '#30a46c'],
    [4, 45, 37, 74, '#f5b82e'],
    [45, 45, 33, 33, '#c9b27c'],
  ];
  const s = mats.map(([x, y, w, h, c], i) =>
    `<g class="mat" style="animation-delay:${animate ? i * 90 : 0}ms">
      <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="3" fill="${c}"/>
      <rect x="${x + 2.5}" y="${y + 2.5}" width="${w - 5}" height="${h - 5}" rx="1.5" fill="none" stroke="rgba(255,255,255,.28)" stroke-width="1"/>
      ${w > h
        ? `<path d="M${x + 6} ${y + h / 3}H${x + w - 6}M${x + 6} ${y + 2 * h / 3}H${x + w - 6}" stroke="rgba(0,0,0,.10)" stroke-width="1"/>`
        : `<path d="M${x + w / 3} ${y + 6}V${y + h - 6}M${x + 2 * w / 3} ${y + 6}V${y + h - 6}" stroke="rgba(0,0,0,.10)" stroke-width="1"/>`}
    </g>`).join('');
  return `<svg viewBox="0 0 123 123" xmlns="http://www.w3.org/2000/svg"><rect x="0" y="0" width="123" height="123" rx="14" fill="#2f4a3a"/>${s}</svg>`;
}
