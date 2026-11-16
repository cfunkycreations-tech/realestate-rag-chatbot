import json
import time
from fastapi.testclient import TestClient
import app as service
from test_app import FakeClient, FakeStream, setup, configure_budget


def answer(usage=True):
    parts=['data: '+json.dumps({'choices':[{'delta':{'content':'The real answer.'}}]})]
    if usage: parts.append('data: '+json.dumps({'choices':[],'usage':{'prompt_tokens':200,'completion_tokens':50}}))
    parts.append('data: [DONE]')
    return FakeStream(200,parts)


def test_budget_refuses_before_gateway_request_or_message(monkeypatch):
    FakeClient.responses=[answer()]
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        assert c.get('/api/budget').status_code == 401
        setup(c)
        bot=c.post('/api/bots',json={'name':'Scout','title':'Editor'}).json()['id']
        assert c.get('/api/budget').json()['account']['daily']=='5'
        missing=c.post(f'/api/bots/{bot}/chat',json={'content':'Hi'})
        assert missing.status_code==402 and 'Configure prices' in missing.text
        configure_budget(c)
        assert c.put('/api/budget/limits/account',json={'daily':'0.01','monthly':None}).status_code==200
        blocked=c.post(f'/api/bots/{bot}/chat',json={'content':'Hi'})
        assert blocked.status_code==402 and 'daily budget cap' in blocked.text
        assert c.get(f'/api/bots/{bot}/messages').json()==[]
        assert len(FakeClient.responses)==1
        assert c.put('/api/budget/limits/account',json={'daily':'5','monthly':'0.01'}).status_code==200
        assert 'monthly budget cap' in c.post(f'/api/bots/{bot}/chat',json={'content':'Hi'}).text
        assert c.put('/api/budget/limits/account',json={'daily':'5','monthly':None}).status_code==200
        assert c.put(f'/api/budget/limits/bot:{bot}',json={'daily':'0','monthly':None}).status_code==200
        assert 'daily budget cap' in c.post(f'/api/bots/{bot}/chat',json={'content':'Hi'}).text
        assert len(FakeClient.responses)==1


def test_usage_prices_settle_and_unknown_charge_blocks_until_verified(monkeypatch):
    FakeClient.responses=[answer(),answer(False),answer()]
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Hi'}).json()['job_id']
        assert '"type": "done"' in c.get(f'/api/jobs/{run}/events').text
        with service.db() as db:
            u=db.execute('SELECT prompt_tokens,completion_tokens,cost FROM usage').fetchone()
            assert u['prompt_tokens']==200 and u['completion_tokens']==50 and u['cost']==0.0003
            assert db.execute('SELECT status FROM budget_reservations WHERE run_id=?',(run,)).fetchone()['status']=='settled'
        run2=c.post(f'/api/bots/{bot}/chat',json={'content':'Next'}).json()['job_id']
        assert 'did not report token usage' in c.get(f'/api/jobs/{run2}/events').text
        assert c.post(f'/api/bots/{bot}/chat',json={'content':'Next'}).status_code==402
        assert c.post(f'/api/budget/reconcile/run/{run2}',json={'amount':'0.001','source':'Verified invoice'}).status_code==200
        run3=c.post(f'/api/bots/{bot}/chat',json={'content':'Next'}).json()['job_id']
        assert '"type": "done"' in c.get(f'/api/jobs/{run3}/events').text
        with service.db() as db:
            assert db.execute('SELECT note FROM budget_reconciliations WHERE run_id=?',(run2,)).fetchone()['note']=='Verified invoice'


def test_failed_and_interrupted_runs_hold_uncertain_reservations(monkeypatch):
    FakeClient.responses=[FakeStream(401,[])]
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Hi'}).json()['job_id']
        assert 'charges are unknown' in c.get(f'/api/jobs/{run}/events').text
        assert c.post(f'/api/bots/{bot}/chat',json={'content':'Again'}).status_code==402
        with service.db() as db:
            db.execute("INSERT INTO runs VALUES ('interrupted',?,'running',?,?)",(bot,time.time(),time.time()))
            db.execute("INSERT INTO budget_reservations (run_id,bot_id,profile,created_at,reserved_nanos,prompt_usd_per_million,completion_usd_per_million,max_prompt_tokens,max_completion_tokens,status) VALUES ('interrupted',?,'smart',?,1,'1','1',100,100,'reserved')",(bot,time.time()))
    service.mark_interrupted_runs()
    with service.db() as db:
        assert db.execute("SELECT status FROM budget_reservations WHERE run_id='interrupted'").fetchone()['status']=='uncertain'


def test_invalid_budget_inputs_and_token_bound():
    with TestClient(service.app) as c:
        setup(c)
        bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        assert c.put('/api/budget/limits/account',json={'daily':'NaN','monthly':None}).status_code==400
        assert c.put('/api/budget/prices/smart',json={'prompt':'-1','completion':'2','max_prompt_tokens':8192,'max_completion_tokens':512}).status_code==400
        assert c.put('/api/budget/prices/smart',json={'prompt':'1','completion':'2','max_prompt_tokens':1,'max_completion_tokens':512}).status_code==200
        assert c.post(f'/api/bots/{bot}/chat',json={'content':'Hi'}).status_code==400


def test_configured_output_bound_is_sent_to_gateway(monkeypatch):
    captured=[]
    class RecordingClient(FakeClient):
        def stream(self, method, url, **kwargs):
            captured.append(kwargs['json'])
            return super().stream(method,url,**kwargs)
    FakeClient.responses=[answer()]
    monkeypatch.setattr(service.httpx,'AsyncClient',RecordingClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Hi'}).json()['job_id']
        c.get(f'/api/jobs/{run}/events')
        assert captured[0]['max_tokens']==512
        assert captured[0]['stream_options']=={'include_usage':True}


def test_fallback_after_unknown_failure_remains_unreconciled(monkeypatch):
    FakeClient.responses=[FakeStream(429,[]),answer()]
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Hi'}).json()['job_id']
        assert 'could not be verified' in c.get(f'/api/jobs/{run}/events').text
        assert c.post(f'/api/bots/{bot}/chat',json={'content':'Again'}).status_code==402
        assert len(c.get('/api/budget').json()['unreconciled']) == 1
        assert c.post(f'/api/budget/reconcile/run/{run}',json={'amount':'0.0003','source':'Provider billing'}).status_code==200
        assert c.get('/api/budget').json()['unknown_usage']==[]
        assert c.get('/api/settings').json()['usage']['unknown']==0
        assert c.get('/api/settings').json()['usage']['cost']==0.0003


def test_deleting_bot_preserves_budget_usage_and_saved_key(monkeypatch):
    from test_vault import archive, png
    FakeClient.responses=[answer()]
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        c.put('/api/settings/gateways/openrouter',json={'url':'https://gateway.test/v1','key':'disposable-secret'})
        assert c.post('/api/vault/import',files={'file':('vault.zip',archive([('sprite.png',png('Sprite'))]),'application/zip')}).json()['added']==1
        bot=c.post('/api/bots',json={'name':'Bot'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Hi'}).json()['job_id']
        c.get(f'/api/jobs/{run}/events')
        assert c.delete(f'/api/bots/{bot}').status_code==200
        status=c.get('/api/vault/status').json();assert (status['total'],status['available'])==(1,1)
        assert c.get('/api/settings').json()['gateways']['openrouter']['has_key']
        with service.db() as db:
            assert db.execute('SELECT bot_id FROM usage').fetchone()['bot_id'] is None
            row=db.execute('SELECT bot_id,status,actual_nanos FROM budget_reservations').fetchone()
            assert row['bot_id']==bot and row['status']=='settled' and row['actual_nanos']==300_000


def test_restart_marks_followup_charge_uncertain_and_interrupts_pending_tool():
    from funkbot.budget import reserve, reserve_followup, settle
    from funkbot.tool_audit import propose
    with TestClient(service.app) as client:
        setup(client);configure_budget(client)
        bot=client.post('/api/bots',json={'name':'Scout'}).json()['id']
        with service.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?)',('parent',bot,'running',time.time(),time.time()))
            reserve(db,'parent',bot,'smart',time.time())
            db.execute('INSERT INTO usage (bot_id,prompt_tokens,completion_tokens,created_at) VALUES (?,?,?,?)',(bot,20,10,time.time()))
            settle(db,'parent',db.execute('SELECT last_insert_rowid()').fetchone()[0],20,10)
            followup,_=reserve_followup(db,'parent',bot,'smart',time.time())
            call=propose(db,'parent',bot,'write_note',{'filename':'not-written.txt','content':'safe'},lambda text:text)
    service.mark_interrupted_runs()
    service.mark_interrupted_runs()  # recovery is idempotent
    with service.db() as db:
        assert db.execute('SELECT status FROM budget_reservations WHERE run_id=?',('parent',)).fetchone()['status']=='settled'
        assert db.execute('SELECT status FROM budget_reservations WHERE run_id=?',(followup,)).fetchone()['status']=='uncertain'
        assert db.execute('SELECT status FROM tool_calls WHERE id=?',(call,)).fetchone()['status']=='failed'
        assert [r['action'] for r in db.execute('SELECT action FROM tool_audit WHERE call_id=? ORDER BY id',(call,))]==['proposed','interrupted']
    assert not (service.DATA/'workspaces'/bot/'not-written.txt').exists()
    with TestClient(service.app) as client:
        assert client.post('/api/auth/login',json={'password':'correct horse battery staple'}).status_code==200
        assert client.post(f'/api/bots/{bot}/chat',json={'content':'Again'}).status_code==402
        assert client.post(f'/api/budget/reconcile/run/{followup}',json={'amount':'0.01','source':'Verified provider statement'}).status_code==200
        with service.db() as db:
            assert db.execute('SELECT status FROM budget_reservations WHERE run_id=?',(followup,)).fetchone()['status']=='settled'
