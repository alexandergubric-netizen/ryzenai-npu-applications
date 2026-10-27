// Keep moving: sit-stand rhythm, the optional move reminder, and six animated desk stretches.
import { S, onState, post, setSettings, toggleHTML, segHTML, wireSeg, toast, ui, setUi } from './core.js';
import { icon } from './icons.js';

// front-view figure; groups carry the animation classes
function figure(kind) {
  const L = 'class="lim"';
  const head = `<g class="${kind === 'neck' ? 'a-neck' : ''}"><line x1="60" y1="44" x2="60" y2="54" ${L} stroke-width="6"/><circle cx="60" cy="33" r="11" class="fig-fill"/></g>`;
  const torso = `<line x1="60" y1="56" x2="60" y2="100" ${L} stroke-width="16"/>`;
  const legs = `<line x1="55" y1="102" x2="52" y2="142" ${L} stroke-width="9"/><line x1="65" y1="102" x2="68" y2="142" ${L} stroke-width="9"/>`;
  let arms = `<line x1="49" y1="60" x2="41" y2="98" ${L} stroke-width="8"/><line x1="71" y1="60" x2="79" y2="98" ${L} stroke-width="8"/>`;
  if (kind === 'chest') arms = `<g class="a-armL"><line x1="49" y1="60" x2="41" y2="98" ${L} stroke-width="8"/></g><g class="a-armR"><line x1="71" y1="60" x2="79" y2="98" ${L} stroke-width="8"/></g>`;
  if (kind === 'wrist') arms = `<line x1="49" y1="60" x2="41" y2="98" ${L} stroke-width="8"/><line x1="71" y1="60" x2="100" y2="60" ${L} stroke-width="8"/>
      <g class="a-wrist"><line x1="100" y1="60" x2="111" y2="60" ${L} stroke-width="7"/></g>
      <path d="M86 50 q8 -10 18 -2" stroke="var(--c-move)" stroke-width="2" fill="none" stroke-linecap="round"/>`;
  if (kind === 'side') arms = `<line x1="52" y1="58" x2="50" y2="20" ${L} stroke-width="8"/><line x1="68" y1="58" x2="70" y2="20" ${L} stroke-width="8"/>`;
  const floor = `<line x1="20" y1="146" x2="100" y2="146" stroke="var(--floor)" stroke-width="2"/>`;
  if (kind === 'shrug') return `<svg viewBox="0 0 120 150">${floor}${legs}${torso}<g class="a-shrug">${arms}${head}</g></svg>`;
  if (kind === 'side') return `<svg viewBox="0 0 120 150">${floor}${legs}<g class="a-back">${torso}${arms}${head}</g></svg>`;
  if (kind === 'twist') return `<svg viewBox="0 0 120 150">${floor}${legs}<g class="a-twist">${torso}<line x1="49" y1="62" x2="71" y2="66" class="lim" stroke-width="8"/><line x1="71" y1="62" x2="49" y2="66" class="lim" stroke-width="8" opacity=".5"/>${head}</g></svg>`;
  if (kind === 'calf') return `<svg viewBox="0 0 120 150">${floor}<g class="a-calf">${legs}${torso}${arms}${head}</g></svg>`;
  return `<svg viewBox="0 0 120 150">${floor}${legs}${torso}${arms}${head}</svg>`;
}

const STRETCHES = [
  { id: 'neck', title: 'Neck tilt', secs: 30, steps: ['Sit tall, shoulders down.', 'Slowly tilt one ear towards your shoulder.', 'Hold 10 s, then switch sides.'], cues: ['Tilt left…', 'Hold…', 'Back to centre', 'Tilt right…', 'Hold…', 'Centre — well done'] },
  { id: 'shrug', title: 'Shoulder shrugs', secs: 20, steps: ['Lift both shoulders to your ears.', 'Hold for a breath, then let them drop.', 'Repeat 8 times.'], cues: ['Up…', 'Drop…'] },
  { id: 'chest', title: 'Chest opener', secs: 30, steps: ['Raise your arms out to the sides.', 'Squeeze your shoulder blades together.', 'Breathe deeply, then lower slowly.'], cues: ['Arms up and out…', 'Open the chest…', 'Lower slowly…'] },
  { id: 'wrist', title: 'Wrist stretch', secs: 30, steps: ['Stretch one arm out, palm up.', 'Gently pull the fingers back with the other hand.', 'Hold 15 s, then switch hands.'], cues: ['Right hand…', 'Gently…', 'Switch to the left…', 'Hold…'] },
  { id: 'side', title: 'Side stretch', secs: 30, steps: ['Stand and raise both arms overhead.', 'Lean slowly to one side.', 'Hold 10 s each side.'], cues: ['Reach up…', 'Lean left…', 'Lean right…', 'Back to centre'] },
  { id: 'calf', title: 'Calf raises', secs: 30, steps: ['Stand behind your chair, hands on the back.', 'Rise onto your toes, then lower slowly.', 'Repeat 15 times — it wakes up the circulation.'], cues: ['Up on your toes…', 'And down…'] },
];

export default {
  id: 'move', title: 'Keep moving', icon: 'move', color: 'var(--c-move)',
  mount(root) {
    const sitMin = ui('rhythm', 45);
    root.innerHTML = `
      <div class="page-head"><div class="grow">
        <div class="kicker" style="--k:var(--c-move)">Keep moving</div>
        <h1>Alternate sitting and standing</h1>
        <p>A flexible setup encourages movement and keeps your spine in a natural position. Change position regularly rather than staying in one for long periods.</p>
      </div></div>
      <div class="grid" style="grid-template-columns:minmax(0,1.3fr) minmax(0,1fr)">
        <div class="card">
          <div class="row"><h2 style="flex:1">Your day, in rhythm</h2>${segHTML('rh', [[30, 'Sit 30'], [45, 'Sit 45'], [60, 'Sit 60 min']], sitMin)}</div>
          <p class="muted small">Sit, then stand for about 15 minutes — take calls standing, walk to a colleague, refill your water.</p>
          <div class="rhythm" id="rhythm"></div>
          <div class="bar-labels" style="margin-top:6px"><span style="text-align:left">9:00</span><span>11:00</span><span>13:00</span><span>15:00</span><span style="text-align:right">17:00</span></div>
          <div class="row mt" style="gap:18px">
            <div class="chip"><span class="dot" style="background:var(--c-posture)"></span>Sitting</div>
            <div class="chip"><span class="dot" style="background:var(--c-move)"></span>Standing / moving</div>
          </div>
        </div>
        <div class="list" id="mopts"></div>
      </div>
      <h2 style="font-size:18px;margin:26px 0 12px">Two-minute desk stretches</h2>
      <div class="grid g3">${STRETCHES.map(s => `
        <div class="card stretch" data-s="${s.id}">
          <div class="art">${figure(s.id)}<span class="timer" hidden></span></div>
          <div class="row"><h3 style="flex:1">${s.title}</h3><button class="btn" data-go="${s.id}">${icon('play')}${s.secs} s</button></div>
          <ol>${s.steps.map(x => `<li>${x}</li>`).join('')}</ol>
        </div>`).join('')}</div>
      <div class="callout mt">${icon('info')}<div class="muted">Stretch gently and never into pain. If something hurts, stop and ask for advice.</div></div>`;
    const $ = s => root.querySelector(s);

    const rhythm = m => {
      const blocks = [];
      let t = 0;
      while (t < 480) {
        const sit = Math.min(m, 480 - t); blocks.push(['sit', sit]); t += sit;
        if (t >= 480) break;
        const st = Math.min(t >= 210 && t < 270 ? 45 : 15, 480 - t); blocks.push(['stand', st]); t += st;  // lunch walk around midday
      }
      $('#rhythm').innerHTML = blocks.map(([k, d]) => `<div style="flex:${d};background:${k === 'sit' ? 'var(--c-posture)' : 'var(--c-move)'};border-right:2px solid var(--card)" title="${k === 'sit' ? 'Sit' : 'Stand / move'} ${d} min">${d >= 30 ? (k === 'sit' ? 'sit' : 'stand') : ''}</div>`).join('');
    };
    rhythm(sitMin);
    wireSeg(root, 'rh', v => { rhythm(+v); setUi({ rhythm: +v }); });

    let lastKey = '';
    const unsub = onState(st => {
      const s = st.settings, key = s.moveEnabled + '/' + s.moveInterval;
      if (key === lastKey) return;
      lastKey = key;
      $('#mopts').innerHTML = `
        <div class="item"><div class="t"><b>Move reminder</b><small>A notification to stand up or stretch</small></div>${toggleHTML('mOn', s.moveEnabled)}</div>
        <div class="item"><div class="t"><b>Every</b></div>${segHTML('mInt', [[30, '30'], [45, '45'], [60, '60'], [90, '90 min']], s.moveInterval)}</div>
        <div class="item"><div class="t"><b>Try it</b><small>Shows the move notification now</small></div><button class="btn" id="mTest">${icon('send')}Test</button></div>`;
      $('#mOn').addEventListener('change', e => setSettings({ moveEnabled: e.target.checked }));
      wireSeg(root, 'mInt', v => setSettings({ moveInterval: +v }));
      $('#mTest').onclick = async () => { await post('test-move'); toast('Sent — look at the bottom-right of your screen'); };
    });

    // guided stretch timers
    const timers = new Map();
    root.querySelectorAll('[data-go]').forEach(b => b.addEventListener('click', () => {
      const s = STRETCHES.find(x => x.id === b.dataset.go);
      const card = b.closest('.stretch'), tEl = card.querySelector('.timer');
      if (timers.has(s.id)) { clearInterval(timers.get(s.id)); timers.delete(s.id); tEl.hidden = true; b.innerHTML = `${icon('play')}${s.secs} s`; return; }
      const t0 = Date.now();
      tEl.hidden = false;
      b.innerHTML = `${icon('x')}Stop`;
      const tick = () => {
        const el = (Date.now() - t0) / 1000, left = Math.ceil(s.secs - el);
        const cue = s.cues[Math.min(s.cues.length - 1, Math.floor(el / (s.secs / s.cues.length)))];
        tEl.innerHTML = left > 0 ? `${left}s <span class="small muted" style="font-weight:500">${cue}</span>` : '<span style="color:var(--ok)">Done ✓</span>';
        if (left <= 0) {
          clearInterval(timers.get(s.id)); timers.delete(s.id);
          b.innerHTML = `${icon('play')}${s.secs} s`;
          setTimeout(() => { tEl.hidden = true; }, 2500);
        }
      };
      tick();
      timers.set(s.id, setInterval(tick, 250));
    }));
    this.unmount = () => { unsub(); timers.forEach(clearInterval); };
  },
};
