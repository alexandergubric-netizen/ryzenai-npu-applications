// Quick self-check: the guide's eight points, a progress ring, and falling bamboo leaves when all are done.
import { ui, setUi, go, ringSVG, setRing, reduced } from './core.js';
import { icon } from './icons.js';
import { CHECKLIST, HELP, LOCAL_RULES, MK } from './content.js';

function leaves() {
  if (reduced()) return;
  const colors = MK ? ['#c3db76', '#99bf9c', '#58915b', '#cfe7cc'] : ['#3bb273', '#4cc37f', '#f4a63a', '#2f6fdb'];
  for (let i = 0; i < 26; i++) {
    const l = document.createElement('div');
    l.className = 'leaf-fall';
    l.style.left = Math.random() * 100 + 'vw';
    l.style.animationDelay = Math.random() * .8 + 's';
    l.style.animationDuration = 2.4 + Math.random() * 1.6 + 's';
    l.innerHTML = `<svg width="22" height="12" viewBox="0 0 22 12"><path d="M1 6 Q11 -3 21 6 Q11 15 1 6Z" fill="${colors[i % colors.length]}"/></svg>`;
    document.body.appendChild(l);
    setTimeout(() => l.remove(), 5000);
  }
}

export default {
  id: 'check', title: 'Self-check', icon: 'check', color: 'var(--c-check)',
  mount(root) {
    const saved = ui('check', {});
    const items = Object.assign({}, saved.items || {});
    root.innerHTML = `
      <div class="page-head"><div class="grow">
        <div class="kicker" style="--k:var(--c-check)">Quick self-check</div>
        <h1>One minute for your setup</h1>
        <p>Review your setup whenever you change desk or location. Tap each line that is true for you right now.</p>
      </div></div>
      <div class="grid" style="grid-template-columns:minmax(0,1.6fr) minmax(0,1fr)">
        <div class="list" id="rows">${CHECKLIST.map(c => `
          <div class="item check-row" data-id="${c.id}">
            <span class="tick">${icon('tick')}</span>
            <div class="t"><b>${c.title}</b><small>${c.text}</small></div>
            <button class="btn ghost" data-go="${c.page}" title="How?">How?</button>
          </div>`).join('')}</div>
        <div class="stack">
          <div class="card" style="text-align:center">
            <div style="width:170px;height:170px;margin:6px auto;position:relative" id="ring">${ringSVG(0, { size: 170, stroke: 9, color: MK ? 'var(--accent)' : 'var(--c-check)' })}
              <div style="position:absolute;inset:0;display:grid;place-items:center"><div><b style="font:700 38px var(--font-display)" id="n">0</b><span class="muted"> / ${CHECKLIST.length}</span></div></div></div>
            <div id="msg" class="muted"></div>
            <div class="small muted mt-s" id="when"></div>
            <button class="btn mt" id="reset">Start over</button>
          </div>
          <div class="card tip"><div class="ti" style="--c:var(--c-check)">${icon('help')}</div><div><h3>${HELP.title}</h3><p class="muted">${HELP.text}</p></div></div>
        </div>
      </div>
      <p class="small muted mt">${LOCAL_RULES}</p>`;
    const $ = s => root.querySelector(s);
    const ring = $('#ring svg');
    let wasDone = CHECKLIST.every(c => items[c.id]);
    const render = () => {
      const n = CHECKLIST.filter(c => items[c.id]).length;
      root.querySelectorAll('.check-row').forEach(r => r.classList.toggle('done', !!items[r.dataset.id]));
      $('#n').textContent = n;
      setRing(ring, n / CHECKLIST.length);
      $('#msg').textContent = n === CHECKLIST.length ? 'All eight — a great setup.' : n >= 5 ? 'Nearly there. Use “How?” for the rest.' : 'Every point you fix makes a difference.';
      $('#when').textContent = saved.date ? 'Last reviewed ' + new Date(saved.date).toLocaleDateString([], { day: 'numeric', month: 'long', year: 'numeric' }) : '';
      const done = n === CHECKLIST.length;
      if (done && !wasDone) leaves();
      wasDone = done;
    };
    const save = () => { saved.items = items; saved.date = new Date().toISOString(); setUi({ check: { items, date: saved.date } }); };
    $('#rows').addEventListener('click', e => {
      const how = e.target.closest('[data-go]');
      if (how) { go(how.dataset.go); return; }
      const r = e.target.closest('.check-row');
      if (!r) return;
      items[r.dataset.id] = !items[r.dataset.id];
      save(); render();
    });
    $('#reset').onclick = () => { CHECKLIST.forEach(c => delete items[c.id]); save(); render(); };
    render();
  },
};
