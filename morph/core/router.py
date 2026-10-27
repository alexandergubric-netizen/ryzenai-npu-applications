"""Which conversions are possible and how: a small graph of engines, searched for the cheapest route.

A route can chain engines (e.g. DOCX -> HTML (pandoc) -> PDF (Edge)), so Morph can reach far more
formats than any single tool.
"""
import heapq

from . import data, docs, images, media
from .formats import FORMATS

VIDEO_IN = {"mp4", "mkv", "webm", "mov", "m4v", "avi", "wmv", "flv", "mpeg", "ts", "3gp", "ogv", "mxf"}
AUDIO_IN = {"mp3", "m4a", "aac", "flac", "wav", "aiff", "ogg", "opus", "wma", "ac3", "amr", "ape", "wv", "caf",
            "mka", "dts"}
VIDEO_OUT = set(media.VIDEO)
AUDIO_OUT = set(media.AUDIO)
IMG_IN = {"png", "jpg", "webp", "avif", "heic", "gif", "bmp", "tiff", "ico", "icns", "tga", "jp2", "ppm", "psd",
          "svg", "dds", "pcx", "qoi", "raw"}
IMG_OUT = {"png", "jpg", "webp", "avif", "heic", "gif", "bmp", "tiff", "ico", "icns", "tga", "jp2", "ppm", "pdf"}
FITZ_DOCS = {"epub", "mobi", "fb2", "xps", "cbz"}
TABLE_IN = {"csv", "tsv", "xlsx", "xls", "ods", "parquet", "sqlite", "json", "yaml", "toml", "xml"}
TABLE_OUT = {"csv", "tsv", "xlsx", "ods", "json", "parquet", "xml", "html", "md", "sqlite"}
STRUCT = {"json", "yaml", "toml", "xml"}
ARCH_OUT = {"zip", "7z", "tar", "tgz", "tbz2", "txz"}
FONTS = {"ttf", "otf", "woff", "woff2"}
WRITER = {"doc", "docx", "odt", "rtf"}
CALC = {"xls", "xlsx", "ods"}
IMPRESS = {"ppt", "pptx", "odp"}

ALLOWED = {
    "video": {"video", "audio", "image"}, "audio": {"audio"}, "image": {"image", "document"},
    "document": {"document", "ebook", "presentation", "image"}, "ebook": {"ebook", "document"},
    "presentation": {"presentation", "document", "image"}, "spreadsheet": {"spreadsheet", "data", "document"},
    "data": {"data", "spreadsheet"}, "archive": {"archive"}, "font": {"font"}, "subtitle": {"subtitle"},
}
PAGE_IMAGES = {"png", "jpg", "webp", "tiff", "svg"}


class Edge:
    def __init__(self, engine, fn, srcs, dsts, cost=1.0, note=""):
        self.engine, self.fn, self.srcs, self.dsts, self.cost, self.note = engine, fn, set(srcs), set(dsts), cost, note


def _ffmpeg(ctx, src, dst, s, d):
    return media.run(ctx, src, dst, s, d, FORMATS[s]["cat"], ctx.info_for(src))


def engines():
    """What is installed right now."""
    return {
        "ffmpeg": bool(media.FFMPEG and media.FFPROBE), "pandoc": bool(docs.PANDOC), "pymupdf": bool(docs.fitz),
        "edge": bool(docs.edge_exe()), "libreoffice": bool(docs.soffice_exe()), "heif": images.HEIF,
        "raw": bool(images.rawpy), "7zip": bool(data.seven_zip_exe()),
        "pdf2docx": _has("pdf2docx") and _has("cv2"), "parquet": _has("pyarrow"),
    }


_found = {}


def _has(module):
    """Is an optional library installed? (checked without importing it - some are slow to load)"""
    if module not in _found:
        import importlib.util
        try:
            _found[module] = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            _found[module] = False
    return _found[module]


def edges():
    have = engines()
    img_in, img_out = set(IMG_IN), set(IMG_OUT)
    if not have["heif"]:
        img_in.discard("heic")
        img_out.discard("heic")
    if not have["raw"]:
        img_in.discard("raw")
    E = []
    if have["ffmpeg"]:
        E.append(Edge("ffmpeg", _ffmpeg, VIDEO_IN, VIDEO_OUT | AUDIO_OUT | {"gif", "webp", "png", "jpg"}))
        E.append(Edge("ffmpeg", _ffmpeg, AUDIO_IN, AUDIO_OUT))
        E.append(Edge("ffmpeg", _ffmpeg, {"gif"}, {"mp4", "webm", "mov", "mkv", "hevc"}))
        E.append(Edge("ffmpeg", _ffmpeg, {"srt", "vtt", "ass", "ssa", "sub"}, {"srt", "vtt", "ass", "ssa"}))
    E.append(Edge("pillow", images.convert, img_in, img_out))
    if have["pymupdf"]:
        E.append(Edge("pymupdf", docs.fitz_convert, {"pdf"}, {"pdf", "txt", "html"} | PAGE_IMAGES))
        E.append(Edge("pymupdf", docs.fitz_convert, FITZ_DOCS | {"svg"}, {"pdf"}, 1.6))
        E.append(Edge("pymupdf", docs.fitz_convert, FITZ_DOCS, {"txt", "html"}, 1.5))
        if have["pdf2docx"]:   # optional; without it PDF -> Word goes through HTML
            E.append(Edge("pdf2docx", docs.pdf_to_docx, {"pdf"}, {"docx"}, 2.5,
                          "Layout is rebuilt - complex pages may shift"))
    if have["pandoc"]:
        E.append(Edge("pandoc", docs.pandoc_convert, set(docs.READ), set(docs.WRITE)))
        E.append(Edge("text", docs.text_to_html, {"txt"}, {"html"}, 0.5))
    if have["edge"]:
        E.append(Edge("edge", docs.html_to_pdf, {"html"}, {"pdf"}, 1.0))
    if have["libreoffice"]:
        E.append(Edge("libreoffice", docs.office_convert, WRITER, {"pdf", "docx", "doc", "odt", "rtf", "txt"}, 0.8))
        E.append(Edge("libreoffice", docs.office_convert, CALC, {"pdf", "xlsx", "xls", "ods"}, 0.8))
        E.append(Edge("libreoffice", docs.office_convert, IMPRESS, {"pdf", "pptx", "ppt", "odp"}, 0.8))
    table_in, table_out = set(TABLE_IN), set(TABLE_OUT)
    if not have["parquet"]:
        table_in.discard("parquet")
        table_out.discard("parquet")
    E.append(Edge("table", data.table_convert, table_in, table_out - {"json"}, 1.2))
    E.append(Edge("table", data.table_convert, table_in - STRUCT, {"json"}, 1.1))  # JSON keeps all sheets in one file
    E.append(Edge("struct", data.struct_convert, STRUCT, STRUCT, 1.0))
    E.append(Edge("archive", data.archive_convert, {"zip", "7z", "tar", "tgz", "tbz2", "txz"} |
                  ({"rar"} if have["7zip"] else set()), ARCH_OUT))
    E.append(Edge("font", data.font_convert, FONTS, FONTS))
    return E


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


def plan(sfid, dfid, info=None):
    """The steps (engine function, from, to) for one conversion."""
    E = edges()
    r = routes(sfid, info, E)
    if dfid not in r:
        raise ValueError(f"No route from {sfid} to {dfid}")
    by_engine = {}
    for e in E:
        by_engine.setdefault(e.engine, []).append(e)
    steps = []
    for engine, a, b in r[dfid]["steps"]:
        fn = next(e.fn for e in by_engine[engine] if a in e.srcs and b in e.dsts)
        steps.append((engine, fn, a, b))
    return steps
