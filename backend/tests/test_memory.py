import json
from fastapi.testclient import TestClient
import app as service
from test_app import setup,configure_budget,FakeClient
from test_live_tools import final_reply
from test_missions_api import wait_mission


def test_memory_crud_redaction_size_cap_and_model_context(monkeypatch):
    payloads=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs): payloads.append(kwargs['json']);return super().stream(*args,**kwargs)
    FakeClient.responses=[final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',Recording)
    with TestClient(service.app) as c:
        assert c.get('/api/bots/x/memory').status_code==401
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Memory Bot'}).json()['id']
        c.put('/api/settings/gateways/openrouter',json={'url':'https://example.com/v1','key':'private-key-abcdefgh12345'})
        mem=c.post(f'/api/bots/{bot}/memory',json={'content':'Preference private-key-abcdefgh12345','pinned':True}).json()['id']
        data=c.get(f'/api/bots/{bot}/memory').json();assert 'private-key' not in json.dumps(data) and data[0]['pinned']
        assert c.put(f'/api/bots/{bot}/memory/{mem}',json={'content':'Likes concise answers','pinned':True}).status_code==200
        mid=c.post('/api/missions',json={'title':'Answer','instructions':'Hello','bot_id':bot}).json()['id'];assert wait_mission(c,mid,{'done'})['status']=='done'
        assert 'Likes concise answers' in payloads[0]['messages'][0]['content'] and 'untrusted' in payloads[0]['messages'][0]['content']
        for i in range(8): assert c.post(f'/api/bots/{bot}/memory',json={'content':'x'*3990}).status_code==200
        assert c.post(f'/api/bots/{bot}/memory',json={'content':'x'*100}).status_code==400
        assert c.delete(f'/api/bots/{bot}/memory/{mem}').status_code==200
        assert c.get(f'/api/bots/{bot}/memory').json()[0]['content']=='x'*3990
