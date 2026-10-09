# NOVA

A local, voice-driven **command center** desktop AI assistant for Windows 11.
Personal use only: no accounts, no telemetry, no hosting, no payment code.

NOVA talks to you, remembers you, and controls your PC through safe, explicitly
approved tools. It is built to run comfortably on an 8 GB machine with
integrated graphics.

> Status: **Phase 2 complete** — desktop Command Center shell (PySide6 +
> QtWebEngine), bundled React front-end, three live themes, particle orb, chat
> with a mock backend, settings and a loopback API. The AI brain and voice
> follow in later phases.

---

## Requirements

- Windows 11
- **Python 3.12–3.14** (this machine runs 3.14.5; 3.12 is a supported fallback)
- Node.js 20+ (build-time only, for the React front-end; not needed at runtime)
- Git

## Install (development)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

Heavy subsystems are optional extras so the core the tests need stays light:

```powershell
.\.venv\Scripts\python -m pip install -e ".[brain]"   # Google Gemini
.\.venv\Scripts\python -m pip install -e ".[voice]"   # ElevenLabs + faster-whisper
.\.venv\Scripts\python -m pip install -e ".[ui]"      # PySide6 / QtWebEngine
.\.venv\Scripts\python -m pip install -e ".[tools]"   # PC-control tooling
.\.venv\Scripts\python -m pip install -e ".[all]"     # everything
```

## Build the front-end (once)

The desktop shell renders a React front-end that is **bundled locally** — no
CDN, fonts included. It must be built once before `nova ui` will show a window:

```powershell
cd ui\web
npm install --include=dev
npm run build      # writes ui/web/dist
```

Then launch the app:

```powershell
nova ui                            # normal launch
nova ui --panel chat               # open a specific panel
nova ui --theme crimson            # force a theme for one run
```

Development/verification helpers built into the same command:

```powershell
nova ui --shot artifacts\home.png --shot-delay 2      # capture the window and exit
nova ui --measure 12 --out artifacts\memory.json      # measure idle memory and exit
nova ui --panel chat --seed "write me a python function"  # auto-send a message (demo)
python scripts\measure_memory.py --seconds 14         # full process-tree memory report
```

## Verify

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m nova diag
```

`nova diag` prints the resolved data/config/log paths, the active settings and
masked secret status — it never prints a key.

## Secrets

API keys are stored in **Windows Credential Manager** (via `keyring`) through
the Settings screen. For local development you may instead copy `.env.example`
to `.env` and fill it in — `.env` is git-ignored.

Names are **app-specific** (`NOVA_` prefixed) on purpose: an unrelated,
unprefixed `GEMINI_API_KEY` exported by other software on the machine is
**ignored**, never read. Resolution order is:

1. Windows Credential Manager (keyring)
2. project `.env`
3. system environment variables

Keys are never hardcoded, logged, committed, or shown in full. Any value the
secret store returns is registered with the log redactor automatically, and the
audit log redacts its stored fields too. `nova diag` reports where each secret
came from, whether its provider prefix looks right, and any ignored legacy
variables — never any key characters.

| Secret | Where to get it |
|---|---|
| `NOVA_GEMINI_API_KEY` | https://aistudio.google.com/apikey (format `AIza…`) |
| `NOVA_ELEVENLABS_API_KEY` | https://elevenlabs.io/app/settings/api-keys (format `sk_…`) |
| `NOVA_ELEVENLABS_VOICE_ID` | ElevenLabs Voice Lab → voice → ID |

## Architecture

```
src/nova/
  config/       paths, typed settings, schema migrations
  security/     policy engine + allowlists, secret store, redaction, audit log
  api/          local FastAPI + WebSocket surface (auth, state, mock chat, server)
  ui/qt/        PySide6 shell: frameless window, tray, app runner + harness
  diagnostics.py  environment/secret report (shared by CLI and API)
  logging_setup.py  rotating, redacting logs
  cli.py        version / diag / ui
ui/web/         React + TypeScript front-end (Vite), built into ui/web/dist
scripts/        measure_memory.py (performance harness)
```

**Shell and core.** The Qt event loop owns the process. uvicorn runs in a
background thread bound to `127.0.0.1` on a random free port, guarded by a
random per-session token; the same server also serves the built front-end, so
the web view and the API share one origin. Window actions (minimise, maximise,
close, drag) travel from the web title bar to Qt over a queued signal, and
native edge resizing is handled via `WM_NCHITTEST`.

Later phases add `providers/`, `voice/`, `agent/`, `tools/` and `memory/`.

## Performance

Measured on this machine (Windows 11, i7-1355U, 7.5 GB RAM, Intel UHD):

| Metric | Value |
|---|---|
| Idle resident memory (whole process tree) | **~518 MB** |
| — main process | ~413 MB |
| — QtWebEngine renderer | ~96 MB |
| — launcher shims | ~8 MB |
| Orb animation | capped at 30 FPS (20 FPS in Performance mode), auto-degrades on slow frames |

Reproduce with `python scripts\measure_memory.py --seconds 14`.

## Security model

- **Deny by default.** Capabilities are gated by allowlists (folders, apps,
  domains, commands) configured in Settings.
- **Fail-closed.** Any policy error is treated as a denial.
- **Path safety.** Paths are resolved and must stay inside an allowlisted
  folder; `..` traversal and symlink escapes are rejected.
- **No shell chaining.** Commands containing `; & | < > \` $ ( )` are refused.
- **Explicit confirmation** is required for deleting files, running
  non-allowlisted commands, clipboard reads, screenshots and audio recording.
- **Tamper-evident audit log** — a hash chain over every decision; edits or
  deletions are detectable via `AuditLog.verify_chain()`.

## Troubleshooting

- **`no credential-manager backend available`** — install the `keyring` extra
  and ensure you are on Windows with a user profile loaded.
- **`UI bundle not found`** when launching — build the front-end (`cd ui\web &&
  npm install --include=dev && npm run build`).
- **`npm run build` fails with "tsc is not recognized"** — if `NODE_ENV=production`
  is set globally, npm skips devDependencies. Install them with
  `npm install --include=dev`.
- **`pip install` fails with "Missing dependencies for SOCKS support"** — a
  system SOCKS proxy is configured but PySocks is absent. Install `pysocks`
  first, or bypass the proxy for that command: `set "no_proxy=*" && set
  "NO_PROXY=*" && pip ...`.
- **Settings won't load** — check `nova diag` for the settings path; a corrupt
  file raises a `ConfigError` naming the file. Deleting it restores defaults.
- **Want a self-contained layout?** Set `NOVA_PORTABLE=1`; everything then
  lives under `./.data`.

## Roadmap

Phase 2 UI shell & themes · Phase 3 Gemini brain · Phase 4 voice · Phase 5
PC-control tools · Phase 6 coding agent · Phase 7 memory & Agent Town ·
Phase 8 world monitor, system panel, mini mode · Phase 9 packaging & hardening.
