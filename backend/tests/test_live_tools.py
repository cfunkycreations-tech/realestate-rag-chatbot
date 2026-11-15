import json
import time
from fastapi.testclient import TestClient
import pytest
import app as service
from test_app import FakeClient, FakeStream, setup, configure_budget


def tool_reply(name='write_note',args=None,usage=True,done=True):
    if args is None: args={'filename':'approved.txt','content':'a safe note'}
    lines=['data: '+json.dumps({'choices':[{'delta':{'tool_calls':[{'index':0,'id':'model_call_1','function':{'name':name,'arguments':json.dumps(args)}}]},'finish_reason':None}]}),
           'data: '+json.dumps({'choices':[{'delta':{},'finish_reason':'tool_calls'}]})]
    if usage: lines.append('data: '+json.dumps({'choices':[],'usage':{'prompt_tokens':200,'completion_tokens':50}}))
    if done: lines.append('data: [DONE]')
    return FakeStream(200,lines)


def final_reply():
    return FakeStream(200,['data: '+json.dumps({'choices':[{'delta':{'content':'All done.'}}]}),
                           'data: '+json.dumps({'choices':[],'usage':{'prompt_tokens':300,'completion_tokens':40}}),'data: [DONE]'])


def until_calls(client, run):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        calls=client.get(f'/api/jobs/{run}/tool-calls').json()
        if calls: return calls
        time.sleep(.01)
    pytest.fail('Tool call did not arrive')


def get_events(client, run):
    return [json.loads(line[6:]) for line in client.get(f'/api/jobs/{run}/events').text.splitlines() if line.startswith('data: ')]


@pytest.mark.parametrize('decision,exists',[('approve_once',True),('deny',False),('approve',True)])
def test_streamed_tool_approval_and_accounted_followup(monkeypatch,decision,exists):
    captured=[]
    class Client(FakeClient):
        def stream(self,*args,**kwargs):
            captured.append(kwargs['json'])
            return super().stream(*args,**kwargs)
    FakeClient.responses=[tool_reply(),final_reply()]
    monkeypatch.setattr(service.httpx,'AsyncClient',Client)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Save a note'}).json()['job_id']
        call=until_calls(c,run)[0]
        assert call['status']=='pending'
        assert c.get(f'/api/bots/{bot}/latest-run').json()['status']=='waiting_approval'
        assert len(captured)==1
        assert c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':decision}).status_code==200
        events=get_events(c,run)
        assert events[-1]['type']=='done'
        assert any(e['type']=='tool.proposed' and e['needs_decision'] for e in events)
        assert any(e['type']=='tool.decision' and e['decision']==decision for e in events)
        assert (service.DATA/'workspaces'/bot/'approved.txt').exists()==exists
        assert len(captured)==2 and len(captured[0]['tools'])==3
        assert captured[1]['messages'][-1]['role']=='tool'
        assert json.loads(captured[1]['messages'][-1]['content'])['status']==('completed' if exists else 'denied')
        assert c.get(f'/api/bots/{bot}/messages').json()[-1]['content']=='All done.'
        with service.db() as db:
            rounds=db.execute('SELECT status,actual_nanos FROM budget_reservations WHERE parent_run_id=? ORDER BY created_at',(run,)).fetchall()
            assert [(r['status'],r['actual_nanos']) for r in rounds]==[('settled',300000),('settled',380000)]
            assert db.execute('SELECT COUNT(*) FROM usage').fetchone()[0]==2


def test_stopping_pending_approval_leaves_no_note_and_no_unknown_charge(monkeypatch):
    FakeClient.responses=[tool_reply(),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Save'}).json()['job_id']
        call=until_calls(c,run)[0]
        c.post(f'/api/jobs/{run}/stop')
        assert get_events(c,run)[-1]['type']=='error'
        assert not (service.DATA/'workspaces'/bot/'approved.txt').exists()
        assert c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve'}).status_code==409
        assert c.get(f'/api/jobs/{run}/tool-calls').json()[0]['status']=='failed'
        assert c.get('/api/budget').json()['unreconciled']==[]
        assert len(FakeClient.responses)==1


def test_cap_is_rechecked_before_followup_model_request(monkeypatch):
    FakeClient.responses=[tool_reply(),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        c.put('/api/budget/limits/account',json={'daily':'0.0185','monthly':None})
        bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Save'}).json()['job_id']
        call=until_calls(c,run)[0]
        c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'})
        events=get_events(c,run)
        assert 'daily budget cap' in events[-1]['message']
        assert len(FakeClient.responses)==1
        assert (service.DATA/'workspaces'/bot/'approved.txt').exists()
        assert c.get('/api/budget').json()['unreconciled']==[]


@pytest.mark.parametrize('response',[tool_reply(usage=False),tool_reply(done=False)])
def test_unknown_usage_or_incomplete_tool_stream_never_executes(monkeypatch,response):
    FakeClient.responses=[response];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Save'}).json()['job_id']
        assert get_events(c,run)[-1]['type']=='error'
        assert c.get(f'/api/jobs/{run}/tool-calls').json()==[]
        assert c.get('/api/budget').json()['unreconciled']
        assert not (service.DATA/'workspaces').exists()


def test_web_tool_automatic_and_loopback_blocked_in_live_run(monkeypatch):
    FakeClient.responses=[tool_reply('web_fetch',{'url':'http://127.0.0.1:8123/private'}),final_reply()]
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Fetch this'}).json()['job_id']
        events=get_events(c,run)
        assert events[-1]['type']=='done'
        call=c.get(f'/api/jobs/{run}/tool-calls').json()[0]
        assert call['status']=='failed' and 'Private' in call['result']['error']
        assert [a['action'] for a in call['audit']]==['proposed','read_auto_approved','started','failed']
        assert not any(e.get('needs_decision') for e in events)


def test_run_scoped_grant_allows_later_same_tool_only_with_audit(monkeypatch):
    chunks=[{'index':0,'id':'first','function':{'name':'write_note','arguments':json.dumps({'filename':'one.txt','content':'one'})}},
            {'index':1,'id':'second','function':{'name':'write_note','arguments':json.dumps({'filename':'two.txt','content':'two'})}}]
    response=FakeStream(200,['data: '+json.dumps({'choices':[{'delta':{'tool_calls':chunks},'finish_reason':None}]}),
                             'data: '+json.dumps({'choices':[{'delta':{},'finish_reason':'tool_calls'}]}),
                             'data: '+json.dumps({'choices':[],'usage':{'prompt_tokens':200,'completion_tokens':50}}),'data: [DONE]'])
    FakeClient.responses=[response,final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Save two'}).json()['job_id'];first=until_calls(c,run)[0]
        c.post(f'/api/jobs/{run}/tool-calls/{first["id"]}/decision',json={'decision':'approve'})
        events=get_events(c,run);assert events[-1]['type']=='done'
        proposed=[e for e in events if e['type']=='tool.proposed']
        assert [e['needs_decision'] for e in proposed]==[True,False]
        assert [e['decision'] for e in events if e['type']=='tool.decision']==['approve','run_grant']
        calls=c.get(f'/api/jobs/{run}/tool-calls').json()
        assert len(calls)==2 and all(call['status']=='completed' for call in calls)
        assert any(a['action']=='run_grant' for call in calls for a in call['audit'])
        assert (service.DATA/'workspaces'/bot/'one.txt').read_text()=='one'
        assert (service.DATA/'workspaces'/bot/'two.txt').read_text()=='two'


def test_tool_card_note_and_model_followup_use_identical_redacted_arguments(monkeypatch):
    key='sk-fixture-long-secret-123456789'
    captured=[]
    class Client(FakeClient):
        def stream(self,*args,**kwargs):
            captured.append(kwargs['json']);return super().stream(*args,**kwargs)
    FakeClient.responses=[tool_reply(args={'filename':'safe.txt','content':'Do not leak '+key}),final_reply()]
    monkeypatch.setattr(service.httpx,'AsyncClient',Client)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        c.put('/api/settings/gateways/openrouter',json={'url':'https://gateway.test/v1','key':key})
        bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Save'}).json()['job_id'];call=until_calls(c,run)[0]
        assert call['arguments']['content']=='Do not leak [redacted]'
        c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'})
        assert get_events(c,run)[-1]['type']=='done'
        assert (service.DATA/'workspaces'/bot/'safe.txt').read_text()=='Do not leak [redacted]'
        assistant=captured[1]['messages'][-2]
        assert json.loads(assistant['tool_calls'][0]['function']['arguments'])==call['arguments']
        assert key not in json.dumps(captured[1])


def test_unified_tool_approval_queue_only_shows_live_pending_calls(monkeypatch):
    FakeClient.responses=[tool_reply(),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        assert c.get('/api/tool-approvals').status_code==401
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Save a note'}).json()['job_id'];call=until_calls(c,run)[0]
        queued=c.get('/api/tool-approvals').json();assert len(queued)==1 and queued[0]['id']==call['id'] and queued[0]['run_id']==run
        assert queued[0]['arguments']==call['arguments']
        assert c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'deny'}).status_code==200
        get_events(c,run);assert c.get('/api/tool-approvals').json()==[]
