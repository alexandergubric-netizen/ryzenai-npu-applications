// Workstation setup: A sit-stand desk, B chair, C within easy reach, and cabling — straight from the guide.
import { go } from './core.js';
import { icon } from './icons.js';
import { CABLES, MK } from './content.js';

export default {
  id: 'workspace', title: 'Workspace', icon: 'desk', color: 'var(--c-desk)',
  mount(root) {
    root.innerHTML = `
      <div class="page-head"><div class="grow">
        <div class="kicker" style="--k:var(--c-desk)">Workstation setup</div>
        <h1>A flexible setup</h1>
        <p>A flexible setup encourages movement and helps keep your spine in a natural position.</p>
      </div></div>
      <div class="grid g3">
        <div class="card tip"><div class="ti" style="--c:var(--c-desk)"><b style="font-size:15px">A</b></div><div><h3>Sit-stand desk</h3><p class="muted">Where available, use a height-adjustable desk to alternate between sitting and standing during the day. Change position regularly rather than staying in one for long periods.</p><button class="btn ghost" data-go="move" style="padding-left:0">Plan your rhythm →</button></div></div>
        <div class="card tip"><div class="ti" style="--c:var(--c-desk)"><b style="font-size:15px">B</b></div><div><h3>Chair</h3><p class="muted">Adjust your chair so that your feet rest flat on the floor (or on a footrest) and your lower back is fully and continuously supported.</p><button class="btn ghost" data-go="posture" style="padding-left:0">Adjust on the model →</button></div></div>
        <div class="card tip"><div class="ti" style="--c:var(--c-desk)"><b style="font-size:15px">C</b></div><div><h3>Within easy reach</h3><p class="muted">Keep frequently used items close, and place your keyboard and mouse near you so that you do not need to overstretch.</p></div></div>
      </div>
      <div class="card tip mt"><div class="ti" style="--c:${MK ? 'var(--forest)' : 'var(--c-desk)'}">${icon('cable')}</div><div><h3>${CABLES.title}</h3><p class="muted">${CABLES.text}</p></div></div>
      <div class="callout mt">${icon('check')}<div><b>Changed desk or location?</b> <span class="muted">Take a minute to review your setup with the self-check.</span> <button class="btn ghost" data-go="check" style="padding:0 4px">Open self-check →</button></div></div>`;
    root.querySelectorAll('[data-go]').forEach(b => b.onclick = () => go(b.dataset.go));
  },
};
