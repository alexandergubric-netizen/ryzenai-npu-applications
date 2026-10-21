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
| **Postura** | 1.0.2 | Posture and eye-care coach for screen workers: interactive posture and lighting models, 20-20-20 eye-break reminders, sit-stand and stretch guidance, workstation self-check. See [Postura for offices](#postura-for-offices-and-screen-workers). | 🟡 **Assistant only.** Everything else works on any Windows 11 PC. The optional assistant runs on the Ryzen AI NPU (or an Intel Core Ultra NPU, untested). | [Postura-Setup.exe](../../releases/tag/postura-v1.0.2) |
| **Tatami** 畳 | 0.10.0 (beta) | Fast disk space analyser in the spirit of WizTree, with a treemap, duplicate finder and insights. | ⚪ **No.** Contains no AI and runs on any Windows 10/11 PC. | [Tatami-Setup.exe](../../releases/tag/tatami-v0.10.0) |

**Legend:** 🟡 works on any PC, with the AI part needing a Ryzen AI NPU · ⚪ no AI, works everywhere.

All installers install per user, need no admin rights, and remove cleanly from Settings → Apps.

## Postura for offices and screen workers

Postura helps employees set up their workstation and look after their eyes and posture, without a trainer, a server or an account. It runs fully offline and sends nothing off the PC.

**What it gives an employee**
- **Today:** a live countdown to the next eye break, the four essentials, and today's breaks and screen time.
- **Posture:** a side-view model. Move chair, desk and screen and watch neck, elbows and feet respond; five checks turn green, amber or red. "Fit to me" calculates heights from your body height.
- **Lighting:** rearrange the room (window, lamp, screen position) and see glare warnings and an indicative lux level against the 500 lux target.
- **Eye breaks:** 20-20-20 reminders as Windows notifications with a 20-second timer. Only real screen time counts, and it stays quiet during full-screen apps and presentations.
- **Keep moving:** a sit-stand rhythm planner and six animated desk stretches.
- **Workspace and self-check:** advice on desk, chair, reach and cabling, plus an eight-point checklist with progress.
- **Assistant (optional):** answers ergonomics questions locally, in the language of the question, and handles commands such as "remind me every 30 minutes" or "I'm 182 cm".

**Use cases for companies with offices**
- **Onboarding:** new starters check their own workstation on day one, using the same visual guide for everyone.
- **Hybrid and home offices:** employees can assess a workstation that nobody from the company can visit.
- **Regular screen breaks:** automatic reminders to rest the eyes and move, without a manager chasing anyone.
- **Prevention:** helps spot problems early (neck, shoulders, wrists, eye strain) and tells people when to contact their manager, safety representative or health professional.
- **Easy for IT:** one small installer (about 0.3 MB), per user, no admin rights, silent install with `Postura-Setup.exe --install`. Light on resources when the window is closed (about 6 MB in the tray).
- **Privacy by design:** offline, no accounts, no telemetry; settings stay in the user's own profile.
- **Company editions:** the app supports editions with the company's own colours, assistant name and contact points (for example the safety team).

**How it fits EU and Danish requirements**

Postura is a practical aid for obligations employers already have. It is **not** a certification and does not replace them.

- EU [Directive 90/270/EEC on display screen equipment](https://osha.europa.eu/en/legislation/directives/5) asks employers to plan screen work so that it is regularly interrupted by breaks or changes of activity, and to give workers information and training about their workstation. Postura's break reminders, movement guidance and visual workstation guide support exactly that.
- In Denmark the directive is implemented through the Working Environment Act and Arbejdstilsynet's screen-work rules, and employers must carry out a workplace assessment (APV). Employees' self-check results can inform that assessment, but Postura is not an APV and does not replace one.
- It does not replace an eye examination, a workplace assessment by a competent person, or medical advice. The lux value is an orientational calculation, not a measurement.

If you work in a regulated workplace, check the current rules with your own safety organisation or Arbejdstilsynet.

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
