// Today: the live 20-20-20 ring, the four essentials from the guide, and today's numbers.
import { S, onState, post, go, liveNextEye, clock, duration, ringSVG, setRing, toast, refresh, ASSISTANT, esc, ui } from './core.js';
import { avatarSVG, stripesSVG } from './logo.js';
import { icon } from './icons.js';
import { ESSENTIALS, CHECKLIST, COMMITMENT, MK } from './content.js';

// Small looping illustrations for the four essentials.
const ART = {
  light: `<svg viewBox="0 0 200 92"><g transform="translate(100 46)">
      <g class="spin-hand" style="transform-origin:0 0;animation-duration:18s">${[0, 45, 90, 135, 180, 225, 270, 315].map(a =>
        `<line x1="0" y1="-30" x2="0" y2="-38" stroke="var(--c-light)" stroke-width="4" stroke-linecap="round" transform="rotate(${a})"/>`).join('')}</g>
      <circle r="22" fill="var(--c-light)"/><text y="5" text-anchor="middle" font-size="13" font-weight="800" fill="#fff">500</text></g></svg>`,
  // a sit-stand desk that rises while the person stands up, then sits back down
  move: `<svg viewBox="0 0 200 92"><g transform="translate(52 4)">
      <line x1="0" y1="84" x2="100" y2="84" stroke="var(--floor)" stroke-width="2"/>
      <g style="animation:ssChair 6s infinite"><path d="M14 60h22M16 60v-20M25 60v20M16 82h18" stroke="var(--chair)" stroke-width="4" stroke-linecap="round" fill="none"/></g>
      <g style="animation:ssSit 6s infinite"><circle cx="26" cy="26" r="7" fill="var(--fig)"/>
        <path d="M26 34v22h18v24" stroke="var(--fig)" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
        <path d="M27 42l8 9h14" stroke="var(--fig-2)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" fill="none"/></g>
      <g style="animation:ssStand 6s infinite"><circle cx="34" cy="10" r="7" fill="var(--fig)"/>
        <path d="M34 18v30M34 48l-2 34M34 48l3 34" stroke="var(--fig)" stroke-width="7" stroke-linecap="round" fill="none"/>
        <path d="M35 26l6 12h12" stroke="var(--fig-2)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" fill="none"/></g>
      <g style="animation:ssDesk 6s infinite"><rect x="50" y="52" width="44" height="4" rx="2" fill="var(--deskc-2)"/><rect x="80" y="30" width="4" height="22" rx="1" fill="var(--screen)"/></g>
      <rect x="86" y="56" width="4" height="28" fill="var(--deskc-2)" opacity=".7"/>
    </g><style>
      @keyframes ssSit{0%,40%{opacity:1}50%,90%{opacity:0}100%{opacity:1}}
      @keyframes ssStand{0%,40%{opacity:0}50%,90%{opacity:1}100%{opacity:0}}
      @keyframes ssChair{0%,40%{opacity:1}50%,90%{opacity:.25}100%{opacity:1}}
      @keyframes ssDesk{0%,40%{transform:translateY(0)}50%,90%{transform:translateY(-14px)}100%{transform:translateY(0)}}</style></svg>`,
  // the guide's side view in miniature: eye line to the top of the screen, elbow at 90°
  posture: `<svg viewBox="0 0 200 92"><g transform="translate(56 2)">
      <line x1="0" y1="86" x2="100" y2="86" stroke="var(--floor)" stroke-width="2"/>
      <path d="M8 62h22M10 62v-22M18 62v22" stroke="var(--chair)" stroke-width="4" stroke-linecap="round" fill="none"/>
      <circle cx="22" cy="20" r="8" fill="var(--fig)"/>
      <path d="M21 29v29h20v26" stroke="var(--fig)" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
      <path d="M22 37v14h18" stroke="var(--fig-2)" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
      <path d="M22 45a6 6 0 0 0 6 6" stroke="var(--c-posture)" stroke-width="1.8" fill="none"/>
      <line x1="29" y1="18" x2="80" y2="18" stroke="var(--c-posture)" stroke-width="2" class="gaze"/>
      <rect x="80" y="17" width="4" height="26" rx="1.5" fill="var(--screen)"/><rect x="81" y="43" width="2" height="9" fill="var(--chair-2)"/>
      <rect x="36" y="52" width="58" height="4" rx="2" fill="var(--deskc-2)"/><rect x="88" y="56" width="4" height="30" fill="var(--deskc-2)" opacity=".7"/>
    </g></svg>`,
  eyes: `<svg viewBox="0 0 200 92"><g transform="translate(46 22)">
      <g class="blink"><path d="M0 24 Q26 0 52 24 Q26 48 0 24Z" fill="#fff" stroke="var(--c-eyes)" stroke-width="3"/><circle cx="26" cy="24" r="9" fill="var(--c-eyes)"/></g>
      <line x1="58" y1="24" x2="100" y2="24" stroke="var(--c-eyes)" stroke-width="2.5" class="gaze"/>
      <circle cx="108" cy="16" r="8" fill="var(--tree)"/><rect x="106.5" y="20" width="3" height="12" fill="var(--tree)"/>
      <text x="80" y="46" text-anchor="middle" font-size="10" font-weight="700" fill="var(--c-eyes)">6 m · 20 s</text></g></svg>`,
};

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? 'Working late' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

export default {
  id: 'home', title: 'Today', icon: 'home', color: 'var(--c-home)',
  mount(root) {
    root.innerHTML = `
      <div class="hero">
        ${stripesSVG()}
        <div class="big-ring" id="ring">${ringSVG(0, { color: MK ? 'var(--lime)' : 'var(--c-eyes)', track: MK ? 'rgba(255,255,255,.18)' : 'var(--line-2)' })}
          <div class="center"><div><b id="next">--:--</b><span id="nextLbl">until eye break</span></div></div></div>
        <div>
          <div class="kicker" style="--k:${MK ? 'var(--lime)' : 'var(--c-eyes)'}">20-20-20</div>
          <h2 id="greet">${greeting()}</h2>
          <p class="muted mt-s" id="heroText" style="max-width:420px"></p>
          <div class="row wrap mt">
            <button class="btn primary big" id="restNow">${icon('eye')}Rest my eyes now</button>
            <button class="btn big" id="pauseBtn">${icon('pause')}<span>Pause 1 hour</span></button>
          </div>
        </div>
        <div class="row" style="align-items:flex-end;gap:12px;max-width:290px">
          <div class="card" style="padding:12px 14px;font-size:13px;color:var(--text)" id="bubble"></div>
          <div style="width:58px;flex:none;cursor:default" id="heroAv" title="Ask ${ASSISTANT}">${avatarSVG()}</div>
        </div>
      </div>

      <h2 style="font-size:18px;margin:26px 0 12px">The four essentials</h2>
      <div class="grid g4">${ESSENTIALS.map(e => `
        <div class="card ess" data-go="${e.page}" style="--c:${e.color}">
          <div class="art">${ART[e.id]}</div>
          <b>${e.title}</b><span>${e.text}</span>
        </div>`).join('')}</div>

      <div class="grid g4 mt" style="grid-template-columns:1fr 1fr 1fr 1.4fr">
        <div class="card stat"><span>Eye breaks today</span><b id="sTaken">0</b><span id="sTakenOf"></span></div>
        <div class="card stat"><span>Screen time today</span><b id="sActive">0 min</b><span>counted only while you use the PC</span></div>
        <div class="card stat" data-go="check" style="cursor:default"><span>Workspace self-check</span><b id="sCheck">0 / 8</b><span id="sCheckLbl">Take a minute to review</span></div>
        <div class="card"><span class="muted small">Eye breaks this week</span><div class="bars mt-s" id="bars"></div><div class="bar-labels" id="barLbl"></div></div>
      </div>

      <div class="callout mt">${icon('heart')}<div><b>Our commitment.</b> <span class="muted">${COMMITMENT}</span></div></div>
    `;
    const $ = s => root.querySelector(s);
    root.querySelectorAll('[data-go]').forEach(c => c.addEventListener('click', () => go(c.dataset.go)));
    $('#heroAv').addEventListener('click', () => go('assistant'));
    $('#restNow').addEventListener('click', async () => {
      await post('eye-now');
      toast('Look into the distance — the timer is in the corner of your screen');
    });
    $('#pauseBtn').addEventListener('click', async () => {
      const paused = S.state && S.state.paused;
      await post('pause', { minutes: paused ? 0 : 60 });
      toast(paused ? 'Reminders are back on' : 'Reminders paused for 1 hour');
      refresh();
    });

    const ringSvg = $('#ring svg');
    const tickNext = () => {
      const st = S.state;
      if (!st) return;
      const n = liveNextEye();
      const on = st.settings.eyeEnabled;
      $('#next').textContent = !on ? 'Off' : st.paused ? 'Paused' : clock(n);
      $('#nextLbl').textContent = !on ? 'eye reminders' : st.paused ? 'reminders' : st.away ? 'you are away' : 'until eye break';
      setRing(ringSvg, on && !st.paused ? 1 - n / st.eyeIntervalSec : 0);
    };
    const timer = setInterval(tickNext, 1000);

    const unsub = onState(st => {
      tickNext();
      const t = st.today || {};
      const taken = t.eyeTaken || 0, reminded = t.eyeReminded || 0;
      $('#sTaken').textContent = taken;
      $('#sTakenOf').textContent = reminded ? `of ${reminded} reminders` : 'none due yet';
      $('#sActive').textContent = duration(t.activeSec || 0);
      const chk = ui('check', {}).items || {};
      const n = CHECKLIST.filter(c => chk[c.id]).length;
      $('#sCheck').textContent = `${n} / ${CHECKLIST.length}`;
      $('#sCheckLbl').textContent = n === CHECKLIST.length ? 'All good — nice setup' : 'Take a minute to review';
      $('#pauseBtn span').textContent = st.paused ? 'Resume reminders' : 'Pause 1 hour';
      $('#heroText').textContent = st.paused
        ? `Reminders are paused until ${new Date(st.pausedUntil).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}.`
        : `Every ${st.settings.eyeInterval} minutes of screen time, look about 6 metres (20 ft) away for ${st.settings.eyeSeconds} seconds. I'll remind you in the notification area.`;
      const days = Object.entries(st.week || {});
      const max = Math.max(4, ...days.map(([, d]) => d.eyeTaken || 0));
      $('#bars').innerHTML = days.map(([k, d], i) =>
        `<div class="${i === days.length - 1 ? 'today' : ''}" style="height:${Math.max(4, (d.eyeTaken || 0) / max * 100)}%" title="${k}: ${d.eyeTaken || 0} breaks"></div>`).join('');
      $('#barLbl').innerHTML = days.map(([k]) => `<span>${new Date(k + 'T12:00').toLocaleDateString([], { weekday: 'narrow' })}</span>`).join('');
      const tips = [
        taken === 0 ? (st.ai && st.ai.enabled ? `Hi, I'm ${esc(ASSISTANT)}. Try one eye break now — it takes 20 seconds.` : 'Try one eye break now — it takes 20 seconds.') : `${taken} eye break${taken === 1 ? '' : 's'} today. Your eyes say thank you.`,
        n < CHECKLIST.length ? `Your self-check is at ${n} of ${CHECKLIST.length}. Want to finish it?` : 'Your workspace self-check is complete.',
        'Tip: windows to the side of your screen, never behind it.',
      ];
      $('#bubble').innerHTML = tips[Math.floor(Date.now() / 20000) % tips.length];
      $('#heroAv').hidden = !(st.ai && st.ai.enabled);
    });
    this.unmount = () => { clearInterval(timer); unsub(); };
  },
};
