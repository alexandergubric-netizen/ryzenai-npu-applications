# Washi 和紙

A calm, modern PDF editor for Windows with a private AI assistant that runs on the Ryzen AI NPU.

Washi is Japanese hand-made paper: light, strong and made to last. The logo is a sheet of washi with ink strokes
and a vermilion hanko seal; the intro animation lays the sheet down, paints the strokes and stamps the seal.

## What it does

| Area | Features |
|---|---|
| Read | Tabs, thumbnails, bookmarks, find (case / whole word), continuous / single / two-page layouts, zoom & fit, dark pages reading mode, print |
| E-books | EPUB, MOBI, FB2, CBZ (and XPS) laid out on book pages with chapters as bookmarks, working links and adjustable text size; the book itself is never changed - Save as stores a PDF |
| Save | Save, Save as (ribbon, Ctrl+Shift+S, tab menu); if a file can't be written (protected folder like Program Files, read-only, open elsewhere) Washi says why and offers Save a copy as |
| Comment | Highlight, underline, strike-out, squiggly, area highlight, sticky notes, text boxes, rectangles, ellipses, lines, arrows, pen, stamps (with name + date), comments list with filters |
| Edit | Edit existing text (keeps the font when it can, else a matching Windows font, full Unicode e.g. Slovak), add text, erase areas, images, signatures (draw / type / image), links, watermarks, page numbers / header / footer, document properties |
| Pages | Rotate, insert blank / from file, duplicate, drag to reorder, extract, split (every N / bookmarks / ranges), delete, crop / uncrop |
| Forms | Fill text fields, checkboxes, dropdowns; create fields; flatten |
| Protect | True redaction (mark + apply), AES-256 passwords and permissions, remove protection |
| Convert | Word (.docx), text, Markdown, HTML, PNG/JPEG, PDF copy of selected pages, reduce file size, combine files, images to PDF, attachments |
| Local AI | Summaries (quick / key points / detailed, map-reduce for long PDFs), questions about the document with page references, explain / translate / simplify / proofread selected text, and a guide that explains how to do things in Washi and points at the right button |

Everything is undoable (Ctrl+Z, 60 steps). `Ctrl+K` searches every command and help topic.

## Local AI

Runs only on PCs that can run [FastFlowLM](https://github.com/FastFlowLM/FastFlowLM): Windows 11, AMD Ryzen AI
300/400 or Ryzen AI Max (XDNA 2 NPU), NPU driver 32.0.203.311+. Default model `qwen3-it:4b` (about 3 GB).
On other PCs the AI is switched off and hidden; everything else works the same. Documents never leave the PC.
`WASHI_NO_AI=1` simulates an unsupported PC.

## Run from source

```
python app.py            # opens the window (Microsoft Edge app mode)
python app.py file.pdf   # opens a file (also hands it to an already running Washi)
python app.py --no-window
```

Needs Python 3.12 and PyMuPDF (`pip install pymupdf`). Optional: `pdf2docx` for higher-fidelity Word export
(without it Washi uses its own exporter, `core/docx_export.py`).

## Default PDF app

`Washi.exe` is a tiny native launcher (`launcher/Washi.cs`, built with the C# compiler that ships with Windows by
`python make_launcher.py`) so Windows can list Washi in "Open with" and Settings > Default apps.
`python make_shortcut.py` builds it, puts a desktop shortcut on it and registers the source copy; the installer
does the same for installed copies. In Washi: Settings > **Make Washi the default PDF app** opens Windows' Default
apps page for Washi, where you confirm (Windows doesn't let apps change defaults by themselves).

## Build the installer

```
python installer\build.py     # -> Documents\Apps by Alex\Washi-Setup.exe
```

One self-contained .exe (portable Python + PyMuPDF + Washi). Installs per user without admin rights, creates
desktop and Start-menu shortcuts, adds Washi to "Open with" for PDFs, and on Ryzen AI PCs can install
FastFlowLM and the model. Uninstall from Settings > Apps. Dry run: `WASHI_SETUP_TEST=<folder>`.

## Tests

```
python tests\engine.py        # PDF engine checks (82)
python tests\fonts.py         # text editing against embedded / subset / system fonts (88)
python tests\smoke.py --ai    # server API checks incl. the NPU (starts its own Washi on another port)
python tests\stress.py --list pdfs.csv   # every operation on synthetic edge cases + your own PDFs
python tests\make_sample.py   # tests\sample.pdf for trying things by hand
python tests\make_ebooks.py   # test EPUB 3 / EPUB 2 / FB2 books in tests\ebooks
```
Crashes inside MuPDF are written to `%LOCALAPPDATA%\Washi\crash.log`; other errors to `washi.log`.

## Layout

- `app.py` - local HTTP server (port 52694, token-protected), Edge window, single-instance file hand-off
- `core/docs.py` - all PDF work on PyMuPDF (display-space coordinates, undo snapshots)
- `core/assistant.py`, `core/llm.py`, `core/hw.py` - AI features, FastFlowLM client, NPU detection
- `web/` - the UI (vanilla JS): `core.js`, `viewer.js`, `tools.js`, `panels.js`, `ai.js`, `app.js`, `guide.json`
- `installer/` - build script, installer UI and uninstaller

© 2026 Alexander Gubric · MIT License · bundles PyMuPDF (AGPL-3.0)

## The shared AI engine

Washi, Morph, Sensei, Kaizen 5S and Postura share one FastFlowLM server on 127.0.0.1:52625
(`core/flmshare.py`). Whichever app starts it uses the model's full 32k context (`--ctx-len 32768`, about 8.4 GB of RAM; it costs
memory, not speed) and your NPU power mode (default **performance**; **turbo** is about as fast, balanced is about 40 %
slower). Changing the model loads it in place in about 15–20 s, with no restart; changing the power mode restarts the
server. If the server disappears, the app starts it again and retries the question. The server stops when the last
app using it closes.

Summaries read up to about 68,000 characters in one pass. The budget is sized from the server's real context, counting 2.2 characters per token, as measured for Slovak; English is 3.6. If a document is still too long, Washi reads it in parts.
