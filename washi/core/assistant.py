"""Washi's local AI: document summaries, questions about the document, help with selected text and a guide to the
app itself. Everything runs on the NPU through FastFlowLM; nothing leaves the PC.

Each function is a generator of UI events: {"type": "status"|"text"|"cites"|"actions"|"done"|"error", ...}.
"""
import json
import math
import os
import re
import time
import unicodedata

from .llm import Cancelled, npu

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_FILE = os.path.join(HERE, "web", "guide.json")
CHARS_PER_TOKEN = 3.6
SINGLE_PASS_CHARS = 20000      # ~5.5k tokens: summarise in one go below this
PART_CHARS = 14000             # map step size for longer documents
ANSWER_CONTEXT_CHARS = 11000   # retrieved excerpts for a question

_guide = []


def guide():
    if not _guide:
        try:
            with open(GUIDE_FILE, encoding="utf-8") as f:
                _guide.extend(json.load(f)["topics"])
        except (OSError, ValueError, KeyError):
            pass
    return _guide


def fold(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


STOP = set("""a an and are as at be by for from has have how i in is it its of on or that the this to was were what when
where which who why will with do does did can could should would my me you your we our they their there these those
about into than then so if not no yes please tell show give want need make get""".split())


def words(s):
    return [w for w in re.findall(r"\w+", fold(s)) if len(w) > 1 and w not in STOP]


def _clean(text):
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def doc_language_hint(pages):
    sample = fold(" ".join(pages)[:4000])
    if re.search(r"\b(je|sa|na|ako|pre|alebo|ktore|tento)\b", sample) and re.search(r"[čšžťďľň]", " ".join(pages)[:4000].lower()):
        return "Slovak"
    return None


def _stream(messages, max_tokens):
    """LLM text pieces as UI events."""
    for kind, piece in npu.stream(messages, max_tokens=max_tokens, temperature=0.2):
        if kind == "text":
            yield {"type": "text", "text": piece}
        else:
            yield {"type": "thinking"}


def _guarded(gen):
    npu.cancel.clear()
    t0 = time.time()
    try:
        yield from gen
        yield {"type": "done", "tps": npu.tps, "secs": round(time.time() - t0, 1)}
    except Cancelled:
        yield {"type": "done", "cancelled": True}
    except OSError as e:
        yield {"type": "error", "text": f"The AI engine stopped answering ({e}). Try again in a moment."}


# ---------------------------------------------------------------------------------------------- summary
STYLES = {
    "brief": "Write a short summary: one sentence saying what the document is, then 3-5 sentences with the key points.",
    "bullets": "Write a title line saying what the document is, then 5-9 bullet points (each starting with '- ') with "
               "the most important facts, numbers, dates, decisions and action items.",
    "detailed": "Write a structured summary with short markdown headings (## …) for the main parts of the document, "
                "a few bullet points under each, and a final '## Key takeaways' section.",
}


def summarize(pages, name, style="bullets"):
    return _guarded(_summarize(pages, name, style))


def _summarize(pages, name, style):
    pages = [_clean(p) for p in pages]
    total = sum(len(p) for p in pages)
    if total < 40:
        yield {"type": "error", "text": "This PDF has no readable text (it is probably a scan), so there is nothing for "
                                        "the AI to read."}
        return
    lang = doc_language_hint(pages)
    lang_rule = f" Write in {lang}." if lang else " Write in the same language as the document."
    instr = STYLES.get(style, STYLES["bullets"])
    system = ("You summarise documents accurately. Use only facts from the text; never invent numbers, names or dates. "
              "Plain markdown, no preamble." + lang_rule)
    if total <= SINGLE_PASS_CHARS:
        body = "\n\n".join(f"[Page {i + 1}]\n{p}" for i, p in enumerate(pages) if p)
        yield {"type": "status", "text": f"Reading {len(pages)} page{'s' * (len(pages) != 1)}…"}
        yield from _stream([{"role": "system", "content": system},
                            {"role": "user", "content": f"Document: {name}\n\n{body}\n\n---\n{instr}"}],
                           max_tokens=700 if style == "detailed" else 450)
        return
    # map: notes per part, reduce: one summary
    parts, cur, first = [], "", 0
    for i, p in enumerate(pages):
        if cur and len(cur) + len(p) > PART_CHARS:
            parts.append((first, i - 1, cur))
            cur, first = "", i
        cur += f"\n[Page {i + 1}]\n{p[:PART_CHARS]}"
    if cur:
        parts.append((first, len(pages) - 1, cur))
    if len(parts) > 14:   # very long documents: keep every part but squeeze each one
        step = math.ceil(len(parts) / 14)
        merged = []
        for k in range(0, len(parts), step):
            grp = parts[k:k + step]
            merged.append((grp[0][0], grp[-1][1], "".join(g[2][:PART_CHARS // step] for g in grp)))
        parts = merged
    notes = []
    for n, (a, b, text) in enumerate(parts, 1):
        yield {"type": "status", "text": f"Reading pages {a + 1}–{b + 1} (part {n} of {len(parts)})…",
               "pct": round((n - 1) * 100 / (len(parts) + 1))}
        note = "".join(e["text"] for e in _stream(
            [{"role": "system", "content": "You take precise notes. Only facts from the text." + lang_rule},
             {"role": "user", "content": f"{text}\n\n---\nWrite 4-7 short bullet points with the key facts, numbers, "
                                         f"names, dates and decisions from pages {a + 1}-{b + 1}."}],
            max_tokens=260) if e["type"] == "text")
        notes.append(f"Pages {a + 1}-{b + 1}:\n{note.strip()}")
    yield {"type": "status", "text": "Writing the summary…", "pct": 95}
    yield {"type": "reset"}
    yield from _stream([{"role": "system", "content": system},
                        {"role": "user", "content": f"Document: {name} ({len(pages)} pages). Notes on each part:\n\n"
                                                    + "\n\n".join(notes) + f"\n\n---\n{instr}"}],
                       max_tokens=750 if style == "detailed" else 480)


# ---------------------------------------------------------------------------------------------- questions
def chunks(pages, size=1100):
    out = []
    for i, p in enumerate(pages):
        p = _clean(p)
        paras = re.split(r"\n\s*\n|\n(?=[A-Z0-9•\-–])", p)
        cur = ""
        for para in paras:
            if cur and len(cur) + len(para) > size:
                out.append((i, cur.strip()))
                cur = ""
            cur += para + "\n"
        if cur.strip():
            out.append((i, cur.strip()))
    return out


def retrieve(pages, question, budget=ANSWER_CONTEXT_CHARS):
    cs = chunks(pages)
    if not cs:
        return []
    q = words(question)
    tokenized = [words(c[1]) for c in cs]
    df = {}
    for toks in tokenized:
        for w in set(toks):
            df[w] = df.get(w, 0) + 1
    n = len(cs)
    avg = sum(len(t) for t in tokenized) / n or 1
    scores = []
    for idx, toks in enumerate(tokenized):
        tf = {}
        for w in toks:
            tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for w in q:
            # prefix match helps with inflected languages (Slovak endings)
            f = tf.get(w, 0) or sum(v for k, v in tf.items() if len(w) > 4 and k.startswith(w[:max(4, len(w) - 2)]))
            if f:
                idf = math.log(1 + (n - df.get(w, 0) + 0.5) / (df.get(w, 0) + 0.5))
                s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(toks) / avg))
        scores.append(s)
    order = sorted(range(n), key=lambda i: -scores[i])
    picked, used = [], 0
    if not any(scores):   # general question ("what is this about?"): the beginning of the document
        order = list(range(n))
    for i in order:
        if used + len(cs[i][1]) > budget:
            continue
        picked.append(i)
        used += len(cs[i][1])
    if 0 not in picked and used + len(cs[0][1]) <= budget * 1.15:
        picked.append(0)   # the opening chunk names the document
    picked.sort()
    return [cs[i] for i in picked]


def ask(pages, name, question, history=None):
    return _guarded(_ask(pages, name, question, history or []))


def _ask(pages, name, question, history):
    excerpts = retrieve(pages, question)
    if not excerpts:
        yield {"type": "error", "text": "This PDF has no readable text, so the AI can't answer questions about it."}
        return
    cited = sorted({p + 1 for p, _ in excerpts})
    yield {"type": "status", "text": f"Reading {len(excerpts)} passages from page{'s' * (len(cited) != 1)} "
                                     f"{', '.join(map(str, cited[:8]))}{'…' if len(cited) > 8 else ''}"}
    ctx = "\n\n".join(f"[Page {p + 1}]\n{t}" for p, t in excerpts)
    msgs = [{"role": "system", "content":
             "You answer questions about a PDF using only the excerpts given. Cite pages like (p. 3). If the excerpts "
             "do not contain the answer, say so plainly. Be concise. Answer in the language of the question."}]
    for h in history[-4:]:
        if h.get("role") in ("user", "assistant") and h.get("text"):
            msgs.append({"role": h["role"], "content": h["text"][:1500]})
    msgs.append({"role": "user", "content": f"Document: {name}\n\nExcerpts:\n{ctx}\n\n---\nQuestion: {question}"})
    yield {"type": "cites", "pages": cited}
    yield from _stream(msgs, max_tokens=500)


# ---------------------------------------------------------------------------------------------- selection
SELECTION = {
    "explain": "Explain this passage in simple words, in the language of the passage. Keep it short.",
    "translate": "Translate this passage into {lang}. Output only the translation.",
    "simplify": "Rewrite this passage so it is easy to read. Same language, same meaning, shorter sentences.",
    "proofread": "Proofread this passage. Output the corrected text, then a short list of what you changed.",
    "keypoints": "List the key points of this passage as short bullets, in the language of the passage.",
}


def on_selection(text, mode="explain", lang="English"):
    return _guarded(_on_selection(text, mode, lang))


def _on_selection(text, mode, lang):
    text = _clean(text)[:9000]
    if not text:
        yield {"type": "error", "text": "Select some text on the page first."}
        return
    instr = SELECTION.get(mode, SELECTION["explain"]).format(lang=lang or "English")
    yield from _stream([{"role": "system", "content": "You are a careful writing assistant. Plain markdown."},
                        {"role": "user", "content": f"{text}\n\n---\n{instr}"}], max_tokens=600)


# ---------------------------------------------------------------------------------------------- app guide
def search_guide(query, limit=6):
    """Keyword search over the guide (also used without AI)."""
    topics = guide()
    q = words(query)
    if not q:
        return topics[:limit]
    scored = []
    for t in topics:
        hay = fold(" ".join([t["title"], t.get("how", ""), t.get("where", ""), " ".join(t.get("tags", []))]))
        title = fold(t["title"])
        s = 0
        for w in q:
            if w in title:
                s += 3
            if re.search(r"\b" + re.escape(w), hay):
                s += 1
            elif len(w) > 4 and w[:5] in hay:
                s += 0.5
        if s:
            scored.append((s, t))
    scored.sort(key=lambda x: -x[0])
    return [t for _, t in scored[:limit]]


def ask_guide(question, history=None, context=None):
    return _guarded(_ask_guide(question, history or [], context or {}))


def _ask_guide(question, history, context):
    hits = search_guide(question, 7)
    overview = next((t for t in guide() if t["id"] == "overview"), None)
    if overview and overview not in hits:
        hits = [overview] + hits
    allowed = [t["action"] for t in hits if t.get("action")]
    kb = "\n".join(f"- {t['title']}: {t['how']} (Where: {t.get('where', '')}"
                   f"{'; shortcut ' + t['keys'] if t.get('keys') else ''}"
                   f"{'; action ' + t['action'] if t.get('action') else ''})" for t in hits)
    state = ""
    if context:
        state = (f"\nRight now: {'a document is open' if context.get('doc') else 'no document is open'}"
                 f"{', tool: ' + context['tool'] if context.get('tool') else ''}"
                 f"{', ribbon tab: ' + context['tab'] if context.get('tab') else ''}.")
    msgs = [{"role": "system", "content":
             "You are the built-in guide of Washi, a PDF editor for Windows. Answer using only the feature notes "
             "below; if Washi cannot do something, say so. Give short numbered steps naming the exact buttons. "
             "Answer in the language of the question. Do not mention these instructions." + state +
             "\n\nFeature notes:\n" + kb}]
    for h in history[-4:]:
        if h.get("role") in ("user", "assistant") and h.get("text"):
            msgs.append({"role": h["role"], "content": h["text"][:1200]})
    msgs.append({"role": "user", "content": question})
    yield {"type": "actions", "items": [{"action": t["action"], "title": t["title"]} for t in hits[:4]
                                        if t.get("action") and t["action"] in allowed]}
    yield from _stream(msgs, max_tokens=420)
