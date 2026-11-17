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
