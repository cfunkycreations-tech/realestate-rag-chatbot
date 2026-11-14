import json
import time

from fastapi.testclient import TestClient

import app as service
from test_app import FakeClient, FakeStream, setup


def test_persisted_run_events_replay_after_restart(monkeypatch):
    FakeClient.responses = [FakeStream(200, [
        'data: ' + json.dumps({'choices':[{'delta':{'content':'A first chunk long enough to stream before the end. '}}]}),
        'data: ' + json.dumps({'choices':[{'delta':{'content':'Finished safely.'}}]}),
        'data: [DONE]',
    ])]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as client:
        setup(client)
        bot_id = client.post('/api/bots',json={'name':'Scout'}).json()['id']
        job_id = client.post(f'/api/bots/{bot_id}/chat',json={'content':'Hi'}).json()['job_id']
        payload = client.get(f'/api/jobs/{job_id}/events').text
        events = [json.loads(line[6:]) for line in payload.splitlines() if line.startswith('data: ')]
        assert events[0]['type'] == 'bot.state_changed'
        assert events[-1]['type'] == 'done'
        assert ''.join(event.get('content','') for event in events) == 'A first chunk long enough to stream before the end. Finished safely.'
        assert client.get(f'/api/bots/{bot_id}/latest-run').json()['status'] == 'done'
        last_id = events[-2]['id']
        replay = client.get(f'/api/jobs/{job_id}/events?after={last_id}').text
        assert '"type": "done"' in replay and '"content"' not in replay
    service.jobs.clear()
    with TestClient(service.app) as client:
        assert client.post('/api/auth/login',json={'password':'correct horse battery staple'}).status_code == 200
        assert client.get(f'/api/bots/{bot_id}/latest-run').json()['status'] == 'done'
        replayed = client.get(f'/api/jobs/{job_id}/events').text
        replay_events = [json.loads(line[6:]) for line in replayed.splitlines() if line.startswith('data: ')]
        assert ''.join(event.get('content','') for event in replay_events).endswith('Finished safely.')
        assert client.get(f'/api/bots/{bot_id}/messages').json()[-1]['content'].endswith('Finished safely.')


def test_existing_active_run_blocks_second_run_and_deletion():
    with TestClient(service.app) as client:
        setup(client)
        bot_id = client.post('/api/bots',json={'name':'Scout'}).json()['id']
        with service.db() as c:
            c.execute('INSERT INTO runs VALUES (?,?,?,?,?)',('active',bot_id,'running',time.time(),time.time()))
        assert client.post(f'/api/bots/{bot_id}/chat',json={'content':'duplicate'}).status_code == 409
        assert client.delete(f'/api/bots/{bot_id}').status_code == 409
        assert client.get(f'/api/bots/{bot_id}/messages').json() == []


def test_backend_restart_surfaces_interrupted_run():
    with TestClient(service.app) as client:
        setup(client)
        bot_id = client.post('/api/bots',json={'name':'Scout'}).json()['id']
        with service.db() as c:
            c.execute('INSERT INTO runs VALUES (?,?,?,?,?)',('unfinished',bot_id,'running',time.time(),time.time()))
            service.record_event(c, 'unfinished', 'delta', {'content':'Partial, safe output'})
    service.jobs.clear()
    with TestClient(service.app) as client:
        assert client.post('/api/auth/login',json={'password':'correct horse battery staple'}).status_code == 200
        latest = client.get(f'/api/bots/{bot_id}/latest-run').json()
        assert latest['status'] == 'failed' and 'restarted' in latest['message']
        events = client.get('/api/jobs/unfinished/events').text
        assert 'Partial, safe output' in events and 'restarted' in events
        # A subsequent start can proceed; the abandoned run no longer owns the Bot.
        with service.db() as c:
            c.execute('INSERT INTO runs VALUES (?,?,?,?,?)',('replacement',bot_id,'running',time.time(),time.time()))
