import time
from fastapi.testclient import TestClient
import app as service


def test_single_bot_mission_continues_across_multiple_tool_rounds(monkeypatch):
    from test_app import FakeClient,setup,configure_budget
    from test_live_tools import tool_reply,final_reply
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    FakeClient.responses=[*[tool_reply('notify_owner',{'title':'Progress','message':f'Step {i}'}) for i in range(6)],final_reply()]
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);c.put('/api/budget/prices/smart',json={'prompt':'1','completion':'2','max_prompt_tokens':100000,'max_completion_tokens':512});bot=c.post('/api/bots',json={'name':'Worker'}).json()['id']
        mid=c.post('/api/missions',json={'title':'Multi-step','instructions':'Plan and work','bot_id':bot}).json()['id']
        for _ in range(200):
            mission=c.get('/api/missions/'+mid).json()
            if mission['status'] in ('done','failed'): break
            time.sleep(.02)
        assert mission['status']=='done',mission
        assert len([n for n in c.get('/api/inbox/notices').json() if n['kind']=='bot'])==6
        assert any(event['type']=='delta' for event in mission['runs'][0]['log'])
