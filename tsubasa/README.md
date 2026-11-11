# Tsubasa 翼

A private AI assistant that runs on your own computer. Chat, documents, a coding and terminal agent, a knowledge
library and (experimental) 3D-print design, all offline: Tsubasa listens only on 127.0.0.1, sends no telemetry and
checks no updates.

| Platform | Engine | Status |
|---|---|---|
| **Windows 11**, AMD Ryzen AI 300/400/Max (NPU) | [FastFlowLM](https://github.com/FastFlowLM/FastFlowLM) | Built and tested on the author's PC. Installer: `Tsubasa-Setup.exe`. |
| **macOS**, Apple silicon | [MLX](https://github.com/ml-explore/mlx-lm) (`mlx_lm.server`) | **Experimental.** Written on Windows and built by GitHub Actions on a macOS arm64 runner; not yet run by the author on a real Mac. See [MAC.md](MAC.md). |

## What it does

- **Chat:** streaming answers, saved chats, workspaces, your own instructions, "Think first" for reasoning models,
  a context meter. Attach PDFs, Word, Excel, code, e-mails or pictures (pictures need a vision model).
- **Code mode:** an agent that writes files and runs terminal steps one at a time. Every step waits for your
  click; read-only commands can run by themselves; destructive ones need a second click. On Windows it uses 541
  tested PowerShell tasks (the author's Sensei app) and a checker that validates each command on your PC, and it
  can run a step as administrator after asking in the app and through Windows' own prompt.
- **Files on this computer:** list, read and write your files, each with an approval and a diff. System and
  app-data folders and key folders (`.ssh` and similar) are refused.
- **Library:** packs of notes, files and folders, indexed locally (SQLite FTS5) and cited in answers.
- **Documents and tables:** read, search and merge PDFs; draft and export DOCX, PDF, CSV and XLSX.
- **Images (optional):** a local stable-diffusion.cpp server with RealVisXL; see "Optional engines".
- **3D Print (experimental):** describe a part, get an OpenSCAD-style model, a 3D viewer, editable sizes and an STL.
- **Three themes:** Midnight, Paper and a 1-bit Bitmap theme with its own pixel font.

Small local models can be wrong. Tsubasa never acts without your click, and it marks file and tool output as
untrusted data for the model.

## Install on Windows

1. Download `Tsubasa-Setup.exe` from the release and run it (per user, no administrator rights). Windows may show
   "Unknown publisher": choose More info, then Run anyway.
2. Setup checks the PC. On a Ryzen AI PC it can install FastFlowLM and download two models (`qwen3.5:4b` for chat,
   `qwen3-it:4b` for Code mode, about 6 GB). Any other model you add with `flm pull` appears in the model menu.
3. Open Tsubasa from the desktop or Start menu. It starts the engine if it is not running; Settings → Engine has
   Start and Stop.

Requirements: Windows 11, Microsoft Edge or Google Chrome (for the app window), 16 GB memory recommended. Code mode
uses PowerShell 7 (`pwsh`) when installed, else Windows PowerShell. On PCs without a supported NPU Tsubasa installs,
but chat stays offline.

Uninstall from Settings → Apps. It removes exactly the files setup installed and asks whether to keep your chats.

## Install on a Mac (experimental)

Download `Tsubasa-mac-arm64.dmg` from the release, drag Tsubasa to Applications, then right-click → Open the first
time (the app is not signed). In Settings → Engine, download a model (never automatic), then chat.
[MAC.md](MAC.md) lists what works, what does not yet, and exactly what has and has not been verified.

## Your data

Chats, settings, the Library index and workspace files are stored unencrypted in `%LOCALAPPDATA%\Tsubasa` (Windows)
or `~/Library/Application Support/Tsubasa` (macOS). Close Tsubasa before copying that folder as a backup.
`TSUBASA_HOME` points the app at another folder.

## Optional engines

- **Images:** put stable-diffusion.cpp's `sd-server` in `<data folder>\image-studio\bin` and
  `RealVisXL_V5.0_Lightning_fp16.safetensors` in `<data folder>\image-studio\models` (or set
  `TSUBASA_IMAGE_STUDIO`). Tsubasa starts it for the first picture and stops it after 3 idle minutes.
- **Audio transcription:** needs `ffmpeg` on PATH and FastFlowLM running with `--asr 1` and `whisper-v3:turbo`.

## Run from source

The app needs only the Python standard library (3.12 or newer).

```powershell
python app.py --start-engine
```

The document worker (PDF, Word, Excel) runs in its own Python with the packages pinned in
`tools/file-worker-requirements.txt`; put it in `.venv/file-worker`.

Tests (no engine needed; they use isolated homes under `.test-runs`):

```powershell
python -B -m unittest discover -s tests
```

Build the Windows installer (into `Documents\Apps by Alex`): `.venv\file-worker\python.exe installer\build.py`.
Build the Mac app and DMG on an Apple-silicon Mac: `bash mac/build_app.sh`.

## File map

- `app.py`: the loopback HTTP/SSE server, launch-key gate, window and single-instance handling.
- `core/`: the app. `client.py` (FastFlowLM engine) and `mlx_client.py` (MLX engine) share one interface;
  `platform.py` holds everything that differs between Windows and macOS; `config.py` the defaults.
  `agent.py` (Code mode and file agent), `sensei_term.py` (Windows terminal pipeline), `posix_term.py` (macOS zsh
  terminal and checker), `elevated.py` (Windows administrator steps), `pc_files.py` (path policy),
  `storage.py` (SQLite chats), `library.py`, `extract.py` (attachments), `tool_loop.py`, `file_hub.py`,
  `images.py`, `audio.py`, `cad_api.py` and `cad/` (3D Print), `job_runner*.py` (resource-limited child processes).
- `web/`: the interface (vanilla HTML, CSS and JavaScript, no CDN).
- `tools/`: the document worker, the icon and pixel-font generators, the audit script.
- `vendor/`: unchanged copies of the author's Sensei, Washi and Morph modules, with provenance.
- `library/`: built-in Library packs.
- `installer/`: the Windows installer (`build.py`, the setup wizard, the manifest-based uninstaller).
- `mac/`: the macOS app bundle and DMG build.
- `tests/`: the test suite.
- `MAC.md`, `CHANGELOG.md`, `THIRD-PARTY-NOTICES.txt`, `LICENSE`.

## Licence

Tsubasa's own code is MIT (see `LICENSE`). The installers bundle PyMuPDF (AGPL-3.0) for PDF work, so Tsubasa as
distributed is covered by the AGPL; details and the written offer are in `THIRD-PARTY-NOTICES.txt`.
