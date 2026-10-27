// The Postura logo: a bamboo stalk — straight and segmented like a healthy spine — on a rounded tile.
// Same 100-unit geometry as make_icon.py (which draws the .ico files).

export const EDITION = document.documentElement.dataset.edition;
export const ASSISTANT = document.querySelector('meta[name="postura-assistant"]').content;

function leafPath([bx, by], [tx, ty], w) {
  const mx = (bx + tx) / 2, my = (by + ty) / 2, dx = tx - bx, dy = ty - by, l = Math.hypot(dx, dy);
  const nx = -dy / l * w, ny = dx / l * w;
  return `M${bx} ${by}Q${mx + nx} ${my + ny} ${tx} ${ty}Q${mx - nx} ${my - ny} ${bx} ${by}Z`;
}

export function logoSVG(animated = false) {
  const mk = false;   // public edition
  const id = 'lg' + Math.random().toString(36).slice(2, 7);
  const c = mk
    ? { top: '#2a4734', bot: '#2a4734', stalk: '#c3db76', hi: '#e6f2be', node: '#7ca042', l1: '#c3db76', l2: '#99bf9c' }
    : { top: '#6cb8ff', bot: '#2f6fdb', stalk: '#3bb273', hi: '#8cdeac', node: '#186e42', l1: '#4cc37f', l2: '#2e9a5f' };
  const bands = mk ? `
    <g clip-path="url(#${id}c)">
      <g class="band"><line x1="4" y1="50" x2="46" y2="96" stroke="#fff" stroke-width="4"/><path d="M4 50L4 96L46 96Z" fill="#99bf9c"/></g>
      <g class="band" style="animation-delay:.1s"><line x1="60" y1="4" x2="96" y2="50" stroke="#fff" stroke-width="4"/><path d="M60 4L96 4L96 50Z" fill="#cfe7cc"/></g>
    </g>` : '';
  const sun = mk ? '' : `<g class="sun"><circle cx="71" cy="30" r="15" fill="#ffc65c" opacity=".28"/><circle cx="71" cy="30" r="10" fill="#ffc65c"/></g>`;
  return `<svg viewBox="0 0 100 100" class="${animated ? 'anim' : ''}" aria-hidden="true">
    <defs>
      <linearGradient id="${id}g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c.top}"/><stop offset="1" stop-color="${c.bot}"/></linearGradient>
      <clipPath id="${id}c"><rect x="4" y="4" width="92" height="92" rx="22"/></clipPath>
    </defs>
    <rect class="tile" x="4" y="4" width="92" height="92" rx="22" fill="url(#${id}g)"/>
    ${bands}${sun}
    <path class="leafA" d="${leafPath([55, 41], [79, 50], 7)}" fill="${c.l1}"/>
    <path class="leafB" d="${leafPath([43, 61], [22, 54], 6.5)}" fill="${c.l2}"/>
    <g class="stalk">
      <rect x="43" y="18" width="12" height="68" rx="6" fill="${c.stalk}"/>
      <rect x="46" y="24" width="2.5" height="56" rx="1.25" fill="${c.hi}"/>
      <rect class="node" style="animation-delay:.55s" x="41" y="39" width="16" height="4" rx="2" fill="${c.node}"/>
      <rect class="node" style="animation-delay:.45s" x="41" y="60" width="16" height="4" rx="2" fill="${c.node}"/>
    </g>
  </svg>`;
}

/** The assistant's face: a soft round character whose eyes blink and glance around. */
export function avatarSVG() {
  const mk = false;   // public edition
  const id = 'av' + Math.random().toString(36).slice(2, 7);
  const g1 = mk ? '#3d6b4c' : '#7c6cf0', g2 = mk ? '#2a4734' : '#2f6fdb', eye = mk ? '#c3db76' : '#ffffff', cheek = mk ? '#99bf9c' : '#ffb07a';
  const tuft = mk
    ? `<path d="${leafPath([50, 14], [64, 3], 4.5)}" fill="#c3db76"/>`
    : `<path d="${leafPath([50, 14], [62, 2], 4.5)}" fill="#4cc37f"/>`;
  return `<svg viewBox="0 0 100 100" class="av" aria-hidden="true">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${g1}"/><stop offset="1" stop-color="${g2}"/></linearGradient></defs>
    ${tuft}
    <circle cx="50" cy="55" r="41" fill="url(#${id})"/>
    <ellipse cx="50" cy="40" rx="26" ry="12" fill="#fff" opacity=".09"/>
    <g class="lid"><ellipse cx="36" cy="54" rx="6.5" ry="8" fill="${eye}"/><ellipse cx="64" cy="54" rx="6.5" ry="8" fill="${eye}"/></g>
    <g class="pupil"><circle cx="37" cy="56" r="2.6" fill="${g2}"/><circle cx="65" cy="56" r="2.6" fill="${g2}"/></g>
    <circle cx="27" cy="68" r="4.5" fill="${cheek}" opacity=".5"/><circle cx="73" cy="68" r="4.5" fill="${cheek}" opacity=".5"/>
    <path d="M42 71 Q50 77 58 71" stroke="${eye}" stroke-width="3" fill="none" stroke-linecap="round"/>
  </svg>`;
}

/** Company-edition cover-art bands for hero headers (sage, forest, mint with white gaps). */
export function stripesSVG() {
  return `<svg class="stripes" viewBox="0 0 1000 300" preserveAspectRatio="xMaxYMid slice" aria-hidden="true">
    <path d="M560 0 L690 0 L1000 260 L1000 300 L930 300 Z" fill="#fff" opacity=".9"/>
    <path d="M575 0 L680 0 L1000 270 L1000 300 L940 300 Z" fill="#3d6b4c"/>
    <path d="M705 0 L735 0 L1000 222 L1000 247 Z" fill="#fff" opacity=".9"/>
    <path d="M745 0 L1000 0 L1000 214 Z" fill="#cfe7cc"/>
    <path d="M880 300 L990 300 L1000 300 L1000 292 Z" fill="#99bf9c"/>
  </svg>`;
}
