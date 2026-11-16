import io
import json
import random
import zipfile

from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin

import app as service
import funkbot.vault as vault
from test_app import setup


def png(name=None, role='Illustrator', rarity='common'):
    info = PngImagePlugin.PngInfo()
    if name is not None: info.add_text('CharacterName', name)
    info.add_text('CharacterRole', role)
    info.add_text('Tags', 'design, cheerful')
    info.add_text('Notes', 'A thoughtful collaborator.')
    info.add_text('funk:rarity', rarity)
    output = io.BytesIO()
    Image.new('RGBA',(8,8),(50,100,150,128)).save(output,format='PNG',pnginfo=info)
    return output.getvalue()


def archive(entries):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for filename,data in entries: z.writestr(filename,data)
    return output.getvalue()


def test_slicer_import_hidden_assets_and_no_repeat_draw():
    names=[f'HiddenCharacter{i}' for i in range(15)]
    data=archive([(f'{i}.png',png(name)) for i,name in enumerate(names)])
    with TestClient(service.app) as client:
        assert client.post('/api/vault/import',files={'file':('input.zip',data,'application/zip')}).status_code == 401
        assert client.get('/api/vault/status').status_code == 401
        setup(client)
        old=client.post('/api/bots',json={'name':'Existing Bot'}).json()
        assert old['character'] is None
        result=client.post('/api/vault/import',files={'file':('input.zip',data,'application/zip')})
        assert result.status_code == 200 and result.json()=={'added':15,'duplicates':0,'invalid':0}
        again=client.post('/api/vault/import',files={'file':('input.zip',data,'application/zip')})
        assert again.status_code==409 and 'already uploaded' in again.json()['detail']
        assert client.get('/api/vault/status').json()['total']==15
        public=client.get('/api/vault/status').text+client.get('/api/bots').text
        assert all(name not in public for name in names)
        assert client.get(f"/api/bots/{old['id']}/avatar").status_code==404
        drawn=[]
        for i in range(16):
            response=client.post('/api/bots',json={'name':f'Bot {i}'})
            assert response.status_code==200
            bot=response.json()
            char=bot['character']
            assert char['name'] in names and char['role']=='Illustrator'
            assert char['tags']==['design','cheerful'] and char['notes']=='A thoughtful collaborator.'
            drawn.append(char['name'])
            image=client.get(char['avatar_url'])
            assert image.status_code==200 and image.headers['cache-control']=='private, no-store'
            assert image.content.startswith(b'\x89PNG')
            with Image.open(io.BytesIO(image.content)) as decoded:
                assert 'CharacterName' not in decoded.info
        assert len(set(drawn[:15]))==15
        assert drawn[15] in names
        client.post('/api/auth/logout')
        assert client.get(bot['character']['avatar_url']).status_code == 401


def test_vault_invalid_files_and_deleted_bot_return_character_to_pool(tmp_path):
    zip_data=archive([('valid.png',png('PrivateName')), ('same-name.png',png('PrivateName',role='Different')),
                      ('missing.png',png()), ('../unsafe.png',png('OtherName')), ('not.png',b'broken'), ('readme.txt',b'text')])
    with TestClient(service.app) as client:
        setup(client)
        r=client.post('/api/vault/import',files={'file':('vault.zip',zip_data,'application/zip')})
        assert r.json()=={'added':1,'duplicates':1,'invalid':4}
        assert 'PrivateName' not in r.text and 'OtherName' not in r.text
        assert not (tmp_path/'unsafe.png').exists()
        bot=client.post('/api/bots',json={'name':'One'}).json()
        assert bot['character']['name']=='PrivateName'
        assert client.get('/api/vault/status').json()['available']==0
        assert client.delete('/api/bots/'+bot['id']).status_code==200
        assert client.get('/api/vault/status').json()['available']==1
        assert client.post('/api/bots',json={'name':'Two'}).json()['character']['name']=='PrivateName'
        assert client.post('/api/vault/import',files={'file':('bad.zip',b'not zip','application/zip')}).status_code==400


def test_weighted_draw_uses_rarity_weights(monkeypatch):
    seeded=random.Random(42)
    monkeypatch.setattr(vault.secrets,'randbelow',seeded.randrange)
    with service.db() as c:
        c.execute('INSERT INTO bots VALUES (?,?,?,?,?,?,?,?)',('b','Bot','Helper','Be helpful','mint','round','smart',1))
        for rarity in ('common','legendary'):
            c.execute('INSERT INTO characters VALUES (?,?,?,?,?,?,?,?,?,?)',(rarity,rarity,rarity,rarity,'','[]','',rarity,0,1))
        counts={'common':0,'legendary':0}
        for _ in range(2000):
            c.execute('UPDATE characters SET drawn=0')
            result=vault.draw_character(c,'b')
            counts[result['rarity']]+=1
            c.execute('DELETE FROM bot_characters WHERE bot_id=?',('b',))
    assert 1850 < counts['common'] < 1990


def test_vault_metadata_never_returns_saved_gateway_key():
    secret='opaque-key-to-keep-private'
    zip_data=archive([('asset.png',png(secret,role='Role '+secret))])
    with TestClient(service.app) as client:
        setup(client)
        client.put('/api/settings/gateways/openrouter',json={'url':'https://openrouter.ai/api/v1','key':secret})
        result=client.post('/api/vault/import',files={'file':('assets.zip',zip_data,'application/zip')})
        assert result.json()['added']==1
        response=client.post('/api/bots',json={'name':'One'})
        assert secret not in response.text
        assert secret not in client.get('/api/bots').text
        with service.db() as c:
            row=c.execute('SELECT name,role FROM characters').fetchone()
            assert secret not in row['name'] and secret not in row['role']


def test_existing_vault_metadata_is_redacted_when_key_saved_later():
    secret='later-added-secret-value'
    zip_data=archive([('asset.png',png(secret))])
    with TestClient(service.app) as client:
        setup(client)
        assert client.post('/api/vault/import',files={'file':('assets.zip',zip_data,'application/zip')}).json()['added']==1
        bot=client.post('/api/bots',json={'name':'One'}).json()
        assert bot['character']['name']==secret
        client.put('/api/settings/gateways/openrouter',json={'url':'https://openrouter.ai/api/v1','key':secret})
        assert secret not in client.get('/api/bots').text


def test_packs_listed_blocked_when_repeated_and_removable():
    first=archive([(f'a{i}.png',png(f'PackA{i}')) for i in range(3)])
    second=archive([(f'b{i}.png',png(f'PackB{i}')) for i in range(2)])
    with TestClient(service.app) as client:
        assert client.get('/api/vault/packs').status_code==401
        setup(client)
        assert client.get('/api/vault/packs').json()==[]
        r=client.post('/api/vault/import',files={'file':('heroes.zip',first,'application/zip')})
        assert r.status_code==200 and r.json()['added']==3 and client.get('/api/vault/packs').json()[0]['name']=='heroes'
        # Same ZIP, even under another file name or collection label, is blocked.
        blocked=client.post('/api/vault/import',files={'file':('renamed.zip',first,'application/zip')},data={'collection':'Other'})
        assert blocked.status_code==409 and '"heroes"' in blocked.json()['detail']
        # A different ZIP reusing an existing pack name is blocked too.
        clash=client.post('/api/vault/import',files={'file':('x.zip',second,'application/zip')},data={'collection':'HEROES'})
        assert clash.status_code==409 and 'already exists' in clash.json()['detail']
        ok=client.post('/api/vault/import',files={'file':('villains.zip',second,'application/zip')},data={'collection':'Villains'})
        assert ok.status_code==200
        packs=client.get('/api/vault/packs').json()
        assert [p['name'] for p in packs]==['Villains','heroes']
        assert [p['characters'] for p in packs]==[2,3] and all(p['in_use']==0 for p in packs)
        assert 'PackA0' not in client.get('/api/vault/packs').text  # characters stay hidden
        assert client.get('/api/vault/status').json()['total']==5
        # A ZIP whose characters all exist already adds nothing and records no pack.
        repack=archive([(f'z{i}.png',png(f'PackA{i}')) for i in range(3)])
        none=client.post('/api/vault/import',files={'file':('again.zip',repack,'application/zip')})
        assert none.status_code==409 and 'Nothing new' in none.json()['detail']
        assert len(client.get('/api/vault/packs').json())==2
        hero=next(p for p in packs if p['name']=='heroes')
        removed=client.delete('/api/vault/packs/'+hero['id'])
        assert removed.json()=={'removed':3,'kept_in_use':0}
        assert client.get('/api/vault/status').json()['total']==2
        assert client.delete('/api/vault/packs/'+hero['id']).status_code==404
        # Removing a pack frees it for upload again.
        assert client.post('/api/vault/import',files={'file':('heroes.zip',first,'application/zip')}).json()['added']==3


def test_removing_pack_keeps_characters_assigned_to_bots(tmp_path):
    data=archive([('one.png',png('OnlyOne')),('two.png',png('Second'))])
    with TestClient(service.app) as client:
        setup(client)
        assert client.post('/api/vault/import',files={'file':('duo.zip',data,'application/zip')}).status_code==200
        pack=client.get('/api/vault/packs').json()[0]
        bot=client.post('/api/bots',json={'name':'Worker'}).json()
        listed=client.get('/api/vault/packs').json()[0]
        assert listed['in_use']==1 and listed['available']==1
        result=client.delete('/api/vault/packs/'+pack['id']).json()
        assert result=={'removed':1,'kept_in_use':1}
        assert client.get(bot['character']['avatar_url']).status_code==200
        status=client.get('/api/vault/status').json()
        assert status['total']==1 and status['unpacked']==1
