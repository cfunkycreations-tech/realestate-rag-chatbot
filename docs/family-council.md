# AI Family — Bot messaging, careers, mentorship and the Council (Phases 4 and 5)

Everything here is **off or inert by default**, costs nothing until you start something, and never changes anyone's authority.
Costs shown are the prices you configured, not a provider invoice. Everything was verified against mocked models only; no real provider was used.

## Phase 4 — Bots messaging each other

- **Enable:** Settings → Web access → *Bot-to-Bot messaging* → "Allow Bots to start conversations" (default off).
- **How it works:** a Bot may call the `send_bot_message` tool (and `find_colleague`, which ranks colleagues with no model call). The colleague answers once; the reply goes back to the sender's run.
- **Approval:** you approve each message unless a pair is pre-approved (Settings → Bot-to-Bot messaging → *Pre-approved pairs*) or same-department routing is on. A deny policy always wins.
- **Safeguards:** self-messages, 10 allowed purposes, chain depth, cycles (except `escalate_blocker`), ping-pong, duplicates, pair cooldown, daily and per-mission caps, simultaneous-conversation cap, per-conversation message, model-call and USD caps, timeouts, Global Pause, restart recovery. A reply cannot start another message. A message is data, never authority.
- **Cost:** replies are charged to the Bot that started the conversation and limited by its caps and the account caps.
- **Watch it:** Bot DMs → *Started by Bots* shows who, why, mission, status, tokens, cost, outcome and blocked attempts.

## Phase 5 — careers, mentorship and the Council

Open **Family** in the main navigation.

### Career Center
- Six levels: Trainee, Junior, Specialist, Senior, Lead, Principal. A level is a **label**. Nothing reads it for tool policies, budgets, model tier or the Vault.
- Everything is counted from records, with no model call (free, repeatable): completed and failed missions, reliability, work **you** marked verified, colleagues worked with, mentees graduated, training missions finished.
- "Completed" is a Bot's own report. Only work you mark **Verified** (Career Center → *Check finished work*) counts as verified. Nothing infers quality.
- Requirements to move up are fixed rules (see `RULES` in `backend/funkbot/progression.py`), counted only from work done since the Bot reached its current level.
- **Promotions:** a recommendation (from the eligibility check, a Bot that has really worked with the colleague, or you) changes nothing. Only your *Approve promotion* click changes the label, one level at a time, and it writes only `career_levels` plus a `career_history` row.
- **Reviews:** one cached review per Bot per period or per mission, with metrics, evidence links, strengths, development areas and suggested training. Feedback from mentors and peers is shown beside the review but is **never** used in eligibility. It is accepted only from a Bot that really worked with the subject, never from itself, once per review.
- Bots with no career record are Trainees (or the mapped role-preset level) and behave exactly as before.

### Mentorship
- A mentor must be at a higher level than the trainee (at most 3 trainees per mentor; one mentor per trainee).
- Objectives can be suggested from the trainee's Employee DNA skills.
- **Training missions** are ordinary missions you start from the mentorship card. The worst-case cost is shown first and you must accept it; they use normal budgets and tool approvals, and are blocked by Global Pause.
- Progress counts only finished training missions; graduation also needs your verified marks. Graduating records history and does **not** promote anyone or change any permission.

### Family Council
- Off by default. You enroll up to 5 Bots, add proposals, and **you start** a meeting. Nothing starts on a schedule.
- *Plan a meeting* shows the worst-case cost (one short tool-less reply per member, at the model profile's reserved ceiling) against your per-meeting cap. A meeting that could exceed the cap, or whose members have no configured price, cannot be planned.
- Each member's reply is an ordinary budgeted reply (so Global Pause, per-Bot and account caps, and attribution all apply). Votes are parsed by code; unreadable replies count as abstentions. Cited mission ids are kept only if that Bot really finished that mission.
- Votes are one per member per proposal, and cannot be edited (a database trigger blocks changes).
- Tallies are deterministic. Quorum is half the members. Proposals about budgets, permissions, publication, destructive actions, security, organization or promotion, and any proposal whose text mentions those topics, are always **escalated to you** even when unanimous.
- **A "passed" proposal is a recommendation only.** The council has no way to run, apply or publish anything.

## Not implemented (honest list)
- Bots do not yet *author* council proposals or give peer feedback on their own; you enter proposals, and Bot feedback has a tested function but no autonomous trigger. (Phase 4 messaging kinds `nominate_colleague` and `request_mentorship` exist but are not wired to create promotion recommendations or mentorships.)
- Mission-triggered reviews and "system" promotion recommendations run only when you click (endpoints exist and are tested); nothing builds them automatically when a mission ends or a Bot becomes eligible.
- Scheduled and event-triggered meetings, and automatic periodic reviews on a timer. Meetings and "Run this period's reviews" are started by you.
- Mentors cannot propose training missions themselves; you start them.
- Real-provider behaviour, phone behaviour and Windows/Compose upgrade of migration `0034` are not verified.
- Existing-Bot career migration (Phase 2) remains outstanding.
