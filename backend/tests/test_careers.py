from fastapi.testclient import TestClient

import app as service
from test_app import setup
from test_vault import archive, png


def role(pid='software-architect', **over):
    base = {'id': pid, 'title': 'Software Architect', 'department': 'Engineering', 'level': 'senior',
            'personality': 'Calm, systems-minded.', 'job_description': 'Designs systems.',
            'instructions': 'Always write an ADR before changing architecture.',
            'responsibilities': ['Own the architecture'], 'model_tier': 'advanced',
            'permission_boundaries': ['Never deploy to production'], 'escalation': ['Security risk found'],
            'mentorship_eligible': True}
    base.update(over)
    return base


def test_requires_auth():
    with TestClient(service.app) as client:
        assert client.get('/api/role-presets').status_code == 401
        assert client.post('/api/role-presets/import', json={'presets': [role()]}).status_code == 401
        assert client.post('/api/bots/birth', json={'mode': 'surprise'}).status_code == 401
        assert client.get('/api/bots/x/career').status_code == 401


def test_import_validation_duplicates_and_versioning():
    with TestClient(service.app) as client:
        setup(client)
        r = client.post('/api/role-presets/import', json={'presets': [
            role(), role('qa-engineer', title='QA Engineer'), role(), {'id': 'Bad Id'}, role('x1', model_tier='GODMODE')]})
        out = {(i['id'], i['outcome']) for i in r.json()['results']}
        assert ('software-architect', 'created') in out and ('qa-engineer', 'created') in out
        assert ('software-architect', 'invalid') in out  # duplicate inside the import
        assert ('x1', 'invalid') in out and ('Bad Id', 'invalid') in out
        # identical re-import is a no-op; changed content becomes version 2
        again = client.post('/api/role-presets/import', json={'presets': [role(), role('qa-engineer', title='QA Engineer', instructions='New text.')]}).json()
        assert {i['id']: i['outcome'] for i in again['results']} == {'software-architect': 'unchanged', 'qa-engineer': 'new_version'}
        versions = client.get('/api/role-presets/qa-engineer/versions').json()
        assert [v['version'] for v in versions] == [1, 2]
        assert client.get('/api/role-presets/nope/versions').status_code == 404


def test_owner_customization_is_not_silently_replaced():
    with TestClient(service.app) as client:
        setup(client)
        client.post('/api/role-presets/import', json={'presets': [role()]})
        assert client.put('/api/role-presets/software-architect', json=role(instructions='Owner edit.')).json()['version'] == 2
        skipped = client.post('/api/role-presets/import', json={'presets': [role(instructions='Pack update.')]}).json()
        assert skipped['results'][0]['outcome'] == 'skipped_customized'
        current = {p['id']: p for p in client.get('/api/role-presets').json()}['software-architect']
        assert current['instructions'] == 'Owner edit.' and current['customized'] is True
        forced = client.post('/api/role-presets/import', json={'presets': [role(instructions='Pack update.')], 'overwrite_customized': True}).json()
        assert forced['results'][0]['outcome'] == 'new_version'
        assert len(client.get('/api/role-presets/software-architect/versions').json()) == 3


def test_export_round_trips_into_a_fresh_import():
    with TestClient(service.app) as client:
        setup(client)
        client.post('/api/role-presets/import', json={'presets': [role(), role('qa-engineer', title='QA Engineer')]})
        pack = client.get('/api/role-presets/export').json()
        assert pack['format'] == 'funkbot-role-pack' and len(pack['presets']) == 2
        again = client.post('/api/role-presets/import', json={'presets': pack['presets']}).json()
        assert {i['outcome'] for i in again['results']} == {'unchanged'}


def test_birth_choose_career_with_vault_character_and_precedence():
    with TestClient(service.app) as client:
        setup(client)
        client.post('/api/role-presets/import', json={'presets': [role()]})
        data = archive([(f'{i}.png', png(f'Ghost{i}')) for i in range(3)])
        assert client.post('/api/vault/import', files={'file': ('v.zip', data, 'application/zip')}).status_code == 200
        born = client.post('/api/bots/birth', json={'mode': 'choose', 'preset_id': 'software-architect'}).json()
        assert born['character']['name'].startswith('Ghost')
        bot = next(b for b in client.get('/api/bots').json() if b['id'] == born['id'])
        assert bot['title'] == 'Software Architect' and bot['name'] == born['character']['name']
        assert 'PROFESSIONAL INSTRUCTIONS' in bot['personality'] and 'ADR' in bot['personality']
        assert 'Never deploy to production' in bot['personality']
        career = client.get(f"/api/bots/{born['id']}/career").json()['career']
        assert career['preset_id'] == 'software-architect' and career['preset_version'] == 1
        assert career['level'] == 'senior' and career['model_tier'] == 'ADVANCED'
        assert career['history'][0]['event'] == 'born' and career['history'][0]['detail']['birth_mode'] == 'choose'


def test_birth_surprise_and_errors():
    with TestClient(service.app) as client:
        setup(client)
        assert client.post('/api/bots/birth', json={'mode': 'surprise'}).status_code == 409  # no presets yet
        client.post('/api/role-presets/import', json={'presets': [role()]})
        assert client.post('/api/bots/birth', json={'mode': 'choose'}).status_code == 400
        assert client.post('/api/bots/birth', json={'mode': 'choose', 'preset_id': 'missing'}).status_code == 404
        assert client.post('/api/bots/birth', json={'mode': 'wild'}).status_code == 422
        born = client.post('/api/bots/birth', json={'mode': 'surprise'}).json()
        assert born['career']['preset_id'] == 'software-architect' and born['character'] is None


def test_career_snapshot_survives_preset_changes_and_existing_bots_untouched():
    with TestClient(service.app) as client:
        setup(client)
        old = client.post('/api/bots', json={'name': 'Existing Bot', 'title': 'Hand made'}).json()
        client.post('/api/role-presets/import', json={'presets': [role()]})
        born = client.post('/api/bots/birth', json={'mode': 'choose', 'preset_id': 'software-architect'}).json()
        client.put('/api/role-presets/software-architect', json=role(instructions='Changed later.'))
        career = client.get(f"/api/bots/{born['id']}/career").json()['career']
        assert career['preset_version'] == 1 and 'ADR' in career['career']['instructions']
        assert client.get(f"/api/bots/{old['id']}/career").json()['career'] is None
        assert next(b for b in client.get('/api/bots').json() if b['id'] == old['id'])['title'] == 'Hand made'


def test_workforce_capacity_limit(monkeypatch):
    monkeypatch.setattr(service, 'MAX_BOTS', 1)
    with TestClient(service.app) as client:
        setup(client)
        client.post('/api/role-presets/import', json={'presets': [role()]})
        assert client.post('/api/bots/birth', json={'mode': 'surprise'}).status_code == 200
        assert client.post('/api/bots/birth', json={'mode': 'surprise'}).status_code == 409
