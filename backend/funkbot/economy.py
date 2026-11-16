"""Resource policy, Economy Mode, attribution, alerts and usage reports.

Pure policy lives here; app.py only calls these functions at the two choke
points every model run already passes through: start_chat (reserve) and
settle_round. Nothing here makes a model request or raises a spending limit.

Rules that must hold:
- A profile with no configured price is never "cheaper": unknown is not free.
- Tier policy, Economy Mode and delegation caps can only lower the reservation
  or keep it equal. A promotion or a tier never raises spending authority.
- Free/local status is an explicit owner attestation per exact gateway+model.
  OmniRoute (a router) is never assumed free.
"""
import json
import time

from funkbot import budget, inbox
from funkbot.budget import BudgetError, NANOS_PER_DOLLAR, period_starts, token_cost_nanos

TIERS = ('LIGHT', 'STANDARD', 'ADVANCED', 'RESEARCH')
PROFILES = ('fast', 'smart', 'thinker', 'vision', 'cheap-bulk')
DEFAULT_TIER_POLICY = {'LIGHT': 'cheap-bulk', 'STANDARD': 'fast', 'ADVANCED': 'smart', 'RESEARCH': 'thinker'}
DEFAULT_ECONOMY = {'enabled': False, 'ceiling_tier': 'STANDARD', 'prefer_free': True}
DEFAULT_ALERTS = {'thresholds': [50, 80, 100], 'enabled': True}
DEFAULT_FALLBACK = {'enabled': False}


def _load(c, key, default):
    row = c.execute('SELECT value FROM config WHERE key=?', (key,)).fetchone()
    if not row:
        return dict(default)
    try:
        return {**default, **json.loads(row['value'])}
    except (ValueError, TypeError):
        return dict(default)


def settings(c):
    return {'tier_policy': _load(c, 'tier_policy', DEFAULT_TIER_POLICY),
            'economy': _load(c, 'economy', DEFAULT_ECONOMY),
            'alerts': _load(c, 'budget_alert_policy', DEFAULT_ALERTS),
            'fallback': _load(c, 'budget_fallback', DEFAULT_FALLBACK)}


def validate_settings(body):
    """Return a normalized dict or raise BudgetError. Unknown keys are ignored."""
    out = {}
    if 'tier_policy' in body:
        tp = body['tier_policy']
        if not isinstance(tp, dict) or set(tp) != set(TIERS) or any(v not in PROFILES for v in tp.values()):
            raise BudgetError('Tier policy must map LIGHT, STANDARD, ADVANCED and RESEARCH to existing profiles.')
        out['tier_policy'] = dict(tp)
    if 'economy' in body:
        e = body['economy']
        if not isinstance(e, dict) or type(e.get('enabled')) is not bool or e.get('ceiling_tier') not in TIERS or type(e.get('prefer_free')) is not bool:
            raise BudgetError('Economy settings need enabled, ceiling_tier and prefer_free.')
        out['economy'] = {'enabled': e['enabled'], 'ceiling_tier': e['ceiling_tier'], 'prefer_free': e['prefer_free']}
    if 'alerts' in body:
        a = body['alerts']
        th = a.get('thresholds') if isinstance(a, dict) else None
        if not isinstance(th, list) or not 1 <= len(th) <= 6 or any(type(x) is not int or not 1 <= x <= 100 for x in th) or type(a.get('enabled')) is not bool:
            raise BudgetError('Alert thresholds must be one to six whole percentages between 1 and 100.')
        out['alerts'] = {'enabled': a['enabled'], 'thresholds': sorted(set(th))}
    if 'fallback' in body:
        f = body['fallback']
        if not isinstance(f, dict) or type(f.get('enabled')) is not bool:
            raise BudgetError('Fallback settings need enabled true or false.')
        out['fallback'] = {'enabled': f['enabled']}
    return out


def save_settings(c, normalized):
    keys = {'tier_policy': 'tier_policy', 'economy': 'economy', 'alerts': 'budget_alert_policy', 'fallback': 'budget_fallback'}
    for name, value in normalized.items():
        c.execute('INSERT OR REPLACE INTO config VALUES (?,?)', (keys[name], json.dumps(value)))


def profile_cost(c, profile):
    """Reserved maximum for one run on `profile` in nanodollars (price x every
    configured fallback model, as reserve() charges), or None when unpriced."""
    p = c.execute('SELECT * FROM budget_prices WHERE profile=?', (profile,)).fetchone()
    if not p:
        return None
    row = c.execute("SELECT value FROM config WHERE key='profiles'").fetchone()
    try:
        attempts = len(json.loads(row['value']).get(profile, [])) if row else 1
    except (ValueError, TypeError, AttributeError):
        attempts = 1
    return token_cost_nanos(p['max_prompt_tokens'], p['max_completion_tokens'], p['prompt_usd_per_million'], p['completion_usd_per_million']) * max(1, attempts)


def bot_tier(c, bot_id):
    row = c.execute('SELECT model_tier FROM bot_careers WHERE bot_id=?', (bot_id,)).fetchone()
    return row['model_tier'] if row else None


def choose_profile(c, bot, requested, explicit, delegation=None):
    """Return (profile, tier, adjustment). `requested` is body.profile or the
    Bot's own profile; `explicit` is True when the caller named a profile.

    Order: career tier (only for career Bots and only when nothing was named),
    Economy ceiling, then the delegator's profile as an upper bound. Vision is
    never moved: a desktop session needs it. Unpriced profiles are never
    swapped in and never treated as cheaper.
    """
    tier = bot_tier(c, bot['id'])
    s = settings(c)
    profile, notes = requested, []
    if tier and not explicit and requested != 'vision':
        target = s['tier_policy'].get(tier)
        if target and target != profile:
            # A tier may only move a Bot to a priced profile that reserves no
            # more than the Bot's own. Otherwise the Bot keeps its profile.
            own, want = profile_cost(c, profile), profile_cost(c, target)
            if want is not None and (own is None or want <= own):
                profile = target
                notes.append(f'tier:{tier}->{target}')
            else:
                notes.append(f'tier:{tier}:kept {profile}')
    if profile != 'vision' and s['economy']['enabled']:
        ceiling = s['tier_policy'].get(s['economy']['ceiling_tier'])
        cost, cap = profile_cost(c, profile), profile_cost(c, ceiling) if ceiling else None
        if cost is not None and cap is not None and cost > cap:
            notes.append(f'economy:{profile}->{ceiling}')
            profile = ceiling
    if delegation and profile != 'vision' and delegation['origin_profile'] != 'vision':
        cost, cap = profile_cost(c, profile), profile_cost(c, delegation['origin_profile'])
        if cost is not None and cap is not None and cost > cap:
            notes.append(f"delegation:{profile}->{delegation['origin_profile']}")
            profile = delegation['origin_profile']
    return profile, tier, ';'.join(notes) or None


def cheaper_profiles(c, profile):
    """Priced, non-vision profiles strictly cheaper than `profile`, dearest first."""
    base = profile_cost(c, profile)
    if base is None or profile == 'vision':
        return []
    found = []
    for name in PROFILES:
        if name in (profile, 'vision'):
            continue
        cost = profile_cost(c, name)
        if cost is not None and cost < base:
            found.append((cost, name))
    return [name for _, name in sorted(found, reverse=True)]


def order_entries(c, entries, economy_on):
    """In Economy Mode, owner-attested free/local models go first (stable)."""
    if not economy_on or not settings(c)['economy']['prefer_free']:
        return list(entries)
    flagged = {(r['gateway'], r['model']) for r in c.execute('SELECT gateway,model FROM model_flags')}
    return sorted(entries, key=lambda e: (e['gateway'], e['model']) not in flagged)


def model_is_free(c, gateway, model):
    return bool(c.execute('SELECT 1 FROM model_flags WHERE gateway=? AND model=?', (gateway, model)).fetchone())


def delegation_for(c, mission_id):
    if not mission_id:
        return None
    return c.execute('SELECT origin_run_id,origin_bot_id,origin_profile FROM delegation_origins WHERE mission_id=?', (mission_id,)).fetchone()


def record_delegation(c, mission_id, origin_run_id, origin_bot_id, now):
    """Called when a handoff mission is created. The root of a chain is kept."""
    parent = c.execute('SELECT mission_id,delegated,effective_profile FROM run_attribution WHERE run_id=?', (origin_run_id,)).fetchone()
    if not parent:
        return  # owner-started handoff: no delegating run, so no inherited limits
    root = c.execute('SELECT origin_bot_id,origin_profile FROM delegation_origins WHERE mission_id=?', (parent['mission_id'],)).fetchone() if parent['delegated'] else None
    if root:
        bot_id, profile = root['origin_bot_id'], root['origin_profile']
    else:
        bot_id, profile = origin_bot_id, parent['effective_profile']
    c.execute('INSERT OR REPLACE INTO delegation_origins VALUES (?,?,?,?,?)', (mission_id, origin_run_id, bot_id, profile, now))


def record_attribution(c, run_id, bot_id, mission_id, tier, requested, effective, adjustment, delegation, now):
    project = None
    if mission_id:
        link = c.execute('SELECT project_id FROM project_missions WHERE mission_id=?', (mission_id,)).fetchone()
        project = link['project_id'] if link else None
    c.execute('INSERT INTO run_attribution VALUES (?,?,?,?,?,?,?,?,?,?,?)',
              (run_id, bot_id, mission_id, project, 1 if delegation else 0, delegation['origin_bot_id'] if delegation else None,
               tier, requested, effective, adjustment, now))


def check_alerts(c, bot_id, now=None):
    """Fire each threshold once per scope+period. Runs inside the settle transaction."""
    now = time.time() if now is None else now
    policy = _load(c, 'budget_alert_policy', DEFAULT_ALERTS)
    if not policy['enabled']:
        return []
    day, month = period_starts(now)
    fired = []
    for scope, filt in (('account', None), ('bot:' + bot_id, bot_id)):
        daily, monthly = budget.limits_for(c, scope)
        for start, cap, period in ((day, daily, 'daily'), (month, monthly, 'monthly')):
            if not cap:
                continue
            try:
                spent = budget.spent_nanos(c, start, now, filt, scope, period)
            except BudgetError:
                continue  # unverifiable spend is already blocked and reported elsewhere
            pct = spent * 100 // cap
            for threshold in policy['thresholds']:
                if pct >= threshold and not c.execute('SELECT 1 FROM budget_alerts WHERE scope=? AND period=? AND period_start=? AND threshold=?', (scope, period, start, threshold)).fetchone():
                    c.execute('INSERT INTO budget_alerts VALUES (?,?,?,?,?)', (scope, period, start, threshold, now))
                    label = 'Account' if scope == 'account' else 'Bot'
                    inbox.add(c, bot_id, 'budget', f'{label} {period} budget at {threshold}%',
                              f'{label} spending is ${spent / NANOS_PER_DOLLAR:.4f} of the ${cap / NANOS_PER_DOLLAR:.4f} {period} limit ({pct}%).')
                    fired.append((scope, period, threshold))
    return fired


GROUPS = {
    'bot': ('COALESCE(r.bot_id, u.bot_id)', 'bot'),
    'model': ('COALESCE(u.model, \'(unknown)\')', 'model'),
    'provider': ('COALESCE(u.gateway, \'(unknown)\')', 'provider'),
    'profile': ('r.profile', 'profile'),
    'mission': ('a.mission_id', 'mission'),
    'project': ('a.project_id', 'project'),
    'tier': ('a.tier', 'tier'),
}


def usage_report(c, group, since):
    """Actual tokens and USD, grouped. Uses the same figures budgets enforce.

    USD is the reservation's configured price for the profile that ran, or the
    owner-attested zero for flagged free/local models; it is not a provider
    invoice. Rounds whose charge is unverified are reported separately.
    """
    if group not in GROUPS:
        raise BudgetError('Unknown grouping.')
    expr = GROUPS[group][0]
    rows = c.execute(f'''SELECT {expr} AS k,
            COUNT(*) AS rounds,
            COALESCE(SUM(u.prompt_tokens),0) AS prompt_tokens,
            COALESCE(SUM(u.completion_tokens),0) AS completion_tokens,
            COALESCE(SUM(CASE WHEN r.status='settled' THEN r.actual_nanos END),0) AS settled_nanos,
            SUM(CASE WHEN r.status='uncertain' THEN 1 ELSE 0 END) AS unverified_rounds,
            SUM(CASE WHEN f.basis IS NOT NULL THEN 1 ELSE 0 END) AS owner_free_rounds
        FROM budget_reservations r
        LEFT JOIN usage u ON u.id=r.usage_id
        LEFT JOIN run_attribution a ON a.run_id=r.parent_run_id
        LEFT JOIN usage_flags f ON f.usage_id=u.id
        WHERE r.created_at>=? AND r.status IN ('settled','uncertain')
        GROUP BY k ORDER BY settled_nanos DESC, rounds DESC''', (since,)).fetchall()
    out = [{'key': row['k'], 'rounds': row['rounds'], 'prompt_tokens': row['prompt_tokens'], 'completion_tokens': row['completion_tokens'],
            'usd': str(budget.Decimal(row['settled_nanos']) / NANOS_PER_DOLLAR), 'unverified_rounds': row['unverified_rounds'],
            'owner_free_rounds': row['owner_free_rounds'], 'source': 'reservation'} for row in rows]
    if group in ('bot', 'model', 'provider'):
        # Usage recorded before budgets existed has no reservation; keep it visible.
        col = {'bot': 'u.bot_id', 'model': 'u.model', 'provider': 'u.gateway'}[group]
        legacy = c.execute(f'''SELECT {col} AS k, COUNT(*) AS rounds, COALESCE(SUM(u.prompt_tokens),0) AS p, COALESCE(SUM(u.completion_tokens),0) AS q,
                COALESCE(SUM(u.cost),0) AS usd, SUM(CASE WHEN u.cost IS NULL THEN 1 ELSE 0 END) AS unknown
            FROM usage u WHERE u.created_at>=? AND NOT EXISTS (SELECT 1 FROM budget_reservations r WHERE r.usage_id=u.id) GROUP BY k''', (since,)).fetchall()
        out += [{'key': row['k'], 'rounds': row['rounds'], 'prompt_tokens': row['p'], 'completion_tokens': row['q'], 'usd': str(row['usd']),
                 'unverified_rounds': row['unknown'], 'owner_free_rounds': 0, 'source': 'legacy'} for row in legacy]
    return out
