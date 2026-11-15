import json
from fastapi.testclient import TestClient
import app as service
from test_app import setup, configure_budget, FakeClient, FakeStream
from test_live_tools import tool_reply
from test_missions_api import wait_mission


def response(text):
    return FakeStream(200,['data: '+json.dumps({'choices':[{'delta':{'content':text}}]}),'data: '+json.dumps({'choices':[],'usage':{'prompt_tokens':300,'completion_tokens':40}}),'data: [DONE]'])


def test_group_mission_uses_chief_plan_member_reply_and_synthesis(monkeypatch):
    payloads=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs): payloads.append(kwargs['json']);return super().stream(*args,**kwargs)
    monkeypatch.setattr(service.httpx,'AsyncClient',Recording)
    with TestClient(service.app) as c:
        assert c.get('/api/groups').status_code==401
        setup(c);configure_budget(c)
        chief=c.post('/api/bots',json={'name':'Chief'}).json()['id']
        member=c.post('/api/bots',json={'name':'Researcher'}).json()['id']
        assert c.post('/api/groups',json={'name':'g','chief_bot_id':chief,'member_ids':[chief,chief]}).status_code==400
        assert c.post('/api/groups',json={'name':'g','chief_bot_id':chief,'member_ids':[chief,'missing']}).status_code==404
        group=c.post('/api/groups',json={'name':'Team','chief_bot_id':chief,'member_ids':[member,chief]}).json()['id']
        assert c.get('/api/groups').json()[0]['member_ids']==[member,chief]
        FakeClient.responses=[response(json.dumps({'tasks':[{'bot_id':member,'instructions':'Research the question'}]})),response('Real research'),response('Final synthesis')]
        mid=c.post('/api/missions',json={'title':'Question','instructions':'Answer it','group_id':group}).json()['id']
        result=wait_mission(c,mid,{'done','failed'})
        assert result['status']=='done',result
        assert result['result']=='Final synthesis' and len(result['runs'])==3
        assert [r['role'] for r in result['runs']]==['chief','member','chief']
        assert result['cost_usd']==0.00114
        assert 'Research the question' in payloads[1]['messages'][-1]['content']
        assert 'Real research' in payloads[2]['messages'][-1]['content']
        events=c.get('/api/events?since=0&limit=500').json()['events']
        types=[e['type'] for e in events]
        assert types.count('group.session_started')==types.count('group.session_ended')==1
        assert types.count('group.delegated')==types.count('group.replied')==1
        assert next(e for e in events if e['type']=='group.delegated')['payload']['summary']=='Research the question'


def test_invalid_plan_fails_without_member_dispatch_and_cancel_waiting_approval(monkeypatch):
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        chief=c.post('/api/bots',json={'name':'Chief'}).json()['id'];member=c.post('/api/bots',json={'name':'Member'}).json()['id']
        group=c.post('/api/groups',json={'name':'Team','chief_bot_id':chief,'member_ids':[chief,member]}).json()['id']
        FakeClient.responses=[response('not a plan'),response('must not dispatch')]
        mid=c.post('/api/missions',json={'title':'Invalid','instructions':'Work','group_id':group}).json()['id']
        result=wait_mission(c,mid,{'failed'})
        assert 'valid delegation plan' in result['error'] and len(result['runs'])==1 and len(FakeClient.responses)==1
        FakeClient.responses=[tool_reply()]
        mid=c.post('/api/missions',json={'title':'Cancel','instructions':'Work','group_id':group}).json()['id']
        result=wait_mission(c,mid,{'waiting_approval'})
        assert c.delete(f'/api/bots/{member}').status_code==409
        assert c.post(f'/api/missions/{mid}/cancel').status_code==200
        result=wait_mission(c,mid,{'cancelled'})
        assert result['status']=='cancelled'
        assert not (service.DATA/'workspaces'/chief/'approved.txt').exists()


def test_group_budget_refusal_prevents_all_dispatch(monkeypatch):
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        chief=c.post('/api/bots',json={'name':'Chief'}).json()['id'];member=c.post('/api/bots',json={'name':'Member'}).json()['id']
        group=c.post('/api/groups',json={'name':'Team','chief_bot_id':chief,'member_ids':[chief,member]}).json()['id']
        c.put('/api/budget/limits/account',json={'daily':'0','monthly':None})
        FakeClient.responses=[response('never dispatched')]
        mid=c.post('/api/missions',json={'title':'Blocked','instructions':'Work','group_id':group}).json()['id']
        result=wait_mission(c,mid,{'failed'})
        assert 'daily budget cap' in result['error'] and result['runs']==[] and len(FakeClient.responses)==1
