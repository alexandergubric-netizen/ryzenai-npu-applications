# Postura — posture & eye care for Windows 11

Postura means *posture* in Latin, Spanish, Italian, Portuguese and Polish. It teaches good office ergonomics in a visual, hands-on way and reminds you to follow the
20-20-20 rule with Windows notifications. Open source (MIT), © 2026 Alexander Gubric.

The assistant is called **Theo**. Company editions (own colours, assistant name and contact points) are built from
an `editions\<id>\org.js` file that replaces `web\org.js`; they are not part of this public source.

## What it does

- **Today** — live countdown to the next eye break, the four essentials, today's breaks and screen time.
- **Posture** — a side-view model in the guide's style. Move chair, desk and screen; the figure's neck, elbows
  and feet respond and the five guide checks turn green/amber/red. *Fit to me* computes heights from your body height.
- **Lighting** — a room you can rearrange (window side/behind screen/behind you, daylight, lamp) with a lux meter
  and glare warnings. Target: 500 lux, no glare. The lux value is an orientational calculation, not a measurement —
  measuring needs a calibrated light meter.
- **Eye breaks** — 20-20-20 explained with animations, a full-window guided break, and the reminder settings.
- **Keep moving** — sit-stand rhythm planner, optional move reminders, six animated desk stretches with timers.
- **Workspace** — the guide's sit-stand desk, chair, easy-reach and cabling advice.
- **Self-check** — the guide's eight-point checklist with progress.
- **Ask Theo** (only on AI PCs, see below) — answers ergonomics questions with a local model grounded in the
  guide, in the language of the question. Exact commands (“remind me every 30 minutes”, “pause for 2 hours”,
  “I’m 182 cm”) are handled by built-in rules.

## AI assistant (optional, poka-yoke)

The installer checks the hardware and unlocks the AI option only when every requirement passes. The server checks again,
and the app's settings API can't switch an engine on.

| PC | Engine | Model | Requirements |
|---|---|---|---|
| AMD Ryzen AI 300/400/Max (XDNA 2 NPU) | FastFlowLM on the NPU | qwen3.5:4b, plus the faster qwen3.5:2b (~5.1 GB together) | NPU driver ≥ 32.0.203.311, Windows 11, 16 GB RAM, free space |
| Intel Core Ultra with an NPU (e.g. 225U) | Microsoft Foundry Local (OpenVINO: NPU on Core Ultra 200, otherwise Intel graphics) | qwen2.5-1.5b (~1.6 GB, small for modest NPUs) | Windows 11, 16 GB RAM, winget, free space |
| anything else | — | — | Postura installs without the assistant |

**Choosing the model:** when the engine already has chat models (for example several downloaded with `flm pull`), the
installer lists them and you pick one (the recommended model is preselected; speech/embedding models are never offered).
Postura → Settings → AI model switches later, again only between models the engine really has installed.
Qwen3/Qwen3.5 hybrid models get `/no_think` so they answer directly.

If the engine or model is missing, the installer offers to download and install it (the FastFlowLM MSI asks for admin
permission; Foundry Local comes through winget). An AI failure never blocks Postura itself. The engine starts only when
the assistant is opened. After 10 idle minutes Postura stops using FastFlowLM (the server stops if no other app uses it); Foundry Local has a
15-minute idle timeout. Silent install for IT: `Postura-Setup.exe --install --ai` (AI only if the check passes).

## Reminders

Choose **Remind me with: Notification · Card · Both** on the Eye breaks page (default: Both). The card is Postura's own
floating window in the corner. Windows 11's Do not disturb can hide notifications without telling apps, which is why
Both is the default; Postura also uses the card by itself when notifications are off for it or an app is full screen. Notification buttons work through
`postura:` links, so they still work when clicked later from the notification centre.


Postura lives in the notification area (≈6 MB working set when the window is closed). Only real screen time counts:
5 minutes without keyboard/mouse (or sleep/lock) restarts the clock. Every 20 minutes it shows a Windows
notification with **Start 20 s timer** / **Snooze 5 min**; the timer is a small floating card above the clock that
never steals focus. Looking away for 20 s after a reminder also counts as a break. Quiet during full-screen apps and
presentations. Tray menu: open, rest my eyes now, pause (30 min / 1 h / 2 h / until tomorrow), quit.

## Offline, light, plug and play

- One ~300 KB exe built with the C# compiler that ships with Windows (.NET Framework 4.8) — nothing to install first.
- The window is Microsoft Edge in app mode (on every Windows 11) with a local page served only to 127.0.0.1; background
  networking, sync and updates are off and the page's Content-Security-Policy blocks any outside request. Software
  rendering keeps the open window at about 160 MB; closing it frees all of that.
- Per-user install to `%LOCALAPPDATA%\Programs\Postura`, no admin rights. Data: `%LOCALAPPDATA%\Postura\postura.json`.

## Build

```
pwsh -File build.ps1               # → build\public\Postura.exe
pwsh -File build.ps1 -Release      # also copies the installers to Documents\Apps by Alex
python make_icon.py                # regenerate the icons (needs Pillow; build runs it if icons are missing)
```

The installer is the same exe with "setup" in its name. Silent: `Postura-Setup.exe --install [--no-desktop] [--no-autostart]`.
Uninstall from Settings → Apps, or `Postura.exe --uninstall [--quiet]`.

Where each recommendation comes from: Settings → About → Sources.
General guidance, not medical advice.

## The shared AI engine

Washi, Morph, Sensei, Kaizen 5S and Postura share one FastFlowLM server on 127.0.0.1:52625
(`src/FlmShare.cs`). Whichever app starts it uses the model's full 32k context (`--ctx-len 32768`, about 8.4 GB of RAM; it costs
memory, not speed) and your NPU power mode (default **performance**; **turbo** is about as fast, balanced is about 40 %
slower). Changing the model loads it in place in about 15–20 s, with no restart; changing the power mode restarts the
server. If the server disappears, the app starts it again and retries the question. The server stops when the last
app using it closes.
