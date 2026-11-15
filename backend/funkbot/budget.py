"""Conservative, transaction-friendly budget accounting primitives.

No model request is authorized by this module on its own. The caller must
hold an SQLite BEGIN IMMEDIATE transaction around reservation and use an
explicit gateway token bound. Prices are configured, never inferred.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import time

NANOS_PER_DOLLAR = 1_000_000_000
DEFAULT_DAILY = 5 * NANOS_PER_DOLLAR
MAX_DOLLARS = Decimal('1000000')


class BudgetError(ValueError):
    pass


def dollars_to_nanos(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > MAX_DOLLARS:
            raise BudgetError('Dollar amounts must be between 0 and 1,000,000.')
        return int((amount * NANOS_PER_DOLLAR).to_integral_value(rounding=ROUND_CEILING))
    except (InvalidOperation, TypeError) as exc:
        raise BudgetError('Enter a valid dollar amount.') from exc


def token_cost_nanos(prompt_tokens, completion_tokens, prompt_price, completion_price):
    if type(prompt_tokens) is not int or type(completion_tokens) is not int or min(prompt_tokens, completion_tokens) < 0:
        raise BudgetError('Gateway token usage is missing or invalid.')
    # Per-million price * tokens * 1000 produces nanodollars.
    try:
        p, q = Decimal(str(prompt_price)), Decimal(str(completion_price))
        if not p.is_finite() or not q.is_finite() or min(p, q) < 0 or max(p, q) > MAX_DOLLARS:
            raise BudgetError('Model prices must be between 0 and 1,000,000 USD per million tokens.')
        amount = (p * prompt_tokens + q * completion_tokens) * 1000
        if amount > 9_000_000_000_000_000_000:
            raise BudgetError('Calculated cost is too large.')
        return int(amount.to_integral_value(rounding=ROUND_CEILING))
    except (InvalidOperation, TypeError) as exc:
        raise BudgetError('Enter valid model prices.') from exc


def period_starts(now):
    # Shared, deterministic boundaries independent of server locale or DST.
    date = datetime.fromtimestamp(now, timezone.utc)
    return (date.replace(hour=0, minute=0, second=0, microsecond=0).timestamp(),
            date.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())


def limits_for(c, scope):
    row = c.execute('SELECT daily_nanos,monthly_nanos FROM budget_limits WHERE scope=?', (scope,)).fetchone()
    return (row['daily_nanos'], row['monthly_nanos']) if row else (DEFAULT_DAILY, None)


def reserve(c, run_id, bot_id, profile, now, attempts=1):
    """Reserve the configured maximum. Caller holds BEGIN IMMEDIATE.

    Existing historical usage is included once; missing historical costs or an
    uncertain run fail closed rather than silently pretending they cost zero.
    """
    price = c.execute('SELECT * FROM budget_prices WHERE profile=?', (profile,)).fetchone()
    if not price:
        raise BudgetError(f'Configure prices and token limits for the {profile} profile before running.')
    if type(attempts) is not int or not 1 <= attempts <= 10:
        raise BudgetError('A profile must contain one to ten models.')
    maximum = token_cost_nanos(price['max_prompt_tokens'], price['max_completion_tokens'], price['prompt_usd_per_million'], price['completion_usd_per_million']) * attempts
    if maximum > 9_000_000_000_000_000_000:
        raise BudgetError('Calculated reservation is too large.')
    day, month = period_starts(now)
    for scope, bot_filter in [('account', None), ('bot:' + bot_id, bot_id)]:
        daily, monthly = limits_for(c, scope)
        for start, cap, period in [(day, daily, 'daily'), (month, monthly, 'monthly')]:
            if cap is None:
                continue
            condition = ' AND bot_id=?' if bot_filter else ''
            params = (start, now, bot_filter) if bot_filter else (start, now)
            old = c.execute('''SELECT cost FROM usage WHERE created_at>=? AND created_at<=?''' + condition +
                ' AND NOT EXISTS (SELECT 1 FROM budget_reservations WHERE budget_reservations.usage_id=usage.id)', params).fetchall()
            if any(row['cost'] is None for row in old):
                raise BudgetError(f'{scope} has historical usage without a cost in this {period} period; spending cannot be verified.')
            spent = sum(dollars_to_nanos(row['cost']) for row in old)
            # Outstanding commitments can cross UTC midnight/month-end; count
            # them in every current period until reconciled, never just by start.
            reservation_params = (start, now, bot_filter) if bot_filter else (start, now)
            reservations = c.execute("SELECT * FROM budget_reservations WHERE (status IN ('reserved','uncertain') OR (status='settled' AND settled_at>=? AND settled_at<=?))" + condition, reservation_params).fetchall()
            if any(row['status'] == 'uncertain' for row in reservations):
                raise BudgetError(f'{scope} has an unreconciled run in this {period} period; spending cannot be verified.')
            spent += sum(row['actual_nanos'] if row['status'] == 'settled' else row['reserved_nanos'] for row in reservations)
            if spent + maximum > cap:
                raise BudgetError(f'{scope} {period} budget cap would be exceeded by the maximum possible run cost.')
    c.execute('''INSERT INTO budget_reservations
        (run_id,bot_id,profile,created_at,reserved_nanos,prompt_usd_per_million,completion_usd_per_million,max_prompt_tokens,max_completion_tokens,status)
        VALUES (?,?,?,?,?,?,?,?,?,'reserved')''', (run_id,bot_id,profile,now,maximum,price['prompt_usd_per_million'],price['completion_usd_per_million'],price['max_prompt_tokens'],price['max_completion_tokens']))
    return maximum


def settle(c, run_id, usage_id, prompt_tokens, completion_tokens, now=None):
    row = c.execute('SELECT * FROM budget_reservations WHERE run_id=?', (run_id,)).fetchone()
    if not row or row['status'] != 'reserved':
        raise BudgetError('Reservation is not active.')
    try:
        if prompt_tokens > row['max_prompt_tokens'] or completion_tokens > row['max_completion_tokens']:
            raise BudgetError('Gateway exceeded the configured token limit.')
        cost = token_cost_nanos(prompt_tokens, completion_tokens, row['prompt_usd_per_million'], row['completion_usd_per_million'])
        usage = c.execute('SELECT bot_id,prompt_tokens,completion_tokens FROM usage WHERE id=?', (usage_id,)).fetchone()
        if not usage or usage['bot_id'] != row['bot_id'] or usage['prompt_tokens'] != prompt_tokens or usage['completion_tokens'] != completion_tokens:
            raise BudgetError('Usage record does not match the reservation.')
    except (BudgetError, TypeError):
        c.execute("UPDATE budget_reservations SET status='uncertain' WHERE run_id=?", (run_id,))
        return None
    c.execute("UPDATE usage SET cost=? WHERE id=?", (cost / NANOS_PER_DOLLAR, usage_id))
    c.execute("UPDATE budget_reservations SET status='settled',actual_nanos=?,usage_id=?,settled_at=? WHERE run_id=?", (cost, usage_id, time.time() if now is None else now, run_id))
    return cost


def reconcile_run(c, run_id, amount, note, now=None):
    """Record an owner's externally verified charge; caller holds a write lock.

    A correction is not represented as reported token usage. Its audit record
    makes clear that this amount was supplied by the owner, not the gateway.
    """
    row = c.execute('SELECT * FROM budget_reservations WHERE run_id=?', (run_id,)).fetchone()
    if not row or row['status'] != 'uncertain':
        raise BudgetError('Only an unreconciled run can be corrected.')
    clean_note = note.strip() if isinstance(note, str) else ''
    if not clean_note or len(clean_note) > 500:
        raise BudgetError('Provide a short source for the verified charge.')
    cost = dollars_to_nanos(amount)
    timestamp = time.time() if now is None else now
    c.execute('INSERT INTO budget_reconciliations (run_id,cost_nanos,note,created_at) VALUES (?,?,?,?)', (run_id,cost,clean_note,timestamp))
    c.execute("UPDATE budget_reservations SET status='settled', actual_nanos=?, settled_at=? WHERE run_id=?", (cost,timestamp,run_id))
    return cost


def reconcile_usage(c, usage_id, amount, note, now=None):
    """Record an owner's externally verified historical charge."""
    row = c.execute('SELECT cost FROM usage WHERE id=?', (usage_id,)).fetchone()
    if not row or row['cost'] is not None:
        raise BudgetError('Only historical usage without a cost can be corrected.')
    clean_note = note.strip() if isinstance(note, str) else ''
    if not clean_note or len(clean_note) > 500:
        raise BudgetError('Provide a short source for the verified charge.')
    cost = dollars_to_nanos(amount)
    timestamp = time.time() if now is None else now
    c.execute('INSERT INTO budget_reconciliations (usage_id,cost_nanos,note,created_at) VALUES (?,?,?,?)', (usage_id,cost,clean_note,timestamp))
    c.execute('UPDATE usage SET cost=? WHERE id=?', (cost / NANOS_PER_DOLLAR, usage_id))
    return cost
