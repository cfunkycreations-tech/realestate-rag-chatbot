import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import app as service


def setup(client):
    assert client.post('/api/auth/setup', json={'password': 'correct horse battery staple', 'setup_token': service.ensure_setup_token(service.DATA)}).status_code == 200


def test_auth_and_persistent_bot_deletion():
    with TestClient(service.app) as client:
        assert client.get('/api/bots').status_code == 401
        setup(client)
        assert client.post('/api/auth/setup', json={'password': 'another password'}).status_code == 409
        bot = client.post('/api/bots', json={'name': 'Scout'}).json()['id']
        with service.db() as c:
            c.execute('INSERT INTO messages VALUES (?,?,?,?,?)', ('msg', bot, 'user', 'Remember my preference', 1))
        assert client.get(f'/api/bots/{bot}/messages').json()[0]['content'] == 'Remember my preference'
        assert client.delete(f'/api/bots/{bot}').status_code == 200
        with service.db() as c:
            assert c.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0
        client.post('/api/auth/logout')
        assert client.get('/api/bots').status_code == 401
        assert client.post('/api/auth/login', json={'password': 'wrong password'}).status_code == 401
        assert client.post('/api/auth/login', json={'password': 'correct horse battery staple'}).status_code == 200


def test_gateway_key_is_encrypted_and_not_returned():
    with TestClient(service.app) as client:
        setup(client)
        key = 'sk-test-secret-abcdef123456'
        assert client.put('/api/settings/gateways/openrouter', json={'url': 'https://example.com/v1', 'key': key}).status_code == 200
        response = client.get('/api/settings')
        assert key not in response.text
        assert response.json()['gateways']['openrouter']['has_key']
        assert key not in service.config('gateways')
        assert service.redact('do not reveal '+key) == 'do not reveal [redacted]'
        assert client.put('/api/settings/gateways/openrouter', json={'url': 'https://example.com/v1', 'clear_key': True}).status_code == 200
        assert not client.get('/api/settings').json()['gateways']['openrouter']['has_key']


class FakeStream:
    def __init__(self, status, lines): self.status, self.lines = status, lines
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def raise_for_status(self):
        if self.status >= 400:
            request = httpx.Request('POST', 'https://gateway.test/v1/chat/completions')
            raise httpx.HTTPStatusError('bad response', request=request, response=httpx.Response(self.status, request=request))
    async def aiter_lines(self):
        for line in self.lines: yield line


class FakeClient:
    responses = []
    def __init__(self, *args, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def stream(self, *args, **kwargs): return self.responses.pop(0)


def create_test_bot():
    bot = {'id': 'b1', 'name': 'Scout', 'title': 'Helper', 'personality': 'Be helpful', 'color': 'mint', 'shape': 'round', 'profile': 'smart'}
    with service.db() as c:
        c.execute('INSERT INTO bots VALUES (?,?,?,?,?,?,?,?)', (*bot.values(), 1))
    return bot


@pytest.mark.asyncio
async def test_failover_usage_and_persisted_response(monkeypatch):
    bot = create_test_bot()
    service.set_config('profiles', json.dumps({'smart': [{'gateway':'openrouter','model':'first'}, {'gateway':'omniroute','model':'second'}]}))
    FakeClient.responses = [FakeStream(429, []), FakeStream(200, [
        'data: {"choices":[{"delta":{"content":"Hello!"}}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":2,"cost":0.01}}',
        'data: [DONE]'])]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    job = {'events': [], 'done': False}
    await service.run_chat(job, bot, [{'role':'user','content':'Hi'}], 'smart')
    assert [e['type'] for e in job['events']] == ['delta', 'done']
    assert job['events'][0]['content'] == 'Hello!'
    with service.db() as c:
        assert c.execute('SELECT content FROM messages').fetchone()[0] == 'Hello!'
        usage = c.execute('SELECT * FROM usage').fetchone()
        assert usage['model'] == 'second' and usage['prompt_tokens'] == 5 and usage['cost'] == 0.01


@pytest.mark.asyncio
async def test_non_transient_failure_does_not_fall_back(monkeypatch):
    bot = create_test_bot()
    service.set_config('profiles', json.dumps({'smart': [{'gateway':'openrouter','model':'first'}, {'gateway':'omniroute','model':'second'}]}))
    FakeClient.responses = [FakeStream(401, []), FakeStream(200, [])]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    job = {'events': [], 'done': False}
    await service.run_chat(job, bot, [], 'smart')
    assert job['events'][0]['type'] == 'error'
    assert len(FakeClient.responses) == 1


def test_chat_http_flow_and_restart_persistence(monkeypatch):
    FakeClient.responses = [FakeStream(200, [
        'data: {"choices":[{"delta":{"content":"A useful answer."}}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":2,"completion_tokens":3}}',
        'data: [DONE]'])]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as client:
        setup(client)
        bot = client.post('/api/bots', json={'name': 'Scout'}).json()['id']
        run = client.post(f'/api/bots/{bot}/chat', json={'content':'Make a plan'}).json()['job_id']
        events = client.get(f'/api/jobs/{run}/events')
        payloads = [json.loads(line[6:]) for line in events.text.splitlines() if line.startswith('data: ')]
        assert events.status_code == 200
        assert ''.join(e.get('content', '') for e in payloads) == 'A useful answer.'
        assert payloads[-1]['type'] == 'done'
    # A fresh client and database initialization simulate a server restart.
    service.init_db()
    with TestClient(service.app) as client:
        assert client.post('/api/auth/login', json={'password':'correct horse battery staple'}).status_code == 200
        messages = client.get(f'/api/bots/{bot}/messages').json()
        assert [m['content'] for m in messages] == ['Make a plan', 'A useful answer.']
        assert client.get('/api/settings').json()['usage']['completion_tokens'] == 3


def test_setup_requires_one_time_token():
    with TestClient(service.app) as client:
        assert client.post('/api/auth/setup', json={'password':'long enough password'}).status_code == 403
        assert client.post('/api/auth/setup', json={'password':'long enough password', 'setup_token':'wrong'}).status_code == 403
        token = service.ensure_setup_token(service.DATA)
        assert token not in client.get('/api/auth/status').text
        assert client.post('/api/auth/setup', json={'password':'long enough password', 'setup_token':token}).status_code == 200
        assert not (service.DATA / 'setup.token').exists()
        assert client.post('/api/auth/setup', json={'password':'long enough password', 'setup_token':token}).status_code == 409


def test_login_backoff_is_persistent():
    with TestClient(service.app) as client:
        setup(client)
        client.post('/api/auth/logout')
        for _ in range(5):
            assert client.post('/api/auth/login', json={'password':'incorrect password'}).status_code == 401
        response = client.post('/api/auth/login', json={'password':'correct horse battery staple'})
        assert response.status_code == 429 and int(response.headers['retry-after']) >= 1
        service.init_db()
        assert client.post('/api/auth/login', json={'password':'correct horse battery staple'}).status_code == 429
        with service.db() as c:
            c.execute('UPDATE login_guard SET locked_until=0 WHERE id=1')
        assert client.post('/api/auth/login', json={'password':'correct horse battery staple'}).status_code == 200
        with service.db() as c:
            assert c.execute('SELECT failures FROM login_guard').fetchone()[0] == 0


def test_slice_one_database_upgrade_preserves_existing_data(tmp_path, monkeypatch):
    """The additive login guard must not recreate or erase the user's old DB."""
    old = tmp_path / 'old.db'
    import sqlite3
    with sqlite3.connect(old) as c:
        c.executescript('''
        CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE bots (id TEXT PRIMARY KEY, name TEXT NOT NULL, title TEXT NOT NULL, personality TEXT NOT NULL, color TEXT NOT NULL, shape TEXT NOT NULL, profile TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE messages (id TEXT PRIMARY KEY, bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE usage (id INTEGER PRIMARY KEY, bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL, gateway TEXT, model TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, cost REAL, created_at REAL NOT NULL);
        ''')
        c.execute('INSERT INTO config VALUES (?,?)', ('password_hash', service.ph.hash('existing password')))
        c.execute('INSERT INTO bots VALUES (?,?,?,?,?,?,?,?)', ('old-bot','Existing','Assistant','Help','mint','round','smart',1))
        c.execute('INSERT INTO messages VALUES (?,?,?,?,?)', ('old-msg','old-bot','user','Hello from before',2))
        c.execute('INSERT INTO usage VALUES (?,?,?,?,?,?,?,?)', (1,'old-bot','openrouter','test',3,4,0.01,2))
    monkeypatch.setattr(service, 'DB', old)
    service.init_db()
    with TestClient(service.app) as client:
        assert client.get('/api/auth/status').json()['setup'] is True
        assert client.post('/api/auth/login', json={'password':'existing password'}).status_code == 200
        assert client.get('/api/bots').json()[0]['name'] == 'Existing'
        assert client.get('/api/bots/old-bot/messages').json()[0]['content'] == 'Hello from before'
        assert client.get('/api/settings').json()['usage']['completion_tokens'] == 4
