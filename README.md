# Funk Bot

Funk Bot is a local-first personal assistant workspace. This repository is a **partial implementation**, not the full persistent-agent platform: it provides password-protected, persistent Bot identities and conversations, configurable OpenAI-compatible gateways, model-profile fallback, and reported token usage. It provides two limited audited tools, single-Bot missions and chief-led group missions, but not a computer, autonomous routines, or semantic memory. Do not use it for unattended work or assume it has the safety controls of a complete agent runtime.

## Quickstart (Docker Desktop)

1. Install and start Docker Desktop. On Windows, enable its WSL 2 backend.
2. In PowerShell, run `Copy-Item .env.example .env` and `docker compose up --build`.
3. For a new installation only, open another PowerShell window in the project folder and run `docker compose logs backend`. Find the **first-run setup code**. Open `http://localhost:3000`, enter that code and create a password and Bot. Existing installations retain their password and do not need a setup code.
4. Open **Settings → Gateways**, save an OpenRouter key (or configure OmniRoute at `http://localhost:20128`), then test the saved connection. Keys are encrypted on disk and never returned by the API.
5. Check **Model profiles**, then open **Settings → Budget**. Enter the input/output prices per million tokens and token bounds for every profile you use, using the highest prices among its fallback models. No price is assumed. Adjust the default $5/day account and per-Bot limits if needed; monthly limits are optional. Then send your Bot a message.

Docker volumes retain the database, vault key, and OmniRoute data across restarts. For upgrades, rebuild from the same project folder and Compose project name so the existing volumes are reused; do not run `docker compose down -v`, which deletes them. Back up the entire `funk_data` volume: the database and vault key are both needed to recover saved credentials. The OmniRoute container uses the upstream image. Its first start needs network access; check its logs if it fails. Never expose its dashboard publicly.

## Local development

Python 3.12 and Node 22 are recommended. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 8000
# In another PowerShell window, from the repository root:
Set-Location frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. The frontend proxies `/api` to the backend; use `BACKEND_URL` to override the server-side target. Local data lives in `data/`; set `FUNK_DATA_DIR` to change it. `OMNIROUTE_URL` changes the initial default gateway URL. `FUNK_SESSION_SECRET` can override the automatically generated signing key. For HTTPS deployment set `FUNK_SECURE_COOKIE=1`, terminate TLS, and restrict both the application and OmniRoute to trusted users. This is single-user software, not a hardened multi-tenant service. Login attempts have account-wide backoff. A new installation requires a one-time code from the backend logs; anyone with access to those logs or the data directory can set up the account. Do not expose an uninitialized installation to an untrusted network.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q backend/tests
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
```

## Character Vault

Open **Settings → Character Vault**, then import a ZIP of PNGs from Sprite Grid Slicer. The importer reads `CharacterName`, `CharacterRole`, `Tags` and `Notes` (and `funk:` equivalents); `CharacterName` or `funk:name` is required. ZIPs are limited to 20 MB, 500 files and 64 MB uncompressed; individual PNGs are limited to 8 MB and 16 megapixels. Invalid files and duplicate names or files are skipped with counts. Names and artwork are not sent to the interface until a character is assigned to a Bot. A new Bot gets a weighted random character without replacement until the draw pool is exhausted; existing Bots and an empty Vault use the built-in shapes. Deleting a Bot returns its character to the available pool if no other Bot has it.

New Bots pick a job preset or custom job, with editable instructions; their name comes from the drawn Vault character, or from the fallback name if the Vault is empty. Existing names and job titles stay unchanged. For an existing Bot without a sprite, open its spotlight and choose **Give me a sprite**; explicitly choose whether to keep the name or adopt the character name. The job title is included in the system prompt. The Vault role is an archetype shown in the spotlight, not a job title.

Character images are stored in the same private data volume as the database; back up the whole volume. Image routes require login and a Bot assignment. Files on your own machine cannot be hidden from an administrator with filesystem access. There is no CLI, reroll, per-character animation map or bulk editing in this slice. Imported notes are shown on reveal but are not automatically injected into prompts.

## Team Command Center and Office

**Gallery** is the home view. It shows assigned characters only; unassigned Vault art stays hidden. Search Bots, switch grid/list/cluster layout, or use the tag-based collection groups in the sidebar. At import, an optional collection tag is added to each newly imported character; duplicates are not modified. An untagged Bot appears in Uncategorized. The gallery paginates 60 Bots at a time and virtualizes visible rows; the sidebar limits its displayed Bot lists to 50, so use search to narrow them. Bot metadata is still fetched in one request, not server-paginated.

Select a Bot to open its spotlight and chat. To remove it, select **Delete Bot** and confirm; its conversation and recorded activity are permanently deleted, while its assigned sprite stays in the Vault. A Bot with a run in progress cannot be deleted until the run ends. Quick Mission sends to the selected Bot through the same chat path. The Activity panel and status indicators come from recorded events. Runs today means `run.started` events since local midnight, not a count of historic runs that predate the event log. Last activity is the latest surviving event. No uptime or mission count is calculated. Upload or remove a private banner under **Settings → Appearance**; otherwise a gradient is shown. The recommended banner size is 2400 × 600. Drag the preview or use the sliders to choose a focal point and zoom, then select **Save placement**. The hero contracts while scrolling and expands again when the content returns to the top.

**Office** renders assigned sprites at desks, falling back to built-in shapes, with real recorded activity. It makes no model calls and displays 50 Bots per page. The earlier scripted demo is not exposed in this view because the Command Center is restricted to real Bots and recorded activity. Group chats and real meeting events are not implemented. The live feed starts with events recorded after the event-log upgrade. On a phone, swipe the canvas horizontally to explore; use the Bot buttons below it for a keyboard-accessible way to open a chat.

### Browser screenshots

The checked-in screenshots under `docs/screenshots` were captured with Playwright against a **disposable test installation** with synthetic Bots, artwork, and mock-gateway activity; they are not your data. To repeat, first set up a separate test installation with at least one Bot and a working test gateway. This test sends a message, so **never point it at your real installation**. In that disposable installation, configure the test profile price and token bounds under Budget first:

```powershell
Set-Location frontend
npm ci
npx playwright install chromium
$env:E2E_URL = "http://localhost:3000"
$env:E2E_PASSWORD = "your-disposable-test-password"
npm run test:e2e
```

### Identity browser check

The identity screenshots are from a disposable test installation with synthetic sprites. This test creates Bots and imports a ZIP; never run it against your real data. Start a fresh separate test installation, obtain its one-time setup code from the backend logs, then in PowerShell:

```powershell
Set-Location frontend
$env:E2E_URL = "http://localhost:3000"
$env:E2E_SETUP_TOKEN = "your-disposable-setup-code"
npm run test:identity
```

### Visual-pass browser check

The `visual-*` screenshots show Gallery, Roster, and Office at desktop and phone widths, plus the phone sidebar. They use a **fresh disposable installation**, 12 Bots assigned synthetic Vault sprites from the two-image identity fixture, and one fallback Bot. The visual check makes no model calls, but it creates Bots and imports artwork: **never run it against your real installation**. Start a separate fresh test installation and use its one-time setup code:

```powershell
Set-Location frontend
npm ci
npx playwright install chromium
$env:E2E_URL = "http://localhost:3000"
$env:E2E_SETUP_TOKEN = "your-disposable-setup-code"
npm run test:visual
```

### Banner browser check

The banner check imports synthetic artwork and creates Bots on a **fresh disposable installation only**. Start a separate installation and use its one-time setup code:

```powershell
Set-Location frontend
npm ci
npx playwright install chromium
$env:E2E_URL = "http://localhost:3000"
$env:E2E_SETUP_TOKEN = "your-disposable-setup-code"
npm run test:banner
```

### Budget browser check

The budget check imports synthetic artwork and creates a Bot, and deliberately checks that a zero account cap refuses a message before it reaches a gateway. Use a **fresh disposable installation only**:

```powershell
Set-Location frontend
npm ci
npx playwright install chromium
$env:E2E_URL = "http://localhost:3000"
$env:E2E_SETUP_TOKEN = "your-disposable-setup-code"
npm run test:budget
```

### Delete Bot browser check

This check creates and deletes Bots; run it **only against a fresh disposable installation**:

```powershell
Set-Location frontend
npm ci
npx playwright install chromium
$env:E2E_URL = "http://localhost:3000"
$env:E2E_SETUP_TOKEN = "your-disposable-setup-code"
npm run test:delete
```

### Tool browser check

This check creates a Bot, writes one fixture note, and changes the web policy and gateway. Run it **only against a fresh disposable installation**. In one PowerShell window, from the repository root:

```powershell
Set-Location frontend
npm ci
npx playwright install chromium
$env:MOCK_PORT = "8030"
node scripts/mock-tool-gateway.mjs
```

In a second PowerShell window, use the setup code from the disposable backend logs. The gateway address must be reachable **from the backend**; the example below assumes both backend and mock gateway run directly on the same host, not in separate containers:

```powershell
Set-Location frontend
$env:E2E_URL = "http://localhost:3000"
$env:E2E_GATEWAY_URL = "http://127.0.0.1:8030/v1"
$env:E2E_SETUP_TOKEN = "your-disposable-setup-code"
npm run test:tools
```

### Mission browser check

Run the disposable mock gateway as shown above, then use a **different fresh disposable installation** and its setup code:

```powershell
Set-Location frontend
$env:E2E_URL = "http://localhost:3000"
$env:E2E_GATEWAY_URL = "http://127.0.0.1:8030/v1"
$env:E2E_SETUP_TOKEN = "your-disposable-setup-code"
npm run test:missions
```

This creates missions and a note, adjusts the budget, and must not be run against a real installation. The gateway address must be reachable from the backend.

### Group browser check

For a fresh disposable installation, run `node scripts/mock-group-gateway.mjs` from `frontend`, then set `E2E_URL`, `E2E_SETUP_TOKEN`, and `E2E_GATEWAY_URL` (for example `http://127.0.0.1:8031/v1`, reachable from the backend) and run `npm run test:groups`. This test creates Bots, a group and a mission, approves a workspace note, and must not target real data.

### Project browser check

With the mock gateway running and a separate fresh disposable installation, set the same `E2E_URL`, `E2E_GATEWAY_URL` and `E2E_SETUP_TOKEN` variables as for the mission browser check and run `npm run test:projects` from `frontend`. This creates a mission, approves a note, and changes project data; do not run it against a real installation.

## Current behavior and limitations

**Budget safeguards are not a guarantee of provider billing.** Funk Bot reserves against account and per-Bot daily/monthly caps before chat requests, but it depends on accurate configured prices, a conservative input-token bound, and the gateway honoring output limits and reporting usage. Tokenization overhead, gateway-added charges, incorrect prices, providers that ignore limits, and spending outside Funk Bot can exceed these estimates. Always set provider-side limits and do not leave runs unattended.

Open **Settings → Budget** to set caps and profile prices. The account and each Bot default to $5/day; monthly limits are disabled until configured. Periods use UTC. Each model round, including a follow-up after a tool call, reserves for every possible fallback; no configured price means the run is refused. Costs for new runs are calculated from reported input/output tokens and the profile's configured prices, not inferred from a model name. If an attempt fails, is interrupted, exceeds configured token bounds, or does not report usage, further spending is blocked until you verify its total in your gateway billing and enter the charge and source in Budget. These owner-supplied corrections are audited. Old usage without a cost must likewise be reconciled when it falls within a capped period. Existing Bots, keys, sprites and messages are not deleted by the budget migrations.

- Projects contain an optional owner, project notes and links to existing missions. Mission totals come from linked runs and may be awaiting verification. The read-only workspace view shows flat `.txt` files belonging to the owner or linked mission assignees; these files remain Bot-local and can appear in multiple projects. Previews are limited to 64 KB and require secure descriptor-based file access (use Docker where unsupported). Unlinking a mission does not delete it or its files.
- The Missions list shows the 100 most recent missions. A group contains two to six Bots including a Chief of Staff; the chief produces a structured plan, each member works sequentially, and the chief synthesizes the actual replies. Invalid plans fail rather than inventing delegation. Each run uses the same approvals and budgets as chat. Group membership is copied into a mission at creation. A queued mission starts when its Bot becomes free. Its result, cost and run events come from the actual run, and tool approvals use the same safety controls as chat. A restart marks unfinished missions failed rather than silently replaying them; check for completed tool side effects before retrying. Quick Mission creates a real mission.
- Each Bot has its own stored timeline and identity. The last 40 messages are sent as context; this is conversation history, not semantic memory. Deleting a Bot deletes its messages.
- The database uses SQLAlchemy connections with Alembic migrations, adopting existing slice databases without replacing their rows. SQL queries and migrations remain SQLite-specific; PostgreSQL support is not implemented. Back up the full data volume before upgrading.
- Chat runs in the backend and can finish after the browser closes, provided the backend keeps running. Run records and streamed events are stored in SQLite. Reopening a Bot reconnects to an active run; after a backend restart, unfinished runs are marked failed and surfaced in that Bot’s chat rather than automatically resumed. Run the backend with one worker only. Provider text streams through a sliding-window redactor for saved gateway keys and common key patterns. The filter deliberately delays a small tail of text and cannot detect all possible secrets.
- Profiles attempt entries in order for rate limits, server failures, connection errors, and empty responses. Client errors and partially emitted responses stop the chain. The gateway and selected model must support OpenAI-compatible streamed tool calls. If a prior attempt may have incurred an unknown charge, no tools are executed and the charge must be reconciled before more spending.
- Bots can request `web_fetch` and `write_note`; there is no shell tool. Web access is default-deny; configure exact hosts or domain suffixes in **Settings → Web access**. Deny rules override allow rules, every resolved address must be public, connections use the validated address, redirects/compression are refused, and requests are limited to 256 KiB and 10 seconds. Web pages remain untrusted and can contain misleading or malicious instructions; these safeguards are not a complete defense against prompt injection.
- `write_note` creates a new `.txt` file only within the individual Bot's workspace. The owner sees the redacted arguments that will actually execute and must choose **Approve once**, **Approve for this response** (same tool only, current run only), or **Deny**. Review the entire content before approving. Tool activity appears in chat and **Settings → Tool audit**. A pending approval can be stopped; an interrupted or restarted run is never replayed automatically. A completed tool action is not undone if a subsequent model round exceeds a cap or fails. Deleting a Bot deletes its tool audit and conversation, but leaves mission records and its workspace note files on disk and returns its sprite to the Vault. Redaction is heuristic, not a guarantee that secrets are removed.
- Token totals come from reported usage. Known costs include configured-price token charges and owner-reconciled amounts; unknown charges are disclosed rather than treated as free. Caps are reservation-based estimates, not provider-enforced billing limits.
- Vault encryption protects database contents from casual inspection, but its key is stored alongside the data on the same host. Protect filesystem access and backups. Messages and provider output are redacted for saved gateway keys and common key patterns; no redaction is perfect.
- The authenticated `/api/events?since=0` endpoint exposes cursor-ordered run starts, message summaries, state changes, errors, and finishes recorded after this upgrade. Existing slice-2 events remain in per-run history and are not backfilled. Deleting a Bot deletes its event history. This is not a complete audit log. Beyond the two tools described above, no general search or file access, MCP, scheduler, webhook, sandbox, notifications, PWA, export, or browser/computer features are provided. The UI intentionally does not advertise those as working.
- Provider names and defaults are configuration examples, not a guarantee that models are currently available. A working account/key and gateway configuration are required for live inference.
