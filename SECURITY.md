# Security

## Reporting a problem

If you find a security problem in any of these apps, please **don't open a public issue**. Use GitHub's private
report instead: the **Security** tab of this repository → **Report a vulnerability**. Please describe the app and
version, what can go wrong, and how to reproduce it. Reports are answered as soon as possible.

## Supported versions

Only the newest release of each app gets security fixes.

| App | Supported |
|---|---|
| Washi | 1.0.3 |
| Morph | 1.0.1 |
| Sensei | 2.0.2 |
| Kaizen 5S | 1.0.1 |
| Postura | 1.0.4 |
| Tatami | 1.0.0 |

## How the apps protect you

- Each app's window talks only to its own local server on 127.0.0.1. The window opens with a one-time launch key
  that becomes a session cookie; nothing secret is in the page, and other programs, users and web pages are refused.
- No telemetry, no accounts. Documents and AI prompts stay on the PC.
- Deletes go to the Recycle Bin only when Windows really can recycle them; uninstalling removes only the app's own files.
- Third-party installers (FastFlowLM, LM Studio) are checked against a pinned fingerprint or their publisher's
  signature before they run.

The October 2026 update fixed the findings of an independent static review of all six apps.
