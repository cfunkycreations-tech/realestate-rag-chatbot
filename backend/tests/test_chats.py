from fastapi.testclient import TestClient
import app as service
from test_app import setup,configure_budget,FakeClient
from test_live_tools import final_reply


def test_named_chats_history_isolation_search_and_delete(monkeypatch):
    seen=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs): seen.append(kwargs['json']);return super().stream(*args,**kwargs)
    monkeypatch.setattr(service.httpx,'AsyncClient',Recording);FakeClient.responses=[final_reply(),final_reply()]
    with TestClient(service.app) as c:
        assert c.get('/api/bots/no/chats').status_code==401
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Researcher'}).json()['id'];other=c.post('/api/bots',json={'name':'Other'}).json()['id']
        initial=c.get(f'/api/bots/{bot}/chats').json()[0]['id'];chat=c.post(f'/api/bots/{bot}/chats',json={'name':'Work notes'}).json()['id']
        assert c.put(f'/api/bots/{bot}/chats/{chat}',json={'name':'Research notes'}).status_code==200
        assert c.get(f'/api/bots/{bot}/chats',params={'q':'research'}).json()[0]['id']==chat
        first=c.post(f'/api/bots/{bot}/chat',json={'content':'Unique apples','chat_id':initial}).json()['job_id'];c.get(f'/api/jobs/{first}/events')
        second=c.post(f'/api/bots/{bot}/chat',json={'content':'Unique oranges','chat_id':chat}).json()['job_id'];c.get(f'/api/jobs/{second}/events')
        assert 'Unique apples' not in str(seen[1]['messages'])
        assert c.get(f'/api/bots/{bot}/chats',params={'q':'oranges'}).json()[0]['id']==chat
        assert len(c.get(f'/api/bots/{bot}/chats/{initial}/messages').json())==2
        assert len(c.get(f'/api/bots/{bot}/chats/{chat}/messages').json())==2
        assert c.get(f'/api/bots/{other}/chats/{chat}/messages').status_code==404
        assert c.post(f'/api/bots/{other}/chat',json={'content':'test','chat_id':chat}).status_code==404
        assert c.get(f'/api/bots/{bot}/chats/{chat}/latest-run').json()['id']==second
        assert c.delete(f'/api/bots/{bot}/chats/{chat}').status_code==200
        assert c.get(f'/api/bots/{bot}/chats/{chat}/messages').status_code==404
        assert len(c.get(f'/api/bots/{bot}/chats/{initial}/messages').json())==2
        assert c.get(f'/api/bots/{bot}/chats',params={'q':'oranges'}).json()==[]


def test_active_chat_cannot_be_deleted_and_memory_is_retained():
    import time
    with TestClient(service.app) as c:
        setup(c);bot=c.post('/api/bots',json={'name':'Researcher'}).json()['id']
        chat=c.get(f'/api/bots/{bot}/chats').json()[0]['id']
        with service.db() as db:
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?)',('running',bot,'running',time.time(),time.time()))
            db.execute('INSERT INTO chat_runs VALUES (?,?)',(chat,'running'))
            db.execute("INSERT INTO bot_memories VALUES ('memory',?,'Keep this fact',0,1,1,'owner',NULL)",(bot,))
        assert c.delete(f'/api/bots/{bot}/chats/{chat}').status_code==409
        with service.db() as db: db.execute("UPDATE runs SET status='done' WHERE id='running'")
        assert c.delete(f'/api/bots/{bot}/chats/{chat}').status_code==200
        with service.db() as db: assert db.execute("SELECT content FROM bot_memories WHERE id='memory'").fetchone()['content']=='Keep this fact'
        assert c.get(f'/api/bots/{bot}/chats').json()[0]['id']==chat
