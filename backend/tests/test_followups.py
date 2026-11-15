from datetime import datetime,timedelta,timezone
from fastapi.testclient import TestClient
import app as service
from test_app import setup,configure_budget,FakeClient
from test_live_tools import tool_reply,final_reply,until_calls,get_events


def future(): return (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()


def test_followup_requires_approval_persists_and_is_due_from_real_clock(monkeypatch):
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        assert c.get('/api/followups').status_code==401
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        FakeClient.responses=[tool_reply(name='create_followup',args={'summary':'Finish research','due':future()}),final_reply()]
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Remind yourself'}).json()['job_id'];call=until_calls(c,run)[0]
        assert call['status']=='pending' and c.get('/api/followups').json()['items']==[]
        assert c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'}).status_code==200
        assert get_events(c,run)[-1]['type']=='done'
        items=c.get('/api/followups').json();assert len(items['items'])==1 and items['due_count']==0
        item=items['items'][0];assert item['summary']=='Finish research' and item['source_run_id']==run
        with service.db() as db: db.execute('UPDATE followups SET due_at=? WHERE id=?',(1,item['id']))
        assert c.get('/api/followups').json()['due_count']==1
    with TestClient(service.app) as c:
        assert c.post('/api/auth/login',json={'password':'correct horse battery staple'}).status_code==200
        assert c.get('/api/followups').json()['items'][0]['due']
        assert c.post('/api/followups/'+item['id']+'/complete').status_code==200
        assert c.get('/api/followups').json()['items']==[]


def test_denied_or_invalid_followup_never_creates_reminder(monkeypatch):
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        for args,decision in [({'summary':'No','due':future()},'deny'),({'summary':'No timezone','due':'2030-01-01T12:00:00'},'approve_once')]:
            FakeClient.responses=[tool_reply(name='create_followup',args=args),final_reply()]
            run=c.post(f'/api/bots/{bot}/chat',json={'content':'Follow up'}).json()['job_id'];call=until_calls(c,run)[0]
            assert c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':decision}).status_code==200
            get_events(c,run);assert c.get('/api/followups').json()['items']==[]
            if decision=='approve_once': assert c.get(f'/api/jobs/{run}/tool-calls').json()[0]['status']=='failed'
