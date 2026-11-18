"""Phase 7: read-only Command Cockpit data. Every figure is counted from existing tables.

Nothing here writes, spends or calls a connector. A value with no data behind it is None or
absent so the screen can say "No data" or "Not connected" instead of inventing a number.
"""
import json
import time

from funkbot import budget, mission_control
from funkbot.budget import BudgetError, NANOS_PER_DOLLAR

DAY = 86400
WEEK = 7 * DAY


def _one(c, sql, params=()):
    return c.execute(sql, params).fetchone()[0] or 0


def _money(nanos):
    return str(nanos / NANOS_PER_DOLLAR)


def workforce(c, now=None):
    now = time.time() if now is None else now
    base = mission_control.summary(c, now)
    configured = base['bots']['configured']
    busy = base['bots']['active']
    needing = _one(c, """SELECT COUNT(DISTINCT bot_id) FROM runs WHERE (status='waiting_approval') OR (status='failed' AND updated_at>=?)""", (now - DAY,))
    missions = {'pending': _one(c, "SELECT COUNT(*) FROM missions WHERE status='queued'"),
                'active': _one(c, "SELECT COUNT(*) FROM missions WHERE status='running'"),
                'blocked': _one(c, "SELECT COUNT(*) FROM missions WHERE status='waiting_approval'"),
                'completed': base['missions']['done'], 'failed': base['missions']['failed'], 'window_days': 7}
    # Token spending: account figures, plus the top spenders today. Fails closed to "unverified" like the budget code does.
    spending = {'connected': True}
    try:
        day, month = budget.period_starts(now)
        daily, monthly = budget.limits_for(c, 'account')
        today = budget.spent_nanos(c, day, now, None, 'account', 'daily')
        spending.update({'today': _money(today), 'daily_cap': _money(daily), 'remaining_today': _money(max(0, daily - today)),
                         'percent_today': None if not daily else min(100, round(today * 100 / daily))})
        if monthly:
            spent_month = budget.spent_nanos(c, month, now, None, 'account', 'monthly')
            spending.update({'month': _money(spent_month), 'monthly_cap': _money(monthly), 'remaining_month': _money(max(0, monthly - spent_month)),
                             'percent_month': min(100, round(spent_month * 100 / monthly))})
        else:
            spending.update({'month': _money(budget.spent_nanos(c, month, now, None, 'account', 'monthly'))})
        by_bot = []
        for b in c.execute('SELECT id,name FROM bots ORDER BY created_at,id').fetchall():
            n = budget.spent_nanos(c, day, now, b['id'], 'bot', 'daily')
            if n:
                by_bot.append({'bot_id': b['id'], 'name': b['name'], 'spent': _money(n)})
        by_bot.sort(key=lambda x: -float(x['spent']))
        spending['by_bot'] = by_bot[:5]
        spending['alerts'] = [{'scope': a['scope'], 'period': a['period'], 'threshold': a['threshold']} for a in
                              c.execute('SELECT scope,period,threshold FROM budget_alerts WHERE period_start IN (?,?) ORDER BY threshold DESC', (day, month)).fetchall()]
    except BudgetError as exc:
        spending = {'connected': True, 'error': str(exc)}
    council = {'open_proposals': _one(c, "SELECT COUNT(*) FROM council_proposals WHERE status='open'"),
               'escalated': _one(c, "SELECT COUNT(*) FROM council_proposals WHERE status='escalated'"),
               'meetings_7d': _one(c, "SELECT COUNT(*) FROM council_meetings WHERE created_at>=?", (now - WEEK,)),
               'members': _one(c, 'SELECT COUNT(*) FROM council_members')}
    certs = {r['level']: r['n'] for r in c.execute('SELECT level, COUNT(*) n FROM evaluation_certs GROUP BY level').fetchall()}
    training = {'active_mentorships': _one(c, "SELECT COUNT(*) FROM mentorships WHERE status='active'"),
                'training_missions_done': _one(c, "SELECT COUNT(*) FROM training_missions t JOIN missions m ON m.id=t.mission_id WHERE m.status='done'"),
                'results_recorded': _one(c, 'SELECT COUNT(*) FROM evaluation_results WHERE counts=1'),
                'certified': {k: certs.get(k, 0) for k in ('training', 'competent', 'advanced', 'expert')}}
    return {'generated_at': now, 'paused': base['paused'],
            'bots': {'configured': configured, 'busy': busy, 'waiting_approval': base['bots']['waiting_approval'], 'idle': max(0, configured - busy), 'needing_attention': needing},
            'missions': missions, 'workflow': base['workflow'], 'spending': spending, 'council': council,
            'approvals': base['attention']['approvals'], 'training': training,
            'activity': base['activity']}


# What each source needs. A connector is "connected" only when the owner has added AND enabled one whose name or address names it.
SOURCES = {
    'lyricist': {'title': 'Lyricist Pro development',
                 'wants': ['GitHub project activity', 'Open issues', 'Pull requests', 'Build status', 'Test status', 'Development priorities', 'Release readiness'],
                 'match': ('github',)},
    'business': {'title': 'Business operations',
                 'wants': ['Gumroad sales', 'Revenue', 'Subscription performance', 'Customer activity', 'Product conversion', 'Expenses', 'Business objectives'],
                 'match': ('gumroad', 'stripe')},
}


def sources(c):
    row = c.execute("SELECT value FROM config WHERE key='mcp_connectors'").fetchone()
    try:
        connectors = json.loads(row['value']) if row else {}
    except (ValueError, TypeError):
        connectors = {}
    out = {}
    for key, spec in SOURCES.items():
        found = [{'id': cid, 'name': item.get('name', cid), 'enabled': bool(item.get('enabled'))} for cid, item in connectors.items()
                 if any(m in (item.get('name', '') + ' ' + item.get('url', '')).lower() for m in spec['match'])]
        enabled = [f for f in found if f['enabled']]
        out[key] = {'title': spec['title'], 'wants': spec['wants'], 'connectors': found, 'connected': bool(enabled),
                    # Honest limit: a connector lets Bots use the service through approved tools. The cockpit does not pull or invent figures from it.
                    'figures': None,
                    'note': ('Connected. Bots can use this service through approved tools; live figures are not pulled into this screen yet, so none are shown.'
                             if enabled else 'Not connected. Add a connector in Settings, then Connectors. No figures are shown or invented until one is connected.')}
    return out
