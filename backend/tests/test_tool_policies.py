import json
from fastapi.testclient import TestClient
import app as service
from test_app import setup,configure_budget,FakeClient
from test_live_tools import tool_reply,final_reply,until_calls,get_events


def test_tool_policy_configuration_and_write_auto_forbidden():
    with TestClient(service.app) as c:
        assert c.get('/api/settings/tool-policies').status_code==401
        setup(c);assert c.get('/api/settings/tool-policies').json()=={'web_fetch':'auto','write_note':'ask','create_followup':'ask','create_handoff':'ask','attach_mission_result':'ask','read_work_file':'ask','web_search':'ask','computer_shell':'ask','send_bot_message':'ask'}
        assert c.put('/api/settings/tool-policies',json={'web_fetch':'auto','write_note':'auto','create_followup':'ask'}).status_code==422
        assert c.put('/api/settings/tool-policies',json={'web_fetch':'ask','write_note':'deny','create_followup':'ask'}).status_code==200
        assert c.get('/api/settings/tool-policies').json()['write_note']=='deny'


def test_denied_write_never_runs_and_is_audited(monkeypatch):
    FakeClient.responses=[tool_reply(),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);c.put('/api/settings/tool-policies',json={'web_fetch':'auto','write_note':'deny','create_followup':'ask'})
        bot=c.post('/api/bots',json={'name':'Scout'}).json()['id'];run=c.post(f'/api/bots/{bot}/chat',json={'content':'Write a note'}).json()['job_id']
        assert get_events(c,run)[-1]['type']=='done';call=c.get(f'/api/jobs/{run}/tool-calls').json()[0]
        assert call['status']=='denied' and 'policy_denied' in [entry['action'] for entry in call['audit']]
        assert not (service.DATA/'workspaces'/bot/'approved.txt').exists() and c.get('/api/tool-approvals').json()==[]


def test_ask_web_fetch_requires_approval_and_still_blocks_private_targets(monkeypatch):
    FakeClient.responses=[tool_reply('web_fetch',{'url':'http://127.0.0.1/private'}),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);c.put('/api/settings/tool-policies',json={'web_fetch':'ask','write_note':'ask','create_followup':'ask'})
        bot=c.post('/api/bots',json={'name':'Scout'}).json()['id'];run=c.post(f'/api/bots/{bot}/chat',json={'content':'Fetch'}).json()['job_id'];call=until_calls(c,run)[0]
        assert call['risk']=='read' and call['status']=='pending'
        assert c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'}).status_code==200
        get_events(c,run);call=c.get(f'/api/jobs/{run}/tool-calls').json()[0]
        assert call['status']=='failed' and 'Private' in json.dumps(call['result'])


def test_deny_policy_changed_while_pending_wins_over_approval(monkeypatch):
    FakeClient.responses=[tool_reply(),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id'];run=c.post(f'/api/bots/{bot}/chat',json={'content':'Save'}).json()['job_id'];call=until_calls(c,run)[0]
        c.put('/api/settings/tool-policies',json={'web_fetch':'auto','write_note':'deny','create_followup':'ask'})
        assert c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'}).status_code==200
        get_events(c,run);call=c.get(f'/api/jobs/{run}/tool-calls').json()[0]
        assert call['status']=='denied' and 'policy_denied' in [a['action'] for a in call['audit']]
        assert not (service.DATA/'workspaces'/bot/'approved.txt').exists()


def test_corrupted_policy_configuration_fails_closed():
    with TestClient(service.app) as c:
        setup(c)
        with service.db() as db: db.execute("INSERT OR REPLACE INTO config VALUES ('tool_policies','not-json')")
        assert set(c.get('/api/settings/tool-policies').json().values())=={'deny'}
