// The living scene: a woodblock-style landscape that carries meaning instead of decoration.
//  - the sun travels its arc as the eye-break clock runs (rises after a break, sets when the next one is due)
//  - the sky follows the time of day (dawn, day, dusk, night with a moon and stars)
//  - today's bamboo grows one segment for every eye break taken
// Everything is drawn with CSS variables set per phase in style.css (.hero[data-phase]), so both editions and
// both themes share this file. Motion is slow and small on purpose: the window is rendered without a GPU.

const CX = 965, CY = 262, RX = 195, RY = 200;   // the sun's arc, in the 1200 x 320 drawing
const GROUND = 296;
const STALKS = [{ x: 1090, h: 27, w: 10 }, { x: 1122, h: 24, w: 9 }, { x: 1060, h: 22, w: 8 }];
const PER_STALK = 9;

const STARS = [[520, 38], [588, 96], [655, 52], [712, 24], [770, 84], [826, 40], [884, 112], [930, 30],
  [985, 70], [1040, 26], [1092, 92], [1150, 48], [1178, 120], [610, 150]];

export function sceneSVG(id = 'sc') {
  return `<svg class="scene-art" viewBox="0 0 1200 320" preserveAspectRatio="xMaxYMax slice" aria-hidden="true">
    <defs>
      <linearGradient id="${id}F" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style="stop-color:var(--h-far)"/><stop offset="1" style="stop-color:var(--mist)"/></linearGradient>
      <linearGradient id="${id}M" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style="stop-color:var(--h-mid)"/><stop offset="1" style="stop-color:var(--mist)"/></linearGradient>
    </defs>
    <g class="stars">${STARS.map(([x, y], i) => `<circle cx="${x}" cy="${y}" r="${i % 3 ? 1.3 : 1.9}"/>`).join('')}</g>
    <path class="arc" d="M${CX - RX} ${CY} A${RX} ${RY} 0 0 1 ${CX + RX} ${CY}"/>
    <g class="cloud c1"><ellipse cx="700" cy="74" rx="46" ry="11"/><ellipse cx="730" cy="64" rx="30" ry="10"/><ellipse cx="672" cy="68" rx="22" ry="8"/></g>
    <g class="cloud c2"><ellipse cx="1060" cy="118" rx="38" ry="9"/><ellipse cx="1036" cy="110" rx="24" ry="8"/></g>
    <g class="sun"><circle class="halo" r="34"/><circle class="disc" r="19"/><circle class="bite" cx="9" cy="-6" r="16"/></g>
    <path d="M0 250 C200 235 380 240 520 205 S800 150 920 190 S1110 160 1200 180 V320 H0Z" fill="url(#${id}F)"/>
    <path d="M0 275 C200 262 380 268 560 240 S840 215 990 245 S1140 225 1200 235 V320 H0Z" fill="url(#${id}M)"/>
    <g class="pine"><rect x="778.4" y="222" width="3.2" height="14"/><ellipse cx="780" cy="214" rx="9" ry="12"/></g>
    <g class="bamboo"></g>
    <path class="near" d="M0 300 C240 288 460 304 680 286 S1000 272 1200 294 V320 H0Z"/>
  </svg>`;
}

/** frac 0 = a break was just taken (sunrise), 1 = the next one is due (sunset). */
export function placeSun(svg, frac) {
  const a = Math.PI * (.2 + .75 * Math.max(0, Math.min(1, frac)));   // starts just over the hills, so the sky is never empty
  const sun = svg.querySelector('.sun');
  if (sun) sun.style.transform = `translate(${(CX - RX * Math.cos(a)).toFixed(1)}px, ${(CY - RY * Math.sin(a)).toFixed(1)}px)`;
}

/** One segment per eye break taken today. Segments added since the last call grow in; the first paint is still. */
export function growBamboo(svg, taken) {
  const g = svg.querySelector('.bamboo');
  if (!g) return;
  const n = Math.max(0, Math.min(taken, STALKS.length * PER_STALK));
  if (g.dataset.n === String(n)) return;
  const before = g.dataset.n === undefined ? n : +g.dataset.n;
  g.dataset.n = n;
  if (n === 0) {
    // nothing taken yet: a shoot waits in the ground
    g.innerHTML = `<path class="seg" d="M${STALKS[0].x - 5} ${GROUND} Q${STALKS[0].x} ${GROUND - 26} ${STALKS[0].x + 5} ${GROUND}Z"/>`;
    return;
  }
  let html = '';
  STALKS.forEach((s, si) => {
    const count = Math.max(0, Math.min(PER_STALK, n - si * PER_STALK));
    if (!count) return;
    let parts = '';
    for (let i = 0; i < count; i++) {
      const y = GROUND - (i + 1) * s.h, fresh = si * PER_STALK + i >= before;
      const delay = fresh ? `style="animation-delay:${((si * PER_STALK + i) - before) * 140}ms"` : '';
      parts += `<g class="${fresh ? 'fresh' : ''}" ${delay}>
        <rect class="seg" x="${s.x - s.w / 2}" y="${y + 1}" width="${s.w}" height="${s.h - 1}" rx="3.5"/>
        <rect class="node" x="${s.x - s.w / 2 - 1}" y="${y}" width="${s.w + 2}" height="2.4" rx="1.2"/>
        ${i >= 1 && (i + si) % 2 === 0 ? leaf(s.x, y + 2, (i / 2 + si) % 2 ? 1 : -1) : ''}
      </g>`;
    }
    html += `<g class="stalk s${si}" style="transform-origin:${s.x}px ${GROUND}px">${parts}</g>`;
  });
  g.innerHTML = html;
}

function leaf(x, y, side) {
  return `<path class="leaf" transform="translate(${x} ${y}) scale(${side} 1) rotate(-24)" d="M0 0 Q13 -9 30 -3 Q13 5 0 0Z"/>`;
}

/** Sky for the hour, in the light or the dark theme (night is the same in both). */
export function phase() {
  const h = new Date().getHours();
  const p = h >= 5 && h < 8 ? 'dawn' : h >= 8 && h < 17 ? 'day' : h >= 17 && h < 20 ? 'dusk' : 'night';
  const dark = getComputedStyle(document.documentElement).colorScheme.includes('dark');
  return p === 'night' || !dark ? p : p + '-d';
}
