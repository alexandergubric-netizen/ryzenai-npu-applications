// The AI side of the assistant: a grounded system prompt (the guide's content + the best matching note from the
// rule engine), a streaming call to the local model through the tray app, and a tiny Markdown renderer.
import { get, post } from './api.js';
import { ASSISTANT, HELP, CABLES, LOCAL_RULES, AI_FOR, GUIDE_NAME, MEASURE_DASH } from './content.js';

const token = document.querySelector('meta[name="postura-token"]').content;

const GUIDE = `
OFFICE ERGONOMICS GUIDANCE${GUIDE_NAME}
Four essentials: good light (at least 500 lux at the desk, no glare); keep moving (alternate sitting and standing);
neutral posture (screen at eye level, elbows at about 90°); rest your eyes (20-20-20 rule).
1 Lighting: at least 500 lux at desk level. Use daylight; windows to the side of the screen, not in front of or behind
it. Add an adjustable task lamp if daylight is insufficient or causes shadows or glare. Lux = light reaching the desk;
lumens = a lamp's output. Postura's lux meter is only an orientational calculation; measuring needs a calibrated light
meter${MEASURE_DASH}. Stricter local requirements apply where they exist.
2 Workstation: A sit-stand desk — alternate sitting and standing, change position regularly. B Chair — feet flat on the
floor or a footrest, lower back fully and continuously supported. C Within easy reach — keyboard, mouse and frequently
used items close so you don't overstretch.
3 Posture (sitting): top of the screen at or just below eye level; screen about an arm's length away (50–75 cm);
elbows relaxed at about 90°, wrists straight; lower back supported by the chair; feet flat on the floor or a footrest.
Posture (standing): same screen rules; stand tall with weight on both feet; desk height level with the elbows.
4 Breaks: every 20 minutes look at something about 20 feet (6 metres) away for at least 20 seconds; use breaks to
stand up, stretch and move. Blink fully; match screen brightness to the room.
5 Cables: ${CABLES.title}. ${CABLES.text}
Help: ${HELP.text}
${LOCAL_RULES}
Postura app features you may point to: Posture page (interactive model, "Fit to me" from body height), Lighting page,
Eye breaks page (20-20-20 reminders, settings), Keep moving page (sit-stand rhythm, stretches), Workspace page,
Self-check page (8-point checklist).`.trim();

export function systemPrompt(note) {
  return `You are ${ASSISTANT}, the friendly ergonomics assistant inside the Postura app${AI_FOR}.
Rules:
- Answer only questions about office ergonomics, posture, eyes and screens, lighting, breaks, movement and comfort at work.
  For anything else, say briefly that you can only help with ergonomics.
- Base your answer on the guidance below. Do not invent numbers or rules that are not in it.
- Be brief and practical: at most about 90 words, short bullet points ("- ") when listing steps.
- You are not a doctor: never diagnose. For pain or discomfort that persists, advise seeking advice early (${HELP.contacts.join(', ')}).
- Answer in the same language as the question.

${GUIDE}${note ? `\n\nMost relevant note for this question:\n${note}` : ''}`;
}

export const strip = html => html.replace(/<li>/g, '\n- ').replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/\n{2,}/g, '\n').trim();

/** Minimal, safe Markdown → HTML: escapes everything, then **bold**, bullet and numbered lists, line breaks. */
export function md(text) {
  const esc = s => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>');
  let html = '', inList = false;
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    const m = line.match(/^(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (m) { if (!inList) { html += '<ul>'; inList = true; } html += `<li>${inline(m[1])}</li>`; continue; }
    if (inList) { html += '</ul>'; inList = false; }
    if (line) html += (html && !html.endsWith('</ul>') ? '<br>' : '') + inline(line);
  }
  if (inList) html += '</ul>';
  return html;
}

export const aiState = () => get('state').then(s => s.ai);
export const warm = () => post('ai-warm');

/** Wait until the engine is ready (it may have to load the model onto the NPU first). */
export async function waitReady(onStatus, seconds = 240) {
  let st = await warm();
  for (let i = 0; i < seconds && st.state !== 'ready'; i++) {
    if (st.state === 'error') throw new Error(st.detail || 'The AI engine could not start');
    onStatus && onStatus(st.detail || 'Starting…');
    await new Promise(r => setTimeout(r, 1000));
    st = await aiState();
    if (st.state === 'off') st = await warm();
  }
  if (st.state !== 'ready') throw new Error('The AI engine took too long to start');
}

/** Streams the answer; onText(fullTextSoFar). Resolves to the final text. */
export async function ask(messages, onText) {
  const r = await fetch('/api/ai-chat', {
    method: 'POST',
    headers: { 'X-Postura': token, 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
  });
  if (r.status === 503) throw Object.assign(new Error('not ready'), { notReady: true });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  const reader = r.body.getReader(), dec = new TextDecoder();
  let text = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    text += dec.decode(value, { stream: true });
    const err = text.indexOf('\u0000ERROR ');
    if (err >= 0) throw new Error(text.slice(err + 7));
    onText(text);
  }
  return text;
}
