# Kaizen 5S

A local AI assistant that tidies your PC with the Japanese **5S** method. The AI runs on the
**AMD Ryzen AI NPU** through FastFlowLM, or through **LM Studio** on any other PC. Nothing leaves the computer.

© 2026 Alexander Gubric · Free and open source software under the [MIT License](LICENSE).

**Install:** run `Kaizen5S-Setup.exe`. It checks your PC and offers the AI engine that fits it.
**Start from source:** double-click `Kaizen.bat` (needs Python 3.12 with `Pillow` and `Send2Trash`).

| S | What Kaizen looks for |
|---|---|
| 整理 Seiri (Sort) | Files you haven't opened for a long time (12 months by default), duplicates, and programs you haven't used in ages |
| 整頓 Seiton (Set in order) | Files left in Downloads, loose files on the Desktop, and media saved in Documents. Each gets a suggested folder |
| 清掃 Seiso (Shine) | Temp files, old installers, empty files and folders, broken shortcuts, and leftover Program Files folders |
| 清潔 Seiketsu (Standardize) | Names like "final (2)", "copy" or "untitled". Each gets a suggested clean name; several programs doing the same job are also flagged |
| 躾 Shitsuke (Sustain) | Folders that stay clean, and how regularly you run a 5S check |

## Folders to check
**Settings → Manage folders…** turns Windows libraries on or off and adds extra folders: a second drive, a project
folder, or a network share (a mapped drive or `\\server\share`). **Check access** uses Windows' own permission test
and shows whether you can see, move/rename or recycle files there, without creating or changing anything. Network,
cloud and removable locations show a disclaimer you have to confirm. Network and USB drives have no Recycle Bin, so
Kaizen never deletes files there. A folder that can't be reached during a scan is skipped, and the scan can be
stopped at any time.

## Safety
* A scan only reads. Kaizen changes nothing until you click a button.
* **Recycle** only ever uses the Windows Recycle Bin. Before each item Kaizen checks that the bin can take it (drive
  covered, bin not turned off, item not bigger than the bin); otherwise the item stays where it is and Kaizen says
  why. Windows is also told to ask before deleting anything permanently. Undo restores exactly the recycled item and
  says if one is no longer in the bin.
* Files that changed since the last scan, app data and network/USB files are refused by the server, not only hidden
  in the window.
* Duplicates are always confirmed by comparing the whole file (BLAKE2b), whatever its size.
* **Uninstall** opens the program's own uninstaller. Drivers, runtimes and security software are protected.
* Game saves, AI models, caches and code projects are recognised as **app data** and left alone.
* Reading files for thumbnails or AI descriptions doesn't change their "last used" date.

## AI engines
| Your PC | Engine | Model |
|---|---|---|
| AMD Ryzen AI 300/400 (XDNA 2 NPU), Windows 11, NPU driver 32.0.203.311 or newer | FastFlowLM | `qwen3-it:4b` on the NPU |
| Any other Windows PC (Intel, older AMD, NVIDIA, Snapdragon) | LM Studio | Qwen3 4B on the CPU/GPU |

Kaizen still works without any AI. You get scans, the 5S scores, the map and all the actions, just without the
one-line descriptions and the chat.

## Editions
| Edition | Installer | Differences |
|---|---|---|
| Public (1) | `Kaizen5S-Setup.exe` | Everything enabled |

An edition is a JSON file in `editions\`. The build copies it into the app as `edition.json`.

Data lives in `%LOCALAPPDATA%\Kaizen5S` and never leaves the PC: `kaizen.db` (paths, dates and sizes of the
scanned files, AI descriptions and a log of every action for Undo), cached thumbnails (removed after 60 days
unused) and `kaizen.log`. Uninstalling offers to delete all of it.
To build the installers (written to `Documents\Apps by Alex`):
`python installer\build.py` builds the public edition; `--edition <id>` builds an edition defined in `editions\<id>.json`.

## The shared AI engine

Washi, Morph, Sensei, Kaizen 5S and Postura share one FastFlowLM server on 127.0.0.1:52625
(`core/flmshare.py`). Whichever app starts it uses the model's full 32k context (`--ctx-len 32768`, about 8.4 GB of RAM; it costs
memory, not speed) and your NPU power mode (default **performance**; **turbo** is about as fast, balanced is about 40 %
slower). Changing the model loads it in place in about 15–20 s, with no restart; changing the power mode restarts the
server. If the server disappears, the app starts it again and retries the question. The server stops when the last
app using it closes.
