# Token wallets and Economy Mode

Extends the existing budget system. Nothing was replaced: `usage`,
`budget_limits`, `budget_prices`, `budget_reservations`, `GET /api/budget` and the
reconcile flow behave as before. Migration `0032_economy` adds new tables only.

## What is tracked
Every run writes one `run_attribution` row in the same transaction as its
reservation: Bot, mission, project (snapshotted), career tier, requested vs
effective profile, delegation origin, and what policy changed the profile.
Rounds join through `budget_reservations.parent_run_id`; tokens, model and
provider come from `usage`.

`GET /api/budget/usage?group=bot|mission|project|model|provider|profile|tier&days=30`
returns rounds, input/output tokens and USD per group. Spend before budgets
existed is shown separately as `legacy`. `budget.spent_nanos` is the single spend
calculation used by enforcement, alerts and this report, so they cannot disagree.

USD is the configured price of the profile that ran (or $0 for owner-attested
free models). It is not a provider invoice, and with fallbacks the answering
model is billed at the profile price, which is the conservative figure.

## Resource policy
Role tiers map to the existing five profiles (editable, `PUT /api/economy`):
LIGHT → cheap-bulk, STANDARD → fast, ADVANCED → smart, RESEARCH → thinker.
Applies only to Bots that have a career and only when the chat did not name a
profile. Bots without a career are unchanged. `vision` is never moved.

## Economy Mode (owner-controlled, off by default)
When on, a run whose profile reserves more than the ceiling tier's profile is
moved down to it. It only lowers or keeps the reservation. A profile with no
price is never treated as cheaper. Optionally tries models you marked free/local first.

## Free and local models
`PUT /api/economy/model-flags` records that one exact gateway+model is free or
local. That is an owner attestation; nothing is inferred. Such rounds settle at
$0 and are marked. OmniRoute is a router: flagging `omniroute/auto` is refused,
so OmniRoute is never assumed free.

## Limits, fallback and alerts
- Account and per-Bot caps are enforced exactly as before.
- Budget fallback (on by default, toggle in settings): when the reservation does
  not fit a cap, try strictly cheaper priced profiles, dearest first. Never a
  costlier one, never an unpriced one. The change is recorded in `adjustment`.
  If nothing fits, the original error is returned (HTTP 402).
- Alerts: thresholds (default 50/80/100%) per account and Bot, daily and monthly,
  fire once per period into the Bot inbox. Unverifiable spend is already blocked.

## Delegation cannot bypass budgets
Handoff work runs through the same reservation as any run, against the receiver's
and the account's caps. In addition, a Bot-originated handoff records its origin
(root of any chain). Delegated reservations and spend also count against the
**originating Bot's** cap, without double-counting its own runs, and the receiver
never runs on a costlier profile than its delegator. Follow-up rounds keep the same rule.
Owner-started handoffs have no delegating Bot and are not limited this way.

## Not done / limits
- Costs are configured prices, not invoices; provider-side limits are still needed.
- Per-model prices (distinct from the profile price) are not implemented.
- Tier policy is profile-level; per-role token limits come with the v2 role pack.
- Verified only against mocked providers; no paid calls were made.
