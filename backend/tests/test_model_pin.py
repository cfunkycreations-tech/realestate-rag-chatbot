"""Per-Bot model pin. Every model response is mocked; no network or paid provider is contacted."""
import time

import pytest
from fastapi.testclient import TestClient

import app as service
from test_app import FakeClient, setup, configure_budget
from test_budget_chat import answer
from test_economy import price, finish, attribution, give_career


class Recorder(FakeClient):
    models = []

    def stream(self, *args, **kwargs):
        body = kwargs.get('json') or {}
        Recorder.models.append(body.get('model'))
        return self.responses.pop(0)


def test_pin_is_validated_and_needs_auth():
    with TestClient(service.app) as c:
        assert c.get('/api/bots/x/model-pin').status_code == 401
        setup(c)
        bot = c.post('/api/bots', json={'name': 'Scout'}).json()['id']
        assert c.get(f'/api/bots/{bot}/model-pin').json() == {'pin': None}
        assert c.put(f'/api/bots/{bot}/model-pin', json={'gateway': 'evil', 'model': 'm'}).status_code == 422
        assert c.put(f'/api/bots/{bot}/model-pin', json={'gateway': 'openrouter', 'model': ''}).status_code == 422
        assert c.put('/api/bots/nope/model-pin', json={'gateway': 'openrouter', 'model': 'm'}).status_code == 404
        assert c.put(f'/api/bots/{bot}/model-pin', json={'gateway': 'openrouter', 'model': 'vendor/my-model'}).status_code == 200
        assert c.get(f'/api/bots/{bot}/model-pin').json()['pin'] == {'gateway': 'openrouter', 'model': 'vendor/my-model'}
        assert c.delete(f'/api/bots/{bot}/model-pin').status_code == 200
        assert c.get(f'/api/bots/{bot}/model-pin').json() == {'pin': None}


def test_pinned_model_is_sent_and_a_career_tier_does_not_move_the_bot(monkeypatch):
    Recorder.models = []
    Recorder.responses = [answer(), answer(), answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', Recorder)
    with TestClient(service.app) as c:
        setup(c); configure_budget(c); price(c, 'cheap-bulk', '0.05', '0.1')
        bot = c.post('/api/bots', json={'name': 'Hired', 'profile': 'smart'}).json()['id']
        give_career(bot, 'LIGHT')
        run = c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id']; finish(c, run)
        assert attribution(run)['effective_profile'] == 'cheap-bulk'      # without a pin the tier lowers it
        assert Recorder.models[-1] != 'vendor/my-model'
        assert c.put(f'/api/bots/{bot}/model-pin', json={'gateway': 'openrouter', 'model': 'vendor/my-model'}).status_code == 200
        run = c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id']; finish(c, run)
        a = attribution(run)
        assert (a['effective_profile'], a['adjustment']) == ('smart', None)
        assert Recorder.models[-1] == 'vendor/my-model'
        assert c.delete(f'/api/bots/{bot}/model-pin').status_code == 200
        run = c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id']; finish(c, run)
        assert attribution(run)['effective_profile'] == 'cheap-bulk' and Recorder.models[-1] != 'vendor/my-model'


def test_economy_ceiling_still_beats_a_pin_and_deleting_the_bot_removes_it(monkeypatch):
    Recorder.models = []
    Recorder.responses = [answer(), answer()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', Recorder)
    with TestClient(service.app) as c:
        setup(c); configure_budget(c); price(c, 'fast', '0.1', '0.2')
        bot = c.post('/api/bots', json={'name': 'Scout', 'profile': 'smart'}).json()['id']
        assert c.put(f'/api/bots/{bot}/model-pin', json={'gateway': 'openrouter', 'model': 'vendor/pricey'}).status_code == 200
        assert c.put('/api/economy', json={'economy': {'enabled': True, 'ceiling_tier': 'STANDARD', 'prefer_free': True}}).status_code == 200
        run = c.post(f'/api/bots/{bot}/chat', json={'content': 'Hi'}).json()['job_id']; finish(c, run)
        a = attribution(run)
        assert a['effective_profile'] == 'fast' and Recorder.models[-1] != 'vendor/pricey'   # the owner's cost ceiling wins
        assert c.delete(f'/api/bots/{bot}').status_code == 200
        with service.db() as db:
            assert db.execute('SELECT COUNT(*) FROM bot_model_pins').fetchone()[0] == 0
