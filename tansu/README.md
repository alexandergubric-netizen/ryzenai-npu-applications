# Tansu 箪笥 — smart archive chest

A *tansu* is the traditional Japanese chest of drawers. The *kaidan-tansu* (staircase chest) is the logo: six
coloured drawers, one per kind of content. Tansu archives files into **Documents\Archives** and keeps that library
organised. The "smart" part runs locally on the Ryzen AI NPU: **Qwen3.5 via FastFlowLM** plans each archive.

> **Beta (0.9.0).** Everything described here works and is tested, but Tansu is new: keep the originals of anything
> important until you have seen the archive verified, and please report problems as issues.

## Install

Download **Tansu-Setup.exe** (about 14 MB) from the
[Tansu 0.9.0 release](https://github.com/alexandergubric-netizen/ryzenai-npu-applications/releases/tag/tansu-v0.9.0) and run it. It installs per user (no administrator rights), brings its own
Python and archive engines, and checks your PC first:

- **Any Windows 10/11 PC:** archiving, verification, the library, search, extraction and the checkup all work.
  Plans come from Tansu's built-in rules, which already measure your files.
- **AMD Ryzen AI 300/400/Max with Windows 11:** setup can also install [FastFlowLM](https://github.com/FastFlowLM/FastFlowLM)
  and the qwen3.5:4b and qwen3.5:2b models (about 5 GB), so a local AI explains and adjusts each plan.

The installers are not code-signed yet, so Windows may say "Unknown publisher": click **More info → Run anyway**,
and compare the file with the SHA-256 in the release notes. Uninstall from Settings → Apps: it removes only the
files setup installed. Your archives and the Archives library are never touched.

Start it from the desktop or Start menu shortcut **Tansu**, or right-click files in Explorer → **Send to → Tansu**.
The window runs on http://127.0.0.1:52693 (Edge app mode).

## Security and the shared AI engine

- The local server lets in only its own window, the same way Washi, Morph, Sensei and Kaizen do
  (`core/websec.py`, an identical copy). Tansu writes `%LOCALAPPDATA%\Tansu\instance.json` (port + a random
  secret, readable only by this Windows user). The window opens with a one-time launch key, which the server swaps
  for an HttpOnly, SameSite=Strict session cookie. The page itself holds no secret. Every request also needs the
  right Host, no cross-site `Sec-Fetch-Site`, and (for POST/PUT) the `X-Tansu` header. A second Tansu ("Send to")
  uses the secret to ask the running one for a launch key and hands over its paths through `POST /api/launch`.
- FastFlowLM is the one server all the apps share (`core/flmshare.py`, an identical copy): port 52625, the full
  32k context, power mode *performance*. The bookkeeping is in `%TEMP%\ryzenai-apps-flm.json`. The last app to
  close stops the server. Changing the model swaps it live, without a restart. If the server disappears, it is
  started again.

## Look and motion

- **Opening animation**: the chest builds itself, the drawers drop in one by one, a sheet slips into the top drawer
  and the sparkles pop. Click to skip it, or turn it off in Settings.
- **Packing**: the real file names fly from a pile into an opening drawer labelled with the target folder. The
  stack squeezes to the compression ratio, a scan line checks the checksums, the drawer shuts and a red
  *hanko* seal stamps it **VERIFIED**.
- **Extracting**: files fly out of the drawer in a small dock at the bottom right.
- **Library**: folders are drawer fronts in a cabinet. Each top-level folder keeps its own colour everywhere.
- **Palette**: paper and lacquer in light mode, ink and paulownia in dark mode. The six drawer colours (vermilion,
  saffron, jade, sky, plum, teal) carry the whole UI. Every animation respects Windows' "reduce motion" setting.
- `make_icon.py` draws `tansu.ico` and `web/icon.png` with the same geometry as the SVG logo in `web/app.js`.

## Archive tab

1. **Add files**, **Add a folder**, drop them on the window, or right-click in Explorer → **Send to → Tansu**
   (turn that on in Settings).
2. Tansu scans everything and **measures** it rather than guessing: types, dates, junk (Thumbs.db, `~$` lock files,
   node_modules…), names that look personal or financial, and real compression ratios. It compresses a sample of the
   files with deflate and LZMA2, which also times how fast this PC is.
3. The rule engine scores ZIP / 7z / TAR.XZ with an estimated size and time for each. Qwen gets those numbers, the
   file and folder names, and the current library tree. It answers with a plan as JSON: format, compression level,
   encryption, folder, name, layout inside the archive, the reason, and a tip.
   Every field is checked: invalid values fall back to the rule plan, and odd folders such as
   `Documents/Archives/<name>` are corrected.
4. Change anything you like, or ask in plain words ("smallest possible", "put it under Work"). Then click
   **Archive**. Tansu writes a `.part` file, re-reads it to check every checksum, and only then gives it its real
   name. If you ask, the originals then go to the Recycle Bin.

| Format | When Tansu suggests it | Engine |
|---|---|---|
| ZIP | Photos, videos, Office files and anything already compressed (these are stored as they are, the rest is deflated). Also small sets and anything you want to share | Python `zipfile` |
| 7z | Documents, text and many small files (solid LZMA2). Personal or financial files, with AES-256 that also hides the file names | `py7zr` |
| TAR.XZ | Code projects and Linux/macOS use | Python `tarfile` + liblzma |

Layouts inside the archive: keep your folders, sort by type (Photos/, Documents/…), sort by year/month, or flat.
ZIPs in the target folder can be **appended to** (for example a monthly invoices archive).

## Library tab

This is the overview. It shows the folder tree with counts and these stats: number of archives, size on disk, space
saved, and files inside. It lists every archive with its format, a lock icon if encrypted, its size and how much it
saved. **Search inside every archive** by file name. The detail panel shows:

- why the archive was made this way
- where the files came from
- the browsable contents (also for encrypted 7z, from Tansu's own index)
- extract all, selected files, or to a folder of your choice
- test, move or rename, and Recycle

Notes are kept in `Archives\.tansu\` (hidden), so they travel with the library. If you move or rename archives in
Explorer, Tansu re-links them by size and timestamp.

## Care tab

The checkup finds:

- archives lying loose at the top level (**Suggest folders** asks the AI where they belong)
- files that are not archives
- empty folders
- folders with almost the same name
- byte-identical duplicate archives (it keeps the one Tansu filed, not the "kópia")
- archives that are not indexed yet

**Deep checkup** also re-reads every archive and tests its checksums.

## Why not Windows' tar.exe?

Windows' built-in `tar.exe` (bsdtar/libarchive) can write zip, 7z and tar.xz. But it reads file names in the ANSI
code page: Slovak letters (č, š, ť) are garbled and emoji or Cyrillic names crash it. Tansu therefore writes archives
in-process with open-source Python engines, which are Unicode-safe, and uses `tar.exe` only to *read* formats such as
RAR.

## Files

- `app.py`: local server, window, and the "Send to" hand-off to a running instance
- `core/scan.py`: analysis and compression sampling
- `core/rules.py`: scored options and the fallback plan
- `core/advisor.py`: prompts, JSON parsing and validation
- `core/engine.py`: create, verify, list and extract
- `core/store.py`: library, index, search and checkup
- `core/jobs.py`: background jobs
- `core/llm.py`: FastFlowLM client (same as Morph's), on `core/flmshare.py`
- `core/websec.py`: the web gate (launch key → session cookie)
- `core/hw.py`: can this PC run the AI advisor (Ryzen AI NPU, driver, Windows 11)? Read from the registry.
- `web/`: the UI
- `installer/`: `build.py` makes `Tansu-Setup.exe`; `setup.py` + `setup.html` are the setup window,
  `uninstall.py` the uninstaller, `safety.py` the install-folder and download checks shared with the other apps
- `tests/smoke.py`: 55 end-to-end checks in a throwaway library, including the web gate on a real server
  (`--ai` adds 6 more on the NPU model: 61). Run it with `runtime\python.exe tests\smoke.py --ai`.
- `TANSU_HOME=<folder>`: runs Tansu with a test data folder and test library instead of the real ones;
  `TANSU_PORT=<port>` picks another port; `TANSU_NO_AI=1` behaves like a PC without a Ryzen AI NPU

Settings and log: `%LOCALAPPDATA%\Tansu`.

## Build from source

Tansu runs on its own Python in `runtime\` (not in this repository):

1. Unpack the [Python 3.12 embeddable package](https://www.python.org/downloads/release/python-31210/) (64-bit)
   into `runtime\`, and write `python312.zip`, `.` and `site-packages` on three lines into `runtime\python312._pth`.
2. `py -3.12 -m pip install --target runtime\site-packages py7zr send2trash`
3. `runtime\python.exe tests\smoke.py` must report 55 passed, 0 failed.
4. `runtime\python.exe installer\build.py` builds `Documents\Apps by Alex\Tansu-Setup.exe`. It runs the same
   test on the bundled copy before packing, and wraps everything with Windows' built-in IExpress.

## Licence

Tansu's own code is MIT licensed, © 2026 Alexander Gubric (`LICENSE`). The installer bundles Python (PSF) and
py7zr with its helpers (LGPL-2.1-or-later), pycryptodomex, Brotli, backports.zstd and Send2Trash; see
`THIRD-PARTY-NOTICES.txt` and `licenses\`.
