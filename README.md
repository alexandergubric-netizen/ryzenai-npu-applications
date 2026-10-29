# Ryzen AI NPU applications

Free Windows apps from one author, built around a private AI that runs **locally** on the AMD Ryzen AI NPU through [FastFlowLM](https://github.com/FastFlowLM/FastFlowLM). Your documents and questions stay on your PC. They range from file, PDF and disk tools to a posture and eye-break coach for office work.

**Not every app needs a Ryzen AI PC.** The table below shows exactly what each app needs and what you get without an NPU.

## 🧰 New: Tansu beta

**Tansu** 箪笥 is a smart archive chest. Drop files or folders on it and it packs them into verified ZIP, 7z or TAR.XZ archives, files them in **Documents\Archives** and keeps that library tidy and searchable. On a Ryzen AI PC a local AI plans the format, folder and name of each archive and explains why; on any other PC its built-in rules do the same job. It is a beta: please report what you find.

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
| **Morph** | 1.0.3 | Universal offline file converter. The AI advisor explains the pros and cons of each target format for your exact file. | 🟡 **AI advisor only.** Without an NPU it runs in converter mode: every conversion works, with rule-based format suggestions. | [Morph-Setup.exe](../../releases/tag/morph-v1.0.3) |
| **Sensei** 先生 | 2.0.3 | Offline PowerShell helper. Describe a task in plain words; Sensei finds or writes the command, checks it and runs it when you say so. | 🟡 **AI for new tasks only.** Without an NPU it still answers from its built-in library of about 540 tested tasks. | [Sensei-Setup.exe](../../releases/tag/sensei-v2.0.3) |
| **Kaizen 5S** | 1.0.2 | Tidies your PC with the Japanese 5S method, applied to the files on your computer (not industrial 5S): old files, duplicates, cluttered Downloads and Desktop. Ask the AI about your scan. | 🟡 **AI chat only.** Scans, scores and actions work without AI. The AI runs on the NPU (FastFlowLM). *Experimental:* on PCs without one it can use **LM Studio** instead, which runs the model on the processor or graphics card, not an NPU, and is slower. | [Kaizen5S-Setup.exe](../../releases/tag/kaizen-v1.0.2) |
| **Postura** | 1.0.5 | Your desk-side coach for a healthier workday. Adjust a virtual desk and chair to find your ideal setup, and get gentle reminders to rest your eyes and move. For offices and screen workers, informed by the EU screen-work directive (90/270/EEC), Danish Arbejdstilsynet guidance on screen work and EN 12464-1 lighting; the sources are listed in the app. Works fully offline. General guidance: not medical advice and not a workplace assessment (APV). | 🟡 **Assistant only.** Everything else works on any Windows 11 PC. The optional assistant runs on the Ryzen AI NPU. *Experimental and untested:* on Intel Core Ultra PCs it can use Microsoft Foundry Local instead. | [Postura-Setup.exe](../../releases/tag/postura-v1.0.5) |
| **Tansu** 箪笥 | 0.9.0 beta | Smart archiver: packs files and folders into verified ZIP, 7z (AES-256 with hidden names) or TAR.XZ archives in Documents\Archives, and keeps that library tidy, searchable and checked. The AI advisor plans format, folder and name for each archive. | 🟡 **AI advisor only.** Without an NPU, Tansu plans every archive with its built-in rules; archiving, the library and the checkup work the same. | [Tansu-Setup.exe](../../releases/tag/tansu-v0.9.0) |
| **Tatami** 畳 | 1.0.0 | Fast disk space analyser in the spirit of WizTree, with a treemap, duplicate finder and insights. | ⚪ **No.** Contains no AI and runs on any Windows 10/11 PC. | [Tatami-Setup.exe](../../releases/tag/tatami-v1.0.0) |

**Legend:** 🟡 works on any PC, with the AI part needing a Ryzen AI NPU · ⚪ no AI, works everywhere.

All installers install per user, need no admin rights, and remove cleanly from Settings → Apps. One-time downloads: an AI engine and its model (2–3 GB) when you choose the AI during setup; Sensei only goes online for tasks you ask for (for example an internet speed test).

## Requirements

- **Any app:** Windows 11 (Tatami also runs on Windows 10).
- **For the AI features:** an AMD Ryzen AI 300/400/Max PC with the NPU driver and FastFlowLM. Each installer checks your PC and tells you what is missing, following poka-yoke principles.
- **Intel and other PCs:** the apps still install and work in their no-AI mode. Two *experimental*, untested options exist: Kaizen can use LM Studio, which runs the model on the processor or graphics card (not the NPU), and Postura can use Microsoft Foundry Local on Intel Core Ultra PCs.

## How the AI is kept accurate

The apps run small AI models on your own PC, and small models can be wrong. So the AI is never the only source of facts,
and it never acts on its own:

- **Postura:** the desk, chair and screen heights, the angles, the posture checks and the reminders are calculated by
  the app's own code, not by the AI. When you ask the assistant a question, every request carries the app's built-in
  ergonomics guidance plus the best-matching hand-written answer, and the model is told to use only that and not to
  add numbers of its own. Off-topic questions are declined, medical questions get "seek advice early", and if the AI is
  unavailable you get the hand-written answer instead. Sources are listed in Settings → About.
- **Kaizen 5S:** the chat looks up the relevant files in your own scan and gives the model the counts and sizes as fixed
  facts to quote. It only describes and explains. Nothing is moved or recycled until you click a button, and Recycle
  only ever uses the Windows Recycle Bin.
- **Sensei:** commands written by the AI always wait for your click, and dangerous ones need a second click.

Treat AI answers as a helpful starting point. For anything important, check the app's own pages, your workplace's
guidance or a professional.

## "Windows protected your PC"

The installers are not code-signed yet, so SmartScreen shows "Unknown publisher". Click **More info → Run anyway**. You can verify a download against the SHA-256 checksum in its release notes:

```powershell
Get-FileHash .\Washi-Setup.exe -Algorithm SHA256
```

## Source code

The complete source of every public app is in this repository, one folder per app (`washi`, `morph`, `sensei`, `kaizen`, `postura`, `tansu`, `tatami`), with its own README, build script and tests. Found a security problem? See [SECURITY.md](SECURITY.md).

## Licences

The apps' own code is MIT licensed. © 2026 Alexander Gubric. **Washi** and **Morph** use PyMuPDF (AGPL-3.0), so as distributed they are covered by the AGPL-3.0; Morph also bundles FFmpeg (GPL-3.0) and pandoc (GPL-2.0+). Tansu bundles py7zr (LGPL-2.1+). Each app's folder and installer include the full licence texts and third-party notices.

## Feedback

Please share these apps and open an [issue](../../issues) with ideas, bugs or questions.
