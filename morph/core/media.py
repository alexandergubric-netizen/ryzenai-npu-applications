"""Audio, video, GIF and subtitle conversion with ffmpeg (GPU encoders on Radeon/Intel when they work)."""
import json
import os
import re
import shutil
import subprocess
import threading
from collections import deque

CREATE_NO_WINDOW = 0x08000000
# the installed app carries its own ffmpeg in <install>\tools; from source the one on PATH is used
_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools")


def _tool(name):
    p = os.path.join(_TOOLS, name + ".exe")
    return p if os.path.exists(p) else shutil.which(name)


FFMPEG = _tool("ffmpeg")
FFPROBE = _tool("ffprobe")

# target id -> container settings
VIDEO = {
    "mp4": ("h264", "aac"), "hevc": ("hevc", "aac"), "av1": ("av1", "aac"), "webm": ("vp9", "opus"),
    "mkv": ("h264", "aac"), "mov": ("h264", "aac"), "m4v": ("h264", "aac"), "avi": ("mpeg4", "mp3"),
    "wmv": ("wmv2", "wmav2"), "flv": ("h264", "aac"), "mpeg": ("mpeg2video", "mp2"), "ts": ("h264", "aac"),
    "3gp": ("h264", "aac"), "ogv": ("theora", "vorbis"),
}
AUDIO = {
    "mp3": "mp3", "m4a": "aac", "aac": "aac", "alac": "alac", "flac": "flac", "wav": "pcm", "aiff": "pcm_be",
    "ogg": "vorbis", "opus": "opus", "wma": "wmav2", "ac3": "ac3",
}
SUBS = {"srt": "srt", "vtt": "webvtt", "ass": "ass", "ssa": "ass"}
# which source codecs a container can take as-is (stream copy = instant and lossless)
COPY_V = {
    "mp4": {"h264", "hevc", "av1", "mpeg4"}, "mov": {"h264", "hevc", "prores", "mpeg4", "mjpeg"},
    "m4v": {"h264", "hevc"}, "mkv": None, "webm": {"vp8", "vp9", "av1"}, "ts": {"h264", "hevc", "mpeg2video"},
    "flv": {"h264"}, "avi": {"mpeg4", "msmpeg4v3", "mjpeg"}, "hevc": {"hevc"}, "av1": {"av1"},
    "mpeg": {"mpeg2video", "mpeg1video"}, "3gp": {"h264"}, "wmv": {"wmv2", "wmv3"}, "ogv": {"theora"},
}
COPY_A = {
    "mp4": {"aac", "mp3", "ac3", "alac"}, "mov": {"aac", "mp3", "alac", "pcm_s16le", "pcm_s24le"},
    "m4v": {"aac"}, "mkv": None, "webm": {"opus", "vorbis"}, "ts": {"aac", "mp3", "ac3"}, "flv": {"aac", "mp3"},
    "avi": {"mp3", "ac3", "pcm_s16le"}, "hevc": {"aac", "mp3", "ac3"}, "av1": {"aac", "opus"},
    "mpeg": {"mp2", "ac3"}, "3gp": {"aac"}, "wmv": {"wmav2"}, "ogv": {"vorbis"},
}
CRF = {  # quality -> (x264, x265, aom, vp9, amf h264 qp, amf hevc qp, amf av1 qp, mpeg4/2 q)
    "original": (18, 20, 24, 24, 20, 22, 90, 2),
    "high": (18, 20, 24, 24, 20, 22, 90, 2),
    "balanced": (23, 26, 32, 32, 26, 28, 120, 4),
    "small": (28, 30, 40, 38, 31, 33, 160, 7),
}
_amf = {}


def amf_ok(codec, kind="amf"):
    """Does this GPU encoder (Radeon AMF, or Intel Quick Sync with kind="qsv") actually work here?
    Tested once with a tiny clip; on any other PC the CPU encoders are used."""
    key = f"{codec}_{kind}"
    if key not in _amf:
        try:
            r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                                "testsrc=duration=0.2:size=320x240:rate=10", "-c:v", key, "-pix_fmt", "nv12",
                                "-f", "null", "-"], capture_output=True, timeout=30, creationflags=CREATE_NO_WINDOW)
            _amf[key] = r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            _amf[key] = False
    return _amf[key]


LOCAL_ONLY = ["-protocol_whitelist", "file,pipe"]   # a playlist disguised as .mp4 can't reach the network


def local_inputs(args):
    """Put the local-only protocol list before every input file (not before generated lavfi inputs)."""
    out = []
    for k, a in enumerate(args):
        if a == "-i" and not (k >= 2 and args[k - 2] == "-f" and args[k - 1] == "lavfi"):
            out += LOCAL_ONLY
        out.append(a)
    return out


def probe(path):
    """Facts about a media file from ffprobe."""
    try:
        out = subprocess.run([FFPROBE, "-v", "error"] + LOCAL_ONLY + ["-print_format", "json", "-show_format", "-show_streams", path],
                             capture_output=True, timeout=30, creationflags=CREATE_NO_WINDOW).stdout
        data = json.loads(out or b"{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}
    fmt = data.get("format", {})
    info = {"duration": float(fmt.get("duration") or 0) or None, "bitrate": int(fmt.get("bit_rate") or 0) or None,
            "container": fmt.get("format_name"), "tags": {k.lower(): v for k, v in (fmt.get("tags") or {}).items()
                                                          if k.lower() in ("title", "artist", "album", "make", "model",
                                                                           "com.apple.quicktime.model", "encoder")}}
    for s in data.get("streams", []):
        kind = s.get("codec_type")
        if kind == "video" and s.get("disposition", {}).get("attached_pic"):
            info["cover"] = True
        elif kind == "video" and "vcodec" not in info:
            info.update(vcodec=s.get("codec_name"), width=s.get("width"), height=s.get("height"),
                        pix_fmt=s.get("pix_fmt"), vbitrate=int(s.get("bit_rate") or 0) or None)
            try:
                n, d = (s.get("avg_frame_rate") or "0/1").split("/")
                info["fps"] = round(int(n) / int(d), 2) if int(d) else None
            except ValueError:
                pass
            if s.get("color_transfer") in ("smpte2084", "arib-std-b67"):
                info["hdr"] = True
            rot = next((sd.get("rotation") for sd in s.get("side_data_list", []) if "rotation" in sd), None)
            if rot:
                info["rotation"] = rot
        elif kind == "audio" and "acodec" not in info:
            info.update(acodec=s.get("codec_name"), channels=s.get("channels"),
                        sample_rate=int(s.get("sample_rate") or 0) or None,
                        abitrate=int(s.get("bit_rate") or 0) or None,
                        bits=s.get("bits_per_raw_sample") or s.get("bits_per_sample"))
        elif kind == "subtitle":
            info["subs"] = info.get("subs", 0) + 1
        if kind == "audio":
            info["audio_tracks"] = info.get("audio_tracks", 0) + 1
    if info.get("rotation") in (90, -90, 270, -270) and info.get("width"):
        info["width"], info["height"] = info["height"], info["width"]
    return info


def thumbnail(path, out, info, audio=False):
    """A still frame (video) or a waveform picture (audio)."""
    if audio:
        args = ["-i", path, "-filter_complex", "aformat=channel_layouts=mono,showwavespic=s=640x140:colors=0x8b7cff",
                "-frames:v", "1", out]
    else:
        at = min((info.get("duration") or 0) * 0.1, 30)
        args = ["-ss", f"{at:.2f}", "-i", path, "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4", out]
    r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y"] + local_inputs(args), capture_output=True,
                       timeout=60, creationflags=CREATE_NO_WINDOW)
    return r.returncode == 0


def _secs(v):
    """'1:23.5' or '83.5' -> seconds."""
    if v in (None, ""):
        return None
    try:
        parts = [float(p) for p in str(v).replace(",", ".").split(":")]
    except ValueError:
        return None
    s = 0
    for p in parts:
        s = s * 60 + p
    return s


def _scale(max_h):
    """Limit the short side to max_h (works for portrait video too), keep even sizes."""
    return (f"scale='if(gte(iw,ih),-2,min(iw,{max_h}))':'if(gte(iw,ih),min(ih,{max_h}),-2)'"
            f":flags=lanczos")


def _vcodec_args(codec, q, gpu, info):
    crf = CRF[q]
    if codec == "h264":
        if gpu and amf_ok("h264"):
            return ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", str(crf[4]),
                    "-qp_p", str(crf[4] + 2), "-qp_b", str(crf[4] + 4), "-pix_fmt", "nv12"], True
        if gpu and amf_ok("h264", "qsv"):   # Intel Quick Sync
            return ["-c:v", "h264_qsv", "-global_quality", str(crf[0] + 2), "-preset", "medium", "-look_ahead", "0",
                    "-pix_fmt", "nv12"], True
        return ["-c:v", "libx264", "-crf", str(crf[0]), "-preset", "medium", "-pix_fmt", "yuv420p"], False
    if codec == "hevc":
        if gpu and amf_ok("hevc"):
            return ["-c:v", "hevc_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", str(crf[5]),
                    "-qp_p", str(crf[5] + 2), "-qp_b", str(crf[5] + 4), "-pix_fmt", "nv12", "-tag:v", "hvc1"], True
        if gpu and amf_ok("hevc", "qsv"):
            return ["-c:v", "hevc_qsv", "-global_quality", str(crf[1] + 2), "-preset", "medium",
                    "-pix_fmt", "nv12", "-tag:v", "hvc1"], True
        return ["-c:v", "libx265", "-crf", str(crf[1]), "-preset", "fast", "-pix_fmt", "yuv420p",
                "-x265-params", "log-level=error", "-tag:v", "hvc1"], False
    if codec == "av1":
        if gpu and amf_ok("av1"):
            return ["-c:v", "av1_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", str(crf[6]),
                    "-qp_p", str(crf[6] + 10), "-pix_fmt", "nv12"], True
        return ["-c:v", "libaom-av1", "-crf", str(crf[2]), "-b:v", "0", "-cpu-used", "6", "-row-mt", "1",
                "-tiles", "2x2", "-pix_fmt", "yuv420p"], False
    if codec == "vp9":
        return ["-c:v", "libvpx-vp9", "-crf", str(crf[3]), "-b:v", "0", "-row-mt", "1", "-tile-columns", "2",
                "-deadline", "good", "-cpu-used", "2" if q in ("original", "high") else "5", "-threads", "0",
                "-pix_fmt", "yuv420p"], False
    if codec in ("mpeg4", "mpeg2video", "wmv2"):
        extra = ["-tag:v", "xvid"] if codec == "mpeg4" else []
        return ["-c:v", codec, "-q:v", str(crf[7]), "-pix_fmt", "yuv420p"] + extra, False
    if codec == "theora":
        return ["-c:v", "libtheora", "-q:v", {2: "9", 4: "7", 7: "5"}[crf[7]], "-pix_fmt", "yuv420p"], False
    return ["-c:v", codec], False


def _acodec_args(codec, q, info):
    hi = q in ("original", "high")
    sm = q == "small"
    if codec == "aac":
        return ["-c:a", "aac", "-b:a", "256k" if hi else "96k" if sm else "160k"]
    if codec == "mp3":
        return ["-c:a", "libmp3lame", "-q:a", "0" if hi else "5" if sm else "2"]
    if codec == "opus":
        return ["-c:a", "libopus", "-b:a", "160k" if hi else "64k" if sm else "112k", "-vbr", "on"]
    if codec == "vorbis":
        return ["-c:a", "libvorbis", "-q:a", "7" if hi else "3" if sm else "5"]
    if codec == "wmav2":
        return ["-c:a", "wmav2", "-b:a", "192k" if hi else "96k" if sm else "160k"]
    if codec == "ac3":
        return ["-c:a", "ac3", "-b:a", "448k" if hi else "192k" if sm else "384k"]
    if codec == "mp2":
        return ["-c:a", "mp2", "-b:a", "256k" if hi else "128k" if sm else "192k"]
    if codec == "flac":
        return ["-c:a", "flac", "-compression_level", "8"]
    if codec == "alac":
        return ["-c:a", "alac"]
    deep = str(info.get("bits") or "16") not in ("8", "16") or (info.get("acodec") or "").startswith(("pcm_s24", "pcm_s32", "pcm_f"))
    if codec == "pcm":
        return ["-c:a", "pcm_s24le" if deep else "pcm_s16le"]
    if codec == "pcm_be":
        return ["-c:a", "pcm_s24be" if deep else "pcm_s16be"]
    return ["-c:a", codec]


def build(src, dst, sfid, dfid, scat, info, opts):
    """ffmpeg arguments for one conversion. Returns (args, used_gpu)."""
    q = opts.get("quality") or "balanced"
    gpu = bool(opts.get("gpu", True))
    pre, post, vf = [], [], []
    start, end = _secs(opts.get("start")), _secs(opts.get("end"))
    if start:
        pre += ["-ss", f"{start:.3f}"]
    if end and end > (start or 0):
        post += ["-t", f"{end - (start or 0):.3f}"]
    if opts.get("max_h"):
        vf.append(_scale(int(opts["max_h"])))
    used_gpu = False
    args = []

    if dfid in SUBS:
        return ["-i", src, "-c:s", SUBS[dfid], dst], False

    if scat == "video" and dfid in ("png", "jpg"):
        # one still frame: the requested start or 10 % in
        if not start:
            pre = ["-ss", f"{min((info.get('duration') or 0) * 0.1, 30):.2f}"]
        return pre + ["-i", src, "-frames:v", "1"] + (["-vf", ",".join(vf)] if vf else []) + \
            (["-q:v", "2"] if dfid == "jpg" else []) + [dst], False

    if dfid in ("gif", "webp") and scat in ("video", "image"):
        fps = {"original": 15, "high": 15, "balanced": 12, "small": 10}[q]
        width = {"original": 720, "high": 640, "balanced": 480, "small": 320}[q]
        size = f"scale='min(iw,{width})':-2:flags=lanczos" if not opts.get("max_h") else vf[0]
        if dfid == "gif":
            chain = f"fps={fps},{size},split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4"
            return pre + ["-i", src] + post + ["-filter_complex", chain, "-loop", "0", dst], False
        quality = {"original": 85, "high": 80, "balanced": 70, "small": 55}[q]
        return pre + ["-i", src] + post + ["-vf", f"fps={fps},{size}", "-c:v", "libwebp", "-lossless", "0",
                                           "-q:v", str(quality), "-loop", "0", "-an", dst], False

    if dfid in AUDIO:
        acodec = AUDIO[dfid]
        cover = info.get("cover") and dfid in ("mp3", "flac", "m4a", "alac") and scat == "audio"
        maps = ["-map", "0:a:0"] + (["-map", "0:v:0", "-c:v", "copy", "-disposition:v:0", "attached_pic"] if cover else [])
        same = dfid == sfid and not start and not end
        if dfid == "m4a" and info.get("acodec") == "aac" and q == "original":
            a = ["-c:a", "copy"]
        elif same and q == "original":
            a = ["-c:a", "copy"]
        else:
            a = _acodec_args(acodec, q, info)
        if not cover:
            maps.append("-vn")
        fmt = ["-f", "adts"] if dfid == "aac" else (["-f", "ipod"] if dfid in ("m4a", "alac") else [])
        return pre + ["-i", src] + post + maps + a + ["-map_metadata", "0"] + fmt + [dst], False

    if dfid in VIDEO:
        vcodec, acodec = VIDEO[dfid]
        if scat == "image":  # animated GIF/WebP -> video
            vf.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
        reencode = q != "original" or vf or (start and dfid != "mkv")
        can_v = COPY_V.get(dfid, set())
        can_a = COPY_A.get(dfid, set())
        src_v = info.get("vcodec")
        copy_v = src_v == vcodec if dfid in ("hevc", "av1") else bool(src_v) and (can_v is None or src_v in can_v)
        if copy_v and not reencode:
            v = ["-c:v", "copy"]
            if dfid in ("mp4", "mov", "m4v", "hevc") and info.get("vcodec") == "hevc":
                v += ["-tag:v", "hvc1"]
        else:
            v, used_gpu = _vcodec_args(vcodec, q, gpu, info)
        if not info.get("acodec"):
            a = ["-an"]
        elif q == "original" and (can_a is None or info["acodec"] in can_a):
            a = ["-c:a", "copy"]
        else:
            a = _acodec_args(acodec, "high" if q == "original" else q, info)
        maps = ["-map", "0:v:0"] + (["-map", "0:a?"] if dfid == "mkv" else ["-map", "0:a:0?"])
        if dfid == "mkv":
            maps += ["-map", "0:s?", "-c:s", "copy"]
        fmt = []
        if dfid in ("mp4", "hevc", "av1", "mov", "m4v"):
            fmt = ["-movflags", "+faststart"]
        if dfid in ("hevc", "av1"):
            fmt += ["-f", "mp4"]
        if dfid == "3gp":
            if not opts.get("max_h"):
                vf.append(_scale(480))
            if info.get("acodec"):
                a = ["-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", "22050"]
        filt = ["-vf", ",".join(vf)] if vf and v[1] != "copy" else []
        return pre + ["-i", src] + post + maps + v + filt + a + ["-map_metadata", "0"] + fmt + [dst], used_gpu

    raise ValueError(f"ffmpeg cannot make {dfid}")


def run(ctx, src, dst, sfid, dfid, scat, info):
    """Run ffmpeg with live progress; falls back from the GPU encoder to the CPU one if it fails."""
    opts = dict(ctx.opts)
    args, used_gpu = build(src, dst, sfid, dfid, scat, info, opts)
    try:
        _ffmpeg(ctx, args, info, opts)
    except RuntimeError:
        if not used_gpu or ctx.cancelled:
            raise
        ctx.progress(None, "GPU encoder failed - retrying on CPU")
        opts["gpu"] = False
        args, _ = build(src, dst, sfid, dfid, scat, info, opts)
        _ffmpeg(ctx, args, info, opts)
    return dst


def _ffmpeg(ctx, args, info, opts):
    total = info.get("duration") or 0
    s, e = _secs(opts.get("start")), _secs(opts.get("end"))
    if e and e > (s or 0):
        total = e - (s or 0)
    elif s and total:
        total = max(total - s, 0.1)
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats"] + local_inputs(args)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
    ctx.attach(proc)
    err = deque(maxlen=25)
    t = threading.Thread(target=lambda: [err.append(l.decode("utf-8", "replace").rstrip()) for l in proc.stderr], daemon=True)
    t.start()
    speed = ""
    for raw in proc.stdout:
        line = raw.decode("ascii", "ignore").strip()
        if line.startswith("speed="):
            speed = line[6:].strip()
        elif line.startswith("out_time_us=") and total:
            try:
                done = int(line[12:]) / 1e6
            except ValueError:
                continue
            ctx.progress(min(done / total, 0.999), f"Encoding · {speed}" if speed and speed != "N/A" else "Encoding")
    proc.wait()
    t.join(2)
    if ctx.cancelled:
        raise InterruptedError
    if proc.returncode != 0:
        msg = next((l for l in reversed(err) if l and not l.startswith("[")), None) or (err[-1] if err else "ffmpeg failed")
        raise RuntimeError(re.sub(r"\s+", " ", msg)[:300])
