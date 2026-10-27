// Lighting: a top-down room. Move the window, dim the daylight, switch the lamp — the lux meter and the glare
// warnings respond. 500 lux at desk level is the target.
import { segHTML, wireSeg, paintRange, toggleHTML, ui, setUi, tween } from './core.js';
import { icon } from './icons.js';
import { MK, LUX_NOTE, MEASURE_PAREN } from './content.js';

function estimate(o) {
  const day = o.daylight / 100;
  const winFactor = { side: 1, front: 0.95, behind: 0.85 }[o.window];
  const lux = (o.ceiling ? 320 : 0) + day * 780 * winFactor + (o.lamp ? 380 : 0) + 25;
  let glare = null;
  if (o.window === 'front' && day > 0.25) glare = { s: 'bad', t: 'The bright window behind your screen makes your eyes constantly adjust between bright and dark. Turn the desk so the window is to the side.' };
  else if (o.window === 'behind' && day > 0.25) glare = { s: 'warn', t: 'Daylight from behind you reflects on the screen. Turn the desk so the window is to the side, or use a blind.' };
  return { lux: Math.round(lux), glare };
}

function room(o, r) {
  const day = o.daylight / 100;
  const win = { side: { x: 6, y: 60, w: 6, h: 90, vertical: true }, front: { x: 90, y: 6, w: 120, h: 6 }, behind: { x: 90, y: 238, w: 120, h: 6 } }[o.window];
  const wc = `rgba(255, 215, 120, ${0.25 + day * 0.55})`;
  const rays = [];
  const desk = { x: 100, y: 96, w: 100, h: 48 };
  const target = { x: 150, y: 120 };
  if (day > 0.05) for (let i = 0; i < 5; i++) {
    const sx = win.vertical ? win.x + 6 : win.x + 15 + i * 22;
    const sy = win.vertical ? win.y + 10 + i * 17 : (o.window === 'front' ? win.y + 6 : win.y);
    rays.push(`<line class="ray" x1="${sx}" y1="${sy}" x2="${target.x + (i - 2) * 9}" y2="${target.y + (i - 2) * 4}" stroke="rgba(244,166,58,${0.25 + day * 0.5})" stroke-width="2" style="animation-delay:${-i * .2}s"/>`);
  }
  return `<svg viewBox="0 0 300 250" style="width:100%;height:auto">
    <rect x="6" y="6" width="288" height="238" rx="12" fill="var(--card-2)" stroke="var(--line-2)"/>
    <rect x="${win.x}" y="${win.y}" width="${win.w}" height="${win.h}" rx="2" fill="${wc}" stroke="rgba(244,166,58,.7)"/>
    <text x="${win.vertical ? 20 : win.x + win.w / 2}" y="${win.vertical ? win.y + win.h / 2 : (o.window === 'front' ? 24 : 232)}" text-anchor="${win.vertical ? 'start' : 'middle'}" font-size="9" fill="var(--text-2)" font-weight="600">window</text>
    ${rays.join('')}
    ${o.ceiling ? `<circle cx="150" cy="125" r="70" fill="url(#ceil)"/>` : ''}
    <defs>
      <radialGradient id="ceil"><stop offset="0" stop-color="rgba(255,240,200,.45)"/><stop offset="1" stop-color="rgba(255,240,200,0)"/></radialGradient>
      <radialGradient id="lampg"><stop offset="0" stop-color="rgba(255,214,120,.85)"/><stop offset="1" stop-color="rgba(255,214,120,0)"/></radialGradient>
    </defs>
    <rect x="${desk.x}" y="${desk.y}" width="${desk.w}" height="${desk.h}" rx="5" fill="var(--deskc)"/>
    ${o.lamp ? `<circle cx="186" cy="112" r="40" fill="url(#lampg)"/>` : ''}
    <circle cx="190" cy="106" r="6" fill="${o.lamp ? '#ffc65c' : 'var(--chair-2)'}" stroke="var(--text-3)" stroke-width=".8"/>
    <rect x="130" y="100" width="40" height="5" rx="2" fill="var(--screen)"/>
    ${o.window === 'front' && day > 0.25 ? `<rect x="122" y="88" width="56" height="10" rx="4" fill="rgba(255,240,180,${day})" class="glint"/>` : ''}
    ${o.window === 'behind' && day > 0.25 ? `<g class="glint"><path d="M150 99l2 3 3 1-3 1-2 3-2-3-3-1 3-1z" fill="#fff" stroke="var(--c-light)" stroke-width=".6"/></g>` : ''}
    <rect x="138" y="122" width="24" height="7" rx="2" fill="var(--chair-2)"/>
    <circle cx="150" cy="160" r="13" fill="var(--fig)"/>
    <ellipse cx="150" cy="168" rx="22" ry="9" fill="var(--fig)"/>
    <rect x="132" y="176" width="36" height="22" rx="7" fill="var(--chair)"/>
    <text x="150" y="${r.glare ? 90 : 91}" text-anchor="middle" font-size="8" fill="var(--text-3)"></text>
  </svg>`;
}

function gauge(lux) {
  const max = 1000, a = Math.min(lux, max) / max * 180;
  const pt = (deg, r) => [100 - r * Math.cos(deg * Math.PI / 180), 100 - r * Math.sin(deg * Math.PI / 180)];
  const arc = (d0, d1, r, c, w) => { const [x0, y0] = pt(d0, r), [x1, y1] = pt(d1, r); return `<path d="M${x0} ${y0}A${r} ${r} 0 0 1 ${x1} ${y1}" stroke="${c}" stroke-width="${w}" fill="none"/>`; };
  const [nx, ny] = pt(a, 66);
  return `<svg viewBox="-14 0 228 112" class="lux-gauge" style="width:100%;max-width:300px;margin:auto">
    ${arc(0, 54, 78, 'var(--bad)', 12)}${arc(54, 90, 78, 'var(--warn)', 12)}${arc(90, 180, 78, 'var(--ok)', 12)}
    ${[0, 250, 500, 750, 1000].map(v => { const [x, y] = pt(v / 1000 * 180, 96); return `<text x="${x}" y="${y + 3}" text-anchor="middle">${v === 1000 ? '1000+' : v}</text>`; }).join('')}
    <line x1="100" y1="100" x2="${nx}" y2="${ny}" stroke="var(--text)" stroke-width="3.5" stroke-linecap="round"/>
    <circle cx="100" cy="100" r="6" fill="var(--text)"/>
    <text class="val" x="100" y="86" text-anchor="middle" style="font-size:0"></text>
  </svg>`;
}

export default {
  id: 'light', title: 'Lighting', icon: 'light', color: 'var(--c-light)',
  mount(root) {
    const o = Object.assign({ window: 'front', daylight: 55, lamp: false, ceiling: true }, ui('light', {}));
    root.innerHTML = `
      <div class="page-head"><div class="grow">
        <div class="kicker" style="--k:var(--c-light)">Lighting</div>
        <h1>500 lux, no glare</h1>
        <p>Good lighting helps prevent eye strain and keeps you focused through the day. Try moving the window and the lamp in this room.</p>
      </div></div>
      <div class="grid" style="grid-template-columns:minmax(0,1.25fr) minmax(0,1fr)">
        <div class="card"><div id="room"></div>
          <div class="row wrap mt" style="gap:14px">
            <div><div class="small muted" style="margin-bottom:4px">Window is…</div>${segHTML('win', [['side', 'To the side'], ['front', 'Behind screen'], ['behind', 'Behind me']], o.window)}</div>
          </div>
          <div class="slider mt"><label>Daylight</label><output id="oDay"></output><input type="range" id="day" min="0" max="100" value="${o.daylight}"></div>
          <div class="grid g2 mt-s" style="gap:10px">
            <div class="row"><span style="flex:1;font-weight:550">Ceiling light</span>${toggleHTML('ceil', o.ceiling)}</div>
            <div class="row"><span style="flex:1;font-weight:550">Task lamp</span>${toggleHTML('lamp', o.lamp)}</div>
          </div>
        </div>
        <div class="stack">
          <div class="card" style="text-align:center">
            <div class="small muted">Estimated light at your desk (calculated)</div>
            <div id="gauge"></div>
            <div style="font:700 34px/1 var(--font-display);margin-top:-6px"><span id="luxV">0</span> <span style="font-size:16px" class="muted">lux</span></div>
            <div class="mt-s" id="luxMsg"></div>
            <p class="small muted mt" style="text-align:left;display:flex;gap:8px"><span style="flex:none;width:16px;color:var(--c-light)">${icon('info')}</span><span>${LUX_NOTE}</span></p>
          </div>
          <div class="card" id="glare"></div>
        </div>
      </div>

      <h2 style="font-size:18px;margin:26px 0 12px">How bright is that?</h2>
      <div class="lux-scale">
        <div style="background:#3d4a63;color:#fff"><b>50</b>living room evening</div>
        <div style="background:#8b7ec8;color:#fff"><b>100</b>corridor</div>
        <div style="background:${MK ? '#99bf9c' : '#86d19f'}"><b>500</b>desk work ✓</div>
        <div style="background:#ffd27a"><b>1 000</b>overcast day</div>
        <div style="background:#ffeeb0"><b>10 000+</b>daylight outside</div>
      </div>

      <div class="grid g3 mt">
        <div class="card tip"><div class="ti" style="--c:var(--c-light)">${icon('window')}</div><div><h3>Make the most of daylight</h3><p class="muted">Use natural light where possible, and position your screen so that windows are to the side rather than directly in front of or behind it.</p></div></div>
        <div class="card tip"><div class="ti" style="--c:var(--c-light)">${icon('lamp')}</div><div><h3>Add a task lamp when needed</h3><p class="muted">If daylight is insufficient or creates shadows or glare, complement it with an adjustable task lamp.</p></div></div>
        <div class="card tip"><div class="ti" style="--c:var(--c-light)">${icon('info')}</div><div><h3>Lux vs lumens</h3><p class="muted"><b>Lux</b> measures the light that reaches your desk; <b>lumens</b> describe a lamp’s output. Phone apps only give a rough idea — a reliable measurement needs a calibrated light meter${MEASURE_PAREN}. Where local rules set a higher level, the local requirement applies.</p></div></div>
      </div>`;
    const $ = s => root.querySelector(s);
    const g = { lux: 0 };
    const render = () => {
      const r = estimate(o);
      $('#room').innerHTML = room(o, r);
      $('#oDay').textContent = o.daylight < 15 ? 'dusk' : o.daylight < 45 ? 'overcast' : o.daylight < 80 ? 'bright' : 'sunny';
      tween(g, { lux: r.lux }, v => {
        $('#gauge').innerHTML = gauge(v.lux);
        $('#luxV').textContent = Math.round(v.lux);
      }, 600);
      $('#luxMsg').innerHTML = r.lux >= 500 ? '<span class="chip ok">Enough light for desk work</span>'
        : r.lux >= 300 ? `<span class="chip warn">A bit dim — ${o.lamp ? 'open the blinds' : 'add the task lamp'}</span>`
          : '<span class="chip bad">Too dark — your eyes will tire</span>';
      $('#glare').innerHTML = r.glare
        ? `<div class="tip"><div class="ti" style="--c:${r.glare.s === 'bad' ? 'var(--bad)' : 'var(--warn)'}">${icon('sparkle')}</div><div><h3>${r.glare.s === 'bad' ? 'Glare' : 'Reflections'}</h3><p class="muted">${r.glare.t}</p></div></div>`
        : `<div class="tip"><div class="ti" style="--c:var(--ok)">${icon('tick')}</div><div><h3>No glare</h3><p class="muted">${o.window === 'side' ? 'Window to the side — light falls across the desk without hitting the screen or your eyes.' : 'Not much daylight right now, so no glare from the window.'}</p></div></div>`;
    };
    let t = 0;
    const save = () => { clearTimeout(t); t = setTimeout(() => setUi({ light: o }), 400); };
    wireSeg(root, 'win', v => { o.window = v; render(); save(); });
    const day = $('#day'); paintRange(day);
    day.addEventListener('input', () => { o.daylight = +day.value; render(); save(); });
    $('#ceil').addEventListener('change', e => { o.ceiling = e.target.checked; render(); save(); });
    $('#lamp').addEventListener('change', e => { o.lamp = e.target.checked; render(); save(); });
    render();
  },
};
