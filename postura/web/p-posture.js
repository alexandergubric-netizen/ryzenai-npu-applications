// Posture: a live side-view model in the guide's style. Move the chair, desk and screen and the figure adapts —
// neck bends towards a low screen, elbows open or close with desk height, feet dangle from a high chair.
// All geometry is in centimetres using standard body proportions scaled by the person's height.
import { esc, ui, setUi, tween, paintRange, segHTML, wireSeg, toggleHTML } from './core.js';
import { icon } from './icons.js';

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const rad = d => d * Math.PI / 180, deg = r => r * 180 / Math.PI;
const Y = y => 200 - y;                 // floor at SVG y = 200

const RANGES = {
  sit: { seat: [35, 62], desk: [58, 92], screen: [80, 175], dist: [35, 110] },
  stand: { desk: [70, 130], screen: [105, 205], dist: [35, 110] },
};

export function ideal(H, mode) {
  const dist = Math.round(clamp(0.38 * H, 55, 72));
  if (mode === 'stand') return { desk: Math.round(0.634 * H - 3), screen: Math.round(0.935 * H - 3), dist };
  const seat = Math.round(0.25 * H);
  return { seat, desk: Math.round(seat + 0.154 * H - 3), screen: Math.round(seat + 0.455 * H - 3), dist };
}

/** Solve the whole body for a setup. Returns points (cm, y up) and the five check results. */
function model(H, mode, p, footrest) {
  const L = 0.25 * H, T = 0.245 * H, U = 0.186 * H, F = 0.146 * H, Tr = 0.29 * H, Nk = 0.115 * H, shin = 0.29 * H;
  const sit = mode === 'sit';
  const hip = { x: 0, y: sit ? p.seat + 0.05 * H : 0.53 * H };
  const deskFront = 0.085 * H;
  const desk = p.desk;
  const screenTop = Math.max(p.screen, desk + 34);
  const eye0 = { x: 0.04 * H, y: hip.y + Tr + Nk };
  const screenX = eye0.x + p.dist;
  const screenC = screenTop - 16;

  // neck follows the gaze (comfortable gaze is ~15° down); a far or low screen pulls the trunk forward
  let neck = 0, lean = 0, shoulder, head, eye;
  for (let i = 0; i < 3; i++) {
    lean = clamp((p.dist - 78) * 0.9, 0, 16) + (neck > 14 ? (neck - 14) * 0.45 : 0);
    shoulder = { x: hip.x + Tr * Math.sin(rad(lean)), y: hip.y + Tr * Math.cos(rad(lean)) };
    const ha = rad(lean + neck * 0.6);
    head = { x: shoulder.x + Nk * Math.sin(ha), y: shoulder.y + Nk * Math.cos(ha) };
    eye = { x: head.x + 0.04 * H * Math.cos(rad(-neck)), y: head.y + 0.04 * H * Math.sin(rad(-neck)) };
    const gaze = deg(Math.atan2(eye.y - screenC, Math.max(5, screenX - eye.x)));
    neck = clamp((gaze - 15) * 0.85, -22, 38);
  }

  // arm: two-link IK from shoulder to the keyboard, elbow kept low
  const wristT = { x: deskFront + 0.06 * H, y: desk + 3 };
  let dx = wristT.x - shoulder.x, dy = wristT.y - shoulder.y, d = Math.hypot(dx, dy);
  const reachMax = U + F - 0.5;
  const over = d > reachMax;
  const dd = Math.min(d, reachMax);
  const base = Math.atan2(dy, dx);
  const a = Math.acos(clamp((U * U + dd * dd - F * F) / (2 * U * dd), -1, 1));
  const e1 = { x: shoulder.x + U * Math.cos(base + a), y: shoulder.y + U * Math.sin(base + a) };
  const e2 = { x: shoulder.x + U * Math.cos(base - a), y: shoulder.y + U * Math.sin(base - a) };
  const elbow = e1.y < e2.y ? e1 : e2;
  const wrist = over ? { x: shoulder.x + reachMax * Math.cos(base), y: shoulder.y + reachMax * Math.sin(base) } : wristT;
  const elbowAng = deg(Math.acos(clamp((U * U + F * F - dd * dd) / (2 * U * F), -1, 1)));

  // legs
  let knee, ankle, gap = 0, fr = 0, kneeAng = 90;
  if (sit) {
    fr = footrest ? clamp(p.seat - L, 0, 15) : 0;
    const k0 = p.seat + 0.04 * H;
    if (k0 - shin > fr + 0.5) { knee = { x: hip.x + T, y: k0 }; gap = k0 - shin - fr; }
    else {
      const ky = fr + shin, dyk = ky - hip.y;
      knee = { x: hip.x + Math.sqrt(Math.max(T * T - dyk * dyk, 1)), y: ky };
    }
    ankle = { x: knee.x, y: knee.y - shin };
    kneeAng = 90 + deg(Math.asin(clamp((hip.y - knee.y) / T, -1, 1)));
  } else {
    knee = { x: hip.x + 1, y: 0.285 * H };
    ankle = { x: hip.x, y: 0.04 * H };
  }
  const toe = { x: ankle.x + 0.13 * H, y: ankle.y - 0.02 * H };

  // the five checks from the guide
  const eyeDiff = eye.y - screenTop;   // + = screen top below eye
  const st = (ok, warn) => ok ? 'ok' : warn ? 'warn' : 'bad';
  const checks = [];
  checks.push({
    n: 1, title: 'Top of the screen at or just below eye level',
    s: st(eyeDiff >= -1 && eyeDiff <= 8, eyeDiff >= -5 && eyeDiff <= 15),
    hint: eyeDiff > 8 ? `Screen is ${Math.round(eyeDiff)} cm too low — your neck bends ${Math.round(Math.max(neck, 0))}°. Raise it.` :
      eyeDiff < -1 ? `Screen top is ${Math.round(-eyeDiff)} cm above your eyes — you look up. Lower it.` : 'Your neck can stay relaxed.',
  });
  const realDist = screenX - eye.x;
  checks.push({
    n: 2, title: 'Screen about an arm’s length away',
    s: st(p.dist >= 50 && p.dist <= 76, p.dist >= 42 && p.dist <= 88),
    hint: p.dist > 76 ? `${Math.round(p.dist)} cm is far — you lean in. Bring it closer (50–75 cm).` :
      p.dist < 50 ? `${Math.round(p.dist)} cm is very close — push it back a little.` : `${Math.round(realDist)} cm — about an arm’s length.`,
  });
  checks.push({
    n: 3, title: 'Elbows relaxed at about 90°, wrists straight',
    s: over ? 'bad' : st(elbowAng >= 80 && elbowAng <= 112, elbowAng >= 68 && elbowAng <= 128),
    hint: over ? 'You have to stretch to reach the keyboard.' : elbowAng < 80 ? `Elbows at ${Math.round(elbowAng)}° — the desk is too high${sit ? ' (or raise the chair)' : ''}.` :
      elbowAng > 112 ? `Elbows at ${Math.round(elbowAng)}° — the desk is too low.` : `Elbows at ${Math.round(elbowAng)}° — relaxed.`,
  });
  if (sit) {
    checks.push({
      n: 4, title: 'Lower back fully supported by the chair',
      s: st(lean < 4, lean < 10),
      hint: lean >= 4 ? `You lean ${Math.round(lean)}° forward, so your back leaves the backrest. Fix the screen first, then sit all the way back.`
        : 'You sit all the way back: the backrest’s lumbar pad (green) supports the curve of your lower back.',
    });
    const high = p.seat - L;
    checks.push({
      n: 5, title: 'Feet flat on the floor or on a footrest',
      s: gap > 1.5 ? (gap > 6 ? 'bad' : 'warn') : high < -4 ? 'warn' : 'ok',
      hint: gap > 1.5 ? `Feet hang ${Math.round(gap)} cm above the ${fr ? 'footrest' : 'floor'}. Lower the chair or use a footrest.` :
        high < -4 ? 'Knees are higher than hips — raise the chair a little.' : fr ? 'Feet flat on the footrest.' : 'Feet flat on the floor.',
    });
  } else {
    checks.push({
      n: 4, title: 'Stand tall with weight evenly on both feet',
      s: st(lean < 4, lean < 10),
      hint: lean >= 4 ? `You lean ${Math.round(lean)}° towards the screen.` : 'Upright, weight on both feet. Shift now and then.',
    });
    const elbowRest = shoulder.y - U;
    const diff = desk + 3 - elbowRest;
    checks.push({
      n: 5, title: 'Desk height level with your elbows',
      s: st(Math.abs(diff) <= 4, Math.abs(diff) <= 9),
      hint: Math.abs(diff) <= 4 ? 'Desk is at elbow height.' : diff > 0 ? `Desk is ${Math.round(diff)} cm above your elbows. Lower it.` : `Desk is ${Math.round(-diff)} cm below your elbows. Raise it.`,
    });
  }
  // the back of the trunk: where it is when upright (the backrest touches it there), and where it is at a given
  // height when leaning forward (the gap to the backrest)
  const half = 0.05 * H;
  const backX = hip.x - half;
  const backAt = y => {
    const d = (y - hip.y) / Math.cos(rad(lean));
    return hip.x + Math.sin(rad(lean)) * d - half * Math.cos(rad(lean));
  };
  const lumbar = [0.09 * H, 0.17 * H];   // height of the lumbar pad above the seat (the small of the back)
  const backOk = sit && lean < 4;
  return { H, sit, hip, shoulder, head, eye, elbow, wrist, knee, ankle, toe, neck, lean, gap, fr, elbowAng, kneeAng, deskFront, desk, screenTop, screenX, checks, over,
    backX, backAt, lumbar, backOk };
}

const COL = { ok: 'var(--ok)', warn: 'var(--warn)', bad: 'var(--bad)' };

function line(a, b, w, c, extra = '') {
  return `<line x1="${a.x.toFixed(2)}" y1="${Y(a.y).toFixed(2)}" x2="${b.x.toFixed(2)}" y2="${Y(b.y).toFixed(2)}" stroke="${c}" stroke-width="${w}" stroke-linecap="round" ${extra}/>`;
}

function arc(c, r, a0, a1, color) {
  // angles in degrees, y-up maths → SVG
  const p0 = { x: c.x + r * Math.cos(rad(a0)), y: Y(c.y + r * Math.sin(rad(a0))) };
  const p1 = { x: c.x + r * Math.cos(rad(a1)), y: Y(c.y + r * Math.sin(rad(a1))) };
  let sweep = a1 - a0;
  while (sweep < 0) sweep += 360;
  return `<path d="M${p0.x} ${p0.y} A${r} ${r} 0 ${sweep > 180 ? 1 : 0} 0 ${p1.x} ${p1.y}" fill="none" stroke="${color}" stroke-width="1.2"/>`;
}

function draw(m) {
  const H = m.H, s = [];
  const fig = 'var(--fig)';
  // floor
  s.push(`<line x1="-80" y1="200.6" x2="180" y2="200.6" stroke="var(--floor)" stroke-width="1.6"/>`);
  // chair (behind the person)
  if (m.sit) {
    const seatY = m.hip.y - 0.05 * H;
    // the backrest's front face sits exactly where an upright back is, so a good posture visibly leans on it
    const bx = m.backX - 5;
    s.push(`<rect x="${bx}" y="${Y(seatY + 0.34 * H)}" width="5" height="${0.34 * H}" rx="2.5" fill="var(--chair-2)"/>`);
    // lumbar pad: a cushion that bulges into the small of the back
    const l0 = seatY + m.lumbar[0], l1 = seatY + m.lumbar[1];
    s.push(`<path d="M${bx + 2} ${Y(l0)} Q${m.backX + 3.5} ${Y((l0 + l1) / 2)} ${bx + 2} ${Y(l1)} Z" fill="${m.backOk ? 'var(--ok)' : 'var(--chair)'}"/>`);
    s.push(`<rect x="${bx - 2}" y="${Y(seatY)}" width="${0.3 * H}" height="5" rx="2.5" fill="var(--chair)"/>`);
    s.push(`<rect x="-3" y="${Y(seatY - 4)}" width="4" height="${seatY - 10}" fill="var(--chair-2)"/>`);
    s.push(`<rect x="-26" y="${Y(8)}" width="48" height="4" rx="2" fill="var(--chair)"/>`);
    s.push(`<circle cx="-22" cy="${Y(3)}" r="3" fill="var(--chair-2)"/><circle cx="18" cy="${Y(3)}" r="3" fill="var(--chair-2)"/>`);
    if (m.fr > 0) s.push(`<rect x="${m.ankle.x - 6}" y="${Y(m.fr)}" width="${0.2 * H}" height="${m.fr}" rx="2" fill="var(--chair)" opacity=".9"/>
      <text class="lbl" x="${m.ankle.x + 0.1 * H - 6}" y="${Y(m.fr / 2) + 2}" text-anchor="middle" fill="var(--text)">footrest</text>`);
  }
  // legs
  s.push(line(m.hip, m.knee, 0.075 * H, fig));
  s.push(line(m.knee, m.ankle, 0.062 * H, fig));
  s.push(line(m.ankle, m.toe, 0.05 * H, fig));
  if (!m.sit) {
    // the other leg, a touch lighter
    s.push(line({ x: m.hip.x - 2, y: m.hip.y }, { x: m.knee.x - 3, y: m.knee.y }, 0.062 * H, 'var(--fig-2)', 'opacity=".55"'));
  }
  // desk
  const dx0 = m.deskFront, dx1 = m.deskFront + 80;
  s.push(`<rect x="${dx1 - 8}" y="${Y(m.desk)}" width="4.5" height="${m.desk}" fill="var(--deskc-2)"/>`);
  if (!m.sit) s.push(`<rect x="${dx1 - 14}" y="${Y(m.desk) + 6}" width="12" height="${Math.max(0, m.desk - 12)}" rx="2" fill="var(--deskc-2)" opacity=".6"/>`);
  s.push(`<rect x="${dx0}" y="${Y(m.desk)}" width="80" height="4" rx="2" fill="var(--deskc)"/>`);
  s.push(`<rect x="${dx0 + 4}" y="${Y(m.desk + 2.2)}" width="${0.12 * H}" height="2.2" rx="1" fill="var(--chair-2)"/>`);
  // monitor
  const pb = m.screenTop - 32;
  s.push(`<rect x="${m.screenX + 4}" y="${Y(pb)}" width="3" height="${pb - m.desk}" fill="var(--chair-2)"/>`);
  s.push(`<rect x="${m.screenX - 4}" y="${Y(m.desk + 1.6)}" width="20" height="1.6" rx=".8" fill="var(--chair-2)"/>`);
  s.push(`<rect x="${m.screenX}" y="${Y(m.screenTop)}" width="3.2" height="32" rx="1.2" fill="var(--screen)"/>`);
  // trunk, head
  s.push(line(m.hip, m.shoulder, 0.1 * H, fig));
  if (m.sit) {
    // back support, made explicit: green contact at the lumbar pad, or a red gap where the back has left the backrest
    const seatY = m.hip.y - 0.05 * H, ly = seatY + (m.lumbar[0] + m.lumbar[1]) / 2;
    if (m.backOk) {
      s.push(`<path d="M${m.backX - 0.6} ${Y(seatY + m.lumbar[0])} L${m.backX - 0.6} ${Y(seatY + m.lumbar[1])}" stroke="var(--ok)" stroke-width="2.4" stroke-linecap="round"/>`);
      s.push(`<text class="lbl" x="${m.backX - 9}" y="${Y(ly) - 1}" text-anchor="end" style="font-weight:700;fill:var(--ok)">back</text>
        <text class="lbl" x="${m.backX - 9}" y="${Y(ly) + 5}" text-anchor="end" style="font-weight:700;fill:var(--ok)">supported</text>`);
    } else {
      const gy = seatY + 0.2 * H, gx = m.backAt(gy);
      s.push(`<line x1="${m.backX}" y1="${Y(gy)}" x2="${gx}" y2="${Y(gy)}" stroke="var(--bad)" stroke-width="1.4" stroke-dasharray="1.6 1.4"/>
        <path d="M${m.backX + 2} ${Y(gy) - 2}L${m.backX} ${Y(gy)}L${m.backX + 2} ${Y(gy) + 2}M${gx - 2} ${Y(gy) - 2}L${gx} ${Y(gy)}L${gx - 2} ${Y(gy) + 2}" stroke="var(--bad)" stroke-width="1.2" fill="none"/>
        <text class="ang" x="${m.backX - 8}" y="${Y(gy) + 2}" text-anchor="end" fill="var(--bad)">gap ${Math.max(1, Math.round(gx - m.backX))} cm</text>`);
    }
  }
  s.push(line(m.shoulder, m.head, 0.035 * H, fig));
  s.push(`<circle cx="${m.head.x}" cy="${Y(m.head.y)}" r="${0.066 * H}" fill="${fig}"/>`);
  // arm: a lighter shade with a thin outline so it reads in front of the body
  s.push(line(m.shoulder, m.elbow, 0.055 * H + 1.6, 'var(--card)'));
  s.push(line(m.elbow, m.wrist, 0.048 * H + 1.6, 'var(--card)'));
  s.push(line(m.shoulder, m.elbow, 0.055 * H, 'var(--fig-2)'));
  s.push(line(m.elbow, m.wrist, 0.048 * H, 'var(--fig-2)'));
  // gaze line to the top of the screen (1) and distance arrow (2)
  const c1 = COL[m.checks[0].s], c2 = COL[m.checks[1].s], c3 = COL[m.checks[2].s];
  s.push(`<line x1="${m.eye.x + 4}" y1="${Y(m.eye.y)}" x2="${m.screenX - 1}" y2="${Y(m.screenTop)}" stroke="${c1}" stroke-width="1.4" stroke-dasharray="3 2.4"/>`);
  const ay = Y(Math.max(m.head.y, m.screenTop) + 0.11 * H);
  s.push(`<g stroke="${c2}" stroke-width="1.3" fill="none" stroke-linecap="round"><line x1="${m.eye.x}" y1="${ay}" x2="${m.screenX}" y2="${ay}"/>
    <path d="M${m.eye.x + 4} ${ay - 3}L${m.eye.x} ${ay}L${m.eye.x + 4} ${ay + 3}M${m.screenX - 4} ${ay - 3}L${m.screenX} ${ay}L${m.screenX - 4} ${ay + 3}"/></g>`);
  // elbow angle
  const a0 = deg(Math.atan2(m.shoulder.y - m.elbow.y, m.shoulder.x - m.elbow.x));
  const a1 = deg(Math.atan2(m.wrist.y - m.elbow.y, m.wrist.x - m.elbow.x));
  s.push(arc(m.elbow, 7, a1, a0, c3));
  s.push(`<text class="ang" x="${m.elbow.x + 6}" y="${Y(m.elbow.y) + 11}" fill="${c3}">${Math.round(m.elbowAng)}°</text>`);
  if (m.sit) {
    const ck = COL[m.checks[4].s];
    s.push(`<text class="ang" x="${m.knee.x - 15}" y="${Y(m.knee.y) + 12}" fill="${ck}">${Math.round(m.kneeAng)}°</text>`);
    if (m.gap > 1.5) {
      s.push(`<line x1="${m.toe.x}" y1="${Y(m.ankle.y - 2)}" x2="${m.toe.x}" y2="${Y(m.fr)}" stroke="var(--bad)" stroke-width="1.2" stroke-dasharray="2 2"/>
        <text class="ang" x="${m.toe.x + 3}" y="${Y((m.ankle.y + m.fr) / 2) + 2}" fill="var(--bad)">+${Math.round(m.gap)} cm</text>`);
    }
  }
  // numbered hot spots (same numbers as the guide)
  const spots = [
    { x: m.screenX + 12, y: m.screenTop + 6 },
    { x: (m.eye.x + m.screenX) / 2, y: 200 - ay + 9 },
    { x: m.elbow.x + 6, y: m.elbow.y + 14 },
    m.sit ? { x: m.backX - 14, y: m.hip.y + 0.28 * H } : { x: m.hip.x - 16, y: m.hip.y },
    m.sit ? { x: m.toe.x + 16, y: Math.max(m.ankle.y, m.fr) + 14 } : { x: m.deskFront + 40, y: m.desk - 12 },
  ];
  spots.forEach((p, i) => {
    s.push(`<g class="hot" data-n="${i + 1}"><circle cx="${p.x}" cy="${Y(p.y)}" r="5.2" fill="${COL[m.checks[i].s]}"/><text x="${p.x}" y="${Y(p.y) + 1.9}" text-anchor="middle">${i + 1}</text></g>`);
  });
  return s.join('');
}

export default {
  id: 'posture', title: 'Posture', icon: 'posture', color: 'var(--c-posture)',
  mount(root) {
    const saved = ui('posture', {});
    const S = {
      H: saved.H || 175,
      mode: saved.mode || 'sit',
      footrest: !!saved.footrest,
      // a typical, slightly off laptop-style start so there is something to fix
      sit: Object.assign({ seat: 50, desk: 74, screen: 112, dist: 86 }, saved.sit || {}),
      stand: Object.assign({ desk: 100, screen: 150, dist: 80 }, saved.stand || {}),
    };
    root.innerHTML = `
      <div class="page-head"><div class="grow">
        <div class="kicker" style="--k:var(--c-posture)">Posture and alignment</div>
        <h1>Find your neutral posture</h1>
        <p>A relaxed, neutral posture reduces strain on your joints and muscles. Move the sliders and watch the model — or set your height and press <b>Fit to me</b>.</p>
      </div></div>
      <div class="posture">
        <div class="stack">
          <div class="card scene-card"><svg class="scene" viewBox="-80 -4 260 208" id="scene"></svg></div>
          <div class="callout" id="backTip">${icon('chair')}<div><b>Let the chair carry your back.</b> <span class="muted">Sit all the way back, so your bottom touches the backrest. The backrest — especially its lumbar pad at about belt height (green in the picture) — should touch and support the inward curve of your lower back. If it doesn’t reach, move the backrest up or down, or add a small lumbar cushion. Don’t perch on the front edge of the seat.</span></div></div>
          <div class="list checks" id="checks"></div>
        </div>
        <div class="stack">
          <div class="card">
            <div class="row">${segHTML('mode', [['sit', 'Sitting'], ['stand', 'Standing']], S.mode)}<span class="spacer"></span>
              <span class="chip" id="score"></span></div>
            <div class="slider mt"><label>${icon('ruler', 'style="width:14px;height:14px;display:inline;vertical-align:-2px"')} Your height</label><output id="oH"></output><input type="range" id="H" min="150" max="200" step="1"></div>
            <button class="btn primary mt-s" id="fit" style="width:100%">${icon('sparkle')}Fit to me</button>
          </div>
          <div class="card stack" style="gap:12px" id="ctl"></div>
          <div class="card small muted" id="note"></div>
        </div>
      </div>`;
    const $ = s => root.querySelector(s);
    const scene = $('#scene');
    let cur = { ...S[S.mode] };

    const render = () => {
      const m = model(S.H, S.mode, cur, S.footrest);
      scene.setAttribute('viewBox', S.mode === 'sit' ? '-72 26 244 178' : '-72 -6 244 210');
      scene.innerHTML = draw(m);
      $('#backTip').hidden = S.mode !== 'sit';
      const ok = m.checks.filter(c => c.s === 'ok').length;
      $('#score').textContent = `${ok} of 5 good`;
      $('#score').className = 'chip ' + (ok === 5 ? 'ok' : ok >= 3 ? 'warn' : 'bad');
      $('#checks').innerHTML = m.checks.map(c => `
        <div class="item" data-n="${c.n}"><span class="badge ${c.s}">${c.n}</span>
          <div class="t"><b>${esc(c.title)}</b><small>${esc(c.hint)}</small></div>
          ${c.s === 'ok' ? `<span style="color:var(--ok);width:18px">${icon('tick')}</span>` : ''}</div>`).join('');
    };

    const ctlLabels = { seat: 'Chair height', desk: 'Desk height', screen: 'Screen height (top)', dist: 'Screen distance' };
    const buildControls = () => {
      const r = RANGES[S.mode];
      $('#ctl').innerHTML = Object.keys(r).map(k => `
        <div class="slider"><label>${ctlLabels[k]}</label><output id="o-${k}"></output>
          <input type="range" id="r-${k}" min="${r[k][0]}" max="${r[k][1]}" step="1" value="${Math.round(S[S.mode][k])}"></div>`).join('') +
        (S.mode === 'sit' ? `<div class="row"><span class="t" style="flex:1;font-size:13px;font-weight:550">Footrest</span>${toggleHTML('foot', S.footrest)}</div>` : '');
      Object.keys(r).forEach(k => {
        const inp = $('#r-' + k);
        paintRange(inp);
        $('#o-' + k).textContent = inp.value + ' cm';
        inp.addEventListener('input', () => {
          S[S.mode][k] = cur[k] = +inp.value;
          $('#o-' + k).textContent = inp.value + ' cm';
          render(); save();
        });
      });
      const foot = $('#foot');
      if (foot) foot.addEventListener('change', () => { S.footrest = foot.checked; render(); save(); });
      const id = ideal(S.H, S.mode);
      $('#note').innerHTML = S.mode === 'sit'
        ? `For ${S.H} cm, a good starting point: chair <b>${id.seat} cm</b>, desk/keyboard <b>${id.desk} cm</b>, screen top <b>${id.screen} cm</b> from the floor, screen <b>${id.dist} cm</b> away. Fine-tune by feel.`
        : `Standing at ${S.H} cm: desk at <b>${id.desk} cm</b> (elbow height), screen top <b>${id.screen} cm</b>, about <b>${id.dist} cm</b> away. Change position regularly rather than standing for long periods.`;
    };

    const syncSliders = () => {
      for (const k in RANGES[S.mode]) {
        const inp = $('#r-' + k);
        if (!inp) continue;
        inp.value = Math.round(cur[k]);
        inp.dispatchEvent(new Event('input-paint'));
        inp.style.setProperty('--p', ((inp.value - inp.min) / (inp.max - inp.min) * 100) + '%');
        $('#o-' + k).textContent = Math.round(cur[k]) + ' cm';
      }
    };

    let saveT = 0;
    const save = () => { clearTimeout(saveT); saveT = setTimeout(() => setUi({ posture: { H: S.H, mode: S.mode, footrest: S.footrest, sit: S.sit, stand: S.stand } }), 500); };

    const hIn = $('#H');
    hIn.value = S.H;
    paintRange(hIn);
    $('#oH').textContent = S.H + ' cm';
    hIn.addEventListener('input', () => { S.H = +hIn.value; $('#oH').textContent = S.H + ' cm'; buildControls(); render(); save(); });

    wireSeg(root, 'mode', v => {
      S.mode = v;
      buildControls();
      const target = { ...S[v] };
      // morph between sitting and standing: start from the current setup mapped to the other mode
      cur = { ...target };
      render(); save();
    });

    $('#fit').addEventListener('click', () => {
      const t = ideal(S.H, S.mode);
      Object.assign(S[S.mode], t);
      if (S.mode === 'sit') S.footrest = false;
      const foot = $('#foot'); if (foot) foot.checked = false;
      tween(cur, t, () => { render(); syncSliders(); }, 900);
      save();
    });

    // hovering a number in the picture highlights its row, and the other way round
    const hl = n => root.querySelectorAll('[data-n]').forEach(e => e.style.opacity = !n || e.dataset.n === n ? 1 : .35);
    root.addEventListener('mouseover', e => { const t = e.target.closest('[data-n]'); hl(t ? t.dataset.n : null); });
    root.addEventListener('mouseout', () => hl(null));

    buildControls();
    render();
  },
};
