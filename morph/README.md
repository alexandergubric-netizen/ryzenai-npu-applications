# Morph

A local, offline universal file converter with an AI format advisor that runs on the Ryzen AI NPU.

Drop a file in and Morph shows what it can turn it into. It suggests the best options right away, and
the local AI explains the upsides and downsides of each one for that exact file. Nothing leaves the PC.

## Install on another PC

Share **`Documents\Apps by Alex\Morph-Setup.exe`**. The person installing doesn't need anything installed first:
Python, ffmpeg, pandoc and every library come inside. Morph installs per user, with no admin rights, under
`%LOCALAPPDATA%\Programs\Morph`, and removes cleanly from Settings → Apps.

* **AMD Ryzen AI 300/400/Max (NPU):** setup explains that the AI advisor needs **FastFlowLM**, a free engine and a
  separate program. It can install FastFlowLM (Windows asks for permission) and download the `qwen3:4b` model
  (~3.1 GB). You can also skip this and turn it on later in **Morph → Settings → AI format advisor**, the NPU
  enabler.
* **Intel and every other PC:** Morph installs in **converter mode**. All conversions work, and the format
  suggestions come from built-in rules. The AI advisor and its follow-up questions are off. Video uses Intel Quick
  Sync or Radeon AMF when the GPU supports it, and the CPU otherwise.

The installed version leaves out OpenCV (pdf2docx) and pyarrow to save ~200 MB. PDF → Word still works, through
HTML. Parquet is the only format that isn't available.

To rebuild the setup file, run `python installer\build.py`. It traces the libraries Morph uses by running every
conversion, bundles them, checks the bundle with the full conversion test, and packs one .exe.
To test the installer without touching the registry, set `MORPH_SETUP_TEST=<folder>`. `MORPH_NO_AI=1` simulates a PC
without a supported NPU.

## Start

Double-click **Morph** on the desktop (or `Morph.bat`). The window opens in Edge app mode, and
closing it shuts Morph down. It waits for any conversion that is still running.

* **Add files:** drag them anywhere onto the window, paste with `Ctrl+V` (screenshots too), or
  **Choose files** (`Ctrl+O`). Files picked with *Choose files* are saved **next to the original**.
  Dropped files go to the output folder (default `Downloads\Morph`; you can change it in Settings).
* **Convert:** click a format. Options appear for that format (quality, resolution, trim, max size,
  strip metadata, pages). Then press *Convert*. **All N formats** lists every target.
* **Compress:** re-encodes the file smaller in the same format (video, audio, images, PDF).
* **Several files:** the bottom bar converts all of them to one format. You can also **merge images
  and PDFs into one PDF**, in the order shown.
* **AI advice:** the advisor picks 3 formats, which get a ✦ mark. You can ask follow-ups like
  "smallest for WhatsApp?" or "best for editing in Premiere?". Click a bold format name to select it.

## What it converts (102 formats)

| Kind | Formats |
|---|---|
| Video | MP4 (H.264 / H.265 / AV1), WebM, MKV, MOV, M4V, AVI, WMV, FLV, MPEG-2, TS, 3GP, OGV (+ MXF in) → video, audio, GIF, animated WebP, still frame |
| Audio | MP3, M4A/AAC, ALAC, FLAC, WAV, AIFF, OGG, Opus, WMA, AC3 (+ AMR, APE, WavPack, CAF, MKA, DTS in) |
| Images | PNG, JPG, WebP, AVIF, HEIC, GIF, BMP, TIFF, ICO, ICNS, TGA, JPEG 2000, PPM (+ PSD, SVG, DDS, PCX, QOI, camera RAW in) → also PDF; animated GIF → video |
| Documents | PDF, DOCX, ODT, RTF, TXT, Markdown, HTML, LaTeX, reST, Org, AsciiDoc, Textile, MediaWiki, Typst, Jupyter, PPTX; PDF → images/SVG/DOCX/text |
| E-books | EPUB, FB2 (+ MOBI/AZW3, CBZ, XPS in) |
| Tables & data | XLSX, XLS, ODS, CSV, TSV, Parquet, SQLite, JSON, YAML, TOML, XML |
| Other | ZIP, 7z, TAR(.gz/.bz2/.xz) (+ RAR with 7-Zip) · TTF, OTF, WOFF, WOFF2 · SRT, VTT, ASS, SSA |

Morph finds a route through its engines on its own. For example, DOCX → PDF goes through pandoc, then
styled HTML, then Edge printing. When a route loses something, the format's tooltip says so.

## Engines

| Engine | Used for |
|---|---|
| ffmpeg (+ Radeon AMF GPU encoders, CPU fallback) | audio, video, GIF, subtitles |
| Pillow + pillow-heif + rawpy | pictures, HEIC, camera RAW |
| PyMuPDF, pdf2docx | PDF, EPUB/MOBI/XPS, PDF → Word |
| pandoc (bundled via pypandoc_binary) | text and document formats |
| Microsoft Edge (headless) | HTML → PDF |
| pandas, openpyxl, pyarrow… | spreadsheets and data |
| LibreOffice *(optional, install button in Settings)* | exact Office layouts, DOC/PPT/XLS |
| FastFlowLM (`qwen3:4b` by default) | the AI advisor on the NPU |

## The AI advisor

`core/advisor.py` gives the model only real facts: ffprobe/Pillow/PyMuPDF data such as codec,
resolution, pages and transparency, plus the curated upside/downside notes in `core/formats.py`, and
only the formats that are actually reachable. Its picks are checked against that list, so it cannot
recommend a format Morph can't make. Without the NPU, Morph still shows rule-based picks and tooltips.
It reuses a FastFlowLM server that is already running on port 52625 (for example Sensei's).

## Files

* `app.py`: local server (port 52691) and window
* `core/router.py`: the engine graph and route search
* `core/media.py`, `images.py`, `docs.py`, `data.py`: the engines
* `core/inbox.py`, `jobs.py`: files, facts, thumbnails, background jobs
* `web/`: the UI (vanilla JS, no build step)
* `tests/smoke.py`: makes sample files and converts each to every target (`python tests/smoke.py`)

Settings and logs live in `%LOCALAPPDATA%\Morph`.
