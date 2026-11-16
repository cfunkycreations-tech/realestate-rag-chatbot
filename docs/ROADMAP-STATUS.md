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
