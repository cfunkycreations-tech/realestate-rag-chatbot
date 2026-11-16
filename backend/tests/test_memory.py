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


def test_shared_and_project_memory_owner_crud_is_scoped_and_redacted(monkeypatch):
    with TestClient(service.app) as c:
        assert c.get('/api/memory/shared').status_code==401
        setup(c)
        c.put('/api/settings/gateways/openrouter',json={'url':'https://example.com/v1','key':'private-key-abcdefgh12345'})
        p=c.post('/api/projects',json={'name':'First'}).json()['id']
        other=c.post('/api/projects',json={'name':'Second'}).json()['id']
        shared=c.post('/api/memory/shared',json={'content':'Likes private-key-abcdefgh12345'}).json()['id']
        assert 'private-key' not in c.get('/api/memory/shared').text
        assert c.post('/api/memory/shared',json={'content':'LIKES [REDACTED]'}).status_code==409
        assert c.put(f'/api/memory/shared/{shared}',json={'content':'Likes short answers'}).status_code==200
        item=c.post(f'/api/projects/{p}/memory',json={'content':'Project deadline is Friday'}).json()['id']
        assert c.get(f'/api/projects/{other}/memory').json()==[]
        assert c.delete(f'/api/projects/{other}/memory/{item}').status_code==404
        assert c.get('/api/projects/missing/memory').status_code==404
        assert c.put(f'/api/projects/{p}/memory/{item}',json={'content':'Project deadline is Monday'}).status_code==200
        assert c.get(f'/api/projects/{p}/memory').json()[0]['source']=='owner'
        assert c.delete(f'/api/projects/{p}/memory/{item}').status_code==200
        assert c.delete(f'/api/memory/shared/{shared}').status_code==200


def test_shared_recall_for_every_bot_and_project_recall_only_for_linked_mission(monkeypatch):
    payloads=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs): payloads.append(kwargs['json']);return super().stream(*args,**kwargs)
    monkeypatch.setattr(service.httpx,'AsyncClient',Recording)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        bots=[c.post('/api/bots',json={'name':name}).json()['id'] for name in ('First','Second')]
        project=c.post('/api/projects',json={'name':'Private project'}).json()['id']
        c.post('/api/memory/shared',json={'content':'Shared preference'})
        c.post(f'/api/projects/{project}/memory',json={'content':'Project-only fact'})
        for bot in bots:
            FakeClient.responses=[final_reply()]
            run=c.post(f'/api/bots/{bot}/chat',json={'content':'Hello'}).json()['job_id']
            c.get('/api/jobs/'+run+'/events')
            prompt=payloads[-1]['messages'][0]['content']
            assert 'Shared preference' in prompt and 'Project-only fact' not in prompt and 'untrusted' in prompt
        # A linked queued mission is the only source of project context.
        with service.db() as db:
            db.execute("INSERT INTO missions VALUES ('queued','Work','Hello',NULL,'queued',NULL,NULL,1,1)")
            db.execute("INSERT INTO mission_assignees VALUES ('queued',0,?)",(bots[0],))
            db.execute("INSERT INTO project_missions VALUES (?, 'queued', 1)",(project,))
        import asyncio
        FakeClient.responses=[final_reply()]
        async def run_linked():
            job=await service.start_chat(bots[0],service.ChatIn(content='Hello'),mission_id='queued')
            await service.jobs[job['job_id']]['task']
        asyncio.run(run_linked())
        prompt=payloads[-1]['messages'][0]['content']
        assert 'Shared preference' in prompt and 'Project-only fact' in prompt


def test_direct_chat_memory_commands_are_local_scoped_exact_and_preserve_pins(monkeypatch):
    payloads=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs): payloads.append(kwargs['json']);return super().stream(*args,**kwargs)
    monkeypatch.setattr(service.httpx,'AsyncClient',Recording)
    with TestClient(service.app) as c:
        assert c.post('/api/bots/no/chat',json={'content':'!memory show'}).status_code==401
        setup(c);configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Memory Bot'}).json()['id']
        other=c.post('/api/bots',json={'name':'Other Bot'}).json()['id']
        chat=c.get(f'/api/bots/{bot}/chats').json()[0]['id']
        def command(text): return c.post(f'/api/bots/{bot}/chat',json={'content':text,'chat_id':chat})
        assert command('!memory help').json()=={'local_memory':True}
        assert 'Use !memory show' in c.get(f'/api/bots/{bot}/chats/{chat}/messages').text
        assert command('!memory remember ...').status_code==400
        assert command('!memory remember I prefer concise answers').json()=={'local_memory':True}
        item=c.get(f'/api/bots/{bot}/memory').json()[0]
        assert item['source']=='direct_chat' and item['source_ref']
        assert c.get(f'/api/bots/{other}/memory').json()==[]
        assert command('!memory remember i prefer concise answers.').status_code==409
        assert c.put(f'/api/bots/{bot}/memory/{item["id"]}',json={'content':item['content'],'pinned':True}).status_code==200
        assert command('!memory show').status_code==200
        assert 'I prefer concise answers (pinned)' in c.get(f'/api/bots/{bot}/chats/{chat}/messages').text
        assert command('!memory replace I prefer concise answers => I prefer detailed answers').status_code==200
        updated=c.get(f'/api/bots/{bot}/memory').json()[0]
        assert updated['pinned'] and updated['content']=='I prefer detailed answers' and updated['source']=='direct_chat'
        assert command('!memory forget I prefer detailed').status_code==404
        assert len(c.get(f'/api/bots/{bot}/memory').json())==1
        FakeClient.responses=[final_reply()]
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'Hello','chat_id':chat}).json()['job_id']
        c.get('/api/jobs/'+run+'/events')
        assert 'I prefer detailed answers' in payloads[-1]['messages'][0]['content']
        assert command('!memory forget I prefer detailed answers').status_code==200
        assert c.get(f'/api/bots/{bot}/memory').json()==[]
        assert 'Chat history and event logs remain' in c.get(f'/api/bots/{bot}/chats/{chat}/messages').text
        assert command('!memory replace x => y => z').status_code==400
        assert c.post(f'/api/bots/{bot}/chat',json={'content':'!memory show','chat_id':chat,'attachment_ids':['x']}).status_code==400
        assert c.post(f'/api/bots/{other}/chat',json={'content':'!memory show','chat_id':chat}).status_code==404
        c.put('/api/settings/gateways/openrouter',json={'url':'https://example.com/v1','key':'private-key-abcdefgh12345'})
        assert command('!memory remember private-key-abcdefgh12345').status_code==400
        assert 'private-key-abcdefgh12345' not in c.get(f'/api/bots/{bot}/chats/{chat}/messages').text
        assert len(payloads)==1


def test_chat_forget_never_deletes_ambiguous_memory():
    with TestClient(service.app) as c:
        setup(c);bot=c.post('/api/bots',json={'name':'Memory Bot'}).json()['id']
        c.post(f'/api/bots/{bot}/memory',json={'content':'duplicate fact'})
        c.post(f'/api/bots/{bot}/memory',json={'content':'Duplicate fact.'})
        assert c.post(f'/api/bots/{bot}/chat',json={'content':'!memory forget duplicate fact'}).status_code==409
        assert len(c.get(f'/api/bots/{bot}/memory').json())==2


def test_model_learns_chat_fact_and_owner_can_review_edit_delete(monkeypatch):
    from test_live_tools import tool_reply
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    FakeClient.responses=[tool_reply('remember_fact',{'fact':'The owner lives in Austin.'}),final_reply()]
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Learner'}).json()['id']
        other=c.post('/api/bots',json={'name':'Other'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'I live in Austin.'}).json()['job_id']
        assert '"type": "done"' in c.get(f'/api/jobs/{run}/events').text
        memories=c.get(f'/api/bots/{bot}/memory').json()
        assert len(memories)==1 and memories[0]['content']=='The owner lives in Austin.' and memories[0]['source']=='learned_chat'
        assert c.get(f'/api/bots/{other}/memory').json()==[]
        mid=memories[0]['id']
        assert c.put(f'/api/bots/{bot}/memory/{mid}',json={'content':'The owner lives in Texas.','pinned':True}).status_code==200
        assert c.get(f'/api/bots/{bot}/memory').json()[0]['content']=='The owner lives in Texas.'
        assert c.delete(f'/api/bots/{bot}/memory/{mid}').status_code==200
        assert c.get(f'/api/bots/{bot}/memory').json()==[]
