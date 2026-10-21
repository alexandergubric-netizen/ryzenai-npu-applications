# Ryzen AI NPU applications

Free Windows apps from one author, built around a private AI that runs **locally** on the AMD Ryzen AI NPU through [FastFlowLM](https://github.com/FastFlowLM/FastFlowLM). Nothing leaves your PC. They range from everyday tools to ones useful in a workplace (quality, health & safety).

**Not every app needs a Ryzen AI PC.** The table below shows exactly what each app needs and what you get without an NPU.

## Downloads

| App | Version | What it does | Needs Ryzen AI NPU? | Download |
|---|---|---|---|---|
| **Washi** 和紙 | 1.0.2 | PDF editor: read, edit, annotate and search PDFs, plus EPUB, MOBI and FB2 books. The AI assistant summarises and answers questions about a document. | 🟡 **AI features only.** The editor works on any PC; the AI is switched off and hidden without an NPU. | [Washi-Setup.exe](../../releases/tag/washi-v1.0.2) |
| **Morph** | 1.0.0 | Universal offline file converter. The AI advisor explains the pros and cons of each target format for your exact file. | 🟡 **AI advisor only.** Without an NPU it runs in converter mode: every conversion works, with rule-based format suggestions. | [Morph-Setup.exe](../../releases/tag/morph-v1.0.0) |
| **Sensei** 先生 | 2.0.1 | Offline PowerShell helper. Describe a task in plain words; Sensei finds or writes the command, checks it and runs it. | 🟡 **AI for new tasks only.** Without an NPU it still answers from its built-in library of about 540 tested tasks. | [Sensei-Setup.exe](../../releases/tag/sensei-v2.0.1) |
| **Kaizen 5S** | 1.0.0 | Tidies your PC with the Japanese 5S method: old files, duplicates, cluttered Downloads and Desktop. Ask the AI about your scan. | 🟡 **AI chat only.** Scans, scores and actions work without AI. The AI runs on the NPU (FastFlowLM) or on **LM Studio** (untested). | [Kaizen5S-Setup.exe](../../releases/tag/kaizen-v1.0.0) |
| **Postura** | 1.0.2 | Your desk-side coach for a healthier workday. Adjust a virtual desk and chair to find your ideal setup, and get gentle reminders to rest your eyes and move. Built for offices and screen workers according to EU and Danish guidelines, and works fully offline. | 🟡 **Assistant only.** Everything else works on any Windows 11 PC. The optional assistant runs on the Ryzen AI NPU (or an Intel Core Ultra NPU, untested). | [Postura-Setup.exe](../../releases/tag/postura-v1.0.2) |
| **Tatami** 畳 | 0.10.0 (beta) | Fast disk space analyser in the spirit of WizTree, with a treemap, duplicate finder and insights. | ⚪ **No.** Contains no AI and runs on any Windows 10/11 PC. | [Tatami-Setup.exe](../../releases/tag/tatami-v0.10.0) |

**Legend:** 🟡 works on any PC, with the AI part needing a Ryzen AI NPU · ⚪ no AI, works everywhere.

All installers install per user, need no admin rights, and remove cleanly from Settings → Apps.

## Requirements

- **Any app:** Windows 11 (Tatami also runs on Windows 10).
- **For the AI features:** an AMD Ryzen AI 300/400/Max PC with the NPU driver and FastFlowLM. Each installer checks your PC and tells you what is missing.
- **Intel and other PCs:** the apps still install and work in their no-AI mode. LM Studio support exists in Kaizen but has not been tested on Intel.

## "Windows protected your PC"

The installers are not code-signed yet, so SmartScreen shows "Unknown publisher". Click **More info → Run anyway**. You can verify a download against the SHA-256 checksum in its release notes:

```powershell
Get-FileHash .\Washi-Setup.exe -Algorithm SHA256
```

## Feedback

Please share these apps and open an [issue](../../issues) with ideas, bugs or questions.

MIT licensed. © 2026 Alexander Gubric.
