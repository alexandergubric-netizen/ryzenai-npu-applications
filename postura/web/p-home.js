// Today: the live 20-20-20 ring, the four essentials from the guide, and today's numbers.
import { S, onState, post, go, liveNextEye, clock, duration, ringSVG, setRing, toast, refresh, ASSISTANT, esc, ui, setUi, segHTML, wireSeg } from './core.js';
import { avatarSVG } from './logo.js';
import { sceneSVG, placeSun, growBamboo, phase } from './scene.js';
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
      <div class="hero" id="hero" data-phase="${phase()}">
        ${sceneSVG()}
        <div class="hero-text">
          <h2 id="greet">${greeting()}</h2>
          <div class="hero-clock"><b id="next">--:--</b><span id="nextLbl">until your eyes rest</span></div>
          <p class="hero-sub" id="heroText"></p>
          <div class="row wrap mt">
            <button class="btn primary big" id="restNow">${icon('eye')}Rest my eyes now</button>
            <button class="btn big" id="pauseBtn">${icon('pause')}<span>Pause 1 hour</span></button>
          </div>
        </div>
        <div class="hero-note" id="grown"></div>
      </div>
      <div class="hero-tip"><span class="av" id="heroAv" title="Ask ${ASSISTANT}">${avatarSVG()}</span><span id="bubble"></span></div>

      <h2 style="font-size:18px;margin:26px 0 12px">The four essentials</h2>
      <div class="grid g4" style="gap:22px">${ESSENTIALS.map(e => `
        <div class="ess" data-go="${e.page}" style="--c:${e.color}">
          <div class="art">${ART[e.id]}</div>
          <b>${e.title}</b><span>${e.text}</span>
        </div>`).join('')}</div>

      <div class="card stats mt" style="margin-top:28px">
        <div class="stat"><span>Eye breaks today</span><b id="sTaken">0</b><span id="sTakenOf"></span></div>
        <div class="stat"><span>Screen time today</span><b id="sActive">0 min</b><span>counted only while you use the PC</span></div>
        <div class="stat" data-go="move" style="cursor:default"><span>Moves today</span><b id="sMoves">0</b><span id="sMovesLbl"></span></div>
        <div class="stat" data-go="check" style="cursor:default"><span>Workspace self-check</span><b id="sCheck">0 / 8</b><span id="sCheckLbl">Take a minute to review</span></div>
      </div>

      <div class="card mt">
        <div class="row"><h2 style="flex:1;font-size:18px">Your progress</h2>${segHTML('pRange', [[7, 'Week'], [30, '30 days']], ui('progressDays', 7))}</div>
        <div class="progress-chips mt-s" id="pChips"></div>
        <div class="bars tall mt" id="bars"></div><div class="bar-labels" id="barLbl"></div>
        <div class="small muted mt-s">Your grove: one stalk a day, as tall as the eye breaks you took. Hover a stalk for that day’s screen time, moves and stretches.</div>
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

    // the last 7 or 30 days from the kept history (Postura keeps 40 days)
    let range = +ui('progressDays', 7) === 30 ? 30 : 7;
    const dayKey = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    let progressKey = '';
    const progress = st => {
      const hist = st.history || {};
      // drawn again only when the numbers change, so the grove grows in once and then stands still
      const key = range + JSON.stringify(hist);
      if (key === progressKey) return;
      progressKey = key;
      const at = i => { const d = new Date(); d.setDate(d.getDate() - i); return d; };
      const days = [];
      for (let i = range - 1; i >= 0; i--) { const d = at(i); days.push([d, hist[dayKey(d)] || {}]); }
      const sum = k => days.reduce((n, [, d]) => n + (d[k] || 0), 0);
      const taken = sum('eyeTaken'), reminded = sum('eyeReminded'), used = days.filter(([, d]) => (d.activeSec || 0) > 0).length;
      // days in a row with at least one eye break, ending today (or yesterday, while today is still young)
      let streak = 0;
      for (let i = 0; i < 40; i++) {
        const n = (hist[dayKey(at(i))] || {}).eyeTaken || 0;
        if (n > 0) streak++; else if (i > 0) break;
      }
      const chips = [
        streak > 1 ? `<span class="chip ok">${streak}-day streak</span>` : '',
        `<span class="chip">${taken} eye break${taken === 1 ? '' : 's'}</span>`,
        reminded ? `<span class="chip">${Math.min(100, Math.round(taken / reminded * 100))}% of reminders followed</span>` : '',
        used ? `<span class="chip">${duration(sum('activeSec') / used)} screen time a day</span>` : '',
        sum('moveTaken') + sum('stretches') ? `<span class="chip">${sum('moveTaken')} moves · ${sum('stretches')} stretches</span>` : '',
      ].filter(Boolean);
      $('#pChips').innerHTML = chips.join('');
      const max = Math.max(4, ...days.map(([, d]) => d.eyeTaken || 0));
      $('#bars').className = 'bars tall grove mt' + (range === 30 ? ' month' : '');
      $('#bars').innerHTML = days.map(([day, d], i) => {
        const n = d.eyeTaken || 0;
        const tip = `${day.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })}: ${n} of ${d.eyeReminded || 0} eye breaks · ${duration(d.activeSec || 0)} screen time · ${d.moveTaken || 0} moves · ${d.stretches || 0} stretches`;
        return `<div class="${i === days.length - 1 ? 'today' : ''}${n ? '' : ' none'}" style="height:${Math.max(4, n / max * 100)}%;--i:${i}" title="${tip}"></div>`;
      }).join('');
      $('#barLbl').style.gap = range === 30 ? '3px' : '';
      $('#barLbl').innerHTML = days.map(([day], i) => `<span>${range === 7 ? day.toLocaleDateString([], { weekday: 'narrow' }) : (day.getDate() === 1 || i === 0 || day.getDay() === 1 ? day.getDate() : '')}</span>`).join('');
    };
    wireSeg(root, 'pRange', v => { range = +v; setUi({ progressDays: range }); if (S.state) progress(S.state); });

    // the scene: the sun crosses the sky as the eye-break clock runs, the sky follows the hour
    const hero = $('#hero'), art = hero.querySelector('.scene-art');
    const tickNext = () => {
      const st = S.state;
      if (!st) return;
      const n = liveNextEye();
      const on = st.settings.eyeEnabled;
      $('#next').textContent = !on ? 'Off' : st.paused ? 'Paused' : clock(n);
      $('#nextLbl').textContent = !on ? 'eye reminders' : st.paused ? 'reminders' : st.away ? 'you are away' : st.holding ? 'waits for your call' : 'until your eyes rest';
      const ph = phase();
      if (hero.dataset.phase !== ph) hero.dataset.phase = ph;
      hero.classList.toggle('resting', !on || st.paused);
      placeSun(art, on && !st.paused ? 1 - n / st.eyeIntervalSec : .5);
    };
    const timer = setInterval(tickNext, 1000);

    const unsub = onState(st => {
      tickNext();
      const t = st.today || {};
      const taken = t.eyeTaken || 0, reminded = t.eyeReminded || 0;
      $('#sTaken').textContent = taken;
      growBamboo(art, taken);
      $('#grown').textContent = taken ? `Today’s bamboo: ${taken} segment${taken === 1 ? '' : 's'}, one for each eye break` : 'Your bamboo grows a segment with every eye break';
      $('#sTakenOf').textContent = reminded ? `of ${reminded} reminders` : 'none due yet';
      $('#sActive').textContent = duration(t.activeSec || 0);
      const chk = ui('check', {}).items || {};
      const n = CHECKLIST.filter(c => chk[c.id]).length;
      $('#sCheck').textContent = `${n} / ${CHECKLIST.length}`;
      $('#sCheckLbl').textContent = n === CHECKLIST.length ? 'All good — nice setup' : 'Take a minute to review';
      $('#pauseBtn span').textContent = st.paused ? 'Resume reminders' : 'Pause 1 hour';
      $('#heroText').textContent = st.paused
        ? `Reminders are paused until ${new Date(st.pausedUntil).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}.`
        : `Every ${st.settings.eyeInterval} minutes of screen time, look about 6 metres (20 ft) away for ${st.settings.eyeSeconds} seconds. The sun sets when it is time.`;
      const moves = (t.moveTaken || 0) + (t.stretches || 0);
      $('#sMoves').textContent = moves;
      $('#sMovesLbl').textContent = !st.settings.moveEnabled && !moves ? 'Move reminder is off' :
        `${t.moveTaken || 0} of ${t.moveReminded || 0} reminders · ${t.stretches || 0} stretch${(t.stretches || 0) === 1 ? '' : 'es'}`;
      progress(st);
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
