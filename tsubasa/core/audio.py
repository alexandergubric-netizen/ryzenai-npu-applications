"""Local media decoding and explicit requests to an already running FLM ASR endpoint."""
import http.client
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import wave

from core.service_peer import ServiceConnection
from core.config import FLM_EXE, FLM_PORT
from core.platform import NO_WINDOW
from core.file_hub import LIMIT
from core.file_catalog import filename

MODEL = "whisper-v3:turbo"
FFMPEG = Path(__import__("shutil").which("ffmpeg") or "C:/ProgramData/chocolatey/lib/ffmpeg/tools/ffmpeg/bin/ffmpeg.exe")
FORMATS = {".wav":"wav", ".mp3":"mp3", ".flac":"flac", ".ogg":"ogg",
           ".mp4":"mov", ".m4a":"mov", ".mov":"mov", ".webm":"matroska", ".mkv":"matroska"}
LANGUAGES = {"auto","sk","en"}
MAX_SECONDS = 120

def installed():
    try:
        result=subprocess.run([str(FLM_EXE),"list","--filter","installed","--json","--quiet"],
        capture_output=True,timeout=15,creationflags=NO_WINDOW)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ValueError("Could not verify the installed FLM model inventory.") from exc
    if result.returncode:raise ValueError("Could not verify the installed FLM model inventory.")
    return any(m.get("name")==MODEL for m in json.loads(result.stdout)["models"])

def check_cancel(event):
    if event.is_set():raise ValueError("Transcription cancelled.")

def decode(source,output,event):
    fmt=FORMATS.get(source.suffix.lower())
    if not fmt or not source.is_file() or not 0<source.stat().st_size<=LIMIT:
        raise ValueError("Choose a supported audio or video file up to 8 MiB.")
    if not FFMPEG.is_file():raise ValueError("ffmpeg was not found. Install ffmpeg (it must be on PATH) to transcribe audio and video.")
    check_cancel(event)
    # Only the already-open input descriptor is allowed. Container references cannot read adjacent files or network URLs.
    cmd=[str(FFMPEG),"-nostdin","-hide_banner","-loglevel","error","-max_alloc","67108864",
         "-protocol_whitelist","fd","-threads","1","-f",fmt,"-i","fd:",
         "-map","0:a:0","-vn","-sn","-dn","-ac","1","-ar","16000","-c:a","pcm_s16le",
         "-threads","1","-t",str(MAX_SECONDS+1),"-f","wav","-n",str(output)]
    start=time.monotonic()
    with source.open("rb") as media,subprocess.Popen(cmd,stdin=media,stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,creationflags=NO_WINDOW) as proc:
        try:
            while proc.poll() is None:
                if event.wait(.05):raise ValueError("Transcription cancelled.")
                if time.monotonic()-start>25:raise ValueError("Audio decoding timed out.")
            if proc.returncode:raise ValueError("No decodable audio track was found.")
        finally:
            if proc.poll() is None:proc.kill()
            proc.wait()
    with wave.open(str(output),"rb") as wav:
        frames=wav.getnframes()
        if (wav.getnchannels(),wav.getframerate(),wav.getsampwidth())!=(1,16000,2) or not 0<frames<=MAX_SECONDS*16000:
            raise ValueError("Choose a non-empty clip of at most two minutes.")
    return frames/16000

def submit(wav,language,port):
    boundary=secrets.token_hex(20)
    fields={"model":MODEL,"response_format":"json"}
    if language!="auto":fields["language"]=language
    chunks=[f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k,v in fields.items()]
    chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="clip.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode(),
                   wav.read_bytes(),f'\r\n--{boundary}--\r\n'.encode()])
    connection=ServiceConnection(port,FLM_EXE,timeout=120)
    try:
        connection.request("POST","/v1/audio/transcriptions",b"".join(chunks),
                           {"Content-Type":"multipart/form-data; boundary="+boundary})
        response=connection.getresponse()
        data=response.read(131073)
        if response.status!=200:raise ValueError(f"FLM ASR returned HTTP {response.status}. Check that ASR is enabled.")
        if len(data)>131072:raise ValueError("Transcription response exceeded its size limit.")
        payload=json.loads(data)
        text=payload.get("text") if isinstance(payload,dict) else None
        if not isinstance(text,str) or not text.strip():raise ValueError("FLM returned no transcript.")
        return text.strip()
    except (OSError,http.client.HTTPException) as exc:
        raise ValueError("FLM ASR is unavailable. Use an already running local service with ASR enabled.") from exc
    finally:connection.close()

SCHEMA={"name":"transcribe","risk":"read","description":"Transcribe spoken or sung words in a workspace audio or video file.",
        "parameters":{"type":"object","properties":{"path":{"type":"string"},"language":{"type":"string","enum":["auto","sk","en"]}},
        "required":["path"],"additionalProperties":False}}

def validate(args):
    if not isinstance(args,dict) or set(args)-{"path","language"} or "path" not in args:
        raise ValueError("Supply a workspace media filename and optional language.")
    language=args.get("language","auto")
    if language not in LANGUAGES:raise ValueError("Select Auto, Slovak or English.")
    filename(args["path"])
    return language

def transcribe(hub,workspace,args,event,port=FLM_PORT):
    language=validate(args)
    root=hub.root(workspace)
    source=hub.path(root,args["path"])
    if not source.is_file() or source.suffix.lower() not in FORMATS:raise ValueError("Choose workspace audio or video.")
    check_cancel(event)
    if not installed():raise ValueError("whisper-v3:turbo is not installed. Tsubasa does not download models.")
    with tempfile.TemporaryDirectory(dir=root) as scratch:
        wav=Path(scratch)/"normalized.wav"
        duration=decode(source,wav,event)
        check_cancel(event)
        start=time.monotonic()
        text=submit(wav,language,port)
        check_cancel(event)
        return {"text":text,"language":language,"audio_seconds":duration,"asr_seconds":round(time.monotonic()-start,3)}

