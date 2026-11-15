import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

import app as service
from funkbot.budget import BudgetError, dollars_to_nanos, limit_to_nanos, period_starts, reserve, settle, token_cost_nanos


def price(profile='smart', prompt='1', completion='2', max_prompt=1000, max_completion=500):
    with service.db() as c:
        c.execute('INSERT INTO budget_prices VALUES (?,?,?,?,?)', (profile,prompt,completion,max_prompt,max_completion))


def reservation(run, bot='one', now=None):
    with service.db() as c:
        c.execute('BEGIN IMMEDIATE')
        return reserve(c,run,bot,'smart',now or time.time())


def test_decimal_prices_and_utc_boundaries():
    assert token_cost_nanos(1,2,'0.1','0.2') == 500
    assert dollars_to_nanos('0.0000000001') == 1
    assert limit_to_nanos('0.0000000001') == 0
    for value in ('NaN','Infinity','-1','1000001'):
        with pytest.raises(BudgetError): dollars_to_nanos(value)
    for usage in [(-1,0),(None,1),(True,1)]:
        with pytest.raises(BudgetError): token_cost_nanos(*usage,'1','1')
    day,month = period_starts(datetime(2026,11,14,23,30,tzinfo=timezone.utc).timestamp())
    assert datetime.fromtimestamp(day,timezone.utc).isoformat() == '2026-11-14T00:00:00+00:00'
    assert datetime.fromtimestamp(month,timezone.utc).isoformat() == '2026-11-01T00:00:00+00:00'


def test_missing_price_and_caps_refuse_before_reservation():
    with pytest.raises(BudgetError,match='Configure prices'): reservation('a')
    price()
    with service.db() as c:
        c.execute("INSERT INTO budget_limits VALUES ('account',1000000,NULL)")
    with pytest.raises(BudgetError,match='account daily'): reservation('a')
    with service.db() as c:
        assert c.execute('SELECT count(*) FROM budget_reservations').fetchone()[0] == 0
        c.execute("UPDATE budget_limits SET daily_nanos=5000000000,monthly_nanos=1000000 WHERE scope='account'")
    with pytest.raises(BudgetError,match='account monthly'): reservation('b')
    with service.db() as c:
        c.execute("UPDATE budget_limits SET monthly_nanos=NULL WHERE scope='account'")
        c.execute("INSERT INTO budget_limits VALUES ('bot:one',1000000,NULL)")
    with pytest.raises(BudgetError,match='bot:one daily'): reservation('c')
    assert reservation('d','other') == 2000000


def test_settlement_uses_snapshot_and_unknown_usage_fails_closed():
    price()
    assert reservation('one') == 2_000_000
    with service.db() as c:
        c.execute("INSERT INTO bots VALUES ('one','One','Editor','Instructions','mint','round','smart',1)")
        c.execute("UPDATE budget_prices SET prompt_usd_per_million='999'")
        c.execute("INSERT INTO usage (bot_id,gateway,model,prompt_tokens,completion_tokens,cost,created_at) VALUES ('one','gateway','model',100,50,0.0002,?)", (time.time(),))
        usage_id=c.execute('SELECT id FROM usage').fetchone()['id']
        assert settle(c,'one',usage_id,100,50) == 200_000
    with service.db() as c:
        c.execute("UPDATE budget_prices SET prompt_usd_per_million='1'")
        c.execute("INSERT INTO budget_limits VALUES ('account',2200000,NULL)")
    assert reservation('two') == 2_000_000  # settled usage is counted once, not twice
    with service.db() as c:
        assert settle(c,'two',None,None,10) is None
    with pytest.raises(BudgetError, match='unreconciled'): reservation('three')


def test_unknown_historical_cost_is_not_treated_as_zero():
    price()
    with service.db() as c:
        c.execute("INSERT INTO bots VALUES ('old','Old','Editor','Instructions','mint','round','smart',1)")
        c.execute("INSERT INTO usage (bot_id,gateway,model,prompt_tokens,completion_tokens,cost,created_at) VALUES ('old','gateway','model',1,2,NULL,?)", (time.time(),))
    with pytest.raises(BudgetError,match='historical usage without a cost'): reservation('a')


def test_parallel_reservations_cannot_oversubscribe_account():
    price()
    with service.db() as c:
        c.execute("INSERT INTO budget_limits VALUES ('account',2000000,NULL)")
    def attempt(i):
        try: return reservation(f'r{i}',f'b{i}')
        except BudgetError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,range(2)))
    assert sorted(results,key=lambda x:x or 0) == [None,2000000]


def test_reservation_crossing_midnight_still_counts():
    price()
    before = datetime(2026,11,30,23,59,tzinfo=timezone.utc).timestamp()
    after = datetime(2026,12,1,0,1,tzinfo=timezone.utc).timestamp()
    with service.db() as c:
        c.execute("INSERT INTO budget_limits VALUES ('account',2000000,2000000)")
    reservation('before',now=before)
    with pytest.raises(BudgetError,match='daily'): reservation('after',bot='other',now=after)


def test_reserves_for_every_possible_fallback_attempt():
    price()
    with service.db() as c:
        c.execute("INSERT INTO budget_limits VALUES ('account',5000000,NULL)")
    with service.db() as c:
        c.execute('BEGIN IMMEDIATE')
        assert reserve(c,'two','one','smart',time.time(),attempts=2) == 4_000_000
    with service.db() as c:
        c.execute('BEGIN IMMEDIATE')
        with pytest.raises(BudgetError,match='daily'): reserve(c,'three','two','smart',time.time(),attempts=1)
    with service.db() as c:
        with pytest.raises(BudgetError,match='one to ten'): reserve(c,'zero','two','smart',time.time(),attempts=0)


def test_gateway_exceeding_token_bound_is_uncertain():
    price()
    reservation('exceeded')
    with service.db() as c:
        assert settle(c,'exceeded',None,1001,100) is None
        assert c.execute("SELECT status FROM budget_reservations WHERE run_id='exceeded'").fetchone()['status'] == 'uncertain'
    with pytest.raises(BudgetError,match='unreconciled'): reservation('next')


def test_unsettled_cost_remains_reserved_after_next_month():
    price()
    before = datetime(2026,11,30,23,59,tzinfo=timezone.utc).timestamp()
    after = datetime(2026,12,1,0,1,tzinfo=timezone.utc).timestamp()
    reservation('unknown',now=before)
    with service.db() as c:
        assert settle(c,'unknown',None,None,None) is None
    with pytest.raises(BudgetError,match='unreconciled'): reservation('after',bot='different',now=after)


def test_uncertain_run_reconciliation_is_explicit_audited_and_never_double_applied():
    from funkbot.budget import reconcile_run
    price()
    reservation('unknown')
    with service.db() as c:
        assert settle(c,'unknown',None,None,None) is None
        with pytest.raises(BudgetError,match='source'): reconcile_run(c,'unknown','0.12','')
        assert reconcile_run(c,'unknown','0.12','Verified on gateway invoice') == 120_000_000
        assert c.execute("SELECT note FROM budget_reconciliations WHERE run_id='unknown'").fetchone()['note'] == 'Verified on gateway invoice'
        with pytest.raises(BudgetError,match='Only an unreconciled'): reconcile_run(c,'unknown','0','Again')
    assert reservation('next') == 2_000_000


def test_historical_missing_cost_requires_audited_owner_confirmation():
    from funkbot.budget import reconcile_usage
    price()
    with service.db() as c:
        c.execute("INSERT INTO bots VALUES ('old','Old','Editor','Instructions','mint','round','smart',1)")
        c.execute("INSERT INTO usage (bot_id,gateway,model,prompt_tokens,completion_tokens,cost,created_at) VALUES ('old','gateway','model',1,2,NULL,?)", (time.time(),))
        usage_id=c.execute('SELECT id FROM usage').fetchone()['id']
    with pytest.raises(BudgetError,match='historical usage'): reservation('blocked')
    with service.db() as c:
        assert reconcile_usage(c,usage_id,'0.03','Verified on provider invoice') == 30_000_000
        with pytest.raises(BudgetError,match='Only historical'): reconcile_usage(c,usage_id,'0','Again')
        assert c.execute('SELECT note FROM budget_reconciliations WHERE usage_id=?',(usage_id,)).fetchone()['note'] == 'Verified on provider invoice'
    assert reservation('allowed') == 2_000_000


def test_followup_model_round_requires_a_settled_previous_round_and_obeys_caps():
    from funkbot.budget import reserve_followup
    price()
    with service.db() as c:
        c.execute("INSERT INTO bots VALUES ('one','One','Editor','Instructions','mint','round','smart',1)")
        c.execute("INSERT INTO runs VALUES ('parent','one','running',1,1)")
        c.execute("INSERT INTO budget_limits VALUES ('account',2100000,NULL)")
        reserve(c,'parent','one','smart',time.time())
        with pytest.raises(BudgetError,match='previous model request'): reserve_followup(c,'parent','one','smart',time.time())
        c.execute("INSERT INTO usage (bot_id,prompt_tokens,completion_tokens,created_at) VALUES ('one',100,0,?)",(time.time(),))
        usage=c.execute('SELECT id FROM usage').fetchone()['id']
        assert settle(c,'parent',usage,100,0)==100000
        followup,amount=reserve_followup(c,'parent','one','smart',time.time())
        assert amount==2000000 and followup!='parent'
        assert c.execute('SELECT parent_run_id FROM budget_reservations WHERE run_id=?',(followup,)).fetchone()['parent_run_id']=='parent'
        with pytest.raises(BudgetError,match='previous model request'): reserve_followup(c,'parent','one','smart',time.time())
        with pytest.raises(BudgetError,match='no longer active'): reserve_followup(c,'parent','other','smart',time.time())


def test_followup_rejects_unbudgeted_runs_different_profile_and_overspend():
    from funkbot.budget import reserve_followup
    price()
    with service.db() as c:
        c.execute("INSERT INTO bots VALUES ('one','One','Editor','Instructions','mint','round','smart',1)")
        c.execute("INSERT INTO runs VALUES ('parent','one','running',1,1)")
        with pytest.raises(BudgetError,match='no prior budget'): reserve_followup(c,'parent','one','smart',time.time())
        reserve(c,'parent','one','smart',time.time())
        c.execute("INSERT INTO usage (bot_id,prompt_tokens,completion_tokens,created_at) VALUES ('one',100,0,?)",(time.time(),))
        usage=c.execute('SELECT id FROM usage').fetchone()['id'];settle(c,'parent',usage,100,0)
        with pytest.raises(BudgetError,match='original run profile'): reserve_followup(c,'parent','one','fast',time.time())
        c.execute("INSERT INTO budget_limits VALUES ('account',2000000,NULL)")
        with pytest.raises(BudgetError,match='daily budget cap'): reserve_followup(c,'parent','one','smart',time.time())
