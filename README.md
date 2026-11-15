# Funk Bot

Funk Bot is a local-first personal assistant workspace. This repository is a **partial implementation**, not the full persistent-agent platform: it provides password-protected, persistent Bot identities and conversations, configurable OpenAI-compatible gateways, model-profile fallback, and reported token usage. It provides limited audited tools and a constrained HTTP MCP integration, single-Bot missions and chief-led group missions, and scheduled single-Bot routines, but not a computer or semantic memory. Do not use it for unattended work or assume it has the safety controls of a complete agent runtime. Optional computer-use access to your local machine is not built.

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

### Docker smoke check (PowerShell)

With Docker Desktop running, from the repository root run:

```powershell
.\scripts\docker-smoke.ps1
```

This builds and starts a separate temporary Compose project, checks `/api/health` through the frontend and verifies the database migration head. It exits nonzero on failure, stops its containers, and deliberately retains its isolated smoke volume. It does not use or remove existing installation volumes and does not test a real model gateway.

## Character Vault

Open **Settings → Character Vault**, then import a ZIP of PNGs from Sprite Grid Slicer. The importer reads `CharacterName`, `CharacterRole`, `Tags` and `Notes` (and `funk:` equivalents); `CharacterName` or `funk:name` is required. ZIPs are limited to 20 MB, 500 files and 64 MB uncompressed; individual PNGs are limited to 8 MB and 16 megapixels. Invalid files and duplicate names or files are skipped with counts. Names and artwork are not sent to the interface until a character is assigned to a Bot. A new Bot gets a weighted random character without replacement until the draw pool is exhausted; existing Bots and an empty Vault use the built-in shapes. Deleting a Bot returns its character to the available pool if no other Bot has it.

New Bots pick a job preset or custom job, with editable instructions; their name comes from the drawn Vault character, or from the fallback name if the Vault is empty. Existing names and job titles stay unchanged. For an existing Bot without a sprite, open its spotlight and choose **Give me a sprite**; explicitly choose whether to keep the name or adopt the character name. The job title is included in the system prompt. The Vault role is an archetype shown in the spotlight, not a job title.

Character images are stored in the same private data volume as the database; back up the whole volume. Image routes require login and a Bot assignment. Files on your own machine cannot be hidden from an administrator with filesystem access. There is no CLI, reroll, per-character animation map or bulk editing in this slice. Imported notes are shown on reveal but are not automatically injected into prompts.

## Team Command Center and Office

**Gallery** is the home view. It shows assigned characters only; unassigned Vault art stays hidden. Search Bots or switch grid/list/cluster layout; the sidebar is a flat Bot list. At import, an optional collection tag is added to each newly imported character; duplicates are not modified. An untagged Bot appears in Uncategorized. The gallery paginates 60 Bots at a time and virtualizes visible rows; the flat sidebar displays all matching Bots. Bot metadata is still fetched in one request, not server-paginated.

Select a Bot to open its spotlight and chat. Duplicate Bot copies the identity, profile, sprite assignment, Bot-specific budget limits and routine definitions; copied routines are paused with a fresh next occurrence and no history. Duplication fails if copying the routines would exceed the 50-routine limit. It does not copy conversations, memories, activity, missions or workspace files. Skills are account-wide rather than attached individually to Bots. To remove it, select **Delete Bot** and confirm; its conversation and recorded activity are permanently deleted, while its assigned sprite stays in the Vault. A Bot with a run in progress cannot be deleted until the run ends. Quick Mission creates a real single-Bot mission for the selected Bot. The Activity panel and status indicators come from recorded events. Runs today means `run.started` events since local midnight, not a count of historic runs that predate the event log. Last activity is the latest surviving event. No uptime or mission count is calculated. Upload or remove a private banner under **Settings → Appearance**; otherwise a gradient is shown. The recommended banner size is 2400 × 600. The entire banner image is fitted without cropping; any previously saved placement is retained but not applied. The hero contracts while scrolling and expands again when the content returns to the top.

**Office** renders assigned sprites at desks, falling back to built-in shapes, with real recorded activity. It makes no model calls and displays 50 Bots per page. The earlier scripted demo is not exposed in this view because the Command Center is restricted to real Bots and recorded activity. Chief-led group missions emit real meeting, delegation and reply events; their Bots gather in the meeting room while the group mission is active. The live feed starts with events recorded after the event-log upgrade. On a phone, swipe the canvas horizontally to explore; use the Bot buttons below it for a keyboard-accessible way to open a chat.

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

### Lab and Analytics browser check

Run `node scripts/mock-lab-gateway.mjs` from `frontend` and use a fresh disposable installation. Set `E2E_URL`, `E2E_SETUP_TOKEN`, and `E2E_GATEWAY_URL` (for example `http://127.0.0.1:8032/v1`, reachable by the backend), then run `npm run test:lab`. This changes disposable data; do not run against a real installation.

### Group browser check

For a fresh disposable installation, run `node scripts/mock-group-gateway.mjs` from `frontend`, then set `E2E_URL`, `E2E_SETUP_TOKEN`, and `E2E_GATEWAY_URL` (for example `http://127.0.0.1:8031/v1`, reachable from the backend) and run `npm run test:groups`. This test creates Bots, a group and a mission, approves a workspace note, and must not target real data.

### Project browser check

With the mock gateway running and a separate fresh disposable installation, set the same `E2E_URL`, `E2E_GATEWAY_URL` and `E2E_SETUP_TOKEN` variables as for the mission browser check and run `npm run test:projects` from `frontend`. This creates a mission, approves a note, and changes project data; do not run it against a real installation.

### Analytics, Lab and memory

Analytics groups real runs and model rounds by their UTC start date, and approval decisions by decision date. Latency includes time waiting for approvals; the error rate counts failed runs among terminal runs (including cancellations). Costs are ledger estimates based on configured prices, not provider invoices. Pending or uncertain charges are counted separately and excluded from spend. Older usage without a linked reservation is shown under an unknown profile. CSV contains the same rows.

Lab compares up to three configured profiles sequentially. Each call reserves budget and is counted in the ledger. It sends the tested prompt without Bot conversation history, memory or tools, and rejects unexpected tool calls. Lab runs do not add chat messages or write workspace files. A completed test can explicitly replace the Bot personality or save its results as a project note. A restart marks unfinished tests failed. It cannot prevent a model provider from storing a request; check that provider's policies.

Per-Bot memory is managed in Lab. In a direct chat, use `!memory show`, `!memory remember TEXT`, `!memory forget EXACT TEXT` or `!memory replace OLD => NEW` for local, deterministic memory controls with no model call. Matching ignores case, Unicode compatibility and trailing punctuation; ambiguous matches are never changed. These commands apply only to that Bot, cannot include attachments, and are recorded in the chat and event summaries. Forgetting deletes the selected memory entry, **not** chat history or event logs: historical text may still be sent to the model as conversation context. After a successful direct chat, a narrow local rule captures a standalone “I prefer …” or “Remember that …” message, with its source and date. It does not extract general facts, process mission or tool content, or automatically update shared/project memory. You can manually add, edit and delete shared facts and project facts in Lab; shared facts apply to every Bot, and project facts apply only to linked missions. Both are untrusted model context, and only owner actions can change them. Entries containing recognized secrets are skipped. Entries can be edited, deleted and pinned, with a maximum of 50 entries, 4,000 characters per entry and 32,000 characters per Bot. Normal runs include up to 8,000 characters, pinned then most recent; the memory is described to the model as untrusted data. Known gateway keys and common secret patterns are redacted before storage, but redaction is not guaranteed: never put sensitive information in memory. Deleting a Bot deletes its memory.

## Current behavior and limitations

**Budget safeguards are not a guarantee of provider billing.** Funk Bot reserves against account and per-Bot daily/monthly caps before chat requests, but it depends on accurate configured prices, a conservative input-token bound, and the gateway honoring output limits and reporting usage. Tokenization overhead, gateway-added charges, incorrect prices, providers that ignore limits, and spending outside Funk Bot can exceed these estimates. Always set provider-side limits and do not leave runs unattended.

Open **Settings → Budget** to set caps and profile prices. The account and each Bot default to $5/day; monthly limits are disabled until configured. Periods use UTC. Each model round, including a follow-up after a tool call, reserves for every possible fallback; no configured price means the run is refused. Costs for new runs are calculated from reported input/output tokens and the profile's configured prices, not inferred from a model name. If an attempt fails, is interrupted, exceeds configured token bounds, or does not report usage, further spending is blocked until you verify its total in your gateway billing and enter the charge and source in Budget. These owner-supplied corrections are audited. Old usage without a cost must likewise be reconciled when it falls within a capped period. Existing Bots, keys, sprites and messages are not deleted by the budget migrations.

- Projects contain an optional owner, project notes and links to existing missions. Mission totals come from linked runs and may be awaiting verification. The read-only workspace view shows flat `.txt` files belonging to the owner or linked mission assignees; these files remain Bot-local and can appear in multiple projects. Previews are limited to 64 KB and require secure descriptor-based file access (use Docker where unsupported). Unlinking a mission does not delete it or its files.
- The Missions list shows the 100 most recent missions. A group contains two to six Bots including a Chief of Staff; the chief produces a structured plan, each member works sequentially, and the chief synthesizes the actual replies. Invalid plans fail rather than inventing delegation. Each run uses the same approvals and budgets as chat. Group membership is copied into a mission at creation. A queued mission starts when its Bot becomes free. Its result, cost and run events come from the actual run, and tool approvals use the same safety controls as chat. A restart marks unfinished missions failed rather than silently replaying them; check for completed tool side effects before retrying. Quick Mission creates a real mission.
- Each Bot has named chats with search over names and messages. The last 39 messages of the selected chat plus the new message are sent as context; separate Bot memory may be recalled across chats. Delete a chat only after its response stops. Deleting it removes its messages but does not erase separately saved memory, run/tool audit or event summaries; the default conversation is recreated empty when needed. Missions currently use the default conversation. Deleting a Bot deletes its messages. The Files panel accepts chat-scoped UTF-8 text, text-readable PDF and image attachments; see the limits below.
- The database uses SQLAlchemy connections with Alembic migrations, adopting existing slice databases without replacing their rows. SQL queries and migrations remain SQLite-specific; PostgreSQL support is not implemented. Back up the full data volume before upgrading.
- Chat runs in the backend and can finish after the browser closes, provided the backend keeps running. Run records and streamed events are stored in SQLite. Reopening a Bot reconnects to an active run; after a backend restart, unfinished runs are marked failed and surfaced in that Bot’s chat rather than automatically resumed. Run the backend with one worker only. Provider text streams through a sliding-window redactor for saved gateway keys and common key patterns. The filter deliberately delays a small tail of text and cannot detect all possible secrets.
- Profiles attempt entries in order for rate limits, server failures, connection errors, and empty responses. Client errors and partially emitted responses stop the chain. The gateway and selected model must support OpenAI-compatible streamed tool calls. If a prior attempt may have incurred an unknown charge, no tools are executed and the charge must be reconciled before more spending.
- Bots can request `web_fetch` and `write_note`; there is no shell tool. Web access is default-deny; configure exact hosts or domain suffixes in **Settings → Web access**. Deny rules override allow rules, every resolved address must be public, connections use the validated address, redirects/compression are refused, and requests are limited to 256 KiB and 10 seconds. Web pages remain untrusted and can contain misleading or malicious instructions; these safeguards are not a complete defense against prompt injection.
- `write_note` creates a new `.txt` file only within the individual Bot's workspace. The owner sees the redacted arguments that will actually execute and must choose **Approve once**, **Approve for this response** (same tool only, current run only), or **Deny**. Review the entire content before approving. Tool activity appears in chat and **Settings → Tool audit**. A pending approval can be stopped; an interrupted or restarted run is never replayed automatically. A completed tool action is not undone if a subsequent model round exceeds a cap or fails. Deleting a Bot deletes its tool audit and conversation, but leaves mission records and its workspace note files on disk and returns its sprite to the Vault. Redaction is heuristic, not a guarantee that secrets are removed.
- Token totals come from reported usage. Known costs include configured-price token charges and owner-reconciled amounts; unknown charges are disclosed rather than treated as free. Caps are reservation-based estimates, not provider-enforced billing limits.
- Vault encryption protects database contents from casual inspection, but its key is stored alongside the data on the same host. Protect filesystem access and backups. Messages and provider output are redacted for saved gateway keys and common key patterns; no redaction is perfect.
- The authenticated `/api/events?since=0` endpoint exposes cursor-ordered run starts, message summaries, state changes, errors, and finishes recorded after this upgrade. Existing slice-2 events remain in per-run history and are not backfilled. Deleting a Bot deletes its event history. This is not a complete audit log. Beyond the tools described above and the approved follow-up tool, no general search or file access, stdio MCP, webhook, sandbox, OS push notifications, one-click workspace restore, or browser/computer features are provided. The UI intentionally does not advertise those as working.
- Provider names and defaults are configuration examples, not a guarantee that models are currently available. A working account/key and gateway configuration are required for live inference.

### Follow-ups

### Chat files

Open **Files** in a Bot chat to upload, select, download or delete files. Files are stored in the private Funk Bot database, not exposed as local-machine paths. A message can include up to four selected drafts. Text and PDF excerpts are sent as untrusted data; selecting and sending a file may disclose it to the configured external model provider. Known-key redaction is heuristic and cannot remove unknown secrets or redact text visible in images. Images are re-encoded as PNG, resized to at most 1024 × 1024 and may be sent to a vision-compatible model as image data; previously sent images are not resent on subsequent turns. PDF extraction supports only unencrypted, text-readable PDFs with at most 20 pages, in a time- and resource-limited subprocess on Linux; scanned PDFs without extractable text are not supported. Text and PDF excerpts are capped at 40,000 characters. Files are limited to 2 MB each, 100 per chat and 50 MB workspace-wide; the configured prompt safety bound may reject large excerpts or images before a model request. No OCR or semantic document index is provided. Deleting a chat or file removes its logical record, but SQLite free pages, separate events and backups may retain older data. Do not treat deletion as secure erasure.

### Install and in-app review

Funk Bot serves an installable web manifest and, in a secure context, registers a service worker. Supported browsers can install it from their browser menu; browsers that offer an install prompt may also show an in-app install button. On iPhone use the browser's Share → Add to Home Screen when available. HTTPS is required on a phone (localhost is a browser exception only on the machine running the browser). The service worker caches only the static offline message and icons, not authenticated pages, API responses or workspace data; the app cannot work offline. Browser support, phone installation, TLS deployment and LAN access were not verified in this environment. Configure a trusted HTTPS reverse proxy and trusted local network; do not expose the single-user service or OmniRoute publicly.

While the app is open and connected, the Inbox lists pending routine runs and live tool requests from chats and missions. Review the exact displayed tool arguments before approving; those are the persisted arguments the tool will execute. A banner links to pending reviews and a dismissible in-app notice appears for newly observed completed responses. Polling is best-effort, is not a durable notification history, and cannot notify a closed app; no OS push or background notification service is provided. Other already completed or interrupted external actions cannot be undone.

### Scheduled routines

The Routines screen stores up to 50 single-Bot mission templates. A five-field cron expression (numeric values, lists, ranges, `*`, and `/` steps) uses an IANA timezone. For day-of-month and weekday, if both are restricted either may match. A nonexistent spring-forward wall minute is skipped; a repeated fall-back wall minute runs once at its first occurrence. The displayed next time uses your browser's local timezone. A completed single-Bot mission can seed an editable routine; this copies the original instructions, not learned or versioned workflow steps.

The single-worker scheduler checks every five seconds. Each scheduled occurrence is atomically recorded with a unique slot and a queued mission. An owner must approve its Inbox card before it can send instructions to a model and incur provider charges; normal budgets and separate tool approvals still apply. Manual Run now also requires this approval. Missed slots are caught up incrementally after downtime or a routine/global pause, with at most 20 routine missions awaiting approval, active or queued at a time (owner-created manual runs are not capped). A pending approval can occupy a slot until reviewed. Denial cancels that mission; it does not retry the occurrence. A routine pause does not stop work already created; global pause cancels queued work and stops active work, and those already-created slots are not replayed. Run now is available even when the routine itself is paused, but not during global pause. Editing a routine resets its next occurrence from the edit time, and deleting it removes its routine history while retaining its missions. A removed assigned Bot pauses its routine at the next due check; select another Bot to resume it. In-progress model streams interrupted by restart are marked failed and are not retried, because their external outcome or provider charges may be unknown. Recovery covers recorded, not-yet-started routine missions, not exactly-once external actions. This scheduler is designed for one backend worker only; real Docker volume upgrade and long-running recovery are unverified here.

### Owner-initiated handoffs

In a Bot spotlight, open Handoffs to choose another Bot and enter a reason and context. This immediately creates and starts a receiver mission, subject to the existing budget, pause and tool-approval controls. Both Bot spotlights show the handoff and its mission status; Office and activity show the actual recorded event. Context is untrusted data, not permission for actions. The owner initiates these handoffs; Bots cannot autonomously hand off from arbitrary chats, and these cards are not part of multiple independent chat threads. The latest 100 handoffs per Bot are shown. Deleting a Bot can leave an anonymized handoff on the other Bot; deleting the mission removes its handoff.

During a response a Bot may propose a follow-up with a summary and an ISO 8601 date/time including a timezone offset. The owner must approve the displayed proposal before it is saved. Follow-ups persist across restarts, are limited to 500 open items account-wide and may be due up to 366 days ahead. The Inbox shows approved items, highlights due entries while the app is open, and lets you mark them done or delete them. The app does not launch a new run, send an email or produce an operating-system push notification when one becomes due. Deleting a Bot deletes its follow-ups.

### Global pause

**Pause all Bots** blocks new chat, mission and Lab starts, stops active responses and pending tool approvals, and cancels queued missions and Lab work. The paused state survives a backend restart; resuming does not replay stopped work. An action already completed cannot be undone, and an in-flight provider request can have an uncertain charge. This control covers the current single-worker runtime, not a computer sandbox, which is not built; cancelling an in-flight connector request cannot undo an already accepted remote action.

### Skills

Use **Skills** to create, edit or delete up to 50 account-wide guides. Each has a slash command, when-to-use description, inputs, steps and checks. Type `/` in a Bot chat to select a skill, then add the request and send. A finished mission can open an unsaved skill draft containing its title and up to 6,000 characters of its instructions; review the draft and fill the missing fields before saving.

Import accepts UTF-8 `SKILL.md` files up to 32 KB in either a simple `#` title with `## When to use`, `## Inputs`, `## Steps`, and `## Checks` sections, or simple one-line `name` and `description` frontmatter followed by a Markdown body (up to 6,000 characters). Frontmatter imports leave inputs and checks for you to fill. This is not a full YAML or complete SKILL.md implementation. Import previews only: review and save manually. No document code, links or commands are executed during import. Skill instructions and tool output are untrusted task data, not authorization; existing tool approvals and budget caps still apply.

### Event export

In **Settings → Tool audit**, export recorded events or tool calls and their decision histories as JSON or CSV. The authenticated exports stream in recorded order and reapply known-secret filtering, but no filter is complete. Exports are private and may include message summaries, tool arguments and results. CSV cells that resemble spreadsheet formulas are prefixed for safety. These are not workspace backups. Deleting a Bot deletes its event history and tool activity.

### Tool review policies

Settings → Web access includes owner-controlled review policies for the available tools. Public web reads may be automatic, ask, or deny; workspace note and follow-up writes may only ask or deny. Host allow/deny and SSRF checks still apply. A response-scoped approval grants only that tool for the current run, and a deny policy is checked again before claiming an action. Policy changes cannot cancel or undo actions already started. Connector and computer tools are not implemented.

### Workspace backup and staged restore

In **Settings → Backup**, pause all Bots and wait for responses to stop, then download a ZIP or validate and stage a restore. Do not modify workspace files, settings, or other owner data while exporting; the database uses SQLite's online snapshot, but the database and separately stored files are not a single atomic snapshot. The ZIP contains the database (including attachments), `vault.key`, `session.key`, the banner, Vault artwork and Bot workspaces. It is **not encrypted as a whole** and includes the key needed to decrypt saved gateway credentials. Treat it like a password; transfer and store it securely. It excludes OmniRoute's separate volume, any arbitrary unrecognized files, active runtime processes, and prior restore stages. Size is limited to 256 MiB and 5,000 files.

Restoring is deliberately non-destructive and **not one-click**. Upload only an archive you trust: checksums detect accidental damage, not malicious modification, and a database can contain untrusted data. The upload is validated and unpacked into a new private directory without replacing the active workspace. Backups from this version or an earlier known schema are migrated in the isolated stage; newer or unknown schema versions are rejected. At most three stages are kept; delete unwanted stages in Settings. To activate one in Docker Compose, put the exact `FUNK_DATA_DIR=/data/restores/<stage-id>` displayed in Settings into your `.env`, then run `docker compose up -d --force-recreate backend`. Sign in using the password from the restored backup. The restored workspace is paused; verify it before resuming. For local development, stop the backend and start it with `FUNK_DATA_DIR` set to the absolute stage path. **Never run two backend instances against the same data directory.** The prior workspace remains in the volume; to return to it, remove the override and recreate the backend. A restored workspace may subsequently diverge; keep separate backups of both before switching again. If `FUNK_SESSION_SECRET` is set externally, Compose continues using that value rather than the archived session key. Docker Compose restore has not been verified here.

### Group chats

Open **Group chats** to create a group (two to six Bots including a Chief) and a named conversation. Each owner message starts a bounded sequential turn: the Chief proposes a plan, each other member reads the recent group transcript and contributes using its own Bot memory and model profile, and the Chief synthesizes the actual replies. Contributions and status persist separately from direct Bot chats. The last 30 messages and at most 12,000 content characters are considered for context; older or long content can be omitted. Replies appear when each Bot finishes, rather than streaming. Each model call uses the existing per-Bot and account budget reservations; proposals for tools require their normal approval in Inbox. Stop the turn or use global pause to cancel pending work; already completed actions cannot be undone. A backend restart marks interrupted turns failed instead of replaying them. Actual group events drive Office activity.

Transcripts are sent to each participant's configured model provider and other Bots may repeat information they receive, including information from their own memory. Other Bots' responses are untrusted task data, not authorization. This implementation is sequential only; parallel replies, @mentions and Bot-to-Bot direct messages are not implemented.

### HTTP MCP connectors (limited)

In **Settings → Connectors**, configure up to ten public HTTPS MCP endpoints and optional bearer tokens. Test the saved connection to display the first page of discovered tools and untrusted input schemas. Add exact tool names to the allowlist, enable the connector and save. Bots receive a catalog of enabled connector IDs and names, but not server schemas; they may need the owner to describe required arguments. Each proposed MCP call is treated as an external action and requires **its own** approval. The card shows the endpoint, tool name and exact redacted JSON arguments that will execute. Changing or disabling the connector while a call is pending invalidates the approval before execution; actions already started cannot be undone. Tools, their schemas and results are untrusted data, not instructions.

A constrained MCP streamable-HTTP handshake accepts JSON or bounded SSE responses to POST requests. Progress notifications are ignored; server-initiated requests and separate GET event streams are not supported. TLS certificates are verified; redirects, compressed responses, localhost/private addresses, query-string credentials and proxies are blocked. DNS answers are checked and a validated public address is pinned per connection. Tokens are Fernet-encrypted at rest; the backup includes the key, so protect it. Replace or explicitly clear a saved token before changing its endpoint. Unknown secrets may still leak through arguments or returned content despite redaction. There is no OAuth flow, local/stdio MCP, pagination of tool listings, connector-first browser fallback, ready-made service integrations, or per-tool risk classification. A connector server can itself spend, send data or perform arbitrary actions; review the service, scopes and every proposal. Provider-side charges are not limited by Funk Bot model budgets. Real external MCP service compatibility and security hardening are unverified; tests use a local TLS fixture and a mocked browser-test connector.
