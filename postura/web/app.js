// Shell: sidebar, router, splash and the state poll (which doubles as the "window is open" ping).
import { S, refresh, applyLook, go, reduced, onState } from './core.js';
import { logoSVG, avatarSVG, ASSISTANT, EDITION } from './logo.js';
import { icon } from './icons.js';
import { EDITION_LABEL } from './content.js';
import home from './p-home.js';
import posture from './p-posture.js';
import light from './p-light.js';
import eyes from './p-eyes.js';
import move from './p-move.js';
import workspace from './p-workspace.js';
import check from './p-check.js';
import assistant from './p-assistant.js';
import settings from './p-settings.js';

const PAGES = [home, posture, light, eyes, move, workspace, check, null, assistant, settings];
const byId = Object.fromEntries(PAGES.filter(Boolean).map(p => [p.id, p]));
const $ = id => document.getElementById(id);

// ---- splash (once per window; skippable; skipped for reduced motion)
$('spLogo').innerHTML = logoSVG(true);
const splash = $('splash');
const hideSplash = () => splash.classList.add('out');
splash.addEventListener('click', hideSplash);
setTimeout(hideSplash, reduced() ? 0 : 1700);

// ---- sidebar
$('brandLogo').innerHTML = logoSVG();
if (EDITION_LABEL) $('brandSub').textContent = EDITION_LABEL;
$('footAv').innerHTML = avatarSVG();
$('footName').textContent = ASSISTANT;
$('askFoot').addEventListener('click', () => go('assistant'));

const nav = $('nav');
const aiOn = () => !!(S.state && S.state.ai && S.state.ai.enabled);
let navAi = null;
// the assistant only exists on PCs where setup installed a local AI engine (and it is switched on)
function buildNav() {
  navAi = aiOn();
  $('askFoot').hidden = !navAi;
  const pages = navAi ? PAGES : PAGES.filter(p => p && p.id !== 'assistant');
  nav.innerHTML = pages.map(p => p
    ? `<button data-p="${p.id}"><span class="ico" style="--c:${p.color}">${icon(p.icon)}</span><span>${p.id === 'assistant' ? 'Ask ' + ASSISTANT : p.title}</span></button>`
    : '<div class="sep"></div>').join('');
  if (current) nav.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.p === current.id));
}
nav.addEventListener('click', e => {
  const b = e.target.closest('button[data-p]');
  if (b) go(b.dataset.p);
});

// ---- router
const main = $('main');
let current = null;

function route() {
  const [id, arg] = (location.hash.slice(1) || 'home').split('/');
  const page = (id === 'assistant' && !aiOn()) ? home : byId[id] || home;
  if (current && current.unmount) { try { current.unmount(); } catch (e) { console.error(e); } }
  current = page;
  nav.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.p === page.id));
  main.innerHTML = '';
  main.scrollTop = 0;
  const root = document.createElement('div');
  root.className = 'page';
  main.appendChild(root);
  page.mount(root, arg);
}

window.addEventListener('hashchange', route);
document.addEventListener('keydown', e => {
  // Ctrl+1…9 jumps between pages, like the sidebar order
  if (e.ctrlKey && /^[1-9]$/.test(e.key)) {
    const list = PAGES.filter(p => p && (aiOn() || p.id !== 'assistant'));
    const p = list[+e.key - 1];
    if (p) { go(p.id); e.preventDefault(); }
  }
});

await refresh();
applyLook();
buildNav();
route();
onState(() => {
  if (aiOn() === navAi) return;
  buildNav();
  if (!aiOn() && current && current.id === 'assistant') go('home');
});
setInterval(refresh, 2000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
