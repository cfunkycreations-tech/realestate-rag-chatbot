import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

# Keep module initialization out of the real workspace database.
os.environ['FUNK_DATA_DIR'] = tempfile.mkdtemp(prefix='funk-bot-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as service


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'DB', tmp_path / 'test.db')
    service.jobs.clear()
    service.init_db()


def setup(client):
    assert client.post('/api/auth/setup', json={'password': 'correct horse battery staple'}).status_code == 200


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
        assert events.status_code == 200 and 'A useful answer.' in events.text and '"done"' in events.text
    # A fresh client and database initialization simulate a server restart.
    service.init_db()
    with TestClient(service.app) as client:
        assert client.post('/api/auth/login', json={'password':'correct horse battery staple'}).status_code == 200
        messages = client.get(f'/api/bots/{bot}/messages').json()
        assert [m['content'] for m in messages] == ['Make a plan', 'A useful answer.']
        assert client.get('/api/settings').json()['usage']['completion_tokens'] == 3
