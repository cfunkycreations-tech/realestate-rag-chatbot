# Funk Bot

Funk Bot is a local-first personal assistant workspace. This repository is a **first vertical slice**, not the full persistent-agent platform: it provides password-protected, persistent Bot identities and conversations, configurable OpenAI-compatible gateways, model-profile fallback, and reported token usage. It does not yet give Bots tools, a computer, autonomous routines, semantic memory, delegation, or groups. Do not use it for unattended work or assume it has the safety controls of a complete agent runtime.

## Quickstart (Docker Desktop)

1. Install and start Docker Desktop. On Windows, enable its WSL 2 backend.
2. Copy `.env.example` to `.env`, then run `docker compose up --build`.
3. Open `http://localhost:3000`, create a password, and create a Bot.
4. Open **Settings → Gateways**, save an OpenRouter key (or configure OmniRoute at `http://localhost:20128`), then test the saved connection. Keys are encrypted on disk and never returned by the API.
5. Check **Model profiles**: choose models available through your gateway. Send your Bot a message.

Docker volumes retain the database, vault key, and OmniRoute data across restarts. Back up the entire `funk_data` volume: the database and vault key are both needed to recover saved credentials. The OmniRoute container uses the upstream image. Its first start needs network access; check its logs if it fails. Never expose its dashboard publicly.

## Local development

Python 3.12 and Node 22 are recommended. From the repository root:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && uvicorn app:app --host 0.0.0.0 --port 8000
# in another terminal
cd frontend && npm ci && npm run dev
```

Open `http://localhost:3000`. The frontend proxies `/api` to the backend; use `BACKEND_URL` to override the server-side target. Local data lives in `data/`; set `FUNK_DATA_DIR` to change it. `OMNIROUTE_URL` changes the initial default gateway URL. `FUNK_SESSION_SECRET` can override the automatically generated signing key. For HTTPS deployment set `FUNK_SECURE_COOKIE=1`, terminate TLS, and restrict both the application and OmniRoute to trusted users. This is single-user software, not a hardened multi-tenant service; password login is not rate-limited and the setup endpoint must not be exposed to an untrusted network before setup.

## Checks

```sh
make test       # backend unit/integration tests
make typecheck  # TypeScript
make lint       # TypeScript check
cd frontend && npm run build
```

## Current behavior and limitations

- Each Bot has its own stored timeline and identity. The last 40 messages are sent as context; this is conversation history, not semantic memory. Deleting a Bot deletes its messages.
- Chat runs in the backend and can finish after the browser closes, provided the backend keeps running. Runs do not survive backend restarts. Provider responses are buffered before display to prevent a key split across chunks from leaking; live token streaming is not yet implemented.
- Profiles attempt entries in order for rate limits, server failures, connection errors, and empty responses. Client errors stop the chain. The app does not yet implement tool calling or tool-call fallback.
- Costs and token totals are shown only when gateways report them. No hard budget cap is enforced.
- Vault encryption protects database contents from casual inspection, but its key is stored alongside the data on the same host. Protect filesystem access and backups. Messages and provider output are redacted for saved gateway keys and common key patterns; no redaction is perfect.
- No search, file access, MCP, scheduler, webhook, sandbox, approvals, audit log, notifications, PWA, export, or browser/computer features are provided in this slice. The UI intentionally does not advertise those as working.
- Provider names and defaults are configuration examples, not a guarantee that models are currently available. A working account/key and gateway configuration are required for live inference.
