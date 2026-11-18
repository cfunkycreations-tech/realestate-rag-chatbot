# Phases 6-8: evaluations, Cockpit, hardening

## Phase 6 - Family > Evaluations
- Five suites (v1), scored from records the app already holds, **no model call, $0.00**:
  skill (owner-verified missions, pass 70), compliance (role boundary/escalation text still in the Bot's instructions, pass 100),
  collaboration (peer/mentor/owner ratings, pass 70), reliability (completed vs failed missions, pass 80), career readiness (share of next-level requirements met, pass 100).
- Too little evidence is **Not evaluated**, never a fail, and is not recorded.
- Results store the suite version, mode, score, pass mark, evidence and cost. `simulated` results never count toward certification.
- Certification: Not Evaluated, Training, Competent (skill+compliance+reliability pass), Advanced (all five pass), Expert (all five at 90+). It is a **label**: it changes no permission, budget, tier or secret (tested: no other table changes during a run). A change writes a `certified` row to career history.
- Instruction history: every edit from the Bot editor or a Lab "apply prompt" saves the old text first with the latest scores. Restore any version; the text being replaced is saved too, so a restore can be undone.
- Not built: model-based tests, custom test authoring, automatic improvement proposals.

## Phase 7 - Mission Control and Cockpit
- Banner gauges (already built, audited): click opens the related section, tooltips, "No data"/"Not connected" states, reduced motion, hide/compact toggle.
- New Cockpit (nav > Cockpit), refreshed every 15 s only while the tab is visible, read-only:
  AI Workforce (bots busy/idle/need attention, missions pending/active/blocked/done/failed, workflow health, spend today and month with remaining budget, spend by Bot, budget warnings, approvals, council, training and certifications).
- Lyricist Pro and Business Operations: show whether a matching enabled connector (GitHub; Gumroad or Stripe) exists. **No live figures are pulled yet**; nothing is invented. Credentials stay on the server.

## Phase 8 - verification
- New tests: `test_evaluations.py`, `test_cockpit.py`, `test_hardening.py` (no Bot tool can touch budgets, policies, pause or deletion), `test_attach_career.py`, bulk-delete and purge tests in `test_playbooks.py`.
- Existing coverage of pause, reply-run denial, no-authority promotion/council/mentorship/automation: `test_family_automation.py`, `test_council.py`, `test_career_progression.py`, `test_routines.py`.
- Browser tests: `playbooks`, `bulk`, `attach`, `phase67`, `family`.
- Windows/Docker: your running app was read-only checked on 2026-11-18: migration head 0035 applied, logs clean. Migration 0036 is applied by the next `UPGRADE.bat`, which first backs up your Docker volumes to `_volume_backups`.
- Rollback: restore the newest `_volume_backups` archive into the data volume and run the previous build.
- Not verified: real providers, a physical phone, connector figures, the 0036 upgrade on your real database.
