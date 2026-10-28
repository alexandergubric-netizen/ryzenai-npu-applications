# Sensei 2

An offline PowerShell helper. Describe what you want in plain words. Sensei finds or writes the exact command,
checks it on this PC and runs it in a built-in PowerShell session. The AI runs on the **Ryzen AI NPU through
FastFlowLM**, and nothing leaves the computer.

**Install:** `Documents\Apps by Alex\Sensei-Setup.exe` (per user, no admin rights). It brings its own Python, installs
PowerShell 7 if it's missing and, on Ryzen AI PCs, FastFlowLM and the AI model.
**From source:** `Sensei.exe` or `Sensei.bat` in this folder.

## How it answers (fastest first)
1. **⚡ Library: instant, no AI.** About 540 tested tasks with slots in `core/knowledge/*.txt`. Sensei picks the values
   out of your sentence (folders and paths, apps with their process names and winget IDs, file types and groups,
   sizes, percentages, durations, times, dates, ports, drives, quoted text, URLs and websites, services, time zones,
   Settings pages, models) and fills them in. Typos are corrected ("scrennshot", "wfi").
2. **✦ Tool picked by AI: about 2 s.** If your wording doesn't match exactly, the model chooses the right task from
   the 8 closest candidates. Its answer is a few tokens of JSON, so it's fast and can only ever pick tested commands.
3. **AI-written: about 5 s.** Anything new is written by the model. It gets the closest tasks, facts about the values
   you named, and Sensei's helper commands as references.
4. **Checked on this PC.** PowerShell parses every command. Each command and parameter is looked up in a catalog of
   the 1,600+ commands installed here (built once in the background, so checking takes ~15 ms). Risk is labelled
   Read-only, Makes changes or Destructive. A destructive command for a request that never asked for one (a shutdown
   for "set a timer") is rejected and rewritten.

"Did you mean" chips offer the next-best library tasks, and the **Library** (book icon, Ctrl+L) lets you browse
and search everything Sensei knows.

## Speed work in version 2
| | v1 | v2 |
|---|---|---|
| Checking a command that needs a module (network, disks, devices) | 6 s | 15 ms (command catalog) |
| First run of a network/disk command | 1–4 s module load | preloaded in the background |
| Request with different wording than the library | 5–10 s, AI writes code | ~2 s, AI picks a tested task |
| Typos | AI | instant (corrected) |

## Model choice
`python tests/model_bench.py <models…>` compares FastFlowLM models on 45 routing and 15 code-writing tasks. On
this Ryzen AI 7 350, see `tests/model_bench.json` for the numbers and Settings for the ★ recommended model.

## Sensei helper commands (`core/SenseiTools.psm1`)
| Area | Commands |
|---|---|
| Sound | `Set-AudioVolume -Percent/-Up/-Down/-Mute/-Unmute`, `Get-AudioVolume`, `Out-Speech` |
| Screen | `Set-ScreenBrightness`, `Get-ScreenBrightness`, `Set-DarkMode [-Off]`, `Set-Wallpaper`, `Save-Screenshot [-Delay]` |
| Images | `Convert-Image -Format`, `Resize-Image -Percent/-Width`, `Get-ImageInfo` (originals are always kept) |
| Files | `Remove-ToRecycleBin` (Sensei's own deletes go to the Recycle Bin; a few library tasks such as "empty the Recycle Bin" or "clear temp files" delete for good and always ask first), `Get-FolderSize [-Subfolders]`, `Find-DuplicateFiles` |
| Apps & power | `Close-App [-Force]`, `Start-Timer`, `Start-Shutdown -At/-InMinutes [-Restart]`, `Stop-Shutdown`, `Dismount-Drive` |
| Network | `Get-WifiPassword`, `Set-WifiState -On/-Off`, `Get-PublicIP`, `Test-InternetSpeed`, `Clear-TempFiles` |

## Running commands
* **Run** executes in Sensei's own PowerShell 7 session, which keeps the current folder and variables. **Esc** stops.
* Read-only commands run automatically (Settings). Destructive ones need a second click. Admin-only commands get
  **Run as admin ↗**; an "access denied" failure offers the same.
* **Terminal ↗** opens the command in a normal PowerShell window with the helpers loaded.
* `<placeholders>` must be filled in first: click **Run** to jump to the first one.
* **Tab** (or typing `>`) switches the input to PowerShell mode, where you type commands directly.

## Adding knowledge
Add a block to any `core/knowledge/*.txt` file:
```
? kill {app} | force close {app}                 <- phrasings; {slot} = a value from the request
Stop-Process -Name "{{app|process}}" -Force       <- the command; {{slot}} or {{slot|mod}} is filled in
= Ends every {app} process immediately.           <- explanation
& folder=$HOME ; n=10                            <- optional defaults
% file=images                                    <- optional: only for these file types
! admin                                          <- optional: needs administrator rights
```
Checks:
* `python tests/check_library.py --run --sandbox`: verifies every template on this PC, runs the read-only ones,
  and runs the file, image and video ones in a throwaway folder.
* `python tests/collisions.py`: finds phrasings of different tasks that read the same.
* `python tests/match.py "your request"`: shows which template answers it.
* `pwsh -File tests/check_tools.ps1`: tests the helper commands without changing your settings.
* `python tests/stress.py`: 60 action requests through the whole pipeline. `python tests/perf.py`: timings.

## Building the installer
`python installer\build.py` writes `Documents\Apps by Alex\Sensei-Setup.exe`. Dry-run the wizard with
`SENSEI_SETUP_TEST=<folder>`.

## Requirements
Windows 10/11, PowerShell 7 (the installer adds it), Microsoft Edge, and, for the AI, FastFlowLM with a chat model on
an AMD Ryzen AI 300/400/Max NPU. Without the AI, Sensei still answers from its library. ffmpeg is needed only for the
video/audio tasks. Settings, the command catalog and the log live in `%LOCALAPPDATA%\Sensei`.

© 2026 Alexander Gubric · MIT License

## The shared AI engine

Washi, Morph, Sensei, Kaizen 5S and Postura share one FastFlowLM server on 127.0.0.1:52625
(`core/flmshare.py`). Whichever app starts it uses the model's full 32k context (`--ctx-len 32768`, about 8.4 GB of RAM; it costs
memory, not speed) and your NPU power mode (default **performance**; **turbo** is about as fast, balanced is about 40 %
slower). Changing the model loads it in place in about 15–20 s, with no restart; changing the power mode restarts the
server. If the server disappears, the app starts it again and retries the question. The server stops when the last
app using it closes.
