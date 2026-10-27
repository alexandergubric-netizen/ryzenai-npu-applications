"""Every format Morph knows: category, file extension, and a short upside/downside note.

The notes are the ground truth the AI advisor works from, and they show up as tooltips even without the AI.
"""
import os

CATEGORIES = {
    "video": "Video", "audio": "Audio", "image": "Image", "document": "Document", "ebook": "E-book",
    "presentation": "Presentation", "spreadsheet": "Spreadsheet", "data": "Data", "archive": "Archive",
    "font": "Font", "subtitle": "Subtitles",
}

# id: (category, output extension, display name, upside, downside, extra input extensions)
_F = {
    # ------------------------------------------------------------------ video
    "mp4": ("video", "mp4", "MP4 (H.264)", "Plays on every phone, TV, browser and editor", "Bigger than H.265/AV1 at the same quality", ()),
    "hevc": ("video", "mp4", "MP4 (H.265)", "About half the size of H.264 at the same quality; great for 4K", "Some browsers and older PCs/TVs cannot play it; slower to encode", ()),
    "av1": ("video", "mp4", "MP4 (AV1)", "Smallest files of all, royalty-free, modern streaming codec", "Very slow without a GPU encoder; older devices cannot decode it", ()),
    "webm": ("video", "webm", "WebM (VP9)", "Open web format, small files, perfect for websites", "Slow to encode; weak support in Apple apps and video editors", ()),
    "mkv": ("video", "mkv", "MKV", "Holds any codec, many audio tracks and subtitles; ideal archive container", "Browsers, iPhones and some TVs will not play it", ()),
    "mov": ("video", "mov", "MOV", "Native QuickTime format for Mac/iPhone and Final Cut", "Less universal on Windows/web than MP4", ("qt",)),
    "m4v": ("video", "m4v", "M4V", "Apple TV / iTunes flavour of MP4", "Same as MP4 but fewer apps recognise the extension", ()),
    "avi": ("video", "avi", "AVI", "Opens in very old players and legacy software", "Outdated, large files, no modern codecs", ("divx", "xvid")),
    "wmv": ("video", "wmv", "WMV", "Works in old Windows Media Player and PowerPoint", "Legacy, poor quality per MB, bad Mac support", ("asf",)),
    "flv": ("video", "flv", "FLV", "Accepted by some old streaming/RTMP tools", "Flash-era format, basically obsolete", ("f4v",)),
    "mpeg": ("video", "mpg", "MPEG-2", "DVD-style video understood by old hardware players", "Very large files for the quality", ("mpg", "mpe", "m2v", "vob")),
    "ts": ("video", "ts", "MPEG-TS", "Robust broadcast/streaming container, survives cut-off recordings", "Large, not ideal for sharing", ("mts", "m2ts")),
    "3gp": ("video", "3gp", "3GP", "Tiny files for very old phones", "Low quality, obsolete", ("3g2",)),
    "ogv": ("video", "ogv", "OGV (Theora)", "Fully open and patent-free", "Poor quality per MB, little support", ()),
    "mxf": ("video", "mxf", "MXF", "Professional camera/broadcast format", "Huge files, pro tools only", ()),
    # ------------------------------------------------------------------ audio
    "mp3": ("audio", "mp3", "MP3", "Plays literally everywhere, including car stereos", "Lower quality per MB than AAC or Opus; lossy", ()),
    "m4a": ("audio", "m4a", "M4A (AAC)", "Better than MP3 at the same size; native on iPhone/iTunes", "Lossy; a few very old players skip it", ("m4b", "m4r")),
    "aac": ("audio", "aac", "AAC (raw)", "Same codec as M4A without the container", "Raw stream: no proper tags or cover art", ()),
    "alac": ("audio", "m4a", "ALAC (Apple Lossless)", "Lossless and plays natively on Apple devices", "Files ~2x bigger than MP3/AAC; weaker support outside Apple", ()),
    "flac": ("audio", "flac", "FLAC", "Lossless, ~50% smaller than WAV, full tags", "Several times larger than MP3; some Apple apps lack support", ()),
    "wav": ("audio", "wav", "WAV", "Uncompressed, edit-ready, every DAW opens it", "Huge files (~10 MB per minute), weak tagging", ("wave",)),
    "aiff": ("audio", "aiff", "AIFF", "Uncompressed Apple format with tags", "Huge files, Mac-oriented", ("aif", "aifc")),
    "ogg": ("audio", "ogg", "OGG (Vorbis)", "Open, good quality, used by games and Spotify", "Apple devices do not play it natively", ("oga",)),
    "opus": ("audio", "opus", "Opus", "Best lossy codec: excellent quality at tiny bitrates, great for voice", "Older devices and car stereos may not play it", ()),
    "wma": ("audio", "wma", "WMA", "Old Windows Media format", "Legacy; poor support outside Windows", ()),
    "ac3": ("audio", "ac3", "AC3 (Dolby Digital)", "5.1 surround for DVD and home cinema", "Not for music libraries or phones", ()),
    "amr": ("audio", "amr", "AMR", "Phone voice recordings", "Very low quality, input only", ()),
    "ape": ("audio", "ape", "APE (Monkey's Audio)", "Lossless, compact", "Rare support; input only", ()),
    "wv": ("audio", "wv", "WavPack", "Lossless/hybrid audio", "Rare support; input only", ()),
    "caf": ("audio", "caf", "CAF", "Apple Core Audio files", "Apple-only; input only", ()),
    "mka": ("audio", "mka", "MKA", "Matroska audio", "Rare; input only", ()),
    "dts": ("audio", "dts", "DTS", "Surround sound track", "Input only", ()),
    # ------------------------------------------------------------------ image
    "png": ("image", "png", "PNG", "Lossless, transparency, sharp text/screenshots", "Large for photos", ("apng",)),
    "jpg": ("image", "jpg", "JPG", "Small photos that open everywhere", "Lossy, no transparency, blurs text and edges", ("jpeg", "jpe", "jfif")),
    "webp": ("image", "webp", "WebP", "25-35% smaller than JPG, supports transparency and animation", "Some older editors, print shops and Office versions cannot open it", ()),
    "avif": ("image", "avif", "AVIF", "Smallest modern format (~50% of JPG), HDR and transparency", "Slower to save; older software cannot open it", ()),
    "heic": ("image", "heic", "HEIC", "iPhone photo format, very small", "Poor support on Windows, web and Android", ("heif",)),
    "gif": ("image", "gif", "GIF", "Animation that plays everywhere (chats, email)", "Only 256 colours, huge files for video clips", ()),
    "bmp": ("image", "bmp", "BMP", "Uncompressed, opens in ancient software", "Enormous files", ("dib",)),
    "tiff": ("image", "tiff", "TIFF", "Lossless, multi-page, print and archive standard", "Very large, not for web", ("tif",)),
    "ico": ("image", "ico", "ICO", "Windows/website icon with sizes up to 256 px", "Only for icons", ()),
    "icns": ("image", "icns", "ICNS", "macOS app icon", "Only for Mac icons", ()),
    "tga": ("image", "tga", "TGA", "Game/texture tools", "Large, legacy", ()),
    "jp2": ("image", "jp2", "JPEG 2000", "High quality, used in medicine and cinema", "Very poor everyday support", ("j2k", "jpf", "jpx")),
    "ppm": ("image", "ppm", "PPM (Netpbm)", "Dead-simple raw format for scripts", "Huge, no compression", ("pgm", "pbm", "pnm")),
    "psd": ("image", "psd", "PSD (Photoshop)", "Layered Photoshop file", "Input only - flattened on conversion", ()),
    "svg": ("image", "svg", "SVG", "Vector - infinitely sharp", "Input only here (rendered to pixels or PDF)", ()),
    "dds": ("image", "dds", "DDS", "Game textures", "Input only", ()),
    "pcx": ("image", "pcx", "PCX", "DOS-era paint format", "Input only", ()),
    "qoi": ("image", "qoi", "QOI", "Fast lossless format", "Input only", ()),
    "raw": ("image", "dng", "Camera RAW", "Full sensor data straight from the camera", "Input only - developed to a normal image", ("dng", "cr2", "cr3", "nef", "nrw", "arw", "srf", "sr2", "orf", "rw2", "raf", "pef", "srw", "x3f", "3fr", "iiq", "rwl")),
    # ------------------------------------------------------------------ document
    "pdf": ("document", "pdf", "PDF", "Looks identical everywhere, prints perfectly", "Hard to edit", ()),
    "docx": ("document", "docx", "Word (DOCX)", "Editable in Word, Google Docs, LibreOffice", "Layout can shift between apps", ("docm", "dotx")),
    "doc": ("document", "doc", "Word 97 (DOC)", "Opens in very old Word versions", "Legacy binary format", ("dot",)),
    "odt": ("document", "odt", "OpenDocument (ODT)", "Open standard, native to LibreOffice", "Some Word formatting is lost", ()),
    "rtf": ("document", "rtf", "RTF", "Rich text any word processor opens", "Limited formatting, large files", ()),
    "txt": ("document", "txt", "Plain text", "Opens anywhere, tiny, searchable", "No formatting or images", ("text", "log")),
    "md": ("document", "md", "Markdown", "Readable plain text with headings/lists; perfect for notes, GitHub, AI", "No page layout", ("markdown", "mdown", "mkd")),
    "html": ("document", "html", "HTML", "Opens in any browser, keeps formatting and images", "Not meant for printing or editing in Word", ("htm", "xhtml")),
    "tex": ("document", "tex", "LaTeX", "Scientific typesetting source", "Needs a LaTeX toolchain to view", ("latex",)),
    "rst": ("document", "rst", "reStructuredText", "Python/Sphinx documentation", "Niche", ()),
    "org": ("document", "org", "Org-mode", "Emacs notes and outlines", "Niche", ()),
    "adoc": ("document", "adoc", "AsciiDoc", "Technical documentation", "Niche", ("asciidoc",)),
    "textile": ("document", "textile", "Textile", "Old wiki/blog markup", "Niche", ()),
    "wiki": ("document", "wiki", "MediaWiki", "Paste straight into Wikipedia-style wikis", "Niche", ("mediawiki",)),
    "typ": ("document", "typ", "Typst", "Modern typesetting source", "Niche", ()),
    "ipynb": ("document", "ipynb", "Jupyter notebook", "Opens in Jupyter/VS Code", "Only for notebooks", ()),
    "xps": ("document", "xps", "XPS", "Microsoft's PDF alternative", "Input only", ("oxps",)),
    # ------------------------------------------------------------------ e-book
    "epub": ("ebook", "epub", "EPUB", "Standard e-book: reflows on phones, Kobo, Apple Books, Send-to-Kindle", "Not page-exact like PDF", ()),
    "mobi": ("ebook", "mobi", "MOBI", "Old Kindle format", "Input only (Kindle now accepts EPUB)", ("azw", "azw3", "prc")),
    "fb2": ("ebook", "fb2", "FictionBook", "Popular e-book format in Eastern Europe", "Few western readers support it", ()),
    "cbz": ("ebook", "cbz", "Comic book (CBZ)", "Image comics", "Input only", ()),
    # ------------------------------------------------------------------ presentation
    "pptx": ("presentation", "pptx", "PowerPoint (PPTX)", "Editable slides in PowerPoint/Google Slides", "Needs an office app", ("pptm", "ppsx")),
    "ppt": ("presentation", "ppt", "PowerPoint 97 (PPT)", "Old PowerPoint versions", "Legacy", ("pps",)),
    "odp": ("presentation", "odp", "OpenDocument slides", "LibreOffice Impress", "Some PowerPoint effects lost", ()),
    # ------------------------------------------------------------------ spreadsheet
    "xlsx": ("spreadsheet", "xlsx", "Excel (XLSX)", "Excel/Google Sheets with sheets and formatting", "Needs a spreadsheet app", ("xlsm",)),
    "xls": ("spreadsheet", "xls", "Excel 97 (XLS)", "Old Excel versions", "Legacy, 65k row limit", ()),
    "ods": ("spreadsheet", "ods", "OpenDocument sheet", "LibreOffice Calc, open standard", "Some Excel features lost", ()),
    "csv": ("spreadsheet", "csv", "CSV", "Universal table format every tool imports", "One sheet, no formatting or formulas", ()),
    "tsv": ("spreadsheet", "tsv", "TSV", "Like CSV but tab-separated - safe with commas in text", "One sheet, no formatting", ("tab",)),
    "parquet": ("spreadsheet", "parquet", "Parquet", "Compressed columnar data for pandas/Spark/DuckDB - tiny and fast", "Not human-readable, no Excel", ()),
    "sqlite": ("spreadsheet", "sqlite", "SQLite database", "Query tables with SQL, one portable file", "Needs a database tool", ("db", "sqlite3")),
    # ------------------------------------------------------------------ data
    "json": ("data", "json", "JSON", "Standard for APIs and apps", "No comments, verbose for configs", ()),
    "yaml": ("data", "yaml", "YAML", "Human-friendly config files", "Indentation-sensitive", ("yml",)),
    "toml": ("data", "toml", "TOML", "Clean config format (Python, Rust)", "Needs a table at the top level", ()),
    "xml": ("data", "xml", "XML", "Enterprise/legacy data exchange", "Verbose", ()),
    # ------------------------------------------------------------------ archive
    "zip": ("archive", "zip", "ZIP", "Opens on every OS without extra tools", "Weaker compression than 7z", ()),
    "7z": ("archive", "7z", "7z", "Best compression ratio", "Needs 7-Zip or similar on most systems", ()),
    "tar": ("archive", "tar", "TAR", "Unix bundle keeping permissions", "No compression by itself", ()),
    "tgz": ("archive", "tar.gz", "TAR.GZ", "Standard Linux/macOS archive", "Slower to open single files", ()),
    "tbz2": ("archive", "tar.bz2", "TAR.BZ2", "Better compression than gzip", "Slow", ("tbz",)),
    "txz": ("archive", "tar.xz", "TAR.XZ", "Excellent compression, Linux standard", "Slow to compress", ()),
    "rar": ("archive", "rar", "RAR", "Common download format", "Input only (needs 7-Zip)", ()),
    # ------------------------------------------------------------------ font
    "ttf": ("font", "ttf", "TrueType (TTF)", "Installs on every OS", "Larger than web fonts", ()),
    "otf": ("font", "otf", "OpenType (OTF)", "Installs everywhere, PostScript outlines", "Larger than web fonts", ()),
    "woff": ("font", "woff", "WOFF", "Compressed web font, all browsers", "Not for installing on the PC", ()),
    "woff2": ("font", "woff2", "WOFF2", "Smallest web font - best for websites", "Not for installing on the PC", ()),
    # ------------------------------------------------------------------ subtitles
    "srt": ("subtitle", "srt", "SRT", "Works in every player and YouTube", "No styling", ()),
    "vtt": ("subtitle", "vtt", "WebVTT", "Subtitles for HTML5 web video", "Fewer desktop players", ()),
    "ass": ("subtitle", "ass", "ASS", "Styled/positioned subtitles (anime fansubs)", "Styling lost in simpler players", ()),
    "ssa": ("subtitle", "ssa", "SSA", "Older SubStation Alpha", "Superseded by ASS", ()),
    "sub": ("subtitle", "sub", "MicroDVD SUB", "Old frame-based subtitles", "Input only", ()),
}

FORMATS = {}
EXT_MAP = {}
for _id, (_cat, _ext, _name, _up, _down, _alias) in _F.items():
    FORMATS[_id] = {"id": _id, "cat": _cat, "ext": _ext, "name": _name, "up": _up, "down": _down}
for _id, (_cat, _ext, _n, _u, _d, _alias) in _F.items():
    for e in (_ext,) + tuple(_alias):
        EXT_MAP.setdefault(e, _id)
EXT_MAP["m4a"] = "m4a"          # ALAC and AAC share .m4a; the probe tells them apart
EXT_MAP["mp4"] = "mp4"
EXT_MAP["tar.gz"] = "tgz"
EXT_MAP["tar.bz2"] = "tbz2"
EXT_MAP["tar.xz"] = "txz"
EXT_MAP["txz"] = "txz"
EXT_MAP["tgz"] = "tgz"
EXT_MAP["db"] = "sqlite"

LOSSLESS_AUDIO = {"flac", "wav", "aiff", "alac", "ape", "wv"}


def split_name(name):
    """('holiday', 'tar.gz') - knows the double extensions."""
    low = name.lower()
    for double in ("tar.gz", "tar.bz2", "tar.xz"):
        if low.endswith("." + double):
            return name[: -len(double) - 1], double
    stem, ext = os.path.splitext(name)
    return stem, ext[1:].lower()


MAGIC = [
    (b"\x89PNG", "png"), (b"\xff\xd8\xff", "jpg"), (b"GIF8", "gif"), (b"%PDF", "pdf"), (b"BM", "bmp"),
    (b"fLaC", "flac"), (b"OggS", "ogg"), (b"ID3", "mp3"), (b"\x1a\x45\xdf\xa3", "mkv"), (b"7z\xbc\xaf", "7z"),
    (b"Rar!", "rar"), (b"wOFF", "woff"), (b"wOF2", "woff2"), (b"{\\rtf", "rtf"), (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"), (b"8BPS", "psd"), (b"SQLite format 3", "sqlite"),
]


def sniff(path):
    """Format id from the first bytes, for files with a missing or wrong extension."""
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError:
        return None
    for sig, fid in MAGIC:
        if head.startswith(sig):
            return fid
    if head[:4] == b"RIFF":
        return {b"WAVE": "wav", b"WEBP": "webp", b"AVI ": "avi"}.get(head[8:12])
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"heic", b"heix", b"mif1", b"msf1"):
            return "heic"
        if brand in (b"avif", b"avis"):
            return "avif"
        if brand.startswith(b"M4A"):
            return "m4a"
        if brand == b"qt  ":
            return "mov"
        return "mp4"
    if head[:2] == b"PK":
        import zipfile
        try:
            names = zipfile.ZipFile(path).namelist()
        except (zipfile.BadZipFile, OSError):
            return "zip"
        if "word/document.xml" in names:
            return "docx"
        if "xl/workbook.xml" in names:
            return "xlsx"
        if "ppt/presentation.xml" in names:
            return "pptx"
        if "mimetype" in names and any(n.endswith(".opf") for n in names):
            return "epub"
        return "zip"
    return None


def identify(path, name=None):
    """Format id for a file: extension first, magic bytes when the extension is unknown."""
    _, ext = split_name(name or os.path.basename(path))
    fid = EXT_MAP.get(ext)
    if not fid or fid in ("zip",):
        fid = sniff(path) or fid
    return fid


def suggest(fid, info, targets):
    """Rule-based picks shown instantly (the AI can refine them)."""
    cat = FORMATS[fid]["cat"] if fid in FORMATS else None
    picks = []
    big = info.get("size", 0) > 200 * 1024 * 1024
    if cat == "video":
        picks = ["mp4", "hevc" if big else "webm", "mp3"]
        if fid == "mp4" and info.get("vcodec") == "h264":
            picks = ["hevc", "webm", "gif" if (info.get("duration") or 99) < 20 else "mp3"]
    elif cat == "audio":
        if fid in LOSSLESS_AUDIO or info.get("acodec") == "alac":
            picks = ["flac" if fid != "flac" else "alac", "mp3", "opus"]
        else:
            picks = ["mp3" if fid != "mp3" else "m4a", "opus", "flac"]
    elif cat == "image":
        if fid == "gif" and info.get("frames", 1) > 1:
            picks = ["mp4", "webp", "png"]
        elif fid in ("svg",):
            picks = ["png", "pdf", "webp"]
        elif fid in ("raw", "psd", "tiff"):
            picks = ["jpg", "png", "tiff" if fid != "tiff" else "webp"]
        elif info.get("alpha"):
            picks = ["png" if fid != "png" else "webp", "webp" if fid != "png" else "avif", "ico"]
        else:
            picks = ["jpg", "webp", "avif", "pdf"]
    elif fid == "pdf":
        picks = ["docx", "png", "txt"]
    elif cat == "document":
        picks = ["pdf", "docx" if fid != "docx" else "md", "html" if fid != "html" else "md"]
    elif cat == "ebook":
        picks = ["epub" if fid != "epub" else "pdf", "pdf" if fid != "epub" else "txt", "txt"]
    elif cat == "presentation":
        picks = ["pdf", "pptx" if fid != "pptx" else "md", "md"]
    elif cat == "spreadsheet":
        picks = (["xlsx", "json", "parquet"] if fid in ("csv", "tsv") else ["csv", "pdf", "json"])
    elif cat == "data":
        picks = {"json": ["yaml", "csv", "xml"], "yaml": ["json", "toml"], "toml": ["json", "yaml"],
                 "xml": ["json", "yaml", "csv"]}.get(fid, ["json"])
    elif cat == "archive":
        picks = ["7z", "tgz", "zip"] if fid == "zip" else ["zip", "7z"]
    elif cat == "font":
        picks = ["woff2", "woff"] if fid in ("ttf", "otf") else ["ttf", "otf", "woff2"]
    elif cat == "subtitle":
        picks = ["vtt", "ass"] if fid == "srt" else ["srt", "vtt"]
    out = []
    for p in picks:
        if p in targets and p != fid and p not in out:
            out.append(p)
    return out[:3]
