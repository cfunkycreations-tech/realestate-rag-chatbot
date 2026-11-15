from datetime import datetime,timezone
from fastapi.testclient import TestClient
import app as service
from test_app import setup,configure_budget,FakeClient
from test_live_tools import tool_reply,final_reply
from test_missions_api import wait_mission


def test_analytics_actual_ledger_runs_approvals_and_csv(monkeypatch):
    FakeClient.responses=[tool_reply(),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        assert c.get('/api/analytics?start=2026-01-01&end=2026-01-01').status_code==401
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'=Bad formula'}).json()['id']
        mid=c.post('/api/missions',json={'title':'Note','instructions':'Write','bot_id':bot}).json()['id'];waiting=wait_mission(c,mid,{'waiting_approval'});run=waiting['runs'][0]['run_id'];call=c.get(f'/api/jobs/{run}/tool-calls').json()[0]
        c.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'deny'});wait_mission(c,mid,{'done'})
        day=datetime.now(timezone.utc).date().isoformat();data=c.get(f'/api/analytics?start={day}&end={day}').json()['rows'];row=next(r for r in data if r['bot_id']==bot)
        assert row['runs']==1 and row['completed']==1 and row['failed']==0 and row['profile']=='smart'
        assert row['prompt_tokens']==500 and row['completion_tokens']==90 and row['cost_usd']==0.00068
        assert row['denials']==1 and row['approvals']==0 and row['average_latency_ms'] is not None
        csv=c.get(f'/api/analytics.csv?start={day}&end={day}');assert csv.status_code==200 and "'=Bad formula" in csv.text
        assert c.get('/api/analytics?start=2020-01-01&end=2022-01-01').status_code==400
