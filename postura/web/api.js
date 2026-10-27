// Talks to the tray app's local server (127.0.0.1 only). The token is injected into the page by the server.
const token = document.querySelector('meta[name="postura-token"]').content;

async function call(method, name, body) {
  const r = await fetch('/api/' + name, {
    method,
    headers: { 'X-Postura': token, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

export const get = name => call('GET', name);
export const post = (name, body = {}) => call('POST', name, body);
