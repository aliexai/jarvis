# NOVA

A local, voice-driven **command center** desktop AI assistant for Windows 11.
Personal use only: no accounts, no telemetry, no hosting, no payment code.

NOVA talks to you, remembers you, and controls your PC through safe, explicitly
approved tools. It is built to run comfortably on an 8 GB machine with
integrated graphics.

> Status: **Phase 3 complete** — the Gemini brain: real streaming over the local
> API with cancel, model routing, function calling, conversation summaries,
> JSON-mode output, cost metering and safe network/proxy handling. Voice
> follows in Phase 4.

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
  providers/    vendor-neutral LLM interface, Gemini + mock, routing, pricing
  chat/         context window + summaries, the streaming chat pipeline
  tools/        tool registry, JSON-schema validation, policy-gated executor
  memory/       SQLite (WAL): conversations, messages, summaries, usage
  api/          local FastAPI + WebSocket surface (auth, state, server)
  ui/qt/        PySide6 shell: frameless window, tray, app runner + harness
  budget.py     cost limits and the hard stop
  net.py        proxy detection/resolution and SDK http options
  validation.py minimal JSON-schema validator (tools + structured output)
  intents.py    trivial questions answered locally with no API call
  diagnostics.py  environment/secret report (shared by CLI and API)
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

**Chat pipeline.** A message is answered locally if it matches a trivial intent,
otherwise it is routed to the fast or strong model, sent with a recent-window
context (older turns compressed into a stored summary), streamed back chunk by
chunk, and — if the model asks for a tool — the call is validated against its
JSON schema and checked by the policy engine before it runs. Usage, cost and a
transcript are persisted to SQLite. Streaming runs as a background task, so
`chat.cancel` can stop it mid-flight and the partial reply is still saved.

## Brain, cost and network

- **Models** are configurable in Settings: a *fast* model (default
  `gemini-3.5-flash-lite`) and a *strong* model (default `gemini-3.8-flash`).
  Routing picks automatically — short requests go fast, coding/planning/long
  input goes strong — and Settings can force either, or a per-message override
  is available.
- **Prices** come from a table transcribed from the official pricing page
  (`last_checked 2026-10-09`), with a free/paid tier switch. The free tier is
  free of charge. A model that is not in the table is reported as **unknown**,
  never as a guessed number. A `prices.json` next to the settings file overrides
  the built-in table without a code change.
- **Limits**: daily and monthly soft limits with an optional hard stop that
  blocks new requests. The title bar shows today's spend against the limit, each
  message shows its tokens and cost, and Settings shows the running totals.
- **Proxy**: this machine advertises a SOCKS proxy (`127.0.0.1:9050`) which
  httpx cannot use — it raises `Unknown scheme for proxy URL` simply building a
  client. Settings offers *bypass* (default), *system* and *manual*; an
  unusable system proxy is reported and bypassed. **Windows proxy settings are
  never modified.**
- **Privacy**: a one-time notice explains that free-tier Gemini content may be
  used by Google to improve its products. No local file or code is ever sent
  unless you attach it.
- **Errors** are mapped to friendly messages (invalid key, no network, timeout,
  rate limit, quota exhausted, model unavailable, safety block, budget) and
  retried with exponential backoff where retrying is safe. Stack traces are
  logged, never shown.

## Testing the connection and going live

Settings has a **Test connection** button: it sends one tiny request, reports
OK/failed, the model id it tested and the latency, and never reveals the key.

To enable the real brain, put a key in `.env` (see `.env.example`):

```
NOVA_GEMINI_API_KEY=AIza...
```

Then run the live test, which is skipped when no key is configured:

```powershell
.venv\Scripts\python -m pytest tests\test_live_gemini.py -v
```

## Performance

Measured on this machine (Windows 11, i7-1355U, 7.5 GB RAM, Intel UHD):

| Metric | Value |
|---|---|
| Idle resident memory (whole process tree) | **~508 MB** |
| — main process | ~403 MB |
| — QtWebEngine renderer | ~97 MB |
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
- **“The API key was rejected”** — no usable Gemini key was found. Put
  `NOVA_GEMINI_API_KEY=AIza...` in a local `.env`, then use Settings → Test
  connection. `nova diag` shows which source each secret came from.
- **The live test is skipped** — that is the expected behaviour when
  `NOVA_GEMINI_API_KEY` is not set.
- **A SOCKS system proxy breaks the SDK** — on this machine the Windows proxy
  is `socks4://[::1]:9050`, which httpx cannot use. NOVA defaults to
  *bypass*; switch to *system* in Settings only if the proxy speaks http(s).
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

Done: skeleton & security (1) · Command Center shell (2) · Gemini brain (3).
Next: **Phase 4 voice** · Phase 5 PC-control tools · Phase 6 coding agent ·
Phase 7 memory & Agent Town · Phase 8 world monitor, system panel, mini mode ·
Phase 9 packaging & hardening.
#   j a r v i s  
 