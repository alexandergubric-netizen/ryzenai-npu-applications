// 20-20-20: what it means (three animated tiles), a full-window guided break, and the reminder settings.
import { S, onState, get, post, setSettings, liveNextEye, clock, toggleHTML, segHTML, wireSeg, toast, refresh, reduced, ASSISTANT } from './core.js';
import { icon } from './icons.js';

const TILES = `
  <div class="grid g3 rule3">
    <div class="card"><div class="art"><svg viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="40" fill="none" stroke="var(--line-2)" stroke-width="5"/>
      ${Array.from({ length: 12 }, (_, i) => `<line x1="50" y1="14" x2="50" y2="${i % 3 ? 18 : 21}" stroke="var(--text-3)" stroke-width="2" transform="rotate(${i * 30} 50 50)"/>`).join('')}
      <line x1="50" y1="50" x2="50" y2="28" stroke="var(--text)" stroke-width="4" stroke-linecap="round"/>
      <g class="spin-hand"><line x1="50" y1="50" x2="50" y2="18" stroke="var(--c-eyes)" stroke-width="2.5" stroke-linecap="round"/></g>
      <circle cx="50" cy="50" r="4" fill="var(--c-eyes)"/></svg></div>
      <div class="num">20</div><div class="unit">minutes</div><p class="muted small mt-s">Take a short break from your screen every 20 minutes.</p></div>
    <div class="card"><div class="art"><svg viewBox="0 0 180 100">
      <g class="blink"><path d="M8 50 Q32 26 56 50 Q32 74 8 50Z" fill="#fff" stroke="var(--c-eyes)" stroke-width="3"/><circle cx="34" cy="50" r="9" fill="var(--c-eyes)"/></g>
      <line x1="62" y1="50" x2="140" y2="50" stroke="var(--c-eyes)" stroke-width="2.5" class="gaze"/>
      <path d="M140 72 Q155 60 172 72Z" fill="var(--hill1)"/><circle cx="156" cy="44" r="11" fill="var(--tree)"/><rect x="154" y="52" width="4" height="16" fill="var(--tree)"/>
      <text x="100" y="40" text-anchor="middle" font-size="11" font-weight="700" fill="var(--c-eyes)">6 m</text></svg></div>
      <div class="num">20</div><div class="unit">feet (6 metres)</div><p class="muted small mt-s">Look at something about 20 feet, or 6 metres, away.</p></div>
    <div class="card"><div class="art"><svg viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="38" fill="none" stroke="var(--line-2)" stroke-width="7"/>
      <circle class="count-ring" cx="50" cy="50" r="38" fill="none" stroke="var(--c-eyes)" stroke-width="7" stroke-linecap="round" stroke-dasharray="238.8"/>
      <text x="50" y="58" text-anchor="middle" font-size="24" font-weight="800" fill="var(--text)">20s</text></svg></div>
      <div class="num">20</div><div class="unit">seconds</div><p class="muted small mt-s">Keep your gaze there for at least 20 seconds.</p></div>
  </div>`;

/** Full-window guided break with a drifting landscape to rest the eyes on. */
export function focusBreak(seconds, onDone) {
  const ov = document.createElement('div');
  ov.className = 'focus-overlay';
  ov.innerHTML = `
    <svg class="land" viewBox="0 0 1200 400" preserveAspectRatio="xMidYMax slice">
      <circle cx="930" cy="90" r="48" fill="var(--sun)" opacity=".9"/>
      <g class="drift1"><path d="M-100 260 Q150 170 400 240 T900 220 T1400 250 V400 H-100Z" fill="var(--hill1)"/>
        <g transform="translate(560 180)"><rect x="-4" y="10" width="8" height="40" fill="var(--tree)"/><circle r="26" fill="var(--tree)"/></g></g>
      <g class="drift2"><path d="M-100 320 Q250 260 600 315 T1400 300 V400 H-100Z" fill="var(--hill2)"/></g>
    </svg>
    <button class="btn fo-close" id="foClose">${icon('x')}Stop</button>
    <div class="fo-center">
      <h2 id="foT">Look at something far away</h2>
      <div class="fo-count" id="foN">${seconds}</div>
      <p id="foS">About 6 metres (20 ft) — out of the window is perfect. Blink slowly.</p>
    </div>`;
  document.body.appendChild(ov);
  const t0 = Date.now();
  const lines = ['Blink slowly…', 'Relax your shoulders…', 'Let your eyes soften…', 'Breathe out slowly…'];
  const iv = setInterval(() => {
    const left = Math.ceil(seconds - (Date.now() - t0) / 1000);
    ov.querySelector('#foN').textContent = Math.max(0, left);
    ov.querySelector('#foS').textContent = left > seconds - 3 ? 'About 6 metres (20 ft) — out of the window is perfect.' : lines[Math.floor((seconds - left) / 5) % lines.length];
    if (left <= 0) {
      clearInterval(iv);
      ov.querySelector('#foT').textContent = 'Eyes rested';
      ov.querySelector('#foN').innerHTML = `<span style="color:var(--ok)">✓</span>`;
      ov.querySelector('#foS').textContent = 'Nice. See you in 20 minutes.';
      onDone && onDone();
      setTimeout(() => ov.remove(), 1800);
    }
  }, 250);
  ov.querySelector('#foClose').onclick = () => { clearInterval(iv); ov.remove(); };
}

export default {
  id: 'eyes', title: 'Eye breaks', icon: 'eye', color: 'var(--c-eyes)',
  mount(root) {
    root.innerHTML = `
      <div class="page-head"><div class="grow">
        <div class="kicker" style="--k:var(--c-eyes)">Regular breaks</div>
        <h1>The 20-20-20 rule</h1>
        <p>Short, frequent breaks reduce eye strain and keep you comfortable. ${S.state && S.state.ai && S.state.ai.enabled ? ASSISTANT : 'Postura'} reminds you in the Windows notification area — counting only the time you actually use the PC.</p>
      </div></div>
      ${TILES}
      <div class="grid mt" style="grid-template-columns:minmax(0,1fr) minmax(0,1.2fr)">
        <div class="card stack" style="gap:12px">
          <div class="row"><div class="tip" style="flex:1"><div class="ti" style="--c:var(--c-eyes)">${icon('bell')}</div><div><h3 id="stT">Next eye break</h3><div class="muted" id="stS"></div></div></div>
            <b style="font:700 30px var(--font-display);font-variant-numeric:tabular-nums" id="stN"></b></div>
          <div class="row wrap">
            <button class="btn primary" id="tryNow">${icon('play')}Try a break now</button>
            <button class="btn" id="floatNow">${icon('eye')}Floating timer</button>
            <button class="btn" id="pause"></button>
          </div>
          <p class="small muted">Reminders have <b>Start timer</b> and <b>Snooze</b> buttons. If you simply look away from the screen for <span id="secs">20</span> seconds after a reminder, it counts as a break too.</p>
          <div class="callout" id="nStatus" style="padding:10px 14px"></div>
          <div class="row wrap"><button class="btn ghost" id="test">${icon('send')}Send me a test reminder</button>
            <button class="btn ghost" id="nSettings" hidden>${icon('gear')}Windows notification settings</button></div>
        </div>
        <div class="list" id="opts"></div>
      </div>
      <div class="grid g3 mt">
        <div class="card tip"><div class="ti" style="--c:var(--c-eyes)">${icon('eye')}</div><div><h3>Blink more</h3><p class="muted">We blink up to half as often while reading a screen. Slow, full blinks keep your eyes from drying out.</p></div></div>
        <div class="card tip"><div class="ti" style="--c:var(--c-eyes)">${icon('light')}</div><div><h3>Match the room</h3><p class="muted">Keep screen brightness close to the room’s brightness, and make text large enough to read without leaning in.</p></div></div>
        <div class="card tip"><div class="ti" style="--c:var(--c-eyes)">${icon('info')}</div><div><h3>Not a replacement</h3><p class="muted">Breaks ease strain but don’t replace an eye test. If your eyes often hurt or vision blurs, see an optician.</p></div></div>
      </div>`;
    const $ = s => root.querySelector(s);

    const opts = st => {
      const s = st.settings;
      $('#opts').innerHTML = `
        <div class="item"><div class="t"><b>Eye-break reminders</b><small>A notification every ${s.eyeInterval} minutes of screen time</small></div>${toggleHTML('oOn', s.eyeEnabled)}</div>
        <div class="item"><div class="t"><b>Remind me every</b></div>${segHTML('oInt', [[15, '15'], [20, '20'], [30, '30'], [45, '45'], [60, '60 min']], s.eyeInterval)}</div>
        <div class="item"><div class="t"><b>Break length</b></div>${segHTML('oSec', [[20, '20 s'], [30, '30 s'], [60, '60 s']], s.eyeSeconds)}</div>
        <div class="item"><div class="t"><b>Restart the clock when I’m away</b><small>5 minutes without keyboard or mouse counts as a break</small></div>${toggleHTML('oIdle', s.idleReset)}</div>
        <div class="item"><div class="t"><b>Quiet during full-screen apps</b><small>Presentations, video calls in full screen, games</small></div>${toggleHTML('oBusy', s.skipBusy)}</div>
        <div class="item"><div class="t"><b>Notification sound</b></div>${toggleHTML('oSnd', s.sound)}</div>
        <div class="item"><div class="t"><b>Remind me with</b><small>The card is Postura’s own window in the corner. Windows’ Do not disturb can hide notifications without telling apps, so <b>Both</b> is the safest choice</small></div>${segHTML('oStyle', [['notify', 'Notification'], ['card', 'Card'], ['both', 'Both']], s.remindStyle)}</div>`;
      const bind = (id, key) => $('#' + id).addEventListener('change', e => setSettings({ [key]: e.target.checked }));
      bind('oOn', 'eyeEnabled'); bind('oIdle', 'idleReset'); bind('oBusy', 'skipBusy'); bind('oSnd', 'sound');
      wireSeg(root, 'oStyle', v => setSettings({ remindStyle: v }));
      wireSeg(root, 'oInt', v => setSettings({ eyeInterval: +v }));
      wireSeg(root, 'oSec', v => setSettings({ eyeSeconds: +v }));
    };

    let lastKey = '';
    const status = () => {
      const st = S.state;
      if (!st) return;
      const s = st.settings;
      $('#stN').textContent = !s.eyeEnabled ? 'Off' : st.paused ? '—' : clock(liveNextEye());
      $('#stS').textContent = !s.eyeEnabled ? 'Reminders are switched off' : st.paused ? `Paused until ${new Date(st.pausedUntil).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })}` :
        st.away ? 'You seem to be away — the clock restarts when you’re back' : `of screen time · ${(st.today.eyeTaken || 0)} breaks today`;
      $('#pause').innerHTML = st.paused ? `${icon('play')}Resume` : `${icon('pause')}Pause 1 h`;
      const key = JSON.stringify(s);
      if (key !== lastKey) { lastKey = key; opts(st); $('#secs').textContent = s.eyeSeconds; }
    };
    const unsub = onState(status);
    const iv = setInterval(status, 1000);

    $('#tryNow').onclick = () => focusBreak(S.state ? S.state.settings.eyeSeconds : 20, () => post('eye-done').then(refresh));
    $('#floatNow').onclick = async () => { await post('eye-now'); toast('Timer started in the corner of your screen'); };
    $('#pause').onclick = async () => { await post('pause', { minutes: S.state.paused ? 0 : 60 }); refresh(); };
    // what Windows does with Postura's notifications right now, in plain words
    const showStatus = (n, shown) => {
      const box = $('#nStatus');
      if (!box) return;
      const off = !n.enabled, quiet = n.quiet;
      $('#nSettings').hidden = !(off || quiet);
      const style = S.state && S.state.settings.remindStyle;
      const what = shown === 'card' ? 'The reminder card is in the bottom-right corner of your screen.'
        : shown === 'both' ? 'A notification and the reminder card are in the bottom-right corner.'
        : shown === 'notification' ? 'The notification is in the bottom-right corner (and in the notification centre).' : '';
      box.innerHTML = off
        ? `<div><b>Windows notifications are off for Postura.</b> <span class="muted">Postura shows its own reminder card instead. To get notifications too, switch Postura on in Windows notification settings.</span> ${what}</div>`
        : quiet
          ? `<div><b>Windows is holding notifications back</b> <span class="muted">(a full-screen app or presentation) — they go silently to the notification centre, so Postura shows its reminder card as well.</span> ${what}</div>`
          : `<div><b>Notifications are on.</b> <span class="muted">${style === 'card' ? 'You chose the reminder card.' : style === 'both' ? 'Postura also shows its reminder card, so Do not disturb can’t hide a reminder.' : 'Windows’ Do not disturb may hide them without Postura knowing — choose Both to also get the reminder card.'}</span> ${what}</div>`;
    };
    get('notify-status').then(n => showStatus(n)).catch(() => {});
    $('#nSettings').onclick = () => post('notify-settings');
    $('#test').onclick = async () => {
      const r = await post('test-notify');
      showStatus(r.status, r.shown);
      toast(r.shown === 'notification' ? 'Sent — look at the bottom-right of your screen' : 'Reminder card shown in the bottom-right corner');
    };
    this.unmount = () => { unsub(); clearInterval(iv); };
  },
};
