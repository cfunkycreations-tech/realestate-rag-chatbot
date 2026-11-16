"""Read-only Mission Control summary for the banner gauges.

Everything here is counted from existing tables in one query batch. Nothing is
estimated: a value with no underlying data is returned as None so the UI can
say "No data" instead of inventing a percentage.
"""
import json
import time

from funkbot import budget
from funkbot.budget import BudgetError, NANOS_PER_DOLLAR

ACTIVE = ('queued', 'running', 'waiting_approval')
WEEK = 7 * 86400
DAY = 86400


def _one(c, sql, params=()):
    return c.execute(sql, params).fetchone()[0] or 0


def ratio(done, failed):
    total = done + failed
    return None if total == 0 else round(done * 100 / total)


def summary(c, now=None):
    now = time.time() if now is None else now
    paused = c.execute("SELECT value FROM config WHERE key='global_pause'").fetchone()
    configured = _one(c, 'SELECT COUNT(*) FROM bots')
    active = _one(c, "SELECT COUNT(DISTINCT bot_id) FROM runs WHERE status IN ('running','waiting_approval')")
    waiting_bots = _one(c, "SELECT COUNT(DISTINCT bot_id) FROM runs WHERE status='waiting_approval'")

    since = now - WEEK
    done = _one(c, "SELECT COUNT(*) FROM missions WHERE status='done' AND updated_at>=?", (since,))
    failed = _one(c, "SELECT COUNT(*) FROM missions WHERE status='failed' AND updated_at>=?", (since,))
    queued = _one(c, "SELECT COUNT(*) FROM missions WHERE status='queued'")
    running = _one(c, "SELECT COUNT(*) FROM missions WHERE status IN ('running','waiting_approval')")

    # Automation health: missions that came from a routine or a workflow replay.
    auto = {'done': 0, 'failed': 0}
    for status in auto:
        auto[status] = _one(c, '''SELECT COUNT(*) FROM missions m WHERE m.status=? AND m.updated_at>=?
            AND (EXISTS (SELECT 1 FROM routine_runs r WHERE r.mission_id=m.id) OR EXISTS (SELECT 1 FROM workflow_replays w WHERE w.mission_id=m.id))''', (status, since))
    routines = _one(c, 'SELECT COUNT(*) FROM routines WHERE paused=0')
    workflows = _one(c, 'SELECT COUNT(*) FROM workflows')

    spend = {'connected': True}
    try:
        day, _ = budget.period_starts(now)
        daily, monthly = budget.limits_for(c, 'account')
        spent = budget.spent_nanos(c, day, now, None, 'account', 'daily')
        spend.update({'spent': str(spent / NANOS_PER_DOLLAR), 'cap': str(daily / NANOS_PER_DOLLAR),
                      'percent': None if not daily else min(100, round(spent * 100 / daily))})
    except BudgetError as exc:
        spend = {'connected': True, 'error': str(exc)}
    economy = c.execute("SELECT value FROM config WHERE key='economy'").fetchone()
    try:
        spend['economy'] = bool(economy and json.loads(economy['value']).get('enabled'))
    except (ValueError, TypeError, AttributeError):
        spend['economy'] = False

    tool_approvals = _one(c, """SELECT COUNT(*) FROM tool_calls JOIN runs ON runs.id=tool_calls.run_id
        WHERE tool_calls.status='pending' AND runs.status IN ('running','waiting_approval')""")
    routine_approvals = _one(c, "SELECT COUNT(*) FROM routine_runs WHERE approval='pending'")
    unread = _one(c, 'SELECT COUNT(*) FROM inbox_notices WHERE read_at IS NULL')
    failures = _one(c, "SELECT COUNT(*) FROM runs WHERE status='failed' AND updated_at>=?", (now - DAY,))
    attention = {'approvals': tool_approvals + routine_approvals, 'failures': failures, 'messages': unread}
    attention['total'] = sum(attention.values())

    return {
        'generated_at': now,
        'paused': bool(paused and paused['value'] == '1'),
        'bots': {'configured': configured, 'active': active, 'waiting_approval': waiting_bots},
        'missions': {'done': done, 'failed': failed, 'completion': ratio(done, failed), 'window_days': 7},
        'workflow': {'health': ratio(auto['done'], auto['failed']), 'done': auto['done'], 'failed': auto['failed'],
                     'routines_scheduled': routines, 'workflows_saved': workflows, 'window_days': 7},
        'spending': spend,
        'activity': {'running': running, 'queued': queued, 'active_runs': _one(c, "SELECT COUNT(*) FROM runs WHERE status IN ('queued','running','waiting_approval')")},
        'attention': attention,
    }
