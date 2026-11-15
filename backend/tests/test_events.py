import json
from fastapi.testclient import TestClient
import app as service
from test_app import FakeClient, FakeStream, setup, configure_budget


def test_events_auth_order_cursor_and_redaction(monkeypatch):
    key='opaque-gateway-private-value'
    FakeClient.responses = [FakeStream(200, [
        'data: '+json.dumps({'choices':[{'delta':{'content':'Finished without exposing '+key}}]}),
        'data: [DONE]',
    ])]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as client:
        assert client.get('/api/events').status_code == 401
        setup(client)
        client.put('/api/settings/gateways/openrouter', json={'url':'https://gateway.test/v1','key':key})
        configure_budget(client)
        bot=client.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=client.post(f'/api/bots/{bot}/chat',json={'content':'Hello '+key}).json()['job_id']
        assert client.get(f'/api/jobs/{run}/events').status_code == 200
        page=client.get('/api/events?limit=2').json()
        later=client.get(f"/api/events?since={page['next_cursor']}&limit=20").json()
        events=page['events']+later['events']
        assert [e['type'] for e in events] == ['run.started','bot.state_changed','message.sent','message.sent','bot.state_changed','run.finished']
        assert [e['id'] for e in events] == sorted(set(e['id'] for e in events))
        assert events[2]['payload']['role']=='user' and events[3]['payload']['role']=='assistant'
        assert key not in json.dumps(events) and '[redacted]' in json.dumps(events)
        assert client.get(f"/api/events?since={later['next_cursor']}").json()['events']==[]
        assert client.get('/api/events?since=-1').status_code == 422
        assert client.delete(f'/api/bots/{bot}').status_code == 200
        assert client.get('/api/events').json()['events'] == []  # Bot deletion removes its event history.


def test_failed_run_emits_error_event(monkeypatch):
    FakeClient.responses = [FakeStream(401, [])]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as client:
        setup(client)
        configure_budget(client)
        bot=client.post('/api/bots',json={'name':'Scout'}).json()['id']
        run=client.post(f'/api/bots/{bot}/chat',json={'content':'Hi'}).json()['job_id']
        client.get(f'/api/jobs/{run}/events')
        events=client.get('/api/events').json()['events']
        assert events[-2]['type']=='error.raised'
        assert events[-1]['type']=='run.finished' and events[-1]['payload']['status']=='failed'
