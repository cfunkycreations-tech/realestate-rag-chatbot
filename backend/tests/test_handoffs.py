from fastapi.testclient import TestClient
import app as service
from test_app import setup,configure_budget,FakeClient
from test_live_tools import final_reply
from test_missions_api import wait_mission


def test_owner_handoff_creates_receiver_mission_cards_and_real_event(monkeypatch):
    sent=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs): sent.append(kwargs['json']);return super().stream(*args,**kwargs)
    monkeypatch.setattr(service.httpx,'AsyncClient',Recording);FakeClient.responses=[final_reply()]
    with TestClient(service.app) as c:
        assert c.get('/api/bots/x/handoffs').status_code==401
        setup(c);configure_budget(c)
        sender=c.post('/api/bots',json={'name':'Sender'}).json()['id'];receiver=c.post('/api/bots',json={'name':'Receiver'}).json()['id']
        assert c.post(f'/api/bots/{sender}/handoffs',json={'to_bot_id':sender,'reason':'Need help','context':'Context'}).status_code==400
        response=c.post(f'/api/bots/{sender}/handoffs',json={'to_bot_id':receiver,'reason':'Need help','context':'Check the draft'})
        assert response.status_code==200;mid=response.json()['mission_id'];assert wait_mission(c,mid,{'done'})['status']=='done'
        assert 'Check the draft' in sent[0]['messages'][-1]['content'] and 'untrusted' in sent[0]['messages'][0]['content']
        a=c.get(f'/api/bots/{sender}/handoffs').json();b=c.get(f'/api/bots/{receiver}/handoffs').json()
        assert len(a)==len(b)==1 and a[0]['mission_id']==b[0]['mission_id']==mid and a[0]['status']=='done'
        event=next(e for e in c.get('/api/events?limit=500').json()['events'] if e['type']=='handoff.created')
        assert event['payload']['from_bot_id']==sender and event['payload']['to_bot_id']==receiver
        assert c.put('/api/control/pause',json={'paused':True}).status_code==200
        assert c.post(f'/api/bots/{sender}/handoffs',json={'to_bot_id':receiver,'reason':'Blocked','context':'No work'}).status_code==423
