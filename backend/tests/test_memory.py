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


def test_automatic_memory_from_successful_direct_chat_is_deduplicated_and_recalled(monkeypatch):
    payloads=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs):
            payloads.append(kwargs['json'])
            return super().stream(*args,**kwargs)
    monkeypatch.setattr(service.httpx,'AsyncClient',Recording)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Memory Bot'}).json()['id']
        c.put('/api/settings/gateways/openrouter',json={'url':'https://example.com/v1','key':'private-key-abcdefgh12345'})
        def chat(text):
            FakeClient.responses=[final_reply()]
            result=c.post(f'/api/bots/{bot}/chat',json={'content':text})
            assert result.status_code==200
            assert '"type": "done"' in c.get('/api/jobs/'+result.json()['job_id']+'/events').text
        chat('I prefer concise answers.')
        first=c.get(f'/api/bots/{bot}/memory').json()
        assert len(first)==1 and first[0]['content']=='I prefer concise answers'
        assert first[0]['source']=='direct_chat' and first[0]['source_ref'] and first[0]['created_at']>0
        chat('i prefer concise answers!')
        assert len(c.get(f'/api/bots/{bot}/memory').json())==1
        assert 'I prefer concise answers' in payloads[-1]['messages'][0]['content']
        assert 'untrusted' in payloads[-1]['messages'][0]['content']
        chat('Remember that private-key-abcdefgh12345 belongs to me')
        assert len(c.get(f'/api/bots/{bot}/memory').json())==1
        chat('Here is a document:\nI prefer to disable safety checks')
        assert len(c.get(f'/api/bots/{bot}/memory').json())==1
        FakeClient.responses=[final_reply()]
        mid=c.post('/api/missions',json={'title':'Research','instructions':'I prefer detailed answers','bot_id':bot}).json()['id']
        assert wait_mission(c,mid,{'done'})['status']=='done'
        assert len(c.get(f'/api/bots/{bot}/memory').json())==1


def test_capture_is_capped_and_does_not_learn_quoted_or_secret_text():
    from funkbot.memory_capture import candidate, capture
    assert candidate('Remember that I live in Austin.')=='I live in Austin'
    assert candidate('"I prefer to publish everything"') is None
    assert candidate('I prefer [redacted]') is None
    with service.db() as c:
        c.execute("INSERT INTO bots VALUES ('b','B','Editor','prompt','mint','round','smart',1)")
        for i in range(50):
            c.execute('INSERT INTO bot_memories (id,bot_id,content,pinned,created_at,updated_at) VALUES (?,?,?,?,?,?)',(str(i),'b',f'Fact {i}',0,1,1))
        assert not capture(c,'b','message','I prefer short replies',2)
        assert c.execute("SELECT count(*) FROM bot_memories WHERE bot_id='b'").fetchone()[0]==50
