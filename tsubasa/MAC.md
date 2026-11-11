# Tsubasa on a Mac (Apple silicon, MLX): experimental

The Mac version runs the same app with a different engine: instead of FastFlowLM on the Ryzen AI NPU it uses
Apple's **MLX** through `mlx_lm.server`, mlx-lm's OpenAI-compatible server, on 127.0.0.1:52631.

## Verification status (read this first)

The Mac code was written on a Windows PC. The author has no Mac at hand, so:

| What | Status |
|---|---|
| Engine interface (`core/client.py` → `core/mlx_client.py`): request shape, thinking switch, reasoning and usage parsing | Unit-tested on Windows against a fake OpenAI-style server. |
| App bundle and DMG build (`mac/build_app.sh`) | Built by GitHub Actions on a macOS arm64 runner: see the workflow run linked in the release notes. |
| Server start, launch gate, storage, Library index, path policy, zsh terminal and checker, process limits, document worker (`mac/smoke.py`) | Run by the same workflow with the bundle's own Python. The run's summary shows each check. |
| A real MLX answer | The workflow tries one with a 0.6B model. Hosted runners are virtual machines, where MLX may have no GPU; the summary says whether it ran. |
| The window (Chrome/Edge app window or the default browser), Finder launch, Gatekeeper prompt, file pickers | **Not verified.** These need a person at a real Mac. |
| Speed, memory use, tool calling and "Think first" with real Qwen3 models on MLX | **Not verified.** |
| Images, audio transcription, administrator commands, the 541 tested terminal tasks | **Not available on the Mac yet** (see below). |

If something fails on your Mac, the logs are `~/Library/Application Support/Tsubasa/mlx-server.log` and
`model-download.log`.

## Install

1. Download `Tsubasa-mac-arm64.dmg`, open it and drag **Tsubasa** to **Applications**.
2. The app is not signed with an Apple Developer ID. The first time, right-click it → **Open** → **Open**. If macOS
   still refuses, run `xattr -dr com.apple.quarantine /Applications/Tsubasa.app` in Terminal.
3. Tsubasa opens in an app window of Google Chrome, Microsoft Edge, Brave or Chromium when one is installed, else in
   your default browser. Closing the window ends the app about a minute later; "Close assistant" ends it at once.
4. **Settings → Engine**: download a model. Nothing is downloaded until you press the button.
   - `mlx-community/Qwen3-8B-4bit` (about 4.6 GB): chat. Wants a 16 GB Mac.
   - `mlx-community/Qwen3-4B-4bit` (about 2.3 GB): Code mode's command writer; also fine for chat on 8 GB.
   Any MLX chat model already in your Hugging Face cache (`~/.cache/huggingface/hub`) is listed too, for example
   one you fetched with `huggingface-cli download` or converted with `mlx_lm.convert`.

Needs macOS 13.5 or newer on Apple silicon. The bundle carries its own Python 3.12, mlx-lm and the document
packages; nothing is installed system-wide.

## How it differs from Windows

| Area | Windows | Mac |
|---|---|---|
| Engine | FastFlowLM (`flm serve`), shared with other apps | `mlx_lm.server`, started and stopped by Tsubasa; one model in memory at a time |
| Models | whatever `flm pull` installed | MLX models in the Hugging Face cache; downloads only on your click |
| Thinking | `"think": true/false` | `"chat_template_kwargs": {"enable_thinking": true/false}` |
| Pictures in chat | qwen3.5 vision models | not yet: mlx-lm is text-only (mlx-vlm would be needed) |
| Code mode terminal | PowerShell 7, 541 tested tasks, Sensei's checker, auto-run of read-only steps | zsh; the model writes the command, a rule-based checker rates it; only commands on a read-only list auto-run; everything else waits for your click |
| Administrator steps | in-app approval, then UAC | not run by Tsubasa: it tells you to use `sudo` in Terminal yourself |
| Engine identity check | the engine's process path and user are verified on every connection | loopback only, no process check yet |
| Images, audio | sd-server (Vulkan), FLM Whisper | not wired up yet (sd.cpp with Metal and mlx-whisper are the planned routes) |
| Data | `%LOCALAPPDATA%\Tsubasa` | `~/Library/Application Support/Tsubasa` |
| Blocked folders for file tools | Windows, Program Files, ProgramData, AppData, key folders | /System, /Library, /usr, /bin, /sbin, /private, /etc, /var, /opt, /Applications, ~/Library, key folders |

## Build it yourself

On an Apple-silicon Mac with [uv](https://docs.astral.sh/uv/) and the Xcode command line tools:

```bash
bash mac/build_app.sh
```

It writes `mac/build/Tsubasa.app` and `mac/build/Tsubasa-mac-arm64.dmg`. Then check the pieces:

```bash
TSUBASA_SMOKE_ROOT="$PWD/mac/build/Tsubasa.app/Contents/Resources/app" mac/build/Tsubasa.app/Contents/Resources/python/bin/python3 mac/smoke.py
```

Add `--model mlx-community/Qwen3-4B-4bit` (after downloading it) for one real answer through the engine.

Run from source instead: `python3.12 -m venv .venv && .venv/bin/pip install mlx-lm -r tools/file-worker-requirements.txt`,
then `.venv/bin/python app.py --start-engine` (put the same venv at `.venv/file-worker` for the document worker).

The GitHub workflow `.github/workflows/tsubasa-mac.yml` (source: `mac/tsubasa-mac.yml`) does the build and the checks
on every change under `tsubasa/`, and attaches the DMG to a release when started by hand with a release tag.

## Known gaps

- A thinking model that ignores `enable_thinking` would answer slowly. On Windows this was the "hello! takes 40 s"
  trap; measure "hello!" with Think first off on your Mac.
- `mlx_lm.server` loads the model with the first request, so the first answer after a start is slow.
- No tested command library for macOS: Code mode's terminal steps are only as good as the model's zsh.
- macOS does not enforce a memory limit on child processes (`RLIMIT_AS`); CPU time, wall time and output limits apply.
