# Funk Bot AI Family — status and unfinished work

Branch: `feature/employee-dna`. Nothing here is merged or deployed.

## Unfinished work (recorded on purpose)

### Phase 2 — existing-Bot career migration (NOT DONE)
Bots created before Employee DNA have no career. Needed:
- An owner-approved way to assign a role preset to an existing Bot.
- It must never overwrite the Bot's name, personality, memory, skills or Vault
  character. The career is added beside them (`bot_careers`), exactly as for new hires.
- Preview first (what changes, what stays), then apply per Bot or in bulk, with
  an audit row in `career_history`.
- Until then, Bots without a career behave exactly as before, including profile selection.

### Phase 2 — role pack v2 (waiting on the source pack)
The imported 59 roles are v1: one-paragraph instructions and identical
permission/cost/governance text. They are intentionally not rewritten here.
The v2 pack will bring fuller personalities, structured responsibilities, skills,
career paths and role-specific policies. Re-importing is safe: unchanged roles are
skipped, new content becomes a new version, and roles the owner edited are kept.

### Smaller follow-ups
- Installing the 9 starter roles and then the 59-role pack creates near-duplicate roles (different ids).
- A management screen for the Vault pack endpoints that were restored.
- Real-provider and physical-phone verification has not been done.

## Phase 3 — Token wallets and Economy Mode (this change)
See `docs/economy.md`.

## Phase 4 — Bot-initiated messaging (feature/bot-comms)
See `docs/family-council.md`. Verified with mocked models: backend suite, Vitest, and a browser run of the owner view and settings.
Not done: scheduled collaborative activities, supervisor auto-routing by career, routing that uses mission and tool context beyond keyword scoring.

## Phase 5 — careers, mentorship, Family Council (feature/family-council)
See `docs/family-council.md` for what is real and what is not.
Remaining: Bots authoring proposals and feedback autonomously, scheduled or event-triggered meetings and reviews, mentor-proposed training missions,
wiring the Phase 4 `nominate_colleague` / `request_mentorship` kinds to recommendations, the Phase 2 existing-Bot career migration, real-provider and phone verification.

### Phase 5 test results (2026-11-17)
- Linux suite: 385 passed, 1 skipped (backend unchanged since).
- Vitest: 40 passed. tsc and eslint clean.
- Family browser e2e: passed on the third run; the first two caught a notice-overwrite bug and a duplicate element id, both fixed (de537df).
- Status: governance core built and tested. Autonomous triggers (scheduled/event meetings, Bot-authored proposals and feedback, mentor-proposed training, automatic mission reviews and system recommendations) are NOT built.
