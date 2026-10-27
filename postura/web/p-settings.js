// Settings and About.
import { S, onState, setSettings, toggleHTML, segHTML, wireSeg, go, get, post, toast, refresh, esc, ASSISTANT, EDITION } from './core.js';
import { logoSVG } from './logo.js';
import { icon } from './icons.js';
import { SOURCE, LOCAL_RULES, EDITION_LABEL, ABOUT_HTML, SOURCES } from './content.js';

export default {
  id: 'settings', title: 'Settings', icon: 'gear', color: 'var(--c-settings)',
  mount(root) {
    const ver = document.querySelector('meta[name="postura-version"]').content;
    root.innerHTML = `
      <div class="page-head"><div class="grow"><h1>Settings</h1></div></div>
      <div class="grid" style="grid-template-columns:minmax(0,1.2fr) minmax(0,1fr)">
        <div class="stack">
          <div class="list" id="gen"></div>
          <div class="list" id="aiBox"></div>
          <div class="list">
            <div class="item"><div class="t"><b>Eye breaks and reminders</b><small>Interval, break length, sound, full-screen behaviour</small></div><button class="btn" data-go="eyes">Open</button></div>
            <div class="item"><div class="t"><b>Move reminders</b><small>Stand up and stretch</small></div><button class="btn" data-go="move">Open</button></div>
          </div>
          <div class="card tip"><div class="ti" style="--c:var(--ok)">${icon('shield')}</div><div><h3>Private and offline</h3>
            <p class="muted">Postura never connects to the internet. There is no account and no tracking. The optional AI assistant runs on this PC’s own processor. Settings and break counts stay on this PC in <code>%LOCALAPPDATA%\\Postura</code>. The window is a local page served only to this computer.</p></div></div>
        </div>
        <div class="card" style="text-align:center">
          <div style="width:96px;height:96px;margin:8px auto 10px">${logoSVG()}</div>
          <h2 style="font-size:22px;font-weight:var(--head-weight)">Postura</h2>
          <div class="muted">${EDITION_LABEL || 'Posture & eye care'} · version ${ver}</div>
          <p class="mt muted small" style="max-width:340px;margin-inline:auto"><i>Postura</i> means posture in Latin, Spanish, Italian, Portuguese and Polish. The bamboo stalk stands for a straight, segmented spine.</p>
          <div class="list mt" style="text-align:left;box-shadow:none;background:var(--card-2)">
            <div class="item"><div class="t"><b>Author</b><small>Alexander Gubric</small></div></div>
            <div class="item"><div class="t"><b>Licence</b><small>Open source · MIT License · © 2026 Alexander Gubric</small></div></div>
            ${ABOUT_HTML}
            <div class="item"><div class="t"><b>Assistant</b><small>${ASSISTANT} — local AI on supported PCs (AMD Ryzen AI via FastFlowLM, Intel Core Ultra via Foundry Local)</small></div></div>
            <div class="item"><div class="t"><b>Content</b><small>${SOURCE}</small></div></div>
          </div>
          <details class="mt" style="text-align:left"><summary class="small"><b>Sources</b></summary>
            <div class="list mt-s" style="box-shadow:none;background:var(--card-2)">${SOURCES.map(s => `<div class="item"><div class="t"><b>${esc(s.what)}</b><small>${esc(s.src)}</small></div></div>`).join('')}</div>
          </details>
          <p class="small muted mt">General guidance, not medical advice, and not a workplace risk assessment. ${LOCAL_RULES}</p>
        </div>
      </div>`;
    const $ = s => root.querySelector(s);
    root.querySelectorAll('[data-go]').forEach(b => b.onclick = () => go(b.dataset.go));
    let lastKey = '';
    const unsub = onState(st => {
      const s = st.settings, ai = st.ai || {}, key = JSON.stringify([s.autostart, s.theme, s.motion, st.installed, st.autostartActual, ai.enabled, ai.available, ai.state]);
      if (key === lastKey) return;
      lastKey = key;
      $('#gen').innerHTML = `
        <div class="item"><div class="t"><b>Start with Windows</b><small>${st.installed ? 'Postura waits quietly in the notification area to remind you' : 'Available once Postura is installed'}</small></div>${toggleHTML('gAuto', st.installed ? st.autostartActual : false)}</div>
        <div class="item"><div class="t"><b>Appearance</b></div>${segHTML('gTheme', [['system', 'Auto'], ['light', 'Light'], ['dark', 'Dark']], s.theme)}</div>
        <div class="item"><div class="t"><b>Animations</b><small>Reduced turns off moving illustrations</small></div>${segHTML('gMotion', [['full', 'Full'], ['reduced', 'Reduced']], s.motion)}</div>`;
      const a = $('#gAuto');
      a.disabled = !st.installed;
      a.addEventListener('change', () => setSettings({ autostart: a.checked }));
      wireSeg(root, 'gTheme', v => setSettings({ theme: v }));
      wireSeg(root, 'gMotion', v => setSettings({ motion: v }));
      // poka-yoke: the switch only exists where setup found supported hardware and installed the engine
      $('#aiBox').innerHTML = ai.available
        ? `<div class="item"><div class="t"><b>AI assistant (${ASSISTANT})</b><small>${esc(ai.engineName)}. Runs only on this PC; starts when you open the assistant and sleeps when idle.</small></div>${toggleHTML('gAi', ai.enabled)}</div>
           <div class="item"><div class="t"><b>AI model</b><small id="mHint">Models installed in ${ai.engine === 'flm' ? 'FastFlowLM' : 'Foundry Local'} on this PC</small></div>
             <select id="gModel" class="sel" disabled><option>${esc(ai.model)}</option></select></div>`
        : `<div class="item"><div class="t"><b>AI assistant</b><small>Not set up on this PC. It needs an AMD Ryzen AI 300/400/Max or an Intel Core Ultra processor with an NPU, chosen in the Postura installer. Everything else in Postura works without it.</small></div>${toggleHTML('gAi', false)}</div>`;
      const g = $('#gAi');
      g.disabled = !ai.available;
      g.addEventListener('change', () => setSettings({ aiEnabled: g.checked }));
      if (ai.available) loadModels(ai);
    });

    // the engine's own list of installed chat models (asked fresh, so models added in FastFlowLM later show up too)
    async function loadModels(ai) {
      const sel = $('#gModel');
      try {
        const r = await get('ai-models');
        if (!sel.isConnected) return;
        if (!r.models.length) { $('#mHint').textContent = 'No chat model installed — run the Postura installer again to download one.'; return; }
        const list = r.models.includes(r.current) ? r.models : [r.current, ...r.models];
        sel.innerHTML = list.map(m => `<option value="${esc(m)}">${esc(m)}${m === r.recommended ? ' (recommended)' : ''}</option>`).join('');
        sel.value = r.current;
        sel.disabled = !ai.enabled || list.length < 2;
        $('#mHint').textContent = list.length < 2 ? 'Only one chat model is installed in ' + (ai.engine === 'flm' ? 'FastFlowLM (add more with “flm pull <model>”)' : 'Foundry Local')
          : 'Larger models answer better; smaller ones answer faster. The recommended one is tested with Postura.';
        sel.onchange = async () => {
          try {
            await post('ai-model', { model: sel.value });
            toast(`${ASSISTANT} now uses ${sel.value} — it loads with the next question`);
            refresh();
          } catch (e) { toast(e.message); sel.value = r.current; }
        };
      } catch (e) { $('#mHint').textContent = 'Couldn’t read the installed models: ' + e.message; }
    }
    this.unmount = unsub;
  },
};
