import copy
import json
import time
from pathlib import Path
from fastapi.testclient import TestClient
import app as service
from test_app import setup,configure_budget,FakeClient
from test_live_tools import tool_reply,final_reply,until_calls
from test_missions_api import wait_mission


def test_workflow_migration_preserves_existing_project_files(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    engine=create_engine('sqlite:///'+str(tmp_path/'old.db'))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0021_work_artifacts');c.commit()
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Kept','Editor','prompt','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO projects VALUES ('p','Project','keep','b',1,1)")
        c.exec_driver_sql("INSERT INTO work_artifacts VALUES ('a',NULL,'p',NULL,NULL,'data.txt',X'6869',1)");c.commit()
        command.upgrade(cfg,'head');c.commit()
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
        assert c.exec_driver_sql("SELECT data FROM work_artifacts WHERE id='a'").scalar()==b'hi'
        assert c.exec_driver_sql("SELECT name FROM bots WHERE id='b'").scalar()=='Kept'
        assert c.exec_driver_sql('SELECT COUNT(*) FROM workflow_versions').scalar()==0


def test_demonstration_versions_and_sequential_replay_are_real_and_independent(monkeypatch):
    captured=[]
    class Client(FakeClient):
        def stream(self,*args,**kwargs):captured.append(copy.deepcopy(kwargs['json']));return super().stream(*args,**kwargs)
    FakeClient.responses=[tool_reply(),final_reply(),final_reply(),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',Client)
    with TestClient(service.app) as c:
        assert c.get('/api/workflows').status_code==401
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        source=c.post('/api/missions',json={'title':'Original','instructions':'Original task','bot_id':bot}).json()['id'];waiting=wait_mission(c,source,{'waiting_approval'});run=waiting['runs'][0]['run_id'];card=until_calls(c,run)[0]
        c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision',json={'decision':'approve_once'});wait_mission(c,source,{'done'})
        draft=c.post(f'/api/missions/{source}/workflow');assert draft.status_code==200;wid=draft.json()['id'];detail=c.get(f'/api/workflows/{wid}').json()
        assert detail['steps']==['Original task'] and detail['demonstration']==[{'tool':'write_note','status':'completed'}]
        corrected={'name':'Corrected','bot_id':bot,'steps':['First corrected step','Second corrected step'],'change_note':'Fixed the order','expected_version':1}
        assert c.put(f'/api/workflows/{wid}',json=corrected).json()['version']==2
        assert c.put(f'/api/workflows/{wid}',json=corrected).status_code==409
        detail=c.get(f'/api/workflows/{wid}').json();assert [v['version'] for v in detail['versions']]==[2,1] and detail['versions'][1]['steps']==['Original task']
        replay=c.post(f'/api/workflows/{wid}/replay',json={'version':2});assert replay.status_code==200;mid=replay.json()['mission_id'];mission=wait_mission(c,mid,{'done','failed'})
        assert mission['status']=='done' and len(mission['runs'])==2 and all(r['status']=='done' for r in mission['runs'])
        prompts=[p['messages'][-1]['content'] for p in captured if p['messages'][-1]['role']=='user']
        assert 'First corrected step' in prompts[-2] and 'Second corrected step' in prompts[-1] and 'untrusted data' in prompts[-1] and 'All done.' in prompts[-1]
        assert c.get(f'/api/workflows/{wid}').json()['replays'][0]['mission_id']==mid
        with service.db() as db: snapshot=json.loads(db.execute('SELECT steps FROM workflow_replays WHERE mission_id=?',(mid,)).fetchone()['steps'])
        assert snapshot==corrected['steps']
        assert c.delete(f'/api/workflows/{wid}').status_code==200
        assert c.get(f'/api/missions/{mid}').json()['status']=='done'
        with service.db() as db: assert db.execute('SELECT workflow_id FROM workflow_replays WHERE mission_id=?',(mid,)).fetchone()['workflow_id'] is None


def test_replay_separate_tool_approval_stop_and_budget_refusal(monkeypatch):
    FakeClient.responses=[tool_reply(),final_reply(),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        wid=c.post('/api/workflows',json={'name':'Review','bot_id':bot,'steps':['Write a note','Next step']}).json()['id']
        mid=c.post(f'/api/workflows/{wid}/replay',json={'version':1}).json()['mission_id'];waiting=wait_mission(c,mid,{'waiting_approval'});run=waiting['runs'][0]['run_id'];card=until_calls(c,run)[0]
        assert c.get(f'/api/missions/{mid}').json()['status']=='waiting_approval'
        assert c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision',json={'decision':'deny'}).status_code==200
        done=wait_mission(c,mid,{'done','failed'});assert done['status']=='done' and len(done['runs'])==2
        assert not (service.DATA/'workspaces'/bot/'approved.txt').exists()
        FakeClient.responses=[tool_reply()];mid=c.post(f'/api/workflows/{wid}/replay',json={'version':1}).json()['mission_id'];waiting=wait_mission(c,mid,{'waiting_approval'});run=waiting['runs'][0]['run_id'];card=until_calls(c,run)[0]
        assert c.post(f'/api/missions/{mid}/cancel').status_code==200;assert wait_mission(c,mid,{'cancelled'})['status']=='cancelled'
        assert c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision',json={'decision':'approve_once'}).status_code==409
        assert not (service.DATA/'workspaces'/bot/'approved.txt').exists()
        c.put(f'/api/budget/limits/bot:{bot}',json={'daily':'0','monthly':None});FakeClient.responses=[final_reply()]
        mid=c.post(f'/api/workflows/{wid}/replay',json={'version':1}).json()['mission_id'];failed=wait_mission(c,mid,{'failed'});assert 'budget' in failed['error'].lower() and len(FakeClient.responses)==1


def test_workflow_validation_pause_restart_and_no_silent_replay(monkeypatch):
    FakeClient.responses=[tool_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id']
        assert c.post('/api/workflows',json={'name':'x','bot_id':bot,'steps':[]}).status_code==422
        assert c.post('/api/workflows',json={'name':'x','bot_id':bot,'steps':[' ']}).status_code==400
        assert c.post('/api/workflows',json={'name':'x','bot_id':bot,'steps':['x'*2501]}).status_code==400
        assert c.post('/api/workflows',json={'name':'x','bot_id':'missing','steps':['x']}).status_code==404
        wid=c.post('/api/workflows',json={'name':'Work','bot_id':bot,'steps':['Step']}).json()['id']
        assert c.post(f'/api/workflows/{wid}/replay',json={'version':2}).status_code==404
        mid=c.post(f'/api/workflows/{wid}/replay',json={'version':1}).json()['mission_id'];wait_mission(c,mid,{'waiting_approval'})
        assert c.put('/api/control/pause',json={'paused':True}).status_code==200
        assert c.get(f'/api/missions/{mid}').json()['status']=='cancelled'
        assert c.post(f'/api/workflows/{wid}/replay',json={'version':1}).status_code==423
        c.put('/api/control/pause',json={'paused':False})
        # Simulate a backend restart between steps: the replay is failed, not rescheduled.
        with service.db() as db:
            now=time.time();db.execute("INSERT INTO missions VALUES ('interrupted','x','x',NULL,'running',NULL,NULL,?,?)",(now,now));db.execute("INSERT INTO mission_assignees VALUES ('interrupted',0,?)",(bot,));db.execute("INSERT INTO workflow_replays VALUES ('interrupted',?,1,'[\"step\"]',?)",(wid,now))
        service.mark_interrupted_runs();assert c.get('/api/missions/interrupted').json()['status']=='failed'


def test_file_share_destination_constraints_survive_between_workflow_steps(monkeypatch):
    captured=[]
    class Client(FakeClient):
        def stream(self,*args,**kwargs):
            captured.append(copy.deepcopy(kwargs['json']))
            if len(captured)==3:
                gateways=json.loads(service.config('gateways'));gateways['openrouter']['url']='https://changed.example/v1';service.set_config('gateways',json.dumps(gateways))
            return super().stream(*args,**kwargs)
    FakeClient.responses=[tool_reply('attach_mission_result',{'name':'out.txt','content':'draft'})];monkeypatch.setattr(service.httpx,'AsyncClient',Client)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Scout'}).json()['id'];p=c.post('/api/projects',json={'name':'Project'}).json()['id'];fid=c.post(f'/api/projects/{p}/artifacts',files={'file':('source.txt',b'private workflow data')}).json()['id']
        wid=c.post('/api/workflows',json={'name':'Workflow','bot_id':bot,'steps':['Read the source','Use prior result']}).json()['id'];mid=c.post(f'/api/workflows/{wid}/replay',json={'version':1}).json()['mission_id'];c.put(f'/api/projects/{p}/missions/{mid}')
        first=wait_mission(c,mid,{'waiting_approval'});run=first['runs'][0]['run_id'];card=until_calls(c,run)[0];FakeClient.responses.extend([tool_reply('read_work_file',{'artifact_id':fid}),final_reply(),final_reply()]);c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision',json={'decision':'deny'})
        for _ in range(100):
            calls=c.get(f'/api/jobs/{run}/tool-calls').json()
            if len(calls)>1: break
            time.sleep(.02)
        share=calls[1];assert share['status']=='pending';c.post(f'/api/jobs/{run}/tool-calls/{share["id"]}/decision',json={'decision':'approve_once'})
        failed=wait_mission(c,mid,{'failed'});assert 'destination changed' in failed['error'] and len(captured)==3 and len(failed['runs'])==2
