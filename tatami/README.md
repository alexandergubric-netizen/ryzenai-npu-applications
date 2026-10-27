# Tatami (畳) — see what fills your disk

A free disk space analyser for Windows 10/11 in the spirit of WizTree, with a Windows 11 look.
Tatami lays every file out like mats on a floor (a cushion treemap), so the big ones are easy to spot.

## Features
- **Fast**: reads a whole SSD system drive (1 million files) in about 4 seconds, without administrator rights.
- **Folders tree** with % of parent, size, size on disk, files, folders and dates; sort by any column.
- **Treemap** with shaded cushions, folder labels and tooltips. Click to find an item, double-click to zoom in.
- **File types** panel: what each extension takes up. Click one to highlight it in the map.
- **Largest files** list with search (`*.iso; setup*; \Downloads\`) and filters by type, size and age.
- **Insights**: what grew since your last scan, Recycle Bin, temp files, Windows Update leftovers, old
  downloads, big untouched files, disk images and VMs, caches, page file and hibernation, protected space,
  online-only (cloud) files.
- **Size or On disk**: online-only OneDrive and phone files take no space, so "On disk" (the default) leaves
  them out. Hard links are counted once.
- **Actions**: open, Show in File Explorer, copy path, Properties, rescan a folder, delete to the Recycle Bin
  or permanently. Windows folders, the page file and the scanned folder itself are protected.
- **Include protected folders**: one switch asks for administrator rights for a single scan, so WindowsApps
  and System Volume Information are counted too. The window itself never runs elevated.
- Export to CSV, save and open scans (`.tatami`), light and dark themes that follow Windows and its accent colour.
- "Analyse with Tatami" when you right-click a folder or drive in File Explorer.

## Install
Run `Tatami-Setup.exe`. It installs for the current user only (no admin) to
`%LOCALAPPDATA%\Programs\Tatami`. Uninstall from Settings → Apps.
Scripts: `Tatami-Setup.exe --install` (silent) · `Tatami.exe --uninstall --quiet`.

## Keyboard
F5 rescan · Ctrl+O scan a folder · Ctrl+F find · Enter zoom/open · Backspace up · Alt+← back ·
Del Recycle Bin · Shift+Del delete permanently · Ctrl+C copy path · Ctrl+A select all

## Build
One C# 5 file set compiled with the C# compiler that ships with Windows (.NET Framework 4.8), no SDK needed:

    powershell -File build.ps1            # Tatami.exe (UI files in web/ are embedded)
    powershell -File build.ps1 -Console   # console build for --bench / tests
    python make_icon.py                   # redraws tatami.ico and web/icon.png (needs Pillow)

Development: `Tatami.exe --no-window --web web` serves the UI from disk at http://127.0.0.1:52695.
See PROGRESS.md for the design notes.

## Privacy
Tatami works offline. It talks only to itself on 127.0.0.1, and only the window it opened can use it (a one-time
launch key becomes a session cookie; nothing secret is in the page). Scan history (the file and folder names of the
last 4 scans of each drive or folder, at most 90 days old) stays in `%LOCALAPPDATA%\Tatami\history`; clear it from
the ⋯ menu → Clear scan history.

## Safety when deleting
- Junctions and symbolic links (marked **link**): only the link is removed, never the folder it points to.
- "Delete to Recycle Bin" checks first that the Recycle Bin can take the item (drive covered, not turned off, not
  bigger than the bin, path not too deep). If it can't, nothing is deleted and Tatami says why; Windows is also told
  to ask before ever deleting something permanently instead.
- Duplicates are compared with SHA-256 and re-checked right before deleting; a file that changed since the search
  is kept.
- Windows, Program Files, ProgramData\Microsoft and whole user profiles are refused by the server.

© 2026 Alexander Gubric · MIT License
