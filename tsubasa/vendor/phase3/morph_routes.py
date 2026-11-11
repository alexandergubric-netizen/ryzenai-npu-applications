# Source: morph/core/router.py SHA-256 c7db7ae574fb42156ed45a7ed780c31d9006bdde102a2cb5257f96f5ed81358e
import heapq
from .formats import FORMATS
ALLOWED={"document":{"document","image","data","spreadsheet"},"spreadsheet":{"spreadsheet","data","document"},"data":{"spreadsheet","data","document"}}
WRITER={"docx"}; IMPRESS=set(); PAGE_IMAGES={"png"}

class Edge:
    def __init__(self, engine, fn, srcs, dsts, cost=1.0, note=""):
        self.engine, self.fn, self.srcs, self.dsts, self.cost, self.note = engine, fn, set(srcs), set(dsts), cost, note

def routes(sfid, info=None, edge_list=None):
    """{target id: route} for everything reachable from sfid, cheapest route each."""
    info = info or {}
    E = edge_list or edges()
    scat = FORMATS[sfid]["cat"]
    allowed = ALLOWED.get(scat, {scat})
    best = {}
    heap = [(0.0, 0, sfid, [])]
    counter = 0
    while heap:
        cost, _, node, path = heapq.heappop(heap)
        if len(path) >= 3:
            continue
        for e in E:
            if node not in e.srcs:
                continue
            for d in e.dsts:
                if d == node and path:
                    continue
                if any(d == step[2] for step in path) or (d == sfid and path):
                    continue
                c = cost + e.cost
                step = (e, node, d)
                if d not in best or c < best[d][0]:
                    best[d] = (c, path + [step])
                    if d != sfid:
                        counter += 1
                        heapq.heappush(heap, (c, counter, d, path + [step]))
    out = {}
    for d, (c, path) in best.items():
        if d not in FORMATS:
            continue
        if d == sfid and not (scat in ("video", "audio", "image") or sfid == "pdf"):
            continue  # "same format, smaller" only makes sense where there is something to recompress
        dcat = FORMATS[d]["cat"]
        animated = sfid == "gif" and info.get("frames", 1) > 1
        if dcat not in allowed and not (animated and dcat == "video"):
            continue
        if scat == "image" and d == "svg":
            continue
        if dcat == "image" and scat != "image":
            if scat == "video" and len(path) > 1:
                continue
            if scat != "video" and d not in PAGE_IMAGES:
                continue
        if scat == "image" and dcat == "document" and d != "pdf":
            continue
        if scat == "spreadsheet" and dcat == "document" and d not in ("pdf", "html", "md", "docx", "odt"):
            continue
        if sfid == "gif" and info.get("frames", 1) <= 1 and dcat == "video":
            continue
        if scat == "font" and info.get("outlines"):
            if d == "otf" and info["outlines"] == "TrueType" or d == "ttf" and info["outlines"] != "TrueType":
                continue
        out[d] = _describe(sfid, d, c, path)
    return out

def _describe(sfid, d, cost, path):
    f = FORMATS[d]
    notes = [s[0].note for s in path if s[0].note]
    chain = [s[2] for s in path]
    if len(path) > 1:
        notes.append("Via " + " → ".join(FORMATS[x]["name"].split(" (")[0] for x in chain[:-1]))
    if sfid in WRITER | IMPRESS and d == "pdf" and any(s[0].engine == "edge" for s in path):
        notes.append("Layout approximated - install LibreOffice for an exact copy")
    if FORMATS[sfid]["cat"] == "video" and d in ("png", "jpg"):
        notes.append("Saves one still frame")
    if FORMATS[sfid]["cat"] == "video" and d in ("gif", "webp"):
        notes.append("Animated - best for short clips")
    if sfid == "pdf" and d in PAGE_IMAGES:
        notes.append("One image per page (zipped if several)")
    if d == sfid:
        notes.append("Re-encode smaller in the same format")
    return {"id": d, "name": f["name"], "cat": f["cat"], "ext": f["ext"], "up": f["up"], "down": f["down"],
            "cost": round(cost, 2), "steps": [(s[0].engine, s[1], s[2]) for s in path], "note": " · ".join(notes),
            "compress": d == sfid}
