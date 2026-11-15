from fastapi.testclient import TestClient
import app as service
from test_app import setup, configure_budget, FakeClient
from test_live_tools import final_reply
from test_missions_api import wait_mission


def test_projects_record_real_mission_cost_notes_and_preserve_missions(monkeypatch):
    FakeClient.responses=[final_reply()]; monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        assert c.get('/api/projects').status_code==401
        setup(c); configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Scout','title':'Editor'}).json()['id']
        assert c.post('/api/projects',json={'name':'  '}).status_code==400
        assert c.post('/api/projects',json={'name':'P','owner_bot_id':'missing'}).status_code==404
        p=c.post('/api/projects',json={'name':' Project ','description':' Description ','owner_bot_id':bot}).json()['id']
        p2=c.post('/api/projects',json={'name':'Other'}).json()['id']
        mid=c.post('/api/missions',json={'title':'Work','instructions':'Finish','bot_id':bot}).json()['id']
        wait_mission(c,mid,{'done'})
        assert c.put(f'/api/projects/{p}/missions/{mid}').status_code==200
        assert c.put(f'/api/projects/{p}/missions/{mid}').status_code==200
        assert c.put(f'/api/projects/{p2}/missions/{mid}').status_code==409
        note=c.post(f'/api/projects/{p}/notes',json={'content':'Useful note'}).json()['id']
        project=c.get(f'/api/projects/{p}').json()
        assert project['name']=='Project' and project['description']=='Description' and project['owner_bot_id']==bot
        assert project['counts']['done']==1 and project['cost_usd']==0.00038
        assert project['missions'][0]['result']=='All done.' and project['notes'][0]['content']=='Useful note'
        assert c.delete(f'/api/projects/{p}/notes/{note}').status_code==200
        assert c.delete(f'/api/projects/{p}/missions/{mid}').status_code==200
        assert c.get(f'/api/missions/{mid}').json()['result']=='All done.'
        assert c.delete(f'/api/bots/{bot}').status_code==200
        assert c.get(f'/api/projects/{p}').json()['owner_bot_id'] is None


def test_project_validation_and_missing_records():
    with TestClient(service.app) as c:
        setup(c)
        p=c.post('/api/projects',json={'name':'Project'}).json()['id']
        assert c.get('/api/projects/missing').status_code==404
        assert c.put('/api/projects/missing',json={'name':'x'}).status_code==404
        assert c.put(f'/api/projects/{p}/missions/missing').status_code==404
        assert c.post(f'/api/projects/{p}/notes',json={'content':'   '}).status_code==400
        assert c.delete(f'/api/projects/{p}/notes/missing').status_code==404
        assert c.put(f'/api/projects/{p}',json={'name':'Updated'}).status_code==200
        assert c.get(f'/api/projects/{p}').json()['name']=='Updated'
