// Shared app bar for the workbench pages (the manual editors behind each chat mode).
// Its tabs lead back to the matching chat mode; it keeps the workspace and applies the saved light/dark theme.
const areas = [['chat', 'Chat', '/'], ['terminal', 'Terminal', '/terminal'], ['docs', 'Docs & PDFs', '/docs'], ['tables', 'Tables', '/tables'],
  ['audio', 'Audio', '/audio'], ['knowledge', 'Knowledge', '/knowledge'], ['images', 'Images', '/images']];
const workspace = new URLSearchParams(location.search).get('workspace') || 'default';
const here = location.pathname.replace(/\/$/, '') || '/';
const current = (areas.find(a => a[2] === here) || areas[0])[0];
document.body.dataset.area = current;

const bar = document.createElement('nav');
bar.className = 'appbar';
bar.setAttribute('aria-label', 'Tsubasa areas');
const brand = document.createElement('a');
brand.className = 'brand-mini';
brand.href = '/';
const bird = document.createElement('img');
bird.src = '/bird.svg';
bird.alt = '';
const name = document.createElement('b');
name.textContent = 'Tsubasa';
const tag = document.createElement('span');
tag.textContent = 'WORKBENCH';
brand.append(bird, name, tag);

const back = document.createElement('a');
back.className = 'back-to-chat';
back.href = current === 'chat' ? '/' : `/?mode=${current}`;
back.textContent = '← Back to chat';
back.dataset.tab = current;

const tabs = document.createElement('div');
tabs.className = 'area-tabs';
for (const [id, label, path] of areas) {
  const a = document.createElement('a');
  a.dataset.tab = id;
  a.textContent = label;
  a.href = path === '/' ? '/' : `${path}?workspace=${encodeURIComponent(workspace)}`;
  a.title = id === 'chat' ? 'Chat' : `${label} workbench`;
  if (id === current) a.setAttribute('aria-current', 'page');
  tabs.append(a);
}
bar.append(brand, back, tabs);
document.body.prepend(bar);

fetch('/api/state').then(r => r.ok ? r.json() : null).then(s => {
  if (s?.settings?.theme) document.body.dataset.theme = s.settings.theme;
}).catch(() => {});
