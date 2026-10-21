# Ryzen AI NPU applications

Free Windows apps that run their AI **locally** on the AMD Ryzen AI NPU through [FastFlowLM](https://github.com/FastFlowLM/FastFlowLM). Nothing leaves your PC. From everyday tools to ones useful in a workplace (quality, health & safety).

Some apps can also use **LM Studio** on other PCs (for example Intel). That has not been tested yet.

## Downloads

| App | Version | What it does | Download |
|---|---|---|---|
| **Washi** 和紙 | 1.0.2 | PDF editor with a private AI assistant: read, edit, annotate, summarise and ask questions about your PDFs. Also opens EPUB, MOBI and FB2 books. | [Washi-Setup.exe](../../releases/tag/washi-v1.0.2) |
| **Morph** | 1.0.0 | Offline universal file converter. Drop a file in and the AI explains the pros and cons of each target format. | [Morph-Setup.exe](../../releases/tag/morph-v1.0.0) |
| **Sensei** 先生 | 2.0.1 | Offline PowerShell helper. Describe a task in plain words, Sensei finds or writes the command, checks it and runs it. | [Sensei-Setup.exe](../../releases/tag/sensei-v2.0.1) |
| **Kaizen 5S** | 1.0.0 | Tidies your PC with the Japanese 5S method: old files, duplicates, cluttered Downloads and Desktop. Ask the AI about your scan. | [Kaizen5S-Setup.exe](../../releases/tag/kaizen-v1.0.0) |
| **Tatami** 畳 | 0.10.0 (beta) | Fast disk space analyser in the spirit of WizTree, with a treemap, duplicate finder and insights. No AI needed. | [Tatami-Setup.exe](../../releases/tag/tatami-v0.10.0) |

All installers install per user, need no admin rights, and remove cleanly from Settings → Apps.

## Requirements

- Windows 11 (Tatami also runs on Windows 10)
- For the AI features: an AMD Ryzen AI 300/400/Max PC with the NPU driver and FastFlowLM. Each installer checks your PC and tells you what is missing.
- Without a supported NPU the apps still start, and the AI features are switched off.

## "Windows protected your PC"

The installers are not code-signed yet, so SmartScreen shows "Unknown publisher". Click **More info → Run anyway**. You can verify a download against the SHA-256 checksum in its release notes:

```powershell
Get-FileHash .\Washi-Setup.exe -Algorithm SHA256
```

## Coming later

Tansu (smart archiver) and Muda (process waste analyser) are still in development.

## Feedback

Please share these apps and open an [issue](../../issues) with ideas, bugs or questions.

MIT licensed. © 2026 Alexander Gubric.
