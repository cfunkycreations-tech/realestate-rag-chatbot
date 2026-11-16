import copy
import json
from fastapi.testclient import TestClient
import app as service
from test_app import setup,configure_budget,FakeClient
from test_live_tools import final_reply,get_events


def token(kind,identifier,label='display'):
    return f'@{{{kind}:{identifier}|{label}}}'


def test_mentions_catalog_resolves_actual_metadata_not_fake_labels_or_secrets(monkeypatch):
    sent=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs):sent.append(copy.deepcopy(kwargs['json']));return super().stream(*args,**kwargs)
    monkeypatch.setattr(service.httpx,'AsyncClient',Recording);FakeClient.responses=[final_reply()]
    with TestClient(service.app) as c:
        assert c.get('/api/mentions').status_code==401
        setup(c);configure_budget(c)
        a=c.post('/api/bots',json={'name':'Planner','title':'Planning'}).json()['id'];b=c.post('/api/bots',json={'name':'Researcher','title':'Research'}).json()['id']
        group=c.post('/api/groups',json={'name':'Research Team','chief_bot_id':a,'member_ids':[a,b]}).json()['id']
        routine=c.post('/api/routines',json={'title':'Research Daily','instructions':'Private routine instructions','bot_id':b,'cron':'0 9 * * *','timezone':'UTC'}).json()['id']
        connector=c.put('/api/connectors/new',json={'name':'Research source','url':'https://example.com/mcp','key':'private-key-abcdefgh12345','enabled':True,'allowed_tools':['find']}).json()['id']
        options=c.get('/api/mentions?q=research').json();assert {x['kind'] for x in options}=={'bot','group','routine','connector'}
        assert 'private-key' not in json.dumps(options) and 'example.com' not in json.dumps(options)
        text='Compare '+token('bot',b,'Fake label')+' '+token('group',group)+' '+token('routine',routine)+' '+token('connector',connector)
        run=c.post(f'/api/bots/{a}/chat',json={'content':text}).json()['job_id'];assert get_events(c,run)[-1]['type']=='done'
        model=sent[0]['messages'][-1]['content'];references=json.loads(model.split('): ',1)[1].split('\nOwner message: ',1)[0])
        assert references[0]['name']=='Researcher' and references[0]['title']=='Research'
        assert [x['kind'] for x in references]==['bot','group','routine','connector'] and references[2]['cron']=='0 9 * * *'
        assert references[3]['allowed_tools']==['find'] and 'private-key' not in model and 'Private routine instructions' not in model and 'example.com/mcp' not in model
        assert 'not authorization' in model and len(c.get('/api/missions').json())==0
        assert c.get('/api/bot-dms').json()==[] and c.get('/api/tool-approvals').json()==[]


def test_missing_and_too_many_mentions_fail_without_dispatch(monkeypatch):
    sent=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs):sent.append(1);return super().stream(*args,**kwargs)
    monkeypatch.setattr(service.httpx,'AsyncClient',Recording)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);owner=c.post('/api/bots',json={'name':'Owner'}).json()['id'];bots=[c.post('/api/bots',json={'name':str(i)}).json()['id'] for i in range(9)]
        assert c.post(f'/api/bots/{owner}/chat',json={'content':' '.join(token('bot',id) for id in bots)}).status_code==400
        c.delete('/api/bots/'+bots[0]);assert c.post(f'/api/bots/{owner}/chat',json={'content':token('bot',bots[0])}).status_code==400
        assert sent==[] and c.get(f'/api/bots/{owner}/messages').json()==[]
