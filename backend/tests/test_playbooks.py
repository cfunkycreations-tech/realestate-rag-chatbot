from fastapi.testclient import TestClient

import app as service
from test_app import setup
from test_career_progression import bots


def test_playbook_assignments_are_owner_only_validated_display_only_and_follow_bot_deletion():
    with TestClient(service.app) as c:
        assert c.get('/api/playbooks/assignments').status_code == 401
        assert c.put('/api/playbooks/assignments/swarm', json={'bot_id': 'x'}).status_code == 401
        setup(c)
        a, b = bots(c, 'Ava', 'Ben')
        assert c.get('/api/playbooks/assignments').json() == {'assignments': {}}
        assert c.put('/api/playbooks/assignments/nope', json={'bot_id': a}).status_code == 404
        assert c.put('/api/playbooks/assignments/swarm', json={'bot_id': 'ghost'}).status_code == 404
        assert c.put('/api/playbooks/assignments/swarm', json={'bot_id': a, 'extra': 1}).status_code == 422
        before = c.get('/api/settings/tool-policies').json()
        assert c.put('/api/playbooks/assignments/swarm', json={'bot_id': a}).json()['assignments'] == {'swarm': a}
        assert c.put('/api/playbooks/assignments/morning-brief', json={'bot_id': b}).status_code == 200
        assert c.get('/api/settings/tool-policies').json() == before      # picking a Bot changes no permission
        assert c.delete(f'/api/bots/{a}').status_code in (200, 204)
        assert c.get('/api/playbooks/assignments').json()['assignments'] == {'morning-brief': b}   # deleted Bot is dropped
        assert c.put('/api/playbooks/assignments/morning-brief', json={'bot_id': None}).json()['assignments'] == {}


def test_routine_can_be_created_paused_in_one_step_and_defaults_to_live():
    with TestClient(service.app) as c:
        setup(c)
        a, = bots(c, 'Ava')
        body = {'title': 't', 'instructions': 'i', 'bot_id': a, 'cron': '30 7 * * *', 'timezone': 'UTC'}
        assert c.post('/api/routines', json={**body, 'paused': 'yes'}).status_code == 422
        r1 = c.post('/api/routines', json={**body, 'paused': True}).json()['id']
        r2 = c.post('/api/routines', json=body).json()['id']
        paused = {x['id']: x['paused'] for x in c.get('/api/routines').json()}
        assert paused == {r1: 1, r2: 0}


def test_delete_all_bots_needs_typed_confirmation_and_is_all_or_nothing():
    import time
    with TestClient(service.app) as c:
        assert c.post('/api/bots/delete-all', json={'confirm': 'DELETE ALL'}).status_code == 401
        setup(c)
        a, b = bots(c, 'Ava', 'Ben')
        assert c.post('/api/bots/delete-all', json={'confirm': 'yes'}).status_code == 400
        assert c.post('/api/bots/delete-all', json={'confirm': 'DELETE ALL', 'x': 1}).status_code == 422
        assert len(c.get('/api/bots').json()) == 2
        with service.db() as db:                       # one busy Bot blocks the whole batch
            db.execute("INSERT INTO runs VALUES ('busy',?,'running',?,?)", (b, time.time(), time.time()))
        assert c.post('/api/bots/delete-all', json={'confirm': 'DELETE ALL'}).status_code == 409
        assert len(c.get('/api/bots').json()) == 2     # nothing was deleted, not even the idle Bot
        with service.db() as db:
            db.execute("DELETE FROM runs WHERE id='busy'")
        assert c.post('/api/bots/delete-all', json={'confirm': 'DELETE ALL'}).json() == {'deleted': 2}
        assert c.get('/api/bots').json() == []


def test_vault_purge_removes_unworn_sprites_keeps_worn_ones_and_needs_confirmation():
    from test_vault import png, archive
    with TestClient(service.app) as c:
        assert c.post('/api/vault/purge', json={'confirm': 'PURGE'}).status_code == 401
        setup(c)
        a, = bots(c, 'Ava')
        c.post('/api/vault/import', files={'file': ('a.zip', archive([('a.png', png('One')), ('b.png', png('Two')), ('c.png', png('Three'))]), 'application/zip')})
        assert c.post(f'/api/bots/{a}/sprite', json={'adopt_character_name': False}).status_code == 200
        assert c.get('/api/vault/status').json()['total'] == 3
        assert c.post('/api/vault/purge', json={'confirm': 'nope'}).status_code == 400
        assert c.get('/api/vault/status').json()['total'] == 3
        assert c.post('/api/vault/purge', json={'confirm': 'PURGE'}).json() == {'removed': 2, 'kept_in_use': 1}
        assert c.get('/api/vault/status').json()['total'] == 1
        assert c.get('/api/bots').json()[0]['id'] == a
