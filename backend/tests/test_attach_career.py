from fastapi.testclient import TestClient

import app as service
from funkbot import careers
from test_app import setup
from test_career_progression import bots


def test_existing_bot_career_preview_then_apply_never_touches_the_bot_and_is_all_or_nothing():
    with TestClient(service.app) as c:
        assert c.get('/api/career/unassigned').status_code == 401
        setup(c)
        a, b = bots(c, 'Ava', 'Ben')
        with service.db() as db:
            careers.import_presets(db, [{'id': 'writer', 'title': 'Writer', 'department': 'Content', 'level': 'junior', 'model_tier': 'light',
                                         'personality': 'Warm.', 'instructions': 'Write clearly.', 'permission_boundaries': [], 'escalation': []}])
        un = c.get('/api/career/unassigned').json()
        assert {x['id'] for x in un['bots']} == {a, b} and [p['id'] for p in un['presets']] == ['writer']
        before = {x['id']: x for x in c.get('/api/bots').json()}
        item = {'bot_id': a, 'preset_id': 'writer'}
        pv = c.post('/api/career/attach', json={'assignments': [item]}).json()
        assert pv['applied'] is False and 'Name' in pv['previews'][0]['keeps']
        assert c.get(f'/api/bots/{a}/career').json()['career'] is None      # preview wrote nothing
        assert c.post('/api/career/attach', json={'assignments': [item, {'bot_id': b, 'preset_id': 'nope'}], 'confirm': True}).status_code == 400
        assert c.get(f'/api/bots/{a}/career').json()['career'] is None      # all or nothing
        assert c.post('/api/career/attach', json={'assignments': [item, item], 'confirm': True}).status_code == 400
        assert c.post('/api/career/attach', json={'assignments': [item], 'confirm': 'yes'}).status_code == 422
        r = c.post('/api/career/attach', json={'assignments': [item, {'bot_id': b, 'preset_id': 'writer'}], 'confirm': True}).json()
        assert r['applied'] and r['count'] == 2
        assert {x['id']: x for x in c.get('/api/bots').json()} == before    # name, title, personality untouched
        hist = c.get(f'/api/bots/{a}/career').json()['career']['history']
        assert [h['event'] for h in hist] == ['attached']
        assert c.post('/api/career/attach', json={'assignments': [item], 'confirm': True}).status_code == 400   # already has one
        assert c.get('/api/career/unassigned').json()['bots'] == []
