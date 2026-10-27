"""Pictures with Pillow (+ HEIC, camera RAW and SVG)."""
import io

from PIL import Image, ImageOps, ImageSequence

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF = True
except ImportError:
    HEIF = False
try:
    import rawpy
except ImportError:
    rawpy = None
try:
    import fitz
except ImportError:
    fitz = None

Image.MAX_IMAGE_PIXELS = 400_000_000
MAX_FRAMES = 3000                     # animated GIF/WebP/TIFF: frames kept in memory at once
MAX_FRAME_PIXELS = 1_500_000_000      # frames × width × height (about 6 GB of RGBA)

SAVE_AS = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP", "avif": "AVIF", "heic": "HEIF", "gif": "GIF", "bmp": "BMP",
           "tiff": "TIFF", "ico": "ICO", "icns": "ICNS", "tga": "TGA", "jp2": "JPEG2000", "ppm": "PPM", "pdf": "PDF"}
NO_ALPHA = {"jpg", "bmp", "ppm", "pdf", "jp2"}
ANIMATED = {"gif", "webp", "png", "avif"}
QUALITY = {"original": 95, "high": 90, "balanced": 82, "small": 65}


def open_image(path, fid, max_px=None):
    """Any supported picture as a Pillow image."""
    if fid == "raw":
        if not rawpy:
            raise RuntimeError("Camera RAW support (rawpy) is not installed")
        with rawpy.imread(path) as raw:
            rgb = raw.postprocess(use_camera_wb=True, output_bps=8, no_auto_bright=False)
        return Image.fromarray(rgb)
    if fid == "svg":
        if not fitz:
            raise RuntimeError("SVG needs PyMuPDF")
        doc = fitz.open(path)
        page = doc[0]
        long = max(page.rect.width, page.rect.height) or 1
        zoom = (max_px or 2048) / long
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True)
        return Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
    return Image.open(path)


def facts(path, fid):
    info = {}
    try:
        if fid == "svg":
            info["vector"] = True
            return info
        if fid == "raw" and rawpy:
            with rawpy.imread(path) as raw:
                info.update(width=raw.sizes.width, height=raw.sizes.height, camera=True)
            return info
        im = Image.open(path)
        info.update(width=im.width, height=im.height, mode=im.mode, frames=getattr(im, "n_frames", 1))
        info["alpha"] = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
        if info["alpha"] and im.width * im.height < 30_000_000:
            try:  # is the alpha channel actually used?
                lo, _ = im.convert("RGBA").getchannel("A").getextrema()
                info["alpha"] = lo < 255
            except (OSError, ValueError):
                pass
        exif = im.getexif()
        if exif:
            info["exif"] = True
            make, model = exif.get(0x010F), exif.get(0x0110)
            if model:
                info["camera"] = f"{make or ''} {model}".strip()
        if im.info.get("dpi"):
            info["dpi"] = round(float(im.info["dpi"][0]))
    except Exception:
        pass
    return info


def thumbnail(path, fid, out):
    if fid == "raw" and rawpy:
        with rawpy.imread(path) as raw:
            try:
                th = raw.extract_thumb()
                im = Image.open(io.BytesIO(th.data)) if th.format == rawpy.ThumbFormat.JPEG else Image.fromarray(th.data)
            except rawpy.LibRawError:
                im = open_image(path, fid)
    else:
        im = open_image(path, fid, max_px=640)
    im = ImageOps.exif_transpose(im) if fid not in ("svg",) else im
    im.thumbnail((640, 640))
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA")
    im.save(out, "WEBP", quality=80)


def _flatten(im, bg=(255, 255, 255)):
    """Drop transparency onto white for formats that have none."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        base = Image.new("RGB", im.size, bg)
        base.paste(im, mask=im.getchannel("A"))
        return base
    return im.convert("RGB") if im.mode != "RGB" else im


def _normal(im):
    if im.mode in ("RGB", "RGBA", "L", "LA", "P", "1"):
        return im
    if im.mode.startswith("I;16") or im.mode == "I":   # 16-bit greyscale -> 8-bit
        return im.convert("I").point(lambda v: v * (1 / 256)).convert("L")
    if im.mode == "F":
        return im.convert("L")
    return im.convert("RGBA" if "A" in im.mode else "RGB")


def _prepare(im, dfid, max_px):
    im = _normal(im)
    if max_px and max(im.size) > max_px:
        im = im.copy()
        im.thumbnail((max_px, max_px), Image.LANCZOS)
    if dfid in NO_ALPHA:
        im = _flatten(im)
    elif dfid in ("ico", "icns"):
        im = im.convert("RGBA")
        side = max(im.size)
        if im.width != im.height:
            sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
            im = sq
        if dfid == "icns" and side < 1024:
            im = im.resize((1024, 1024), Image.LANCZOS)
    elif dfid == "gif":
        pass
    elif im.mode == "P":
        im = im.convert("RGBA")
    return im


def convert(ctx, src, dst, sfid, dfid):
    opts = ctx.opts
    q = opts.get("quality") or "balanced"
    max_px = int(opts.get("max_px") or 0) or None
    keep_meta = not opts.get("strip")
    im = open_image(src, sfid, max_px=max_px)
    ctx.progress(0.2, "Decoding")
    frames = getattr(im, "n_frames", 1)
    exif = None
    if sfid not in ("svg", "raw"):
        try:
            im = ImageOps.exif_transpose(im) if frames == 1 else im
            if keep_meta and im.getexif():
                exif = im.getexif().tobytes()
        except Exception:
            exif = None
    icc = im.info.get("icc_profile") if keep_meta else None
    fmt = SAVE_AS[dfid]
    kw = {}
    qual = QUALITY[q]
    if dfid == "jpg":
        kw = dict(quality=qual, optimize=True, progressive=True, subsampling=0 if q in ("original", "high") else 2)
    elif dfid == "webp":
        kw = dict(quality=qual, method=5 if q == "small" else 4)
        if q == "original" and sfid in ("png", "gif", "bmp", "tiff"):
            kw = dict(lossless=True, method=4)
    elif dfid == "avif":
        kw = dict(quality={"original": 85, "high": 78, "balanced": 63, "small": 45}[q], speed=6)
    elif dfid == "heic":
        kw = dict(quality={"original": 90, "high": 82, "balanced": 70, "small": 50}[q])
    elif dfid == "png":
        kw = dict(optimize=q == "small", compress_level=9 if q == "small" else 6)
    elif dfid == "tiff":
        kw = dict(compression="tiff_lzw")
    elif dfid == "ico":
        kw = dict(sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256) if s <= max(im.size)] or [(16, 16)])
    elif dfid == "jp2":
        kw = dict(quality_mode="rates", quality_layers=[{"original": 5, "high": 10, "balanced": 20, "small": 40}[q]])
    elif dfid == "pdf":
        kw = dict(resolution=float(im.info.get("dpi", (150,))[0] or 150))
    if exif and dfid in ("jpg", "webp", "png", "avif", "heic", "tiff"):
        kw["exif"] = exif
    if icc and dfid in ("jpg", "webp", "png", "avif", "heic", "tiff", "pdf"):
        kw["icc_profile"] = icc

    multi = frames > 1 and (dfid in ANIMATED or dfid in ("tiff", "pdf"))
    ctx.progress(0.5, "Encoding")
    if multi and (frames > MAX_FRAMES or frames * im.width * im.height > MAX_FRAME_PIXELS):
        # every frame is held in memory: refuse animations that would eat the RAM
        raise RuntimeError(f"This animation is too large to convert ({frames} frames of {im.width}×{im.height}).")
    if multi:
        seq = []
        durations = []
        for i, fr in enumerate(ImageSequence.Iterator(im)):
            seq.append(_prepare(fr.copy(), dfid, max_px))
            durations.append(fr.info.get("duration", im.info.get("duration", 100)) or 100)
            if ctx.cancelled:
                raise InterruptedError
            ctx.progress(0.5 + 0.4 * (i + 1) / frames, f"Frame {i + 1}/{frames}")
        if dfid != "gif" and len({f.mode for f in seq}) > 1:  # encoders want one mode for all frames
            mode = "RGBA" if any("A" in f.mode or f.mode == "P" for f in seq) and dfid not in NO_ALPHA else "RGB"
            seq = [f.convert(mode) for f in seq]
        extra = dict(duration=durations, loop=im.info.get("loop", 0)) if dfid in ANIMATED else {}
        if dfid == "gif":
            extra["disposal"] = 2
        seq[0].save(dst, fmt, save_all=True, append_images=seq[1:], **extra, **kw)
    else:
        out = _prepare(im, dfid, max_px)
        out.save(dst, fmt, **kw)
    return dst


def to_pdf_bytes(path, fid):
    """One image as a single PDF page (used when merging files into one PDF)."""
    im = open_image(path, fid)
    frames = []
    for fr in ImageSequence.Iterator(im) if fid == "tiff" else [im]:
        frames.append(_flatten(ImageOps.exif_transpose(fr.copy()) if fid not in ("svg", "raw") else fr.copy()))
    buf = io.BytesIO()
    frames[0].save(buf, "PDF", save_all=True, append_images=frames[1:], resolution=150.0)
    return buf.getvalue()
