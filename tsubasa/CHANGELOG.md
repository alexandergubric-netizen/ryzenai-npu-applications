# Changelog

## 0.9.5 (2026-11-11): full audit, Windows installer, experimental Mac (MLX) version

First version meant for other computers than the author's.

- **Installer.** `Tsubasa-Setup.exe` (per user, no admin rights): checks the PC, can install FastFlowLM and two
  models, creates shortcuts, and uninstalls by manifest. The app and its document worker share one bundled
  Python 3.12; the whole test suite runs on that bundle during the build.
- **Starts its own engine.** The installed app starts FastFlowLM when it is not running (`--start-engine`), and
  Settings → Engine → Start/Stop work without the author's launcher scripts. Stop only ends an engine that Tsubasa
  or another Ryzen AI app started.
- **Works with whatever models are installed.** Chat falls back to the first installed model when
  `qwen-liberty3.5:9b` is missing, and Code mode's command writer falls back when `qwen3-it:4b` is missing (it used
  to fail with "Select an installed chat model").
- **Mac (experimental).** One engine interface with two engines: FastFlowLM (`core/client.py`) and MLX through
  `mlx_lm.server` (`core/mlx_client.py`). `core/platform.py` holds the platform differences; macOS gets a zsh
  terminal with its own risk checker, `osascript` pickers, process-group limits, a lock-file single instance and a
  Chrome/Edge/default-browser window. `mac/build_app.sh` builds `Tsubasa.app` and a DMG; a GitHub workflow builds
  and smoke-tests it on a macOS arm64 runner. See MAC.md for what is and is not verified.
- **Fixes from the audit** (details in PROGRESS.md):
  - Images: the engine folder was a hard-coded path on the author's PC; it is now found next to the app, in the data
    folder or through `TSUBASA_IMAGE_STUDIO`, and Images says clearly when it is not set up.
  - Audio: ffmpeg is taken from PATH (it was a fixed Chocolatey path).
  - 3D Print: dropping or pasting a photo did nothing (only the paperclip worked).
  - Entering Images showed a stale "Loading … in the background" line from another tab.
  - New-chat titles read "New 3d print chat" and "New images chat".
  - Settings panes could scroll sideways by a few pixels.
  - At very narrow widths the chat title was cut to "N…"; it now gives way to the mode switch.
  - A crash inside Settings → Engine dropped the connection instead of showing an error.
  - "Think first" is offered by the model's ability, not only for names starting with qwen3.5.
  - Offline messages pointed to "the Tsubasa desktop shortcut"; they now point to Settings → Engine.
  - The restricted calculator works on a Python without the `venv` module.
- 172 tests (4 new: model fallbacks, no personal paths in the source, MLX inventory and request shape, MLX stream).

## 2026-11-10: Code mode runs read-only commands by itself and can run commands as administrator

- **Read-only commands run at once.** When Sensei's checker rates a terminal step as only reading information (no
  syntax problems, nothing to fill in, no typed input), it runs without a click and the card says "Read only · ran by
  itself". Anything that changes something still waits for Run, and deleting/stopping still needs a second click.
  Switch: Settings → Privacy & data → "Run read-only commands automatically" (on by default).
- **Administrator commands.** Steps from the 52 library tasks that need admin rights show a "Needs administrator
  rights" note and a **Run as administrator** button; every other command card has a "Run as admin" button too.
  Tsubasa asks in the app every time, never by itself, and then Windows shows its own UAC prompt. The command runs in a
  hidden one-off administrator PowerShell (Sensei's host, with the helper commands), and its output streams back into
  the card and to the model like any other step. The process ends with the command.
- **"Access is denied"** after a normal run: Tsubasa offers the same command again as administrator, in the app.
- Declining the Windows prompt is reported as "nothing was run". Stop closes the administrator PowerShell's connection;
  Windows may refuse to let Tsubasa end an elevated process early, so a long command can finish in the background.
- Sensei itself was removed from this PC; Tsubasa's Terminal uses its own copy in `vendor/sensei` (identical to
  Sensei 2.0.3).

## 2026-11-05: everyday chat answers in about 2 s again

- **Chat took about 40 s to answer "hello!", even with Think first off.** With no instruction about reasoning,
  FastFlowLM let qwen-liberty3.5 / qwen3.5 decide, and the model reasoned silently for 25-40 s before answering;
  the `/no_think` tag did not stop it. Tsubasa now tells the engine `"think": false` explicitly when Think first is
  off (and `true` when it is on).
  - Measured through Tsubasa with the user's settings: "hello!" took 41.2 s to the first word before (502 tokens,
    mostly reasoning) and 1.7 s after (3.5 s total); "What is the capital of Slovakia?" 1.7 s / 2.5 s; "3 tips for
    better sleep" 1.7 s / 8 s. Think first still reasons when it is on.
## 2026-11-05: 3D Print is an experimental feature

- **New Settings section "Experimental"** with a **3D Print tab** switch (on by default). Off hides the tab, leaves it
  if it is open, and blocks `/print` and `?mode=print3d`. Your 3D chats and STL/SCAD files stay; an old 3D chat
  opens as text (code and advice) without the viewer.
- **Marked experimental everywhere:** an "EXP" tag on the sidebar tab, "3D Print · Experimental" in the top bar, and a
  disclaimer above the composer. Designs come from a local AI and can be wrong: check the shape and every size in
  the viewer and your slicer, and do not rely on printed parts where a failure could hurt someone or damage
  something. After the first message the disclaimer shrinks to one line.

## 2026-11-05: 3D Print designs the object you asked for

- **A "simple pyramid" came back as a cube.** The model had written `cube(...)` under a comment about four
  triangular faces. Tsubasa now checks every design:
  - **Shape check:** after building, the designer is told what it really made (size, how much of its bounding box it
    fills, flat face directions, pieces) and confirms it or corrects it, once. A box fills 100 %, a pyramid 33 %;
    a "pyramid" or "cone" that fills its box gets an explicit warning.
  - **Ready-made `pyramid()`** (and frustum), plus plain examples for a cone, hexagonal prism, wedge and dome.
  - **Only what you asked for:** extras the model adds around a ready-made part that the request gives no reason for
    (screw holes and a "bed contact" slab under a pyramid) are removed; the part and your sizes stay.
  - **True description:** an explanation that claims features the model does not have (holes, rounding, a lid,
    struts, lettering) is rewritten from the real model; if that also fails, the essentials come from the material
    table, so material and print settings are always there.
  - **The answer is assembled by Tsubasa:** one closed code block with the model that was built, then the text. An
    unclosed code block from the model no longer swallows the explanation (the page showed no text).
  - Clearer errors for the repair round: `module x(): …` (a module body goes in braces) and undefined variables
    named in the message.
- **The Chat / Code switch is shown only in Chat and Code**, not on the Images and 3D Print tabs.
- **Bitmap theme:** the Copy button on code blocks was white on white; it is now white on black and inverts on hover.

## 2026-11-04: 3D Print mode

- **New sidebar tab "3D Print"** (all three themes). Describe a part with its sizes, or attach photos or a sketch;
  Tsubasa designs it, shows it in an interactive 3D viewer and saves an STL (for the slicer) and an OpenSCAD file in
  the workspace.
  - **Thinks deeply:** Think first is on by default here, with a large token budget; the reasoning streams in a box
    while the code writes into a live code box with a line count.
  - **Your dimensions:** every size you give becomes an editable field under the model. Change it, press
    Update model, and the part rebuilds in seconds without the AI. Downloads keep the edited values.
  - **Viewer:** drag to turn, right-drag to move, scroll or pinch to zoom, double-click to reset; Iso/Front/Side/Top
    views and an Outline (triangle edges) view; a print-bed grid and the part size.
  - **Materials:** a table of 11 materials (PLA, PLA+, PETG, ABS, ASA, TPU, Nylon, PC, CF blends, two resins) feeds
    the designer's advice and the weight, cost and time estimates. The composer's printer button sets your
    material, infill and build volume. A new Library pack "3D printing" holds the design rules and slicer tips.
  - **Ready-made parts** the designer starts from when a request matches: wall hook, L-bracket, box with lid, phone
    stand, cable clips, knob, hose adapter, mounting plate. Each is tested to build as one printable solid.
  - **Checks it, not just draws it:** a model that does not build goes back to the designer with the exact error
    (up to two repairs); a part that falls apart into separate pieces is sent back once with the pieces' positions;
    overhangs, bed size and thin walls are reported. The part is laid flat on its best face for printing.
  - **Material and print advice** always comes with the model, from what was actually built.
- **Think first now really thinks with liberty and the qwen3.5 models, in Chat too.** FastFlowLM 1.0.9 reasons only
  when the request asks for it (`"think": true`); Tsubasa did not send that before, so those models answered without
  reasoning (measured: 0 reasoning tokens; with it, liberty correctly said 391 = 17 × 23 is not prime).

## 2026-11-04: Bitmap theme (1-bit retro)

- **New theme in Settings → Appearance → Theme → Bitmap (1-bit retro).** It is a classic black-and-white desktop:
  - A dotted, dithered desktop behind square white windows with hard shadows.
  - Answers sit in windows with a black title bar; the greeting and dialogs use a double-ruled alert box.
  - The top bar works as a menu bar, and the Chat/Code switch and selected items are inverted.
  - Motion moves in a few hard steps.
  - It applies to the chat window and to the workbench pages.
- **Tsubasa Bitmap**, an original pixel font made for this theme. `tools/make_pixel_font.py` draws 167 characters
  (ASCII, Slovak, Czech and German letters, €, arrows, ✓) and writes `web/fonts/tsubasa-bitmap.ttf` with the standard
  library only. Nothing is downloaded.
  - Text is 16 px (2 screen pixels per font pixel) so edges stay sharp.
  - Code and terminal output use a readable monospace.

## 2026-11-04: preload, calculator, engine buttons

- **Model preload:** switching between Chat and Code, or picking another model, starts the swap at once in the
  background, about 9 s for qwen3-it:4b and 17-27 s for liberty.
  - A message sent meanwhile waits for it instead of failing.
  - No switch dialog for a model that is already loading.
  - Setting: Models → "Load the model as soon as I switch".
  - Load estimates now use the measured times.
- **Calculator tool:** Chat offers exact arithmetic for number questions, including numbers in attached files. The
  step shows as `🧮 3*7.50 + 2*4.20 = 30.9`.
- **Settings → Engine → Start / Stop:** controls the hidden engine. Stop asks once more and also clears leftover
  gateways. `Start-LocalAI.ps1` has a new `-EngineOnly` switch.

## 2026-11-04: instructions, ember icon, audit fixes

- **Custom instructions:**
  - Settings → Profile → Instructions has "About you" and "How Tsubasa should answer", plus one-click example
    instructions.
  - Each workspace has its own instructions (Workspaces → Instructions), like a project brief.
  - All three go into every system prompt in Chat and Code.
  - Older databases are upgraded in place.
- **Ember icon** for the window, Desktop and project shortcuts. `tools/make_icon.py` builds it from the same shapes
  as the in-app logo, with no image libraries.
- **Audit** (see AUDIT-2026-11-04.md):
  - Stop now frees the app in 0.26 s instead of about 33 s.
  - No repeated switch dialog after Stop.
  - Formulas render as readable text instead of raw LaTeX.
  - Markdown tables, italics, rules and links render.
  - Typing in long chats is 4× faster.
  - Library matching ignores paths and generic words.
  - The image engine frees its memory after 3 idle minutes.
  - Code mode no longer shows the description twice.
  - The workspace select can no longer end up blank.
  - New `tools/audit.py`: gate, fuzzing, concurrency, leak and speed checks.

## 2026-11-03: silent engine, lighter window

- **FastFlowLM starts without a window.** The launcher starts it hidden and writes its log to
  `%LOCALAPPDATA%\flm-gateway\flm-server.log`. Stop it with `flm-gateway\Stop-LocalAI.ps1`. Before, closing the
  minimized FLM window also stopped the engine.
- **The window opens faster.**
  - Edge's component updater had filled Tsubasa's private window profile with about 450 MB (extension cache,
    "provenance" data, DRM, Wallet, entity-extraction models).
  - The window now starts with `--disable-component-update --disable-background-networking --disable-sync
    --no-pings`, and the old components are removed once while no window is open: 503 MB → 58 MB.
  - With FLM already running, the window opens in 1.2 s.
- **You can send while the engine is still loading:** the message waits and goes out by itself when the engine is
  ready. The page keeps checking for the engine after the first two minutes too, every 10 s. The splash screen is
  shorter (0.65 s).
- **PDF export works with Edge 156 again.** Edge's launcher now returns at once and a helper prints, so the export
  waits for the finished file. Three PDF tests had failed.

## 2026-11-03: attach almost any file

- **Many more file types can be attached in Chat:**
  - Word, PowerPoint and Excel
  - OpenDocument (odt, ods, odp)
  - EPUB, RTF, HTML and e-mails (.eml)
  - text, Markdown, CSV and JSON/YAML/XML
  - about 30 code languages
  - pictures (png, jpg, webp, gif, bmp)
  - PDFs, plus audio and video as before

  Several files can be attached at once with 📎, drag-and-drop, or Ctrl+V for screenshots. Names with unusual
  characters are made safe automatically.
- **The model reads attachments directly.**
  - Text, extracted with the standard library or the PDF worker, goes into the message as marked data: up to 16,000
    characters per message (about 4k tokens), newest files first, with a note when a file was cut.
  - Files stay part of the chat, so follow-up questions still see them.
  - Pictures go to models that can see them (liberty and qwen3.5). Pictures over 1.5 MB are shrunk to 1600 px JPEG
    first. Other models show a hint to switch.
- Tools are chosen from your words, not from attached content. Creating a picture from Chat needs an explicit
  "create/draw … image".
- The context meter counts attachments.

## 2026-11-03: Chat + Code, Library, files on this PC

- **New structure:** Chat is the everyday window, and a Chat / Code switch sits at the top right. The sidebar has
  Chat, Images and Library.
  - The Docs, Tables, Audio and Knowledge tabs are gone: Chat handles documents, PDFs, tables, conversion and audio
    itself.
  - The editors open from the + menu.
  - Old chats open in their new home.
- **Code mode:** a step-by-step agent.
  - You pick the code model; the default is qwen3-it:4b.
  - Files are written with write_file, and each change shows a diff.
  - Terminal steps are described in plain words and turned into exact commands by qwen3-it:4b with Sensei's
    references. Short everyday requests that match a tested command run instantly.
  - Every step waits for Run / Allow, Skip or Stop. Destructive commands need a second click, and the server
    re-checks edited commands.
  - A warning sits above the composer, and the project-folder chip opens a folder picker.
- **Files on this PC (Chat):**
  - Requests about files and folders let the model list, read and write anywhere except Windows, Program Files,
    ProgramData, AppData and key folders.
  - Every file asks first, and writes show the exact change.
- **Library:** skills and knowledge packs with on/off switches.
  - Coding, Chemistry and Physics are built in (curated notes plus answer instructions). You can create your own
    skills and add any file or folder via native pickers or a typed path.
  - Everything is indexed locally with FTS5. Switched-on packs add their instructions and the closest passages to
    each message.
- **Images:** a shape picker with 8 shapes (1:1 to 21:9, as SDXL sizes) and Standard (about 1 MP) or Draft
  (about 0.5 MP, twice as fast) quality.
- **Recents** have a delete button (press ✕ then Delete). **Workspaces** can be renamed and deleted (⋯ next to
  Workspace).
- **Design:** the logo is now ember to match the palette, and the model name is never cut off. New animations:
  - a sliding Chat/Code thumb
  - the sidebar bird flaps its wings when work starts
  - Library cards stagger in
  - switches slide
  - Recents slide in and out
  - the shape icon morphs between shapes

## 2026-11-03: Sensei terminal, direct Images, new defaults

- **Terminal mode is Sensei inside the chat.** It has Sensei's 541 tested commands, its router, its writer with
  facts and references, its checker and repair loop, and a persistent PowerShell 7 session with SenseiTools loaded.
  Each answer is a command card:
  - The source: tested/instant, picked by AI, or written by AI.
  - A risk badge (Safe / Review / Careful) with the checker's reasons.
  - The exact code, plus Run, Edit (re-checks the code), Copy and Open in PowerShell.
  - Live output under a `PS C:\…>` prompt, ending with "✓ Done in 0.4 s" or the errors and exit code.
  - "Did you mean" chips for related tested tasks.

  Library commands work without the engine. The Stop button stops a running command.
- **Server gate, as in Sensei:**
  - Read-only code runs on one click.
  - Anything else needs the one-use ticket issued with its check of that exact code.
  - Destructive code also needs a second click.
  - The server checks the code again before every run, and refuses to run if Tsubasa is elevated.
- **Images mode generates directly.** The message is the prompt for RealVisXL V5 Lightning, with no chat model and
  no tool loop.
  - A size picker offers 1024² (about 50 s), 768² and 512². A painting placeholder shows elapsed seconds, then the
    picture fades in with Download and Open gallery links.
  - The image engine starts by itself and stops after 10 idle minutes.
  - RealVisXL also appears in the model menu under "Pictures", and choosing it opens Images mode.
- **Defaults:**
  - Chat uses qwen-liberty3.5:9b and Terminal uses qwen3-it:4b; the model menu follows the mode.
  - The desktop launchers start FLM in Performance mode, with liberty for Tsubasa.
- **UX:**
  - While waiting for the first word, the status counts the seconds, e.g. "Loading qwen-liberty3.5:9b (usually
    about 25 s)… 7 s".
  - The switch dialog has "Don't ask again" (Settings → Models → Ask before switching models).
  - Settings explains which model each mode uses and shows the image engine's state.
  - The composer returns to one line after sending.
  - The Sensei library and PowerShell hosts load only when Terminal is opened.

## 2026-11-03: faster startup

- **The window opens in about 1.4 s instead of 15 s or more.** The desktop launcher used to wait for FLM to load its
  model before opening anything. Now it opens Tsubasa first and starts FLM and the gateway in the background. The
  page shows "Engine starting…" and connects by itself.
- **Ports are checked with a TCP connect** instead of `Invoke-WebRequest`. Each old check cost about 2 s and could time
  out on a busy FLM, which started a second copy. The extra PowerShell hop through Start-Tsubasa.ps1 is gone.
- **One copy only:**
  - A named mutex keeps Tsubasa to one server, so repeated clicks open windows on the same instance instead of
    servers on ports 52699 and 52700.
  - The launcher holds its own mutex while it starts services.
  - The gateway binds its port exclusively, so a duplicate exits instead of lingering.
- **Python startup is 0.4 s instead of 0.8 s:** the Sensei recipe library loads only when the terminal catalog is opened.

## 2026-11-03: Phase 8.6 modes, Settings, context meter

- **Modes:** every sidebar area is a chat mode with its own greeting, suggestions and tools, like switching from Claude to Claude Code.
  - The modes are Chat, Terminal (Sensei-style console), Docs & PDFs, Tables, Audio, Knowledge and Images.
  - An "Open workbench" link leads to the manual editor page, and those pages lead back to the chat mode.
- **Attaching files:** the 📎 button or drag-and-drop imports a file into the workspace for the next message. A file that's already there is reused.
- **Clearer options:**
  - "Think first" and "Long memory" replace Think and Thorough, with explanations.
  - The model picker describes each model.
- **Settings dialog:** Profile, Appearance (theme, text size, animations, send key), Models (defaults and a guide), Engine, Privacy & data and About.
- **Context meter:** a ring in the composer, with details on hover-click.
- **Hidden helper lines:** the lines Tsubasa adds for the model (attachments, the area keyword) are hidden from titles and message bubbles.

## 2026-11-03: Phase 8.5b modern redesign

- Calm, Claude-desktop-like layout with a retro edge:
  - Warm charcoal (Midnight) and paper (Paper) palettes, an ember accent and a faint film grain.
  - Editorial serif type from fonts that ship with Windows: Georgia Pro for headlines, Sitka Text for answers. Segoe UI Variable for the interface.
- New chats open on a time-of-day greeting with the composer centred and suggestion chips. Each launch starts on a fresh greeting; saved chats are under Recents.
- Less clutter:
  - The tool areas moved into the sidebar, with icons.
  - Model, Think, Thorough and per-message tools moved into the composer (a "+" popover).
  - Refresh and Load moved into an engine-status menu. Delete is a top-bar icon. The sidebar collapses, and the choice is remembered.
- Motion:
  - A bird mark beats its wings while an answer streams.
  - Send morphs into Stop with a blur crossfade.
  - Popovers grow from their trigger, and the greeting and tool-page cards settle in with a short stagger.
  - The composer clears as soon as a message is sent, and the text comes back if sending fails.

## 2026-11-03: Phase 8.5 UI overhaul

- New shared design system (`web/theme.css`): one accent per area, press feedback, dialogs that ease in with `@starting-style`, hover effects only on devices with a mouse, reduced motion respected.
- The chat fills the window height, with the composer docked at the bottom and growing as you type. Enter sends; Shift+Enter adds a line.
- Messages are styled by role. Thinking and tool results show as compact expandable chips. New messages fade in; reloaded history appears instantly.
- The confirmation dialog appears only when a request could switch the loaded model, not before every message.
- Tool pages share an app bar (`web/shell.js`) with colour-coded tabs, keep the current workspace and follow the saved theme. `files.css` was rebuilt on the shared design system.
- Removed the stale "Run · Phase 7" code-block button.

## 2026-11-01 — Phase 8

- Verify the Windows process identity before transmitting private chat, audio or image requests. Bound native file and knowledge workers before running them.
- Refreshed the in-folder shortcut, documented cold recovery, clarified offline engine status and grouped optional per-message tools beneath the chat composer’s tools control.

## 2026-11-01 — Phase 7

- Added restricted Terminal tools to chat and the Terminal tab, with single-use approvals, file diffs, bounded worker processes and cancellation.
- Added local Sensei checker provenance, restricted-mode tests and workspace path checks.

## 2026-11-01 — Phase 6
- Added image generation from chat and the Images tab, a persistent workspace gallery, download and recent job history.
- Added one-use image and service-start approvals, memory warnings, indeterminate progress, cancellation and response validation.
- Added simulated-service regression and browser checks.

## 2026-11-01 — Phase 5
- Added authenticated audio transcription, local audio/video import, language selection, cancellation, transcript copying, and a read-only chat tool.
- Added decoder, transport, concurrency and routing regression tests and a local FLM accuracy benchmark.

## 2026-11-01 — Phase 4
- Added workspace knowledge areas, PDF and text indexing, cited BM25 search, source refresh and index removal.
- Added single-use source approvals, idle checks, chat exclusion, a browser workflow and a fixed 100-question retrieval evaluation.

## 2026-11-01 — Phase 3
- Added workspace document and table editors, PDF operations and six offline conversion routes.
- Connected file operations to authenticated UI endpoints and opt-in model tools with single-use write approvals.
- Added authenticated workflow and vision follow-up regression tests.

## 2026-11-01 — Phase 2
- Added an opt-in practice connector, native streamed tool calls, bounded follow-ups, expiring exact-action approvals, expandable results and hash-only argument auditing.
- Added isolated permission/transport tests and a frozen 30-prompt qwen3-it:4b routing evaluation.

## 2026-11-01 — Phase 1
- Added workspaces, persistent chat history, model preferences, persona settings and two themes.
- Added keyboard commands, streamed Markdown blocks, collapsed reasoning, copyable code, a reduced-motion-aware splash and local bird icons.
- Added interrupted-turn recovery, a bounded context builder and an isolated browser fixture.

## 2026-10-31 — Phase 0
- Added a Python 3.13 stdlib loopback assistant with authenticated launch/relaunch, local assets, installed-model selection and streamed one-turn chat.
- Kept model reasoning separate from answer text; added explicit shared-model confirmation and cancellation by draining only this app's request.
- Copied Washi shared modules unchanged with provenance, and adapted lifecycle behavior to avoid restarting or stopping user-owned FLM.
- Added a source launcher, fresh shortcut, isolated tests, approved live benchmark harness and protected-state guard.
- Fixed Windows exclusive socket binding after the port-collision test exposed default socket reuse.
- Reviewed Sensei/Washi/Morph patterns; recorded reference notes, measured results and handoff information.
