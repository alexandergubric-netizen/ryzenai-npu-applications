// Chat with the assistant (its name comes from the edition). Only shown when the installer
// set up a local AI engine on this PC. Commands (reminders, pause, height → desk numbers) are handled by the
// rule engine so they always work exactly; questions go to the local model, grounded in the guide, streamed.
import { S, post, setSettings, setUi, go, refresh, toast, ASSISTANT, reduced } from './core.js';
import { avatarSVG } from './logo.js';
import { icon } from './icons.js';
import { reply, SUGGESTIONS } from './kb.js';
import { focusBreak } from './p-eyes.js';
import { systemPrompt, strip, md, ask as askModel, waitReady } from './ai.js';

const log = [];       // [who, html, actions] — kept while the window is open
const history = [];   // [{role, content}] for the model's context

const escText = t => t.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

export default {
  id: 'assistant', title: 'Assistant', icon: 'chat', color: 'var(--c-assist)',
  mount(root) {
    const ai = S.state.ai || {};
    root.style.paddingBottom = '18px';
    root.innerHTML = `
      <div class="chat">
        <div class="chat-head"><div class="av">${avatarSVG()}</div>
          <div style="flex:1"><h1 style="font-size:22px;font-weight:var(--head-weight)">${ASSISTANT}</h1>
            <div class="muted small">Your ergonomics assistant · local AI on this PC (${ai.engineName || ''} · ${ai.model || ''}) · nothing leaves it</div></div>
          <span class="chip" id="aiChip"></span></div>
        <div class="chat-log" id="log"></div>
        <div class="chat-in">
          <div class="chips" id="chips">${SUGGESTIONS.map(s => `<button class="chip">${s}</button>`).join('')}</div>
          <input id="in" placeholder="Ask ${ASSISTANT} — e.g. “my wrists hurt” or “I’m 168 cm”" autocomplete="off">
          <button class="btn primary" id="send" style="border-radius:22px;min-width:44px">${icon('send')}</button>
        </div>
      </div>`;
    const $ = s => root.querySelector(s);
    const logEl = $('#log');

    const chip = st => {
      const c = $('#aiChip');
      if (!c) return;
      const map = { ready: ['ok', 'AI ready'], starting: ['warn', 'Waking up…'], error: ['bad', 'AI unavailable'], off: ['', 'AI asleep'] };
      const [cls, label] = map[st.state] || map.off;
      c.className = 'chip ' + cls;
      c.textContent = label;
      c.title = st.detail || '';
    };
    chip(ai);
    // load the model while the person is typing their first question
    post('ai-warm').then(chip).catch(() => {});
    const poll = setInterval(() => { if (S.state && S.state.ai) chip(S.state.ai); }, 1500);

    const bubble = (who, html, actions = []) => {
      const m = document.createElement('div');
      m.className = 'msg ' + who;
      m.innerHTML = html + (actions.length ? `<div class="acts">${actions.map(([l, a]) => `<button class="btn" data-a="${a}">${l}</button>`).join('')}</div>` : '');
      logEl.appendChild(m);
      logEl.scrollTop = logEl.scrollHeight;
      return m;
    };

    const run = async a => {
      const [k, v] = [a.slice(0, a.indexOf(':')), a.slice(a.indexOf(':') + 1)];
      if (k === 'go') go(v);
      else if (k === 'say') send(v);
      else if (k === 'height') {
        const p = Object.assign({}, S.state.ui.posture || {}, { H: +v });
        await setUi({ posture: p });
        go('posture');
      } else if (k === 'do') {
        if (v === 'focus') focusBreak(S.state.settings.eyeSeconds, () => post('eye-done').then(refresh));
        if (v === 'moveOn') { await setSettings({ moveEnabled: true }); toast(`Move reminders on — every ${S.state.settings.moveInterval} min`); }
      }
    };

    const apply = async effects => {
      for (const e of effects || []) {
        if (e.settings) await setSettings(e.settings);
        if (e.pause !== undefined) await post('pause', { minutes: e.pause });
        if (e.eyeNow) await post('eye-now');
      }
      if (effects && effects.length) refresh();
    };

    let busy = false;
    const send = async text => {
      text = text.trim();
      if (!text || busy) return;
      busy = true;
      bubble('me', escText(text));
      log.push(['me', text]);
      const r = reply(text, S.state);
      const typing = bubble('bot typing', '<i></i><i></i><i></i>');

      // exact commands: rule engine
      if (r.kind === 'command') {
        await new Promise(res => setTimeout(res, reduced() ? 0 : 350));
        typing.remove();
        bubble('bot', r.html, r.actions || []);
        log.push(['bot', r.html, r.actions || []]);
        busy = false;
        await apply(r.effects);
        return;
      }

      // questions: the local model, grounded in the guide and the best matching note
      const note = r.kind === 'intent' ? strip(r.html) : '';
      const msgs = [{ role: 'system', content: systemPrompt(note) }, ...history.slice(-4), { role: 'user', content: text }];
      let out = null, answer = '';
      try {
        try {
          answer = await askModel(msgs, t => {
            if (!out) { typing.remove(); out = bubble('bot', ''); }
            out.innerHTML = md(t);
            logEl.scrollTop = logEl.scrollHeight;
          });
        } catch (e) {
          if (!e.notReady) throw e;
          typing.innerHTML = '<span class="small muted" id="wake">Waking up the AI…</span>';
          await waitReady(d => { const w = typing.querySelector('#wake'); if (w) w.textContent = d; });
          typing.innerHTML = '<i></i><i></i><i></i>';
          answer = await askModel(msgs, t => {
            if (!out) { typing.remove(); out = bubble('bot', ''); }
            out.innerHTML = md(t);
            logEl.scrollTop = logEl.scrollHeight;
          });
        }
        if (!out) { typing.remove(); out = bubble('bot', ''); }
        if (!answer.trim()) throw new Error('empty answer');
        const acts = r.kind === 'intent' ? (r.actions || []) : [];
        out.innerHTML = md(answer) + (acts.length ? `<div class="acts">${acts.map(([l, a]) => `<button class="btn" data-a="${a}">${l}</button>`).join('')}</div>` : '');
        log.push(['bot', out.innerHTML, []]);
        history.push({ role: 'user', content: text }, { role: 'assistant', content: answer.trim() });
      } catch (e) {
        // the AI is unavailable: answer from the built-in guidance instead of leaving the question hanging
        typing.remove();
        if (out) out.remove();
        const html = r.html + `<p class="small muted mt-s">(Answered from the built-in guide — the local AI is unavailable: ${escText(e.message)})</p>`;
        bubble('bot', html, r.actions || []);
        log.push(['bot', html, r.actions || []]);
      }
      busy = false;
    };

    logEl.addEventListener('click', e => { const b = e.target.closest('[data-a]'); if (b) run(b.dataset.a); });
    $('#chips').addEventListener('click', e => { const b = e.target.closest('button'); if (b) send(b.textContent); });
    $('#send').onclick = () => { send($('#in').value); $('#in').value = ''; };
    $('#in').addEventListener('keydown', e => { if (e.key === 'Enter') { send($('#in').value); $('#in').value = ''; } });

    if (!log.length) {
      const h = new Date().getHours();
      const hello = h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
      const first = `${hello}! I’m <b>${ASSISTANT}</b>, your ergonomics assistant. I run on this PC’s own AI chip — nothing leaves it.<br>Ask me about your chair, screen, light or breaks, tell me where it aches, or tell me your height and I’ll work out your desk setup.`;
      log.push(['bot', first, [['What can you do?', 'say:What can you do?']]]);
    }
    log.forEach(([who, html, acts]) => bubble(who, who === 'me' ? escText(html) : html, acts || []));
    setTimeout(() => $('#in').focus(), 50);
    this.unmount = () => clearInterval(poll);
  },
};
