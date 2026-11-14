from fastapi.testclient import TestClient
import app as service
from test_app import setup
from test_vault import png, archive


def test_new_bot_uses_vault_name_only_when_requested_and_job_is_separate():
    with TestClient(service.app) as client:
        setup(client)
        client.post('/api/vault/import', files={'file':('a.zip',archive([('a.png',png('Zigzag',role='Cosmic Gnome'))]),'application/zip')})
        created=client.post('/api/bots',json={'name':'Fallback','title':'Editor','personality':'Edit thoughtfully','use_character_name':True}).json()
        bot=next(b for b in client.get('/api/bots').json() if b['id']==created['id'])
        assert (bot['name'],bot['title'],bot['character']['role'])==('Zigzag','Editor','Cosmic Gnome')
        prompt=service.bot_system_prompt(bot)
        assert 'Zigzag' in prompt and 'Editor' in prompt and 'Cosmic Gnome' not in prompt
        legacy=client.post('/api/bots',json={'name':'Existing client','title':'Researcher'}).json()
        assert next(b for b in client.get('/api/bots').json() if b['id']==legacy['id'])['name']=='Existing client'


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
