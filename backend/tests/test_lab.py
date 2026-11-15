import time
from fastapi.testclient import TestClient
import app as service
from test_app import FakeClient,setup,configure_budget
from test_live_tools import final_reply,tool_reply


def wait(c,eid):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        item=c.get('/api/lab/'+eid).json()
        if item['status'] in ('done','failed'):return item
        time.sleep(.01)
    raise AssertionError(item)


def test_lab_compares_profiles_without_tools_or_chat_side_effects_and_saves(monkeypatch):
    payloads=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs):payloads.append(kwargs['json']);return super().stream(*args,**kwargs)
    monkeypatch.setattr(service.httpx,'AsyncClient',Recording)
    with TestClient(service.app) as c:
        assert c.get('/api/lab').status_code==401
        setup(c);configure_budget(c);c.put('/api/budget/prices/fast',json={'prompt':'1','completion':'2','max_prompt_tokens':8192,'max_completion_tokens':512})
        bot=c.post('/api/bots',json={'name':'Scout'}).json()['id'];c.post(f'/api/bots/{bot}/memory',json={'content':'Private memory'});project=c.post('/api/projects',json={'name':'Research'}).json()['id']
        FakeClient.responses=[final_reply(),final_reply()]
        eid=c.post('/api/lab',json={'bot_id':bot,'prompt':'Test question','system_prompt':'Tested personality','profiles':['smart','fast']}).json()['id'];item=wait(c,eid)
        assert item['status']=='done' and len(item['runs'])==2
        assert all(r['result']=='All done.' and r['cost_usd']==0.00038 and r['prompt_tokens']==300 and r['latency_ms'] is not None for r in item['runs'])
        assert all('tools' not in p and len(p['messages'])==2 and 'Private memory' not in p['messages'][0]['content'] and 'Tested personality' in p['messages'][0]['content'] for p in payloads)
        assert c.get(f'/api/bots/{bot}/messages').json()==[]
        assert c.post(f'/api/lab/{eid}/save-note',json={'project_id':project}).status_code==200
        assert 'All done.' in c.get(f'/api/projects/{project}').json()['notes'][0]['content']
        assert c.post(f'/api/lab/{eid}/apply-prompt').status_code==200
        with service.db() as db: assert db.execute('SELECT personality FROM bots WHERE id=?',(bot,)).fetchone()['personality']=='Tested personality'


def test_lab_refuses_cap_and_malicious_tool_calls(monkeypatch):
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        c.put('/api/budget/limits/account',json={'daily':'0','monthly':None});FakeClient.responses=[final_reply()]
        eid=c.post('/api/lab',json={'bot_id':bot,'prompt':'Test','system_prompt':'Help','profiles':['smart']}).json()['id'];item=wait(c,eid)
        assert item['status']=='failed' and 'daily budget cap' in item['error'] and len(FakeClient.responses)==1
        c.put('/api/budget/limits/account',json={'daily':'5','monthly':None});FakeClient.responses=[tool_reply()]
        eid=c.post('/api/lab',json={'bot_id':bot,'prompt':'Test','system_prompt':'Help','profiles':['smart']}).json()['id'];item=wait(c,eid)
        assert item['status']=='failed' and 'tool call' in item['error']
        assert not (service.DATA/'workspaces'/bot/'approved.txt').exists()
        assert c.post(f'/api/lab/{eid}/apply-prompt').status_code==409
