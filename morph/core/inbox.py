"""Files the user brought in: identification, facts, thumbnails and possible targets."""
import os
import shutil
import threading
import uuid

from . import config, data, docs, images, media, router
from .formats import CATEGORIES, FORMATS, identify, split_name, suggest

THUMBS = os.path.join(config.WORK, "thumbs")
os.makedirs(THUMBS, exist_ok=True)

POPULAR = ["mp4", "hevc", "webm", "mkv", "mov", "av1", "gif", "mp3", "m4a", "flac", "wav", "opus", "ogg", "alac",
           "jpg", "png", "webp", "avif", "heic", "pdf", "docx", "md", "txt", "html", "odt", "rtf", "epub",
           "xlsx", "csv", "json", "yaml", "zip", "7z", "woff2", "srt", "vtt"]


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def human_time(s):
    s = int(round(s or 0))
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


CODEC_NAMES = {"h264": "H.264", "hevc": "H.265", "av1": "AV1", "vp9": "VP9", "vp8": "VP8", "mpeg4": "MPEG-4",
               "prores": "ProRes", "aac": "AAC", "mp3": "MP3", "opus": "Opus", "vorbis": "Vorbis", "flac": "FLAC",
               "alac": "ALAC", "ac3": "AC3", "eac3": "E-AC3", "mpeg2video": "MPEG-2", "mjpeg": "MJPEG"}


def facts_line(fid, info):
    """Short human facts, e.g. ['3840×2160', 'H.265', '60 fps', '3:24']."""
    out = []
    if info.get("width") and info.get("height"):
        out.append(f"{info['width']}×{info['height']}")
    if info.get("vcodec"):
        out.append(CODEC_NAMES.get(info["vcodec"], info["vcodec"].upper()))
    if info.get("hdr"):
        out.append("HDR")
    if info.get("fps"):
        out.append(f"{info['fps']:g} fps")
    if info.get("duration"):
        out.append(human_time(info["duration"]))
    if info.get("acodec"):
        ch = {1: "mono", 2: "stereo", 6: "5.1", 8: "7.1"}.get(info.get("channels"), f"{info.get('channels')}ch")
        a = CODEC_NAMES.get(info["acodec"], info["acodec"].split("_")[0].upper())
        if info.get("abitrate") and not info.get("vcodec"):
            a += f" {info['abitrate'] // 1000} kb/s"
        if info.get("sample_rate") and not info.get("vcodec"):
            a += f" · {info['sample_rate'] / 1000:g} kHz"
        out.append(f"{a} {ch}")
    if info.get("frames", 1) > 1:
        out.append(f"{info['frames']} frames")
    if info.get("alpha"):
        out.append("transparent")
    if info.get("camera") and isinstance(info["camera"], str):
        out.append(info["camera"])
    if info.get("vector"):
        out.append("vector")
    if info.get("pages"):
        out.append(f"{info['pages']} page{'s' if info['pages'] != 1 else ''}")
    if info.get("scanned"):
        out.append("scanned (no text layer)")
    if info.get("encrypted"):
        out.append("password protected")
    if info.get("words"):
        out.append(f"{info['words']:,} words".replace(",", " "))
    if info.get("sheets"):
        out.append(f"{info['sheets']} sheet{'s' if info['sheets'] != 1 else ''}")
    if info.get("rows"):
        out.append(f"{info['rows']:,} rows × {info.get('cols', '?')} cols".replace(",", " "))
    if info.get("images") and info.get("words"):
        out.append(f"{info['images']} image{'s' if info['images'] != 1 else ''}")
    if info.get("tables") and info.get("words"):
        out.append(f"{info['tables']} table{'s' if info['tables'] != 1 else ''}")
    if info.get("items") is not None:
        out.append(f"list of {info['items']} {'records' if info.get('tabular') else 'items'}")
    if info.get("keys") is not None:
        out.append(f"{info['keys']} top-level keys" + (" · contains tables" if info.get("tabular") else ""))
    if info.get("invalid"):
        out.append("invalid: " + info["invalid"])
    if info.get("files"):
        out.append(f"{info['files']} files, {human_size(info.get('unpacked', 0))} unpacked")
    if info.get("family"):
        out.append(f"{info['family']} · {info.get('outlines')}")
    return out


class Inbox:
    def __init__(self):
        self.items = {}
        self.lock = threading.Lock()

    def add(self, path, name=None, temp=False):
        name = name or os.path.basename(path)
        fid = identify(path, name)
        fid = fid if fid in FORMATS else None
        size = os.path.getsize(path)
        entry = {"id": uuid.uuid4().hex[:12], "path": path, "name": name, "fid": fid, "temp": temp,
                 "size": size, "size_h": human_size(size), "info": {"size": size}}
        if not fid:
            _, ext = split_name(name)
            entry.update(cat=None, error=f"Morph does not know .{ext or '?'} files yet")
        else:
            cat = FORMATS[fid]["cat"]
            entry["cat"] = cat
            entry["info"].update(self._facts(path, fid, cat))
            if fid == "m4a" and entry["info"].get("acodec") == "alac":
                entry["info"]["lossless"] = True
            if entry["info"].get("encrypted"):
                entry["error"] = "This PDF is password protected - unlock it first"
        entry["facts"] = facts_line(fid, entry["info"]) if fid else []
        self.refresh_targets(entry)
        with self.lock:
            self.items[entry["id"]] = entry
        return entry

    def refresh_targets(self, entry):
        if not entry.get("fid") or entry.get("error"):
            entry["targets"], entry["picks"] = [], []
            return
        r = router.routes(entry["fid"], entry["info"])
        order = {k: i for i, k in enumerate(POPULAR)}
        cat_order = list(CATEGORIES)
        targets = sorted(r.values(), key=lambda t: (not t["compress"], cat_order.index(t["cat"]) if t["cat"] != entry["cat"] else -1,
                                                    order.get(t["id"], 99), t["cost"]))
        entry["targets"] = targets
        entry["picks"] = suggest(entry["fid"], entry["info"], {t["id"] for t in targets})
        if not targets:
            hint = " Install LibreOffice to unlock it." if entry["fid"] in ("doc", "ppt", "pptx", "odp", "xls") else ""
            entry["error"] = f"No converter for {FORMATS[entry['fid']]['name']} is available.{hint}"

    def _facts(self, path, fid, cat):
        try:
            if cat in ("video", "audio"):
                return media.probe(path)
            if cat == "image":
                info = images.facts(path, fid)
                if fid == "gif" and info.get("frames", 1) > 1:
                    info.update({k: v for k, v in media.probe(path).items() if k in ("duration",)})
                return info
            if fid == "pdf":
                return docs.pdf_facts(path)
            if fid in ("epub", "mobi", "fb2", "xps", "cbz") and docs.fitz:
                return {"pages": docs.fitz.open(path).page_count}
            if cat == "data":
                return data.struct_facts(path, fid)
            if cat in ("document", "spreadsheet"):
                return {**docs.word_count(path, fid), **data.table_facts(path, fid)}
            if cat == "archive":
                return data.archive_facts(path, fid)
            if cat == "font":
                return data.font_facts(path)
        except Exception:
            pass
        return {}

    def get(self, fid):
        return self.items.get(fid)

    def remove(self, file_id):
        with self.lock:
            e = self.items.pop(file_id, None)
        if e and e["temp"]:
            shutil.rmtree(os.path.dirname(e["path"]), ignore_errors=True)
        for x in (".webp", ".jpg", ".png"):
            if os.path.exists(os.path.join(THUMBS, file_id + x)):
                os.remove(os.path.join(THUMBS, file_id + x))

    def thumbnail(self, file_id):
        """Path of a small preview image, or None."""
        e = self.items.get(file_id)
        if not e or not e.get("fid"):
            return None
        out = os.path.join(THUMBS, file_id)
        made = next((out + x for x in (".webp", ".jpg", ".png") if os.path.exists(out + x)), None)
        if made or e.get("no_thumb"):
            return made
        fid, cat = e["fid"], e["cat"]
        try:
            if cat == "image":
                images.thumbnail(e["path"], fid, out + ".webp")
            elif cat == "video":
                media.thumbnail(e["path"], out + ".jpg", e["info"])
            elif cat == "audio":
                media.thumbnail(e["path"], out + ".png", e["info"], audio=True)
            elif fid in ("pdf", "epub", "xps", "mobi", "fb2", "cbz") and docs.fitz:
                docs.fitz_thumbnail(e["path"], out + ".png")
        except Exception:
            pass
        made = next((out + x for x in (".webp", ".jpg", ".png") if os.path.exists(out + x)), None)
        e["no_thumb"] = not made
        return made

    def public(self, e):
        return {k: e.get(k) for k in ("id", "name", "fid", "cat", "size", "size_h", "facts", "targets", "picks", "error")} | {
            "fmt": FORMATS[e["fid"]]["name"] if e.get("fid") else None,
            "has_path": not e["temp"], "info": {k: v for k, v in e["info"].items() if k != "tags"}}

    def clear_temp(self):
        shutil.rmtree(config.INBOX, ignore_errors=True)
        shutil.rmtree(THUMBS, ignore_errors=True)
        os.makedirs(config.INBOX, exist_ok=True)
        os.makedirs(THUMBS, exist_ok=True)


inbox = Inbox()
