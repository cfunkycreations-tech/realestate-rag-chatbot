from fastapi.testclient import TestClient
import app as service
from test_app import setup,configure_budget,FakeClient
from test_live_tools import tool_reply,final_reply,until_calls,get_events


def test_global_pause_stops_pending_approval_blocks_starts_and_persists(monkeypatch):
    FakeClient.responses=[tool_reply(),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        assert c.get('/api/control/pause').status_code==401
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Write a note'}).json()['job_id']
        call=until_calls(c,run)[0];assert call['status']=='pending'
        assert c.put('/api/control/pause',json={'paused':True}).json()=={'paused':True}
        assert get_events(c,run)[-1]['type']=='error'
        assert not (service.DATA/'workspaces'/bot/'approved.txt').exists()
        assert c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve'}).status_code==423
        assert c.post(f'/api/bots/{bot}/chat',json={'content':'Hello'}).status_code==423
        assert c.post('/api/missions',json={'title':'Work','instructions':'Hello','bot_id':bot}).status_code==423
        assert c.post('/api/lab',json={'bot_id':bot,'prompt':'Hello','system_prompt':'Help','profiles':['smart']}).status_code==423
        assert len(FakeClient.responses)==1
    service.jobs.clear()
    with TestClient(service.app) as c:
        assert c.post('/api/auth/login',json={'password':'correct horse battery staple'}).status_code==200
        assert c.get('/api/control/pause').json()=={'paused':True}
        assert c.put('/api/control/pause',json={'paused':False}).json()=={'paused':False}
        run2=c.post(f'/api/bots/{bot}/chat',json={'content':'Hello'}).json()['job_id']
        assert get_events(c,run2)[-1]['type']=='done'


def test_pause_rejects_non_boolean():
    with TestClient(service.app) as c:
        setup(c)
        assert c.put('/api/control/pause',json={'paused':'yes'}).status_code==422
        assert c.get('/api/control/pause').json()=={'paused':False}


def test_pause_cancels_persisted_queued_work_without_replay():
    with TestClient(service.app) as c:
        setup(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        with service.db() as db:
            db.execute("INSERT INTO missions VALUES ('queued','Work','Do work',NULL,'queued',NULL,NULL,1,1)")
            db.execute("INSERT INTO mission_assignees VALUES ('queued',0,?)",(bot,))
            db.execute("INSERT INTO lab_experiments VALUES ('lab',?,'Question','Prompt','queued',NULL,1,1)",(bot,))
            db.execute("INSERT INTO lab_runs VALUES ('lab-step','lab',0,'smart',NULL,'queued',NULL,NULL,1,1)")
        assert c.put('/api/control/pause',json={'paused':True}).status_code==200
        assert c.get('/api/missions/queued').json()['status']=='cancelled'
        experiment=c.get('/api/lab/lab').json();assert experiment['status']=='failed' and experiment['runs'][0]['status']=='failed'
        assert c.put('/api/control/pause',json={'paused':False}).status_code==200
        assert c.get('/api/missions/queued').json()['status']=='cancelled'
