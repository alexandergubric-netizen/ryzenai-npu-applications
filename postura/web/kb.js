// The assistant's brain: a small offline intent matcher over curated ergonomics answers, plus a few commands
// (reminder interval, pause, start a break) and a body-height calculator. No network, no model download.
import { MK, HELP, CABLES, ASSISTANT, LOCAL_RULES, SEEK_HELP, MEASURE_DASH, MEASURE_SENTENCE } from './content.js';
import { ideal } from './p-posture.js';

const SYN = {
  monitor: 'screen', display: 'screen', laptop: 'laptop', notebook: 'laptop', lamp: 'lamp', bulb: 'lamp',
  bright: 'light', brightness: 'light', lighting: 'light', illumination: 'light', dark: 'light', dim: 'light',
  sore: 'pain', ache: 'pain', aching: 'pain', hurt: 'pain', hurts: 'pain', painful: 'pain', stiff: 'pain', stiffness: 'pain', tension: 'pain', tense: 'pain', strain: 'pain', numb: 'pain', tingling: 'pain',
  seat: 'chair', stool: 'chair', table: 'desk', workstation: 'desk', workplace: 'desk', standing: 'stand', stood: 'stand',
  sitting: 'sit', seated: 'sit', sat: 'sit', eye: 'eyes', vision: 'eyes', sight: 'eyes', blurry: 'eyes', blur: 'eyes',
  wrists: 'wrist', hands: 'wrist', hand: 'wrist', fingers: 'wrist', forearm: 'wrist', carpal: 'wrist', rsi: 'wrist',
  shoulders: 'shoulder', neck: 'neck', spine: 'back', lumbar: 'back', backache: 'back', hips: 'hip',
  break: 'break', breaks: 'break', pause: 'pause', rest: 'rest', reminder: 'remind', reminders: 'remind', notification: 'remind', notifications: 'remind', notify: 'remind', alert: 'remind',
  feet: 'foot', legs: 'leg', knees: 'knee', headache: 'headache', migraine: 'headache', keyboard: 'keyboard', keys: 'keyboard', typing: 'keyboard', mice: 'mouse',
  lux: 'lux', lumen: 'lumens', lumens: 'lumens', glare: 'glare', reflection: 'glare', reflections: 'glare', window: 'window', windows: 'window', sun: 'window', daylight: 'window', sunlight: 'window', sunshine: 'window',
  cables: 'cable', wires: 'cable', wire: 'cable', cord: 'cable', cords: 'cable', plug: 'cable', socket: 'cable',
  stretches: 'stretch', stretching: 'stretch', exercise: 'stretch', exercises: 'stretch', yoga: 'stretch',
  hello: 'hi', hey: 'hi', hiya: 'hi', morning: 'hi', thanks: 'thank', thx: 'thank', cheers: 'thank',
  dual: 'two', second: 'two', multiple: 'two', monitors: 'screen', screens: 'screen', glasses: 'glasses', bifocal: 'glasses', varifocal: 'glasses', progressive: 'glasses', spectacles: 'glasses',
  home: 'home', wfh: 'home', remote: 'home', kitchen: 'home', sofa: 'home', couch: 'home', bed: 'home',
  footrest: 'footrest', phone: 'phone', mobile: 'phone', headset: 'headset', calls: 'phone', call: 'phone',
  dry: 'dry', blink: 'blink', blinking: 'blink', tired: 'tired', fatigue: 'tired', sleepy: 'tired',
  water: 'water', drink: 'water', hydration: 'water', private: 'privacy', data: 'privacy', internet: 'privacy', online: 'privacy', offline: 'privacy',
};

const stem = w => {
  if (SYN[w]) return SYN[w];
  let s = w;
  if (s.length > 5 && s.endsWith('ing')) s = s.slice(0, -3);
  else if (s.length > 4 && s.endsWith('ed')) s = s.slice(0, -2);
  else if (s.length > 4 && s.endsWith('ies')) s = s.slice(0, -3) + 'y';
  else if (s.length > 3 && s.endsWith('s') && !s.endsWith('ss')) s = s.slice(0, -1);
  return SYN[s] || s;
};

export function tokens(text) {
  return text.toLowerCase().replace(/[’']/g, "'").replace(/[^a-z0-9'\s-]/g, ' ').split(/[\s-]+/).filter(Boolean).map(stem);
}

function lev(a, b) {
  if (Math.abs(a.length - b.length) > 1) return 9;
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++)
    d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return d[a.length][b.length];
}

const contactList = `<ul>${HELP.contacts.map(c => `<li>${c}</li>`).join('')}</ul>`;
const seekHelp = `<p class="small muted mt-s">This is general guidance, not medical advice. If discomfort keeps coming back, seek advice early — ${SEEK_HELP}</p>`;

// [keywords with weights], answer, actions. Keywords are stemmed tokens; "a b" means both must appear.
const INTENTS = [
  { id: 'hi', k: [['hi', 3], ['good', .5]], a: () => `Hi! I’m ${ASSISTANT}. Ask me about your chair, screen, desk, light, breaks or aches — or tell me your height (like “I’m 182 cm”) and I’ll work out your desk setup.` },
  { id: 'thanks', k: [['thank', 3], ['great', 1], ['awesome', 1], ['helpful', 1]], a: () => 'You’re welcome! Remember: look far away every 20 minutes. 🙂' },
  { id: 'who', k: [['who', 2], ['you', 1], ['name', 1.5], ['what can you', 2], ['help', .8], ['can you do', 2]], a: () => `I’m ${ASSISTANT}, the assistant inside Postura. I run entirely on this PC — no internet. I can:<ul><li>explain good posture, light and breaks</li><li>calculate chair, desk and screen heights from your height</li><li>change your reminders (“remind me every 30 minutes”, “pause for 2 hours”)</li><li>suggest what to adjust when something aches</li></ul>` },
  { id: 'privacy', k: [['privacy', 3], ['track', 2], ['spy', 2], ['collect', 1.5], ['send', 1], ['cloud', 1.5]], a: () => `Postura works completely offline. There’s no account and nothing is sent anywhere: your settings and break counts stay in a small file in your Windows profile. ${ASSISTANT} runs on your PC too.` },

  { id: 'screen-height', k: [['screen', 2], ['height', 1.5], ['high', 1.5], ['low', 1.5], ['level', 1], ['raise', 1], ['position', 1], ['top', 1], ['eye level', 2], ['tilt', 1]], a: () => `Set the <b>top of the screen at or just below eye level</b>, so you look slightly down at the middle of it. A screen that’s too low bends your neck forward; too high makes you tip your head back.<ul><li>Use the monitor’s stand, a riser or a stack of books</li><li>Tilt it back slightly (10–20°)</li></ul>`, act: [['Try it on the model', 'go:posture']] },
  { id: 'screen-distance', k: [['screen', 1.5], ['distance', 2.5], ['far', 1.2], ['close', 1.2], ['away', .6], ['arm', 1.5], ['how far', 3]], a: () => `Keep the screen <b>about an arm’s length away</b> — roughly 50–75 cm. If you lean in to read, make the text bigger (Ctrl + plus) rather than moving closer.`, act: [['Show on the model', 'go:posture']] },
  { id: 'laptop', k: [['laptop', 3], ['macbook', 3], ['surface', 1]], a: () => `A laptop screen is always too low when you type on its keyboard. For longer work:<ul><li>raise the laptop on a stand so the top of the screen is at eye level</li><li>use a separate keyboard and mouse</li><li>or connect an external monitor</li></ul>On the move, change position more often and take your 20-20-20 breaks.` },
  { id: 'two-screens', k: [['two', 2], ['screen', 1.5]], a: () => `With two screens: if you use both equally, put the join right in front of you. If one is your main screen, put it straight ahead and the second to the side, angled in, at the same height.` },
  { id: 'glasses', k: [['glasses', 3], ['lens', 1.5], ['contact', 1]], a: () => `If you wear varifocal or bifocal glasses, you read through the bottom of the lens — so put the screen a little <b>lower</b> than usual and tilt it back, otherwise you’ll tip your head back. Ask your optician about computer glasses if you often have trouble.` },

  { id: 'chair', k: [['chair', 3], ['adjust', 1], ['backrest', 2], ['armrest', 1.5], ['height', .5]], a: () => `Adjust your chair so that:<ul><li><b>your feet rest flat</b> on the floor (or a footrest)</li><li>knees are about level with your hips (~90°)</li><li><b>your lower back is fully supported</b> — use the lumbar support and sit all the way back</li><li>armrests, if any, let your shoulders relax</li></ul>Then set the desk to your elbows, not the other way round.`, act: [['Adjust on the model', 'go:posture']] },
  { id: 'footrest', k: [['footrest', 3], ['foot', 1.5], ['dangle', 2], ['reach', .5], ['floor', 1.5], ['short', 1.5]], a: () => `If your feet don’t reach the floor once your chair is at the right height for the desk, use a <b>footrest</b> so they rest flat. Dangling feet press the back of your thighs and tire your lower back.`, act: [['See it on the model', 'go:posture']] },
  { id: 'desk-height', k: [['desk', 2], ['height', 1.5], ['high', 1], ['low', 1], ['elbow', 2]], a: () => `Your desk (or keyboard) should be at <b>elbow height</b>, so your elbows rest at about 90° and wrists stay straight. Tell me your height and I’ll calculate the numbers.`, act: [['Calculate for 175 cm', 'say:I am 175 cm']] },
  { id: 'sit-stand', k: [['stand', 2.5], ['sit', 1.5], ['alternate', 2], ['switch', 1.5], ['how long', 2], ['all day', 1.5], ['long', 1], ['desk', .5], ['standing desk', 2]], a: () => `Alternate between sitting and standing during the day — <b>change position regularly</b> rather than staying in one for long. A good start: sit 30–45 minutes, then stand or move for about 15. Take calls standing and walk when you can.<br>Standing desk: set it to elbow height and stand tall with your weight on both feet.`, act: [['Plan my rhythm', 'go:move'], ['Turn on move reminders', 'do:moveOn']] },
  { id: 'reach', k: [['reach', 2.5], ['keyboard', 2], ['mouse', 3], ['placement', 1], ['place', .8], ['where', .6], ['close', 1], ['stretch out', 1], ['overreach', 2], ['item', 1]], a: () => `Keep your keyboard and mouse <b>close and in front of you</b>, so your elbows stay by your sides. Put things you use often (phone, notebook) within arm’s reach, and everything else further away.`, act: [['Workstation setup', 'go:workspace']] },
  { id: 'wrist-rest', k: [['wrist rest', 3], ['wrist', 1], ['pad', 1.5], ['vertical mouse', 3], ['ergonomic mouse', 3], ['ergonomic keyboard', 3]], a: () => `Keep wrists straight and floating while you type; a wrist rest is for resting <i>between</i> bursts of typing. An ergonomic or vertical mouse can help some people — try it before buying many gadgets: position and breaks matter most.` },
  { id: 'phone', k: [['phone', 3], ['headset', 2.5]], a: () => `Don’t cradle the phone between ear and shoulder. Use a headset for calls, and take calls standing up when you can — an easy way to change position.` },
  { id: 'home', k: [['home', 3], ['office', .5]], a: () => `The same principles apply at home: screen at eye level, elbows ~90°, feet supported, good light, regular breaks. Avoid working for long on a sofa or bed. A laptop stand with a separate keyboard and mouse makes a kitchen table workable.` },
  { id: 'posture', k: [['posture', 3], ['sit', 1], ['neutral', 2], ['correct', 1], ['properly', 1], ['how', .3]], a: () => `Neutral posture, in five points:<ul><li>1 · top of the screen at or just below eye level</li><li>2 · screen about an arm’s length away</li><li>3 · elbows relaxed at about 90°, wrists straight</li><li>4 · lower back supported (sitting) / weight on both feet (standing)</li><li>5 · feet flat on the floor or a footrest</li></ul>`, act: [['Open the posture model', 'go:posture']] },

  { id: 'light', k: [['light', 2.5], ['lux', 3], ['how much', .5]], a: () => `Aim for <b>at least 500 lux</b> at desk level, with no glare. Use daylight where you can, with windows to the side of the screen, and add a task lamp if it’s too dim. To actually measure it you need a calibrated light meter${MEASURE_DASH}. ${LOCAL_RULES.startsWith('These') ? 'Where local rules set a higher level, the local requirement applies.' : ''}`, act: [['Try the light room', 'go:light']] },
  { id: 'lumens', k: [['lumens', 3], ['lux', 1], ['measure', 2], ['meter', 2], ['app', 1]], a: () => `<b>Lux</b> measures the light that reaches your desk; <b>lumens</b> describe how much a lamp puts out. Phone apps only give a rough idea: a reliable measurement needs a <b>calibrated light meter</b>.${MEASURE_SENTENCE} The lux meter in Postura is orientational only — a calculation, not a measurement.` },
  { id: 'glare', k: [['glare', 3], ['window', 2.6], ['behind', 1.5], ['reflect', 2], ['shine', 1.5]], a: () => `Place your screen so windows are <b>to the side</b>, not directly in front of or behind it. A bright window behind the screen makes your eyes keep adjusting; a window behind you reflects on the screen. Blinds help when the sun is low.`, act: [['See it in the light room', 'go:light']] },
  { id: 'lamp', k: [['lamp', 3], ['task', 1]], a: () => `If daylight is not enough, or creates shadows or glare, add an <b>adjustable task lamp</b>. Place it on the side opposite your writing hand and point it at the desk, not the screen.` },

  { id: '2020', k: [['20', 2], ['rule', 2], ['202020', 3], ['20-20-20', 3], ['why', .5]], a: s => `The <b>20-20-20 rule</b>: every <b>20 minutes</b>, look at something about <b>20 feet (6 metres)</b> away for at least <b>20 seconds</b>. Focusing on a screen keeps your eye muscles working; looking far away lets them relax. I remind you every ${s.settings.eyeInterval} minutes of screen time.`, act: [['Try a 20-second break', 'do:focus'], ['Reminder settings', 'go:eyes']] },
  { id: 'eyes', k: [['eyes', 3], ['dry', 2], ['blink', 2], ['tired', 1], ['eye strain', 1.5]], a: () => `For tired or dry eyes:<ul><li>follow the 20-20-20 rule</li><li>blink slowly and fully — we blink much less at screens</li><li>check for glare and match screen brightness to the room</li><li>make text larger rather than leaning in</li></ul>If your eyes often hurt or your vision blurs, have an eye test.` + seekHelp, act: [['Rest my eyes now', 'do:focus']] },
  { id: 'headache', k: [['headache', 3]], a: () => `Screen-related headaches often come from eye strain, glare, a screen that’s too close, or a tense neck. Check the light (500 lux, no glare), take 20-20-20 breaks, drink water and relax your shoulders.` + seekHelp },
  { id: 'breaks', k: [['break', 2.5], ['often', 1], ['how often', 2], ['rest', 1.5]], a: () => `Short, frequent breaks work better than one long one. Every 20 minutes rest your eyes for 20 seconds; every 30–60 minutes stand up, stretch or walk a little.`, act: [['Show stretches', 'go:move']] },
  { id: 'stretch', k: [['stretch', 3], ['exercise', 2], ['move', 1.5]], a: () => `Try these at your desk: neck tilts, shoulder shrugs, a chest opener, wrist stretches, a side stretch and calf raises. Each takes under a minute — never stretch into pain.`, act: [['Open stretches', 'go:move']] },
  { id: 'water', k: [['water', 3]], a: () => `Keep a glass of water on your desk — just outside easy reach. Refilling it is a natural reason to stand up and move.` },

  { id: 'pain-neck', k: [['neck', 3], ['pain', 1]], a: () => `Neck discomfort usually means you look down or forward a lot:<ul><li>raise the screen so its top is at eye level</li><li>bring it to an arm’s length so you don’t poke your chin forward</li><li>with a laptop, use a stand and a separate keyboard</li><li>try gentle neck tilts every hour</li></ul>` + seekHelp, act: [['Check my screen', 'go:posture']] },
  { id: 'pain-shoulder', k: [['shoulder', 3], ['pain', 1]], a: () => `Shoulder tension often comes from a desk that’s too high, or a mouse that’s too far away:<ul><li>desk at elbow height, shoulders relaxed</li><li>mouse right next to the keyboard</li><li>headset instead of cradling the phone</li><li>shoulder shrugs and a chest opener</li></ul>` + seekHelp, act: [['Workstation setup', 'go:workspace']] },
  { id: 'pain-back', k: [['back', 3], ['pain', 1], ['lower', 1]], a: () => `For lower-back discomfort:<ul><li>sit all the way back so the backrest supports your lower back</li><li>feet flat (footrest if needed)</li><li>alternate between sitting and standing</li><li>don’t lean towards a far or low screen</li></ul>` + seekHelp, act: [['Adjust on the model', 'go:posture'], ['Turn on move reminders', 'do:moveOn']] },
  { id: 'pain-wrist', k: [['wrist', 3], ['pain', 1]], a: () => `For wrists and hands:<ul><li>elbows at about 90°, wrists straight — not bent up or down</li><li>keyboard and mouse close, so your elbows stay by your sides</li><li>use keyboard shortcuts to reduce mouse use</li><li>wrist stretches and short pauses</li></ul>Numbness or tingling that doesn’t go away needs a professional opinion.` + seekHelp, act: [['Wrist stretch', 'go:move']] },
  { id: 'pain-legs', k: [['leg', 2.5], ['knee', 2.5], ['hip', 2], ['foot', 1], ['pain', 1], ['swollen', 2]], a: () => `For legs and hips: keep feet flat and knees about level with hips, don’t cross your legs for long, and stand up regularly. Calf raises help circulation.` + seekHelp },
  { id: 'pain', k: [['pain', 2]], a: () => `I’m sorry to hear that. Where do you feel it — neck, shoulders, back, wrists or eyes? Small adjustments often make a big difference.` + seekHelp },
  { id: 'help-contact', k: [['contact', 3.2], ['who', 1], ['talk', 1.5], ['speak', 1.5], ['manager', 2], ['doctor', 2], ['physio', 2]], a: () => `${HELP.text}${contactList}` },
  { id: 'cables', k: [['cable', 3], ['trip', 2]], a: () => `<b>${CABLES.title}.</b> ${CABLES.text}` },
  { id: 'selfcheck', k: [['check', 2], ['checklist', 3], ['review', 1.5], ['new desk', 3], ['hot desk', 3], ['self', 1], ['moved', 1.5], ['move to', 1]], a: () => `Take a minute to review your setup whenever you change desk or location — the self-check has the eight points.`, act: [['Open the self-check', 'go:check']] },
];

const ROUND = [5, 10, 15, 20, 25, 30, 40, 45, 50, 60, 75, 90, 120];

function parseHeight(t) {
  let m = t.match(/(\d)\s*(?:'|ft|feet|foot)\s*(\d{1,2})?/);
  if (m && /tall|height|i'?m|i am|ft|feet|'/.test(t)) {
    const cm = Math.round((+m[1] * 12 + (+m[2] || 0)) * 2.54);
    if (cm >= 140 && cm <= 215) return cm;
  }
  m = t.match(/(1\.\d{2}|\d{3})\s*(cm|m\b|centimet)?/);
  if (m) {
    const v = m[1].includes('.') ? Math.round(parseFloat(m[1]) * 100) : +m[1];
    if (v >= 140 && v <= 215 && (m[2] || /tall|height|i'?m|i am|my/.test(t))) return v;
  }
  return null;
}

function parseMinutes(t) {
  const h = t.match(/(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours)\b/);
  if (h) return Math.round(parseFloat(h[1]) * 60);
  if (/half an hour|30 ?min/.test(t)) return 30;
  if (/an hour|one hour|1 hour/.test(t)) return 60;
  const m = t.match(/(\d+)\s*(m|min|mins|minute|minutes)\b/);
  if (m) return +m[1];
  return null;
}

/**
 * Answer one message. Returns { html, actions:[[label, action]], effects:[{settings}|{pause}|{eyeNow}] }.
 * `s` is the current app state (settings, today's numbers).
 */
export function reply(text, s) {
  const t = text.toLowerCase().trim();
  if (!t) return null;

  // commands first
  const cm = parseHeight(t);
  if (cm) {
    const si = ideal(cm, 'sit'), st = ideal(cm, 'stand');
    return {
      html: `For <b>${cm} cm</b>, a good starting point (heights from the floor):
        <table><tr><td>Chair seat</td><td>${si.seat} cm</td></tr><tr><td>Desk / keyboard, sitting</td><td>${si.desk} cm</td></tr>
        <tr><td>Screen top, sitting</td><td>${si.screen} cm</td></tr><tr><td>Desk, standing</td><td>${st.desk} cm</td></tr>
        <tr><td>Screen top, standing</td><td>${st.screen} cm</td></tr><tr><td>Screen distance</td><td>${si.dist} cm</td></tr></table>
        <p class="small muted mt-s">Body proportions vary — fine-tune until your elbows are at ~90° and feet are flat.</p>`,
      actions: [['Show me on the model', 'height:' + cm]], kind: 'command',
    };
  }
  const remindWord = /remind|reminder|break|notif|eye/.test(t);
  if (/(turn|switch|shut)\s*(off|down)|disable|stop (the )?remind|no more remind/.test(t) && remindWord && !/move|stand/.test(t))
    return { kind: 'command', html: 'Eye-break reminders are now <b>off</b>. You can switch them back on any time — just ask me.', effects: [{ settings: { eyeEnabled: false } }], actions: [['Turn them back on', 'say:turn on reminders']] };
  if (/(turn|switch)\s*on|enable|resume|unpause|start remind/.test(t) && (remindWord || /resume|unpause/.test(t)) && !/move|stand/.test(t))
    return { kind: 'command', html: `Reminders are <b>on</b> — every ${s.settings.eyeInterval} minutes of screen time.`, effects: [{ settings: { eyeEnabled: true } }, { pause: 0 }] };
  if (/pause|snooze|mute|silence|do not disturb|\bdnd\b/.test(t) && !/what|how does/.test(t)) {
    let min = parseMinutes(t);
    let label;
    if (/tomorrow|rest of the day|today|for the day/.test(t)) { min = -1; label = 'until tomorrow morning'; }
    if (min == null) min = 60;
    label = label || (min >= 60 ? `for ${min / 60 === Math.round(min / 60) ? min / 60 : (min / 60).toFixed(1)} hour${min === 60 ? '' : 's'}` : `for ${min} minutes`);
    return { kind: 'command', html: `Okay — reminders are paused <b>${label}</b>. Enjoy the focus time.`, effects: [{ pause: min }], actions: [['Resume now', 'say:resume reminders']] };
  }
  if (/(remind|break|notify|ping)[^.]*every\s+\d+|every\s+\d+\s*(m|min|minute)/.test(t) || /(set|change)\s+(the\s+)?(interval|reminder)/.test(t)) {
    let n = parseMinutes(t.replace(/every\s+(\d+)\b(?!\s*(h|hour))/, 'every $1 min'));
    if (n != null) {
      const move = /move|stand|stretch|walk/.test(t);
      const lo = move ? 15 : 5, hi = move ? 180 : 120;
      n = Math.max(lo, Math.min(hi, n));
      if (!move) n = ROUND.reduce((a, b) => Math.abs(b - n) < Math.abs(a - n) ? b : a);
      return move
        ? { kind: 'command', html: `Done — I’ll remind you to <b>move every ${n} minutes</b> of screen time.`, effects: [{ settings: { moveEnabled: true, moveInterval: n } }] }
        : { kind: 'command', html: `Done — eye breaks every <b>${n} minutes</b> of screen time.${n > 30 ? ' (The rule says 20 — but every break helps.)' : ''}`, effects: [{ settings: { eyeEnabled: true, eyeInterval: n } }] };
    }
  }
  if (/move reminder|remind me to (move|stand|stretch|walk)|standing reminder/.test(t))
    return { kind: 'command', html: `I’ll remind you to stand up and move every ${s.settings.moveInterval} minutes of screen time.`, effects: [{ settings: { moveEnabled: true } }], actions: [['Change interval', 'go:move']] };
  if (!/^(how|why|what|when|should|is|are|do i|does)\b/.test(t) && /^(please |can you |let'?s |i want to |i'?d like to )?(start|take|do|begin|give me)\b.*\bbreak|rest my eyes|eye break now|break now/.test(t))
    return { kind: 'command', html: 'Here we go — look at something far away. The timer is in the corner of your screen.', effects: [{ eyeNow: true }] };
  if (/how am i doing|my (stats|progress|day)|how many breaks|statistic|today'?s (stats|numbers|progress)/.test(t)) {
    const d = s.today || {};
    const min = Math.round((d.activeSec || 0) / 60);
    return { kind: 'command', html: `Today so far: <b>${d.eyeTaken || 0}</b> eye break${(d.eyeTaken || 0) === 1 ? '' : 's'} taken${d.eyeReminded ? ` out of ${d.eyeReminded} reminders` : ''}, and about <b>${min >= 60 ? Math.floor(min / 60) + ' h ' + (min % 60) + ' min' : min + ' min'}</b> of screen time.`, actions: [['Open Today', 'go:home']] };
  }

  // intent matching
  const toks = tokens(t);
  const joined = ' ' + toks.join(' ') + ' ';
  let best = null, bestScore = 0;
  for (const it of INTENTS) {
    let score = 0;
    for (const [k, w] of it.k) {
      if (k.includes(' ')) { if (joined.includes(' ' + tokens(k).join(' ') + ' ') || t.includes(k)) score += w; continue; }
      const kk = stem(k);
      if (toks.includes(kk) || (kk.length >= 5 && toks.some(x => x.length >= 5 && lev(x, kk) <= 1))) score += w;
    }
    if (score > bestScore) { bestScore = score; best = it; }
  }
  if (best && bestScore >= 2) {
    return { kind: 'intent', topic: best.id, html: best.a(s), actions: (best.act || []).map(([l, a]) => [l, a]) };
  }
  return {
    kind: 'fallback',
    html: `I’m not sure about that one — I know about posture, screens, chairs, desks, light, breaks, stretches and aches. Try one of these:`,
    actions: [['How high should my screen be?', 'say:How high should my screen be?'], ['My neck hurts', 'say:My neck hurts'], ['I am 175 cm', 'say:I am 175 cm']],
  };
}

export const SUGGESTIONS = ['How high should my screen be?', 'I am 180 cm', 'My lower back aches', 'Remind me every 30 minutes', 'Pause reminders for 1 hour', 'Why 20-20-20?', 'How much light do I need?', 'Laptop tips'];
