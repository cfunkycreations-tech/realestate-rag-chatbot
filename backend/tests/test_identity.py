from fastapi.testclient import TestClient
import app as service
from test_app import setup
from test_vault import png, archive


def test_new_bot_uses_vault_name_and_job_is_separate():
    with TestClient(service.app) as client:
        setup(client)
        client.post('/api/vault/import', files={'file':('a.zip',archive([('a.png',png('Zigzag',role='Cosmic Gnome'))]),'application/zip')})
        created=client.post('/api/bots',json={'name':'Fallback','title':'Editor','personality':'Edit thoughtfully'}).json()
        bot=next(b for b in client.get('/api/bots').json() if b['id']==created['id'])
        assert (bot['name'],bot['title'],bot['character']['role'])==('Zigzag','Editor','Cosmic Gnome')
        prompt=service.bot_system_prompt(bot)
        assert 'Zigzag' in prompt and 'Editor' in prompt and 'Cosmic Gnome' not in prompt
        legacy=client.post('/api/bots',json={'name':'Existing client','title':'Researcher'}).json()
        assert next(b for b in client.get('/api/bots').json() if b['id']==legacy['id'])['name']=='Zigzag'


def test_existing_bot_sprite_requires_explicit_choice_and_preserves_other_fields():
    with TestClient(service.app) as client:
        setup(client)
        one=client.post('/api/bots',json={'name':'Original','title':'Project Manager'}).json()['id']
        two=client.post('/api/bots',json={'name':'Other','title':'Editor'}).json()['id']
        assert client.post(f'/api/bots/{one}/sprite',json={}).status_code==422
        assert client.post(f'/api/bots/{one}/sprite',json={'adopt_character_name':True}).status_code==409
        client.post('/api/vault/import',files={'file':('a.zip',archive([('a.png',png('Gizmo'))]),'application/zip')})
        assert client.post(f'/api/bots/{one}/sprite',json={'adopt_character_name':False}).status_code==200
        assert client.post(f'/api/bots/{one}/sprite',json={'adopt_character_name':True}).status_code==409
        assert client.post(f'/api/bots/{two}/sprite',json={'adopt_character_name':True}).status_code==200
        bots={b['id']:b for b in client.get('/api/bots').json()}
        assert (bots[one]['name'],bots[one]['title'])==('Original','Project Manager')
        assert (bots[two]['name'],bots[two]['title'])==('Gizmo','Editor')
        assert client.post('/api/auth/logout').status_code==200
        assert client.post(f'/api/bots/{two}/sprite',json={'adopt_character_name':False}).status_code==401


def test_duplicate_copies_identity_sprite_and_budget_but_not_history_or_memory():
    with TestClient(service.app) as client:
        assert client.post('/api/bots/missing/duplicate').status_code==401
        setup(client)
        assert client.post('/api/bots/missing/duplicate').status_code==404
        client.post('/api/vault/import',files={'file':('a.zip',archive([('a.png',png('Gizmo'))]),'application/zip')})
        bot=client.post('/api/bots',json={'title':'Editor','personality':'Edit carefully','profile':'fast'}).json()['id']
        client.put('/api/budget/limits/bot:'+bot,json={'daily':'2.5','monthly':'10'})
        client.post(f'/api/bots/{bot}/memory',json={'content':'A private fact'})
        with service.db() as c:
            c.execute('INSERT INTO messages VALUES (?,?,?,?,?)',('message',bot,'user','Private conversation',1))
        clone=client.post(f'/api/bots/{bot}/duplicate').json()['id']
        original,duplicate=({b['id']:b for b in client.get('/api/bots').json()}[key] for key in (bot,clone))
        assert duplicate['name']==original['name']+' (copy)'
        for field in ('title','personality','profile','shape','color'): assert duplicate[field]==original[field]
        assert duplicate['character']['name']==original['character']['name']
        assert client.get(f'/api/bots/{clone}/avatar').content==client.get(f'/api/bots/{bot}/avatar').content
        assert client.get(f'/api/bots/{clone}/memory').json()==[]
        assert client.get(f'/api/bots/{clone}/messages').json()==[]
        assert client.get('/api/budget').json()['bots'][clone]==client.get('/api/budget').json()['bots'][bot]
        assert client.delete(f'/api/bots/{bot}').status_code==200
        assert client.get(f'/api/bots/{clone}/avatar').status_code==200
        assert client.get('/api/vault/status').json()['available']==0
        assert client.delete(f'/api/bots/{clone}').status_code==200
        assert client.get('/api/vault/status').json()['available']==1
