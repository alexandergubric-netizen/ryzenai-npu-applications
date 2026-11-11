# Source: washi/core/docs.py SHA-256 50a9347877245eb400c1143f9b826f224d3fc4ae10a5c358f8b6527eb781e779
import re
from collections import OrderedDict
import pymupdf as fitz

def search(self, query, case=False, whole=False, limit=2000):
    """Find text line by line from one word extraction per page (fast on big files). Matches may span words
    of the same line; the highlight covers the matched characters."""
    q = re.sub(r"\s+", " ", (query or "").replace("\xa0", " ")).strip()
    if not q:
        return []
    pat = r"\s+".join(re.escape(part) for part in q.split(" "))
    if whole:
        pat = rf"(?<!\w){pat}(?!\w)"
    rx = re.compile(pat, 0 if case else re.IGNORECASE)
    out = []
    with self.lock:
        for pno, page in enumerate(self.doc):
            lines = OrderedDict()
            for w in page.get_text("words"):
                lines.setdefault((w[5], w[6]), []).append(w)
            for words in lines.values():
                text, spans = "", []
                for w in words:
                    if text:
                        text += " "
                    spans.append((len(text), len(text) + len(w[4]), fitz.Rect(w[:4])))
                    text += w[4].replace("\xa0", " ")
                for m in rx.finditer(text):
                    rect = fitz.Rect()
                    for a, b, wr in spans:
                        if b <= m.start() or a >= m.end():
                            continue
                        part = fitz.Rect(wr)
                        n = max(b - a, 1)
                        if wr.width >= wr.height:   # trim to the matched letters of a horizontal word
                            x0 = wr.x0 + wr.width * max(0, m.start() - a) / n
                            x1 = wr.x0 + wr.width * min(n, m.end() - a) / n
                            part = fitz.Rect(x0, wr.y0, x1, wr.y1)
                        rect = part if rect.is_empty else rect | part
                    if rect.is_empty:
                        continue
                    s = max(0, m.start() - 60)
                    snippet = ("…" if s else "") + text[s:m.end() + 90]
                    out.append({"p": pno, "r": self.rect_out(page, rect), "snippet": snippet})
                    if len(out) >= limit:
                        return out
    return out
