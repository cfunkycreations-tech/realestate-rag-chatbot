import time
from fastapi.testclient import TestClient
import app as service
from test_app import FakeClient, FakeStream, setup, configure_budget
from test_live_tools import tool_reply, final_reply


def wait_mission(c, mission_id, statuses):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        result=c.get('/api/missions/'+mission_id).json()
        if result['status'] in statuses: return result
        time.sleep(.01)
    raise AssertionError(f'Mission did not reach {statuses}: {result}')


def test_mission_executes_real_run_records_cost_result_and_log(monkeypatch):
    payloads=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs): payloads.append(kwargs['json']);return super().stream(*args,**kwargs)
    FakeClient.responses=[final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',Recording)
    with TestClient(service.app) as c:
        assert c.get('/api/missions').status_code==401
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout','title':'Editor'}).json()['id']
        assert c.post('/api/missions',json={'title':'  ','instructions':'Do work','bot_id':bot}).status_code==400
        assert c.post('/api/missions',json={'title':'Title','instructions':'Do work','bot_id':'missing'}).status_code==404
        mid=c.post('/api/missions',json={'title':'Proofread','instructions':'Check the text','bot_id':bot}).json()['id']
        result=wait_mission(c,mid,{'done','failed'})
        assert result['status']=='done' and result['result']=='All done.'
        assert result['assignees'][0]['bot_id']==bot
        assert result['cost_usd']==0.00038 and result['runs'][0]['status']=='done'
        assert any(e['type']=='done' for e in result['runs'][0]['log'])
        assert payloads[0]['messages'][-1]['content']=='Mission: Proofread\n\nCheck the text'
        assert c.get('/api/missions').json()[0]['id']==mid
        assert c.post(f'/api/missions/{mid}/cancel').status_code==409


def test_mission_cap_refusal_is_real_and_no_model_called(monkeypatch):
    FakeClient.responses=[final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        c.put('/api/budget/limits/account',json={'daily':'0','monthly':None})
        mid=c.post('/api/missions',json={'title':'Blocked','instructions':'Try','bot_id':bot}).json()['id']
        result=wait_mission(c,mid,{'failed'})
        assert 'daily budget cap' in result['error'] and result['runs']==[]
        assert len(FakeClient.responses)==1
        assert c.get(f'/api/bots/{bot}/messages').json()==[]


def test_mission_approval_and_cancel_flow_are_real(monkeypatch):
    FakeClient.responses=[tool_reply(),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        mid=c.post('/api/missions',json={'title':'Write note','instructions':'Save it','bot_id':bot}).json()['id']
        mission=wait_mission(c,mid,{'waiting_approval'});run=mission['runs'][0]['run_id']
        assert mission['runs'][0]['status']=='waiting_approval'
        call=c.get(f'/api/jobs/{run}/tool-calls').json()[0]
        assert c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'}).status_code==200
        done=wait_mission(c,mid,{'done','failed'})
        assert done['status']=='done' and done['cost_usd']==0.00068
        assert (service.DATA/'workspaces'/bot/'approved.txt').read_text()=='a safe note'
        assert c.get(f'/api/jobs/{run}/tool-calls').json()[0]['status']=='completed'
        FakeClient.responses=[tool_reply()]
        mid2=c.post('/api/missions',json={'title':'Cancel note','instructions':'Save it','bot_id':bot}).json()['id']
        waiting=wait_mission(c,mid2,{'waiting_approval'});run2=waiting['runs'][0]['run_id']
        assert c.delete(f'/api/bots/{bot}').status_code==409
        assert c.post(f'/api/missions/{mid2}/cancel').status_code==200
        stopped=wait_mission(c,mid2,{'cancelled'})
        assert stopped['runs'][0]['status']=='cancelled' and 'Response stopped' in stopped['error']
        assert c.get(f'/api/jobs/{run2}/tool-calls').json()[0]['status']=='failed'


def test_busy_bot_mission_queues_can_be_cancelled_without_dispatch(monkeypatch):
    FakeClient.responses=[tool_reply(),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        first=c.post('/api/missions',json={'title':'First','instructions':'Wait','bot_id':bot}).json()['id']
        wait_mission(c,first,{'waiting_approval'})
        second=c.post('/api/missions',json={'title':'Second','instructions':'Wait','bot_id':bot}).json()['id']
        assert c.get(f'/api/missions/{second}').json()['status']=='queued'
        assert c.post(f'/api/missions/{second}/cancel').status_code==200
        assert c.get(f'/api/missions/{second}').json()['status']=='cancelled'
        assert len(FakeClient.responses)==1
        assert c.post(f'/api/missions/{first}/cancel').status_code==200
        wait_mission(c,first,{'cancelled'})


def test_restart_marks_queued_and_running_missions_failed_without_replaying():
    with TestClient(service.app) as c:
        setup(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        with service.db() as db:
            db.execute("INSERT INTO missions VALUES ('queued','Queued','Work',NULL,'queued',NULL,NULL,1,1)")
            db.execute("INSERT INTO mission_assignees VALUES ('queued',0,?)",(bot,))
            db.execute("INSERT INTO missions VALUES ('running','Running','Work',NULL,'running',NULL,NULL,1,1)")
            db.execute("INSERT INTO mission_assignees VALUES ('running',0,?)",(bot,))
            db.execute("INSERT INTO runs VALUES ('run',?,'running',1,1)",(bot,))
            db.execute("INSERT INTO mission_runs VALUES ('mr','running',?,'run','member','running',NULL,NULL,1,1)",(bot,))
    service.mark_interrupted_runs()
    with service.db() as db:
        for row in db.execute('SELECT status,error FROM missions'):
            assert row['status']=='failed' and 'restarted' in row['error']
        assert db.execute('SELECT status FROM mission_runs').fetchone()['status']=='failed'


def test_failed_mission_reports_real_gateway_status_without_provider_payload(monkeypatch):
    FakeClient.responses=[FakeStream(401,[])];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        mid=c.post('/api/missions',json={'title':'Failure','instructions':'Run','bot_id':bot}).json()['id']
        result=wait_mission(c,mid,{'failed'})
        assert 'HTTP 401' in result['error'] and 'charges are unknown' in result['error']
        assert result['cost_usd'] is None and result['runs'][0]['status']=='failed'
        assert c.get('/api/budget').json()['unreconciled']


def test_queued_mission_starts_after_bot_is_free(monkeypatch):
    FakeClient.responses=[tool_reply(),final_reply(),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        first=c.post('/api/missions',json={'title':'First','instructions':'Wait','bot_id':bot}).json()['id']
        waiting=wait_mission(c,first,{'waiting_approval'});run=waiting['runs'][0]['run_id']
        second=c.post('/api/missions',json={'title':'Second','instructions':'Work later','bot_id':bot}).json()['id']
        assert c.get('/api/missions/'+second).json()['status']=='queued'
        call=c.get(f'/api/jobs/{run}/tool-calls').json()[0]
        c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'deny'})
        assert wait_mission(c,first,{'done'})['status']=='done'
        done=wait_mission(c,second,{'done','failed'})
        assert done['status']=='done' and done['runs'][0]['run_id']!=run
        assert not FakeClient.responses
