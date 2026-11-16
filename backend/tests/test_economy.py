"""Phase 3: token wallets, resource policy, Economy Mode, alerts, delegation caps.

Every model response is mocked; no network or paid provider is ever contacted.
"""
import asyncio
import json
import time
import pytest
from fastapi.testclient import TestClient
import app as service
from funkbot import budget, economy
from test_app import FakeClient, setup, configure_budget
from test_budget_chat import answer


def price(c, profile, prompt, completion, max_prompt=8192, max_completion=512):
    assert c.put(f'/api/budget/prices/{profile}', json={'prompt': prompt, 'completion': completion, 'max_prompt_tokens': max_prompt, 'max_completion_tokens': max_completion}).status_code == 200


def finish(c, run):
    assert '"type": "done"' in c.get(f'/api/jobs/{run}/events').text


def attribution(run):
    with service.db() as db:
        return dict(db.execute('SELECT * FROM run_attribution WHERE run_id=?', (run,)).fetchone())


def give_career(bot, tier):
    with service.db() as db:
        db.execute('INSERT INTO bot_careers VALUES (?,?,?,?,?,?,?,?,?)', (bot, 'p', 1, '{}', 'mid', 'Ops', tier, None, time.time()))


def test_endpoints_need_auth_and_validate_input(monkeypatch):
    with TestClient(service.app) as c:
        assert c.get('/api/economy').status_code == 401 and c.get('/api/budget/usage').status_code == 401
        assert c.put('/api/economy', json={}).status_code == 401
        assert c.put('/api/economy/model-flags', json={'gateway': 'custom', 'model': 'm', 'kind': 'free'}).status_code == 401
        assert c.delete('/api/economy/model-flags?gateway=custom&model=m').status_code == 401
        setup(c)
        body = c.get('/api/economy').json()
        assert body['economy']['enabled'] is False and body['fallback']['enabled'] is False
        assert body['tier_policy'] == {'LIGHT': 'cheap-bulk', 'STANDARD': 'fast', 'ADVANCED': 'smart', 'RESEARCH': 'thinker'}
        assert body['alerts']['thresholds'] == [50, 80, 100]
        assert c.put('/api/economy', json={'tier_policy': {'LIGHT': 'nope', 'STANDARD': 'fast', 'ADVANCED': 'smart', 'RESEARCH': 'thinker'}}).status_code == 400
        assert c.put('/api/economy', json={'alerts': {'enabled': True, 'thresholds': [0, 50]}}).status_code == 400
        assert c.put('/api/economy', json={'alerts': {'enabled': True, 'thresholds': [90, 10, 90]}}).status_code == 200
        assert c.get('/api/economy').json()['alerts']['thresholds'] == [10, 90]
        assert c.get('/api/budget/usage?group=nonsense').status_code == 400
        # OmniRoute is a router: never assumed free.
        assert c.put('/api/economy/model-flags', json={'gateway': 'omniroute', 'model': 'auto', 'kind': 'free'}).status_code == 400
        assert c.put('/api/economy/model-flags', json={'gateway': 'custom', 'model': 'llama3', 'kind': 'local'}).status_code == 200
        assert c.delete('/api/economy/model-flags?gateway=custom&model=llama3').status_code == 200
        assert c.delete('/api/economy/model-flags?gateway=custom&model=llama3').status_code == 404


def test_economy_mode_lowers_the_reserved_profile_and_never_raises_it(monkeypatch):
    FakeClient.responses = [answer(), answer(), answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as c:
        setup(c); configure_budget(c); price(c, 'fast', '0.1', '0.2')
        bot = c.post('/api/bots', json={'name': 'Scout', 'profile': 'smart'}).json()['id']
        run = c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id']; finish(c, run)
        assert attribution(run)['effective_profile'] == 'smart' and attribution(run)['adjustment'] is None
        assert c.put('/api/economy', json={'economy': {'enabled': True, 'ceiling_tier': 'STANDARD', 'prefer_free': True}}).status_code == 200
        run = c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id']; finish(c, run)
        a = attribution(run)
        assert (a['requested_profile'], a['effective_profile'], a['adjustment']) == ('smart', 'fast', 'economy:smart->fast')
        with service.db() as db:
            assert db.execute('SELECT profile FROM budget_reservations WHERE run_id=?', (run,)).fetchone()['profile'] == 'fast'
        # A Bot already cheaper than the ceiling is not moved up.
        assert c.put('/api/economy', json={'tier_policy': {'LIGHT': 'cheap-bulk', 'STANDARD': 'smart', 'ADVANCED': 'smart', 'RESEARCH': 'thinker'}}).status_code == 200
        run = c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi', 'profile': 'fast'}).json()['job_id']; finish(c, run)
        assert attribution(run)['effective_profile'] == 'fast'


def test_unpriced_ceiling_is_never_treated_as_cheaper(monkeypatch):
    FakeClient.responses = [answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as c:
        setup(c); configure_budget(c)  # only 'smart' is priced
        c.put('/api/economy', json={'economy': {'enabled': True, 'ceiling_tier': 'STANDARD', 'prefer_free': True}})
        bot = c.post('/api/bots', json={'name': 'Scout', 'profile': 'smart'}).json()['id']
        run = c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id']; finish(c, run)
        assert attribution(run)['effective_profile'] == 'smart'


def test_career_tier_applies_only_to_career_bots_and_explicit_choice_wins(monkeypatch):
    FakeClient.responses = [answer(), answer(), answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as c:
        setup(c); configure_budget(c); price(c, 'cheap-bulk', '0.05', '0.1')
        plain = c.post('/api/bots', json={'name': 'Plain', 'profile': 'smart'}).json()['id']
        hired = c.post('/api/bots', json={'name': 'Hired', 'profile': 'smart'}).json()['id']
        give_career(hired, 'LIGHT')
        a = attribution(c.post(f'/api/bots/{plain}/chat', json={'content': 'Hi'}).json()['job_id'])
        assert a['effective_profile'] == 'smart' and a['tier'] is None
        run = c.post(f'/api/bots/{hired}/chat', json={'content': 'Hi'}).json()['job_id']; finish(c, run)
        a = attribution(run)
        assert (a['tier'], a['effective_profile'], a['adjustment']) == ('LIGHT', 'cheap-bulk', 'tier:LIGHT->cheap-bulk')
        run = c.post(f'/api/bots/{hired}/chat', json={'content': 'Hi', 'profile': 'smart'}).json()['job_id']; finish(c, run)
        assert attribution(run)['effective_profile'] == 'smart'


def test_vision_profile_is_never_moved_by_policy():
    with TestClient(service.app) as c:
        setup(c); price(c, 'vision', '1', '2'); price(c, 'fast', '0.1', '0.2')
        c.put('/api/economy', json={'economy': {'enabled': True, 'ceiling_tier': 'STANDARD', 'prefer_free': True}})
        with service.db() as db:
            db.execute('INSERT INTO bots VALUES (?,?,?,?,?,?,?,?)', ('v1', 'V', 'Helper', 'x', 'mint', 'round', 'vision', 1))
        give_career('v1', 'LIGHT')
        with service.db() as db:
            assert economy.choose_profile(db, {'id': 'v1'}, 'vision', False)[0] == 'vision'
            assert economy.cheaper_profiles(db, 'vision') == []


def test_budget_fallback_moves_only_to_a_cheaper_priced_profile_and_records_it(monkeypatch):
    FakeClient.responses = [answer(), answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as c:
        setup(c); configure_budget(c); price(c, 'fast', '0.1', '0.2')
        bot = c.post('/api/bots', json={'name': 'Scout', 'profile': 'smart'}).json()['id']
        # smart reserves $0.009216, fast reserves $0.0009216. Cap sits between.
        assert c.put('/api/budget/limits/account', json={'daily': '0.005', 'monthly': None}).status_code == 200
        assert c.get('/api/economy').json()['fallback']['enabled'] is False  # opt-in
        refused = c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'})
        assert refused.status_code == 402 and 'daily budget cap' in refused.text
        assert c.put('/api/economy', json={'fallback': {'enabled': True}}).status_code == 200
        run = c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id']; finish(c, run)
        a = attribution(run)
        assert (a['requested_profile'], a['effective_profile']) == ('smart', 'fast') and 'budget_fallback:smart->fast' in a['adjustment']
        assert c.put('/api/economy', json={'fallback': {'enabled': False}}).status_code == 200
        blocked = c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'})
        assert blocked.status_code == 402 and 'daily budget cap' in blocked.text
        assert len(FakeClient.responses) == 1
        # A cap below even the cheapest profile still blocks, with the original error.
        c.put('/api/economy', json={'fallback': {'enabled': True}})
        c.put('/api/budget/limits/account', json={'daily': '0.0001', 'monthly': None})
        assert c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).status_code == 402


def test_owner_attested_free_model_settles_at_zero_and_is_reported(monkeypatch):
    FakeClient.responses = [answer(), answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as c:
        setup(c); configure_budget(c)
        bot = c.post('/api/bots', json={'name': 'Scout'}).json()['id']
        c.put('/api/settings/profiles', json={**c.get('/api/settings').json()['profiles'], 'smart': [{'gateway': 'custom', 'model': 'llama3'}]})
        c.put('/api/settings/gateways/custom', json={'url': 'https://models.example.test/v1', 'key': ''})
        run = c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id']; finish(c, run)
        with service.db() as db:
            assert db.execute('SELECT actual_nanos FROM budget_reservations WHERE run_id=?', (run,)).fetchone()['actual_nanos'] == 300000
        c.put('/api/economy/model-flags', json={'gateway': 'custom', 'model': 'llama3', 'kind': 'local', 'note': 'Ollama on this PC'})
        run = c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id']; finish(c, run)
        with service.db() as db:
            assert db.execute('SELECT actual_nanos,status FROM budget_reservations WHERE run_id=?', (run,)).fetchone()['actual_nanos'] == 0
            assert db.execute('SELECT cost FROM usage ORDER BY id DESC').fetchone()['cost'] == 0
            assert db.execute('SELECT basis FROM usage_flags').fetchone()['basis'] == 'owner_attested_free'
        rows = {r['key']: r for r in c.get('/api/budget/usage?group=model').json()['rows']}
        assert rows['llama3']['rounds'] == 2 and rows['llama3']['owner_free_rounds'] == 1 and rows['llama3']['prompt_tokens'] == 400


def test_usage_report_groups_tokens_and_dollars_by_every_dimension(monkeypatch):
    FakeClient.responses = [answer(), answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as c:
        setup(c); configure_budget(c)
        one = c.post('/api/bots', json={'name': 'One'}).json()['id']; two = c.post('/api/bots', json={'name': 'Two'}).json()['id']
        give_career(two, 'ADVANCED')
        for bot in (one, two): finish(c, c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id'])
        for group, expected in (('bot', {one, two}), ('provider', {'openrouter'}), ('profile', {'smart'}), ('tier', {None, 'ADVANCED'})):
            rows = c.get(f'/api/budget/usage?group={group}').json()['rows']
            assert {r['key'] for r in rows} == expected, group
            assert sum(r['prompt_tokens'] for r in rows) == 400 and sum(r['completion_tokens'] for r in rows) == 100
            assert sum(float(r['usd']) for r in rows) == pytest.approx(0.0006)
        mission_rows = c.get('/api/budget/usage?group=mission').json()['rows']
        assert mission_rows[0]['key'] is None and mission_rows[0]['rounds'] == 2
        # The report and the enforcement code share one spend calculation.
        with service.db() as db:
            assert budget.spent_nanos(db, 0, time.time() + 1) == 600000


@pytest.mark.asyncio
async def test_usage_attributes_mission_and_project(monkeypatch):
    FakeClient.responses = [answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    now = time.time()
    with service.db() as db:
        db.execute('INSERT INTO bots VALUES (?,?,?,?,?,?,?,?)', ('b1', 'Scout', 'Helper', 'x', 'mint', 'round', 'smart', 1))
        db.execute('INSERT INTO missions VALUES (?,?,?,?,?,?,?,?,?)', ('m1', 'Mission', 'Do it', None, 'queued', None, None, now, now))
        db.execute('INSERT INTO mission_assignees VALUES (?,?,?)', ('m1', 0, 'b1'))
        db.execute('INSERT INTO projects VALUES (?,?,?,?,?,?)', ('p1', 'Project', '', None, now, now))
        db.execute('INSERT INTO project_missions VALUES (?,?,?)', ('p1', 'm1', now))
        db.execute("INSERT INTO budget_prices VALUES ('smart','1','2',8192,512)")
    job = (await service.start_chat('b1', service.ChatIn(content='Go'), 'm1'))['job_id']
    await service.jobs[job]['task']
    with service.db() as db:
        a = dict(db.execute('SELECT * FROM run_attribution WHERE run_id=?', (job,)).fetchone())
        assert (a['mission_id'], a['project_id'], a['delegated']) == ('m1', 'p1', 0)
        by_project = economy.usage_report(db, 'project', 0)
        assert by_project[0]['key'] == 'p1' and by_project[0]['prompt_tokens'] == 200
        assert economy.usage_report(db, 'mission', 0)[0]['key'] == 'm1'


def test_alerts_fire_once_per_threshold_and_period_through_the_inbox(monkeypatch):
    FakeClient.responses = [answer(), answer(), answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as c:
        setup(c); configure_budget(c)
        bot = c.post('/api/bots', json={'name': 'Scout'}).json()['id']
        assert c.put('/api/budget/limits/account', json={'daily': '0.02', 'monthly': None}).status_code == 200
        assert c.put('/api/economy', json={'alerts': {'enabled': True, 'thresholds': [1, 3, 100]}}).status_code == 200
        finish(c, c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id'])  # $0.0003 = 1.5%
        with service.db() as db:
            assert [r['threshold'] for r in db.execute("SELECT threshold FROM budget_alerts WHERE scope='account'")] == [1]
            notices = db.execute("SELECT title FROM inbox_notices WHERE kind='budget'").fetchall()
            assert len(notices) == 1 and '1%' in notices[0]['title']
        finish(c, c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id'])  # 3.0% reaches the 3% mark
        with service.db() as db:
            assert sorted(r['threshold'] for r in db.execute("SELECT threshold FROM budget_alerts WHERE scope='account'")) == [1, 3]
        c.put('/api/economy', json={'alerts': {'enabled': False, 'thresholds': [1]}})
        finish(c, c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id'])
        with service.db() as db:
            assert db.execute("SELECT COUNT(*) FROM inbox_notices WHERE kind='budget'").fetchone()[0] == 2


def seed_delegation(origin_profile='smart'):
    now = time.time()
    with service.db() as db:
        for bot in ('a', 'b', 'c'):
            db.execute('INSERT INTO bots VALUES (?,?,?,?,?,?,?,?)', (bot, bot.upper(), 'Helper', 'x', 'mint', 'round', 'smart', 1))
        db.execute('INSERT INTO runs VALUES (?,?,?,?,?)', ('run-a', 'a', 'running', now, now))
        economy.record_attribution(db, 'run-a', 'a', None, None, origin_profile, origin_profile, None, None, now)
        for mission, receiver in (('m-b', 'b'), ('m-c', 'c')):
            db.execute('INSERT INTO missions VALUES (?,?,?,?,?,?,?,?,?)', (mission, 'Handoff', 'Do it', None, 'queued', None, None, now, now))
            db.execute('INSERT INTO mission_assignees VALUES (?,?,?)', (mission, 0, receiver))
            economy.record_delegation(db, mission, 'run-a', 'a', now)
        db.execute("INSERT INTO budget_prices VALUES ('smart','1','2',8192,512)")
        db.execute("INSERT INTO budget_prices VALUES ('fast','0.1','0.2',8192,512)")


@pytest.mark.asyncio
async def test_delegated_work_counts_against_the_delegating_bots_cap(monkeypatch):
    FakeClient.responses = [answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    seed_delegation()
    with service.db() as db:
        # Receivers are uncapped. The default smart profile has two models, so one run reserves $0.018432.
        # The delegator's $0.0186 cap fits one such run, never two (reserved, or settled at $0.0003).
        db.execute("INSERT INTO budget_limits VALUES ('bot:a',18600000,NULL)")
    first = (await service.start_chat('b', service.ChatIn(content='Go'), 'm-b'))['job_id']
    with service.db() as db:
        a = dict(db.execute('SELECT * FROM run_attribution WHERE run_id=?', (first,)).fetchone())
        assert (a['delegated'], a['origin_bot_id']) == (1, 'a'), a
        assert a['effective_profile'] == 'smart', a
    service.set_config('budget_fallback', json.dumps({'enabled': False}))
    with pytest.raises(service.HTTPException) as refused:
        await service.start_chat('c', service.ChatIn(content='Go'), 'm-c')
    assert refused.value.status_code == 402 and 'delegating Bot' in refused.value.detail
    await service.jobs[first]['task']
    with service.db() as db:
        now = time.time()
        assert budget.delegated_nanos(db, 'a', 0, now) == 300000  # settled actual, not the reservation
        assert budget.spent_nanos(db, 0, now + 1, 'a') == 0  # the origin's own spend is not double counted


@pytest.mark.asyncio
async def test_delegated_run_cannot_use_a_costlier_profile_than_its_delegator(monkeypatch):
    FakeClient.responses = [answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    seed_delegation(origin_profile='fast')
    job = (await service.start_chat('b', service.ChatIn(content='Go'), 'm-b'))['job_id']
    await service.jobs[job]['task']
    with service.db() as db:
        a = dict(db.execute('SELECT * FROM run_attribution WHERE run_id=?', (job,)).fetchone())
        assert (a['requested_profile'], a['effective_profile'], a['adjustment']) == ('smart', 'fast', 'delegation:smart->fast')


def test_alert_and_attribution_tables_survive_bot_deletion_and_backup_shape():
    with TestClient(service.app) as c:
        setup(c)
        with service.db() as db:
            names = {r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {'run_attribution', 'delegation_origins', 'model_flags', 'usage_flags', 'budget_alerts'} <= names


def test_tier_never_moves_a_bot_to_an_unpriced_or_costlier_profile(monkeypatch):
    FakeClient.responses = [answer(), answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as c:
        setup(c); configure_budget(c)  # only smart is priced
        light = c.post('/api/bots', json={'name': 'Light', 'profile': 'smart'}).json()['id']
        give_career(light, 'LIGHT')
        run = c.post(f'/api/bots/{light}/chat', json={'content': 'Hi'}).json()['job_id']; finish(c, run)
        a = attribution(run)
        assert a['effective_profile'] == 'smart' and 'kept smart' in a['adjustment']
        # A costlier tier profile is not applied to a Bot already on a cheaper one.
        price(c, 'fast', '0.1', '0.2'); price(c, 'thinker', '5', '10')
        research = c.post('/api/bots', json={'name': 'Research', 'profile': 'fast'}).json()['id']
        give_career(research, 'RESEARCH')
        run = c.post(f'/api/bots/{research}/chat', json={'content': 'Hi'}).json()['job_id']; finish(c, run)
        assert attribution(run)['effective_profile'] == 'fast'


def test_lab_runs_are_never_relabelled_by_economy_or_fallback(monkeypatch):
    FakeClient.responses = [answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as c:
        setup(c); configure_budget(c); price(c, 'fast', '0.1', '0.2')
        c.put('/api/economy', json={'economy': {'enabled': True, 'ceiling_tier': 'STANDARD', 'prefer_free': True}, 'fallback': {'enabled': True}})
        c.put('/api/budget/limits/account', json={'daily': '0.005', 'monthly': None})
        bot = c.post('/api/bots', json={'name': 'Scout'}).json()['id']
        eid = c.post('/api/lab', json={'bot_id': bot, 'prompt': 'Q', 'system_prompt': 'P', 'profiles': ['smart']}).json()['id']
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            item = c.get('/api/lab/' + eid).json()
            if item['status'] in ('done', 'failed'): break
            time.sleep(.02)
        # smart does not fit the cap and the Lab asked for smart: it must fail, not quietly run on fast.
        assert item['status'] == 'failed' and len(FakeClient.responses) == 1
        with service.db() as db:
            assert db.execute("SELECT COUNT(*) FROM budget_reservations WHERE profile='fast'").fetchone()[0] == 0
