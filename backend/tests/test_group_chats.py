import json
import time
from fastapi.testclient import TestClient
import app as service
from test_app import setup,configure_budget,FakeClient
from test_groups_api import response
from test_live_tools import tool_reply


def wait(c,chat,statuses):
    for _ in range(150):
        data=c.get('/api/group-chats/'+chat).json()
        if data['turns'] and data['turns'][0]['status'] in statuses: return data
        time.sleep(.02)
    raise AssertionError(data)


def prepare(c):
    setup(c);configure_budget(c)
    chief=c.post('/api/bots',json={'name':'Chief','title':'Lead'}).json()['id']
    member=c.post('/api/bots',json={'name':'Member','title':'Researcher'}).json()['id']
    group=c.post('/api/groups',json={'name':'Team','chief_bot_id':chief,'member_ids':[member,chief]}).json()['id']
    chat=c.post(f'/api/groups/{group}/chats',json={'name':'Planning'}).json()['id']
    return chief,member,group,chat


def test_group_chat_sequential_transcript_and_private_memory(monkeypatch):
    payloads=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs): payloads.append(kwargs['json']);return super().stream(*args,**kwargs)
    monkeypatch.setattr(service.httpx,'AsyncClient',Recording)
    with TestClient(service.app) as c:
        assert c.get('/api/group-chats/no').status_code==401
        chief,member,group,chat=prepare(c)
        c.post(f'/api/bots/{chief}/memory',json={'content':'Chief-only memory'})
        c.post(f'/api/bots/{member}/memory',json={'content':'Member-only memory'})
        FakeClient.responses=[response('Chief plan'),response('Member contribution'),response('Final synthesis')]
        assert c.post(f'/api/group-chats/{chat}/messages',json={'content':'Explain the plan'}).status_code==200
        result=wait(c,chat,{'done','failed'});assert result['turns'][0]['status']=='done',result
        assert [(m['role'],m['content']) for m in result['messages']]==[('user','Explain the plan'),('chief','Chief plan'),('member','Member contribution'),('summary','Final synthesis')]
        assert 'Chief-only memory' in payloads[0]['messages'][0]['content'] and 'Member-only memory' not in payloads[0]['messages'][0]['content']
        assert 'Member-only memory' in payloads[1]['messages'][0]['content'] and 'Chief-only memory' not in payloads[1]['messages'][0]['content']
        assert 'Chief plan' in payloads[1]['messages'][-1]['content'] and 'untrusted' in payloads[1]['messages'][-1]['content']
        assert 'Member contribution' in payloads[2]['messages'][-1]['content']
        assert c.get(f'/api/bots/{chief}/messages').json()==[] and c.get(f'/api/bots/{member}/messages').json()==[]
        events=c.get('/api/events?since=0&limit=500').json()['events']
        assert any(e['type']=='group.session_started' and e['payload']['session_kind']=='group_chat' for e in events)
        assert any(e['type']=='group.session_ended' and e['payload']['session_kind']=='group_chat' for e in events)
        assert c.delete('/api/group-chats/'+chat).status_code==200


def test_group_stop_waiting_approval_and_budget_refusal(monkeypatch):
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        chief,member,group,chat=prepare(c)
        FakeClient.responses=[tool_reply()]
        assert c.post(f'/api/group-chats/{chat}/messages',json={'content':'Work'}).status_code==200
        for _ in range(150):
            result=c.get(f'/api/group-chats/{chat}').json()
            if c.get('/api/tool-approvals').json(): break
            time.sleep(.02)
        else: raise AssertionError('Approval did not appear')
        assert c.post(f'/api/group-chats/{chat}/messages',json={'content':'Another'}).status_code==409
        assert c.delete(f'/api/bots/{member}').status_code==409
        assert c.delete(f'/api/group-chats/{chat}').status_code==409
        assert c.post(f'/api/group-chats/{chat}/stop').status_code==200
        assert wait(c,chat,{'cancelled'})['turns'][0]['status']=='cancelled'
        assert not (service.DATA/'workspaces'/chief/'approved.txt').exists()
        c.put('/api/budget/limits/account',json={'daily':'0','monthly':None})
        FakeClient.responses=[response('never')]
        assert c.post(f'/api/group-chats/{chat}/messages',json={'content':'Try again'}).status_code==200
        data=wait(c,chat,{'failed'});assert 'budget' in data['turns'][0]['error'].lower() and len(FakeClient.responses)==1


def test_global_pause_cancels_group_turn_waiting_for_approval(monkeypatch):
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        chief,member,group,chat=prepare(c)
        FakeClient.responses=[tool_reply()]
        c.post(f'/api/group-chats/{chat}/messages',json={'content':'Work'})
        for _ in range(150):
            if c.get('/api/tool-approvals').json(): break
            time.sleep(.02)
        else: raise AssertionError('Approval did not appear')
        assert c.put('/api/control/pause',json={'paused':True}).status_code==200
        data=wait(c,chat,{'cancelled'});assert 'pause' in data['turns'][0]['error']
        assert c.get('/api/tool-approvals').json()==[]
        assert not (service.DATA/'workspaces'/chief/'approved.txt').exists()
        assert c.post(f'/api/group-chats/{chat}/messages',json={'content':'Again'}).status_code==423


def test_interrupted_group_turn_is_failed_and_office_session_closed():
    with TestClient(service.app) as c:
        chief,member,group,chat=prepare(c)
        with service.db() as db:
            db.execute("INSERT INTO group_chat_turns VALUES ('t',?,'running',NULL,NULL,1,1)",(chat,))
            service.append_event(db,None,None,'group.session_started',{'mission_id':'t','session_kind':'group_chat','participants':[chief,member]})
        service.mark_interrupted_runs()
        turn=c.get('/api/group-chats/'+chat).json()['turns'][0];assert turn['status']=='failed' and 'restarted' in turn['error']
        events=c.get('/api/events?since=0&limit=500').json()['events']
        assert any(e['type']=='group.session_ended' and e['payload']['mission_id']=='t' for e in events)


def test_group_chat_mentions_share_metadata_and_notify(monkeypatch):
    payloads=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs): payloads.append(kwargs['json']);return super().stream(*args,**kwargs)
    monkeypatch.setattr(service.httpx,'AsyncClient',Recording)
    with TestClient(service.app) as c:
        chief,member,group,chat=prepare(c)
        FakeClient.responses=[response('plan'),response('reply'),response('summary')]
        text=f'Ask @{{bot:{member}|Member}} to help.'
        assert c.post(f'/api/group-chats/{chat}/messages',json={'content':text}).status_code==200
        assert wait(c,chat,{'done','failed'})['turns'][0]['status']=='done'
        assert all(member in p['messages'][-1]['content'] and 'untrusted metadata' in p['messages'][-1]['content'] for p in payloads)
        assert any(n['kind']=='mention' and n['bot_id']==member for n in c.get('/api/inbox/notices').json())
        assert c.post(f'/api/group-chats/{chat}/messages',json={'content':'@{bot:00000000-0000-0000-0000-000000000000|Missing}'}).status_code==400
