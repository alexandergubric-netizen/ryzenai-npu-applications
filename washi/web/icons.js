/* Washi icon set: 24×24 line icons drawn for this app (stroke = currentColor). */
const ICONS = {
  open: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1"/><path d="M3 7v11a2 2 0 0 0 2 2h12.5a2 2 0 0 0 1.9-1.4L21.8 12a1.5 1.5 0 0 0-1.4-2H8.2a2 2 0 0 0-1.9 1.4L4 19"/>',
  save: '<path d="M5 3h11l4 4v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a1 1 0 0 1 1-2z"/><path d="M8 3v5h7V3"/><rect x="7" y="13" width="10" height="7" rx="1"/>',
  saveAs: '<path d="M14 21H6a2 2 0 0 1-2-2V5a1 1 0 0 1 1-2h11l4 4v4"/><path d="M8 3v5h7V3"/><path d="M19.5 14.5l1.9 1.9-5 5H14.5v-1.9z"/>',
  print: '<path d="M7 9V3h10v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M7 14h10v7H7z"/><circle cx="17.5" cy="12" r=".6" fill="currentColor"/>',
  undo: '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  redo: '<path d="M15 14l5-5-5-5"/><path d="M20 9H9a5 5 0 0 0 0 10h3"/>',
  select: '<path d="M5 3l14 7.5-6.2 1.7L10 18.5z"/><path d="M13 13l5 5"/>',
  textSelect: '<path d="M9 4h6M12 4v16M9 20h6"/><path d="M5 9v6M19 9v6" opacity=".5"/>',
  hand: '<path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V12"/><path d="M11 11.5V4a1.5 1.5 0 0 1 3 0v8"/><path d="M14 6a1.5 1.5 0 0 1 3 0v7"/><path d="M17 9a1.5 1.5 0 0 1 3 0v5a7 7 0 0 1-7 7h-1a7 7 0 0 1-5.6-2.8L3.3 14.6a1.6 1.6 0 0 1 2.5-2L8 15"/>',
  zoomIn: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4M8 11h6M11 8v6"/>',
  zoomOut: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4M8 11h6"/>',
  fitWidth: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 12h10M9 10l-2 2 2 2M15 10l2 2-2 2"/>',
  fitPage: '<rect x="6" y="3" width="12" height="18" rx="2"/><path d="M9 8l-1.5-1.5M15 8l1.5-1.5M9 16l-1.5 1.5M15 16l1.5 1.5"/>',
  highlight: '<path d="M15.5 4.5l4 4L11 17l-4.5 1-1-1 1-4.5z"/><path d="M13 7l4 4"/><path d="M4 21h16" stroke-width="3" opacity=".55"/>',
  underline: '<path d="M7 4v6a5 5 0 0 0 10 0V4"/><path d="M5 20h14"/>',
  strike: '<path d="M16 6.5A4 3.2 0 0 0 12 4c-2.5 0-4 1.3-4 3 0 1.3.9 2.2 2.6 2.8"/><path d="M8 17.5A4 3.2 0 0 0 12 20c2.5 0 4.2-1.3 4.2-3.2 0-.9-.3-1.6-.9-2.2"/><path d="M4 12h16"/>',
  squiggly: '<path d="M7 4v5a5 5 0 0 0 10 0V4"/><path d="M4 19c1.3-1.5 2.7-1.5 4 0s2.7 1.5 4 0 2.7-1.5 4 0 2.7 1.5 4 0"/>',
  area: '<rect x="4" y="5" width="16" height="14" rx="2" stroke-dasharray="3 2.5"/><path d="M8 10h8M8 14h5"/>',
  note: '<path d="M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-7l-5 4v-4H6a2 2 0 0 1-2-2z"/><path d="M8 8h8M8 12h5"/>',
  textbox: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 9h8M12 9v7"/>',
  rect: '<rect x="4" y="5" width="16" height="14" rx="1.5"/>',
  ellipse: '<ellipse cx="12" cy="12" rx="8.5" ry="6.5"/>',
  line: '<path d="M5 19L19 5"/>',
  arrow: '<path d="M5 19L19 5M10 5h9v9"/>',
  pen: '<path d="M4 20c3-1 4-4 6-4s2 3 4 3 3-4 6-7"/><path d="M16.5 3.5l3 3L12 14l-3.5.5.5-3.5z"/>',
  stamp: '<path d="M9.5 3.5h5l-.8 6.5h-3.4z"/><path d="M5 13a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v3H5z"/><path d="M5 20h14"/>',
  editText: '<path d="M4 7V5h11v2M9.5 5v14M7.5 19h4"/><path d="M19.5 11.5l1.9 1.9-5.5 5.5H14v-1.9z"/>',
  addText: '<path d="M5 6V4h12v2M11 4v16M8.5 20h5"/><path d="M19 15v6M16 18h6"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5L5 20"/>',
  whiteout: '<path d="M16 4l4.5 4.5-9.8 9.8H6.2L3.5 15.6z"/><path d="M10.5 9.5L15 14"/><path d="M13 20h8"/>',
  link: '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1"/>',
  redact: '<rect x="3" y="9" width="18" height="6" rx="1" fill="currentColor"/><path d="M5 5h9M5 19h12"/>',
  crop: '<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M2 6h14a2 2 0 0 1 2 2v14"/>',
  sign: '<path d="M3 17c2.5 0 3.5-7 6-7 1.8 0 .5 6 2.5 6 1.5 0 2-2.5 3.5-2.5S16.5 16 18 16h3"/><path d="M3 21h18"/>',
  field: '<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M7 10v4"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  checkbox: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 12l3 3 5-6"/>',
  dropdown: '<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M14.5 11l2 2 2-2"/>',
  rotateCw: '<path d="M20 12a8 8 0 1 1-2.4-5.7"/><path d="M20 4v5h-5"/>',
  rotateCcw: '<path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4v5h5"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6"/><path d="M5.5 7l1 12a2 2 0 0 0 2 2h7a2 2 0 0 0 2-2l1-12"/><path d="M9 7V4h6v3"/>',
  pagePlus: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M12 11v6M9 14h6"/>',
  filePlus: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M12 11v6M9 14h6"/>',
  insertFile: '<path d="M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h7"/><path d="M13 3l5 5v3"/><path d="M15 17h7M19 14l3 3-3 3"/>',
  extract: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4"/><path d="M14 3v5h5v3"/><path d="M15 18h7M19 15l3 3-3 3"/>',
  split: '<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><path d="M8 7.5L20 18M8 16.5L20 6"/>',
  duplicate: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
  copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
  hash: '<path d="M5 9h15M4 15h15M10 3L8 21M16 3l-2 18"/>',
  watermark: '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/><path d="M9.5 15a2.5 2.5 0 0 0 2.5 2.5"/>',
  lock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/><circle cx="12" cy="15.5" r="1.3"/>',
  unlock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 7.8-1.2"/>',
  compress: '<path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7"/>',
  clip: '<path d="M20.5 11.5l-8.2 8.2a5.3 5.3 0 0 1-7.5-7.5l8.6-8.6a3.5 3.5 0 0 1 5 5l-8.6 8.6a1.8 1.8 0 0 1-2.5-2.5l7.9-7.9"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  export: '<path d="M12 3v12M8 7l4-4 4 4"/><path d="M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/>',
  download: '<path d="M12 3v12M8 11l4 4 4-4"/><path d="M5 17v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2"/>',
  fileText: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
  word: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M8.5 12l1.2 5 1.6-4 1.6 4 1.2-5"/>',
  layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/><path d="M3 17.5l9 4.5 9-4.5" opacity=".55"/>',
  flatten: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 15h18M3 19h18"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
  bookmark: '<path d="M6 3h12v18l-6-4.5L6 21z"/>',
  bookmarkPlus: '<path d="M6 3h12v18l-6-4.5L6 21z"/><path d="M12 7v6M9 10h6"/>',
  grid: '<rect x="4" y="3" width="7" height="8" rx="1.5"/><rect x="13" y="3" width="7" height="8" rx="1.5"/><rect x="4" y="13" width="7" height="8" rx="1.5"/><rect x="13" y="13" width="7" height="8" rx="1.5"/>',
  comments: '<path d="M4 5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9l-4 3v-3a1 1 0 0 1-1-1z"/><path d="M17 8h1.5a2 2 0 0 1 2 2v6a1 1 0 0 1-1 1v3l-4-3h-4a2 2 0 0 1-2-2v-1"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
  sparkle: '<path d="M12 3c.6 3.9 2.6 6 6.5 6.5-3.9.6-5.9 2.6-6.5 6.5-.6-3.9-2.6-5.9-6.5-6.5C9.4 9 11.4 6.9 12 3z"/><path d="M18.5 15c.3 1.8 1.2 2.7 3 3-1.8.3-2.7 1.2-3 3-.3-1.8-1.2-2.7-3-3 1.8-.3 2.7-1.2 3-3z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 0 1 4.9.6c0 1.7-2.4 2.2-2.4 3.9M12 17v.2"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  chevDown: '<path d="M6 9l6 6 6-6"/>',
  chevUp: '<path d="M6 15l6-6 6 6"/>',
  chevRight: '<path d="M9 6l6 6-6 6"/>',
  chevLeft: '<path d="M15 6l-6 6 6 6"/>',
  more: '<circle cx="5" cy="12" r="1.2" fill="currentColor"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/><circle cx="19" cy="12" r="1.2" fill="currentColor"/>',
  scroll: '<rect x="6" y="2" width="12" height="9" rx="1.5"/><rect x="6" y="13" width="12" height="9" rx="1.5"/>',
  page: '<rect x="5" y="3" width="14" height="18" rx="2"/>',
  book: '<rect x="2.5" y="4" width="9" height="16" rx="1.5"/><rect x="12.5" y="4" width="9" height="16" rx="1.5"/>',
  home: '<path d="M4 11l8-7 8 7v8a2 2 0 0 1-2 2h-3v-6h-6v6H6a2 2 0 0 1-2-2z"/>',
  command: '<path d="M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z"/>',
  keyboard: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
  send: '<path d="M12 19V5M6 11l6-6 6 6"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.6-4.5L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.6 4.5L20 16"/><path d="M20 20v-4h-4"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  palette: '<path d="M12 3a9 9 0 0 0 0 18c1.2 0 2-.8 2-2 0-.6-.3-1-.6-1.4-.3-.4-.5-.8-.5-1.3 0-1 .9-1.8 2-1.8H17a4 4 0 0 0 4-4c0-4.2-4-7.5-9-7.5z"/><circle cx="7.5" cy="11" r="1" fill="currentColor"/><circle cx="10" cy="7" r="1" fill="currentColor"/><circle cx="15" cy="7.5" r="1" fill="currentColor"/>',
  wand: '<path d="M15 4V2M15 10V8M19 6h2M9 6h2M17.8 3.2L19 2M17.8 8.8L19 10M12.2 8.8L3 18l3 3 9.2-9.2"/>',
  translate: '<path d="M4 5h9M8.5 3v2M6 5c.5 3 2.5 5.5 5 7M11 5c-.8 3.5-3.3 6.5-7 8"/><path d="M13 21l4-9 4 9M14.5 18h5"/>',
  quote: '<path d="M7 7h4v4c0 3-1.5 5-4 6M15 7h4v4c0 3-1.5 5-4 6"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  pdf: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M8 17v-4h1.2a1.2 1.2 0 0 1 0 2.4H8M12 13v4h.8a1.8 1.8 0 0 0 0-4zM16 17v-4h2M16 15h1.5"/>',
  chip: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/><path d="M10 10h4v4h-4z"/>',
  indent: '<path d="M3 6h18M11 12h10M11 18h10M3 10l4 3-4 3"/>',
  outdent: '<path d="M3 6h18M11 12h10M11 18h10M7 10l-4 3 4 3"/>',
  pencil: '<path d="M16.5 3.5l4 4L8 20H4v-4z"/><path d="M14 6l4 4"/>',
};

function icon(name, cls) {
  const body = ICONS[name] || ICONS.file;
  return `<svg class="ic${cls ? " " + cls : ""}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

function hydrateIcons(root) {
  (root || document).querySelectorAll("i[data-i]").forEach((el) => {
    el.outerHTML = icon(el.dataset.i);
  });
}

/* The Washi mark: a sheet of washi paper with a folded corner, ink strokes and a vermilion hanko seal. */
function logoSVG(size) {
  return `<svg viewBox="0 0 100 100" width="${size}" height="${size}" aria-hidden="true">
  <defs><linearGradient id="lgP${size}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fffaf0"/><stop offset="1" stop-color="#efe3c8"/></linearGradient></defs>
  <path d="M24 9 H63 L80 26 V88 a3 3 0 0 1 -3 3 H24 a3 3 0 0 1 -3 -3 V12 a3 3 0 0 1 3 -3 Z" fill="url(#lgP${size})" stroke="#cdbf9f" stroke-width="1.2"/>
  <path d="M63 9 V23 a3 3 0 0 0 3 3 H80 Z" fill="#e2d2ae"/>
  <path d="M29 47 C38 41 52 44 72 39" stroke="#27407a" stroke-width="7" fill="none" stroke-linecap="round"/>
  <path d="M30 59 C40 56 50 58 61 55" stroke="#7aa33c" stroke-width="4" fill="none" stroke-linecap="round"/>
  <path d="M30 68 C36 67 41 68 47 66" stroke="#e0a526" stroke-width="3" fill="none" stroke-linecap="round"/>
  <g transform="rotate(-6 67 74)"><rect x="56" y="63" width="22" height="22" rx="4" fill="#e2452f"/>
  <path d="M60.5 69 L63.8 80 L67 72.5 L70.2 80 L73.5 69" stroke="#fff6ee" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></g>
</svg>`;
}
