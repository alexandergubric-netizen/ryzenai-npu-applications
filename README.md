# Ryzen AI NPU applications

Free Windows apps from one author, built around a private AI that runs **locally** on the AMD Ryzen AI NPU through [FastFlowLM](https://github.com/FastFlowLM/FastFlowLM). Your documents and questions stay on your PC. They range from everyday tools to ones useful in a workplace (quality, health & safety).

**Not every app needs a Ryzen AI PC.** The table below shows exactly what each app needs and what you get without an NPU.

## ⚡ October 2026: AI engine update

The five AI apps now get more out of the NPU:

- **Switch models live.** A new model loads in about 15–20 seconds, with no restart.
- **The AI repairs itself.** If the AI engine stops, for example because another app closed it, the app starts it again.
- **Faster by default.** The NPU runs in Performance mode, about 40 % faster than Balanced; Turbo is one click away in Settings.
- **Washi reads more.** Summaries take up to about 68,000 characters in one go (was 20,000), so long PDFs lose far less text.

## 🔒 October 2026: security update for all apps

Every app got a **security update** after an independent code review. In short:

- **Only you can control the apps.** Other programs, other Windows users on the same PC and web pages can no longer talk to an app's window.
- **Deleting is safer.** Uninstalling can never remove anything but the app itself, "Recycle" really goes to the Recycle Bin (or nothing is deleted), and deleting a shortcut-folder (link) never deletes what it points to.
- **Sensei asks before it acts.** Commands written by the AI always wait for your click, and dangerous ones need a second click.
- **Safer handling of files from elsewhere.** Morph unpacks archives and converts documents without letting them reach your other files or the internet; Washi keeps PDF passwords and digital signatures intact.
- **Verified downloads.** The AI engine installer is checked against its known fingerprint before it runs.

Install the new version over the old one — your settings stay. The apps also use less memory (Sensei about 40 % less).

## Downloads

| App | Version | What it does | Needs Ryzen AI NPU? | Download |
|---|---|---|---|---|
| **Washi** 和紙 | 1.0.4 | PDF editor: read, edit, annotate and search PDFs, plus EPUB, MOBI and FB2 books. The AI assistant summarises and answers questions about a document. | 🟡 **AI features only.** The editor works on any PC; the AI is switched off and hidden without an NPU. | [Washi-Setup.exe](../../releases/tag/washi-v1.0.4) |
| **Morph** | 1.0.2 | Universal offline file converter. The AI advisor explains the pros and cons of each target format for your exact file. | 🟡 **AI advisor only.** Without an NPU it runs in converter mode: every conversion works, with rule-based format suggestions. | [Morph-Setup.exe](../../releases/tag/morph-v1.0.2) |
| **Sensei** 先生 | 2.0.3 | Offline PowerShell helper. Describe a task in plain words; Sensei finds or writes the command, checks it and runs it when you say so. | 🟡 **AI for new tasks only.** Without an NPU it still answers from its built-in library of about 540 tested tasks. | [Sensei-Setup.exe](../../releases/tag/sensei-v2.0.3) |
| **Kaizen 5S** | 1.0.2 | Tidies your PC with the Japanese 5S method: old files, duplicates, cluttered Downloads and Desktop. Ask the AI about your scan. | 🟡 **AI chat only.** Scans, scores and actions work without AI. The AI runs on the NPU (FastFlowLM) or on **LM Studio** (untested). | [Kaizen5S-Setup.exe](../../releases/tag/kaizen-v1.0.2) |
| **Postura** | 1.0.5 | Your desk-side coach for a healthier workday. Adjust a virtual desk and chair to find your ideal setup, and get gentle reminders to rest your eyes and move. Built for offices and screen workers according to EU and Danish recommendations, and works fully offline. | 🟡 **Assistant only.** Everything else works on any Windows 11 PC. The optional assistant runs on the Ryzen AI NPU (or an Intel Core Ultra NPU, untested). | [Postura-Setup.exe](../../releases/tag/postura-v1.0.5) |
| **Tatami** 畳 | 1.0.0 | Fast disk space analyser in the spirit of WizTree, with a treemap, duplicate finder and insights. | ⚪ **No.** Contains no AI and runs on any Windows 10/11 PC. | [Tatami-Setup.exe](../../releases/tag/tatami-v1.0.0) |

**Legend:** 🟡 works on any PC, with the AI part needing a Ryzen AI NPU · ⚪ no AI, works everywhere.

All installers install per user, need no admin rights, and remove cleanly from Settings → Apps. One-time downloads: an AI engine and its model (2–3 GB) when you choose the AI during setup; Sensei only goes online for tasks you ask for (for example an internet speed test).

## Requirements

- **Any app:** Windows 11 (Tatami also runs on Windows 10).
- **For the AI features:** an AMD Ryzen AI 300/400/Max PC with the NPU driver and FastFlowLM. Each installer checks your PC and tells you what is missing, following poka-yoke principles.
- **Intel and other PCs:** the apps still install and work in their no-AI mode. LM Studio support exists in Kaizen but has not been tested on Intel.

## "Windows protected your PC"

The installers are not code-signed yet, so SmartScreen shows "Unknown publisher". Click **More info → Run anyway**. You can verify a download against the SHA-256 checksum in its release notes:

```powershell
Get-FileHash .\Washi-Setup.exe -Algorithm SHA256
```

## Source code

The complete source of every public app is in this repository, one folder per app (`washi`, `morph`, `sensei`, `kaizen`, `postura`, `tatami`), with its own README, build script and tests. Found a security problem? See [SECURITY.md](SECURITY.md).

## Licences

The apps' own code is MIT licensed. © 2026 Alexander Gubric. **Washi** and **Morph** use PyMuPDF (AGPL-3.0), so as distributed they are covered by the AGPL-3.0; Morph also bundles FFmpeg (GPL-3.0) and pandoc (GPL-2.0+). Each app's folder and installer include the full licence texts and third-party notices.

## Feedback

Please share these apps and open an [issue](../../issues) with ideas, bugs or questions.
