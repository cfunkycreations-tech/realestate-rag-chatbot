# Funk Bot acceptance status — work in progress

This is an honest snapshot, **not a parity or security certification**. None of the five requested patches is ready to ship as complete. “Partial” means only the listed subset is implemented; the cited tests do not establish the rest of the acceptance item. The README remains marked partial. External gateways can charge or retain data; use a free local model if those properties are required.

| # | Status | Evidence and remaining difference |
|---|---|---|
| 1 | Partial | Identity, editing, deletion and duplication of identity, sprite, profile and Bot budget: `backend/app.py`, `frontend/app/page.tsx`, `backend/tests/test_identity.py`, `frontend/scripts/duplicate-e2e.mjs`. Skills are account-wide rather than Bot-assigned; routines do not exist and are not copied. |
| 2 | Partial | One conversation per Bot, streaming and stop: `backend/app.py`, `backend/tests/test_runs.py`. Multiple chats, chat management, search and attachments are not implemented. |
| 3 | Partial | Manual Bot memory, narrowly rule-based direct-chat capture, owner-managed shared/project layers, bounded untrusted recall: `backend/funkbot/memory_capture.py`, `backend/app.py`, `backend/tests/test_memory.py`, `frontend/scripts/memory-layers-e2e.mjs`. General extraction, automatic shared/project proposals, forgetting and out-of-date chat commands are not implemented. |
| 4 | Not implemented | No follow-up scheduler or inbox. |
| 5 | Partial | Chief-led group missions have real delegation events: `backend/app.py`, `backend/tests/test_groups_api.py`. Arbitrary chat handoff and cards in both chats are not implemented. |
| 6 | Partial | Slash-skill autocomplete exists in `frontend/app/page.tsx`; @Bot, @group, @routine and @connector autocomplete is absent. |
| 7 | Partial | Chief-led sequential group missions, not group chats or parallel group replies: `backend/app.py`, `backend/tests/test_groups_api.py`, `frontend/scripts/groups-e2e.mjs`. |
| 8 | Not implemented | No Bot direct-message conversations. |
| 9 | Partial | Missions, project notes and read-only Bot workspace views: `backend/app.py`, `backend/tests/test_missions_api.py`, `backend/tests/test_projects_api.py`. Attaching arbitrary files/results from any Bot is not implemented. |
| 10 | Not implemented | No persistent scheduler, routine history or routine approval inbox. |
| 11 | Not implemented | No learned or versioned routines, replay or save-as-routine. |
| 12 | Partial | Owner-managed account skills, slash invocation, an editable draft from a finished mission, and limited Markdown/frontmatter import: `backend/funkbot/skills.py`, `backend/tests/test_skills.py`, `frontend/components/skills/SkillsView.tsx`, `frontend/scripts/skills-e2e.mjs`. Import supports only the documented subset, not arbitrary YAML or the full SKILL.md ecosystem. |
| 13 | Not implemented | No persistent computer container or sandbox network boundary. |
| 14 | Partial | Approved Bot-local note writing exists: `backend/funkbot/tools.py`, `backend/tests/test_tool_runtime.py`. No sandbox shell/file tools or per-Bot computer permissions. |
| 15 | Not implemented | No sandbox browser, live viewer, takeover or kill switch. |
| 16 | Not implemented | No browser sign-in/takeover flow. |
| 17 | Partial | Local-machine computer-use access is not built and README says so. There is no dedicated absence test. |
| 18 | Not implemented | No MCP client, connector definitions, per-tool policies or connector test UI. Existing gateway secrets use Fernet but are not MCP connector credentials. |
| 19 | Partial | Public web fetch uses host allow/deny policy and SSRF protections: `backend/funkbot/tools.py`, `backend/funkbot/tool_policy.py`, `backend/tests/test_tools_foundation.py`, `backend/tests/test_tool_policy.py`. Web search is not implemented. |
| 20 | Partial | Existing web reads and note-write approval flow: `backend/funkbot/tool_runtime.py`, `backend/tests/test_tool_bridge.py`. Configurable per-tool auto-review and a unified review queue are absent. |
| 21 | Partial | Budget caps, Analytics, Lab and usage: `backend/tests/test_budget_chat.py`, `backend/tests/test_analytics.py`, `backend/tests/test_lab.py`. Routine, computer and connector accounting do not exist. |
| 22 | Partial | Recorded tool audit, limited Bot activity and authenticated event JSON/CSV export: `backend/app.py`, `frontend/components/team/ToolAuditSettings.tsx`, `backend/tests/test_events.py`, `frontend/scripts/event-export-e2e.mjs`. Export is events only, not a full tool audit; there is no global pause. |
| 23 | Partial | Responsive layout and desktop/mobile browser tests exist, e.g. `frontend/scripts/visual-pass-e2e.mjs`. No installable PWA or in-app notifications; phone network reachability has not been verified. |
| 24 | Not implemented | No one-click whole-workspace export or restore. |

## Verification limitations

The latest backend suite passed 167 tests. Frontend lint, typecheck, 13 Vitest tests and the production build passed. New shared/project memory, duplication, event-export and skills UI flows were exercised at 1440px and 390px against disposable local installations; their screenshots are in `docs/screenshots/`. Browser tests use disposable fixture data and do not establish real-provider behavior.

Docker and PowerShell are unavailable in this environment, so Compose, `scripts/docker-smoke.ps1`, actual Docker volume upgrades, network isolation and phone-on-LAN access were not run. Scheduler recovery/DST, MCP approvals, computer isolation/browser approval, kill-switch and backup/restore tests cannot pass because those features do not yet exist. There is no proof that every external action is approval-gated. The existing local secret redaction is heuristic and does not guarantee removal of unknown secrets. Do not use this partial implementation for unattended or sensitive computer work.
