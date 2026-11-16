import copy
import json
import time
from pathlib import Path
from fastapi.testclient import TestClient
import app as service
from test_app import setup,configure_budget,FakeClient
from test_groups_api import response
from test_live_tools import tool_reply,until_calls


def wait(c,dm,statuses):
    for _ in range(150):
        result=c.get('/api/bot-dms/'+dm).json()
        if result['turns'] and result['turns'][0]['status'] in statuses: return result
        time.sleep(.02)
    raise AssertionError(result)


def prepare(c):
    setup(c);configure_budget(c)
    a=c.post('/api/bots',json={'name':'Sender'}).json()['id'];b=c.post('/api/bots',json={'name':'Receiver'}).json()['id']
    dm=c.post('/api/bot-dms',json={'name':'Discussion','sender_id':a,'receiver_id':b}).json()['id']
    return a,b,dm


def test_dm_real_two_speakers_scoped_memories_and_continuation(monkeypatch):
    payloads=[]
    class Recording(FakeClient):
        def stream(self,*args,**kwargs):payloads.append(copy.deepcopy(kwargs['json']));return super().stream(*args,**kwargs)
    monkeypatch.setattr(service.httpx,'AsyncClient',Recording)
    with TestClient(service.app) as c:
        assert c.get('/api/bot-dms').status_code==401
        a,b,dm=prepare(c);c.post(f'/api/bots/{a}/memory',json={'content':'Only sender memory'});c.post(f'/api/bots/{b}/memory',json={'content':'Only receiver memory'})
        FakeClient.responses=[response('First Bot asks'),response('Second Bot answers'),response('Sender follows up'),response('Receiver follows up')]
        assert c.post(f'/api/bot-dms/{dm}/messages',json={'content':'Coordinate on the plan'}).status_code==200
        r=wait(c,dm,{'done','failed'});assert r['turns'][0]['status']=='done',r
        assert [(m['role'],m['content']) for m in r['messages']]==[('user','Coordinate on the plan'),('sender','First Bot asks'),('receiver','Second Bot answers')]
        assert [m['bot_id'] for m in r['messages']]==[None,a,b]
        assert 'Only sender memory' in payloads[0]['messages'][0]['content'] and 'Only receiver memory' not in payloads[0]['messages'][0]['content']
        assert 'Only receiver memory' in payloads[1]['messages'][0]['content'] and 'Only sender memory' not in payloads[1]['messages'][0]['content']
        assert 'First Bot asks' in payloads[1]['messages'][-1]['content'] and 'untrusted' in payloads[1]['messages'][-1]['content']
        assert c.get(f'/api/bots/{a}/messages').json()==[] and c.get(f'/api/bots/{b}/messages').json()==[]
        assert c.post(f'/api/bot-dms/{dm}/messages',json={'content':'Continue'}).status_code==200
        result=wait(c,dm,{'done','failed'});assert len(result['messages'])==6
        assert 'Second Bot answers' in payloads[2]['messages'][-1]['content']
        assert len([e for e in c.get('/api/events?since=0&limit=500').json()['events'] if e['type']=='bot_dm.message'])==4
        assert c.delete('/api/bot-dms/'+dm).status_code==200


def test_dm_stop_and_global_pause_cancel_approval_and_respect_budget(monkeypatch):
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        a,b,dm=prepare(c)
        FakeClient.responses=[tool_reply()];assert c.post(f'/api/bot-dms/{dm}/messages',json={'content':'Work'}).status_code==200
        for _ in range(150):
            approvals=c.get('/api/tool-approvals').json()
            if approvals: break
            time.sleep(.02)
        else: raise AssertionError('No approval')
        assert c.post(f'/api/bot-dms/{dm}/messages',json={'content':'Again'}).status_code==409
        assert c.delete(f'/api/bot-dms/{dm}').status_code==409
        assert c.delete(f'/api/bots/{b}').status_code==409
        assert c.post(f'/api/bot-dms/{dm}/stop').status_code==200
        assert wait(c,dm,{'cancelled'})['turns'][0]['status']=='cancelled'
        assert c.post(f'/api/jobs/{approvals[0]["run_id"]}/tool-calls/{approvals[0]["id"]}/decision',json={'decision':'approve_once'}).status_code==409
        assert not (service.DATA/'workspaces'/a/'approved.txt').exists()
        FakeClient.responses=[tool_reply()];c.post(f'/api/bot-dms/{dm}/messages',json={'content':'Try again'})
        for _ in range(150):
            if c.get('/api/tool-approvals').json(): break
            time.sleep(.02)
        else: raise AssertionError('No second approval')
        assert c.put('/api/control/pause',json={'paused':True}).status_code==200
        assert 'pause' in wait(c,dm,{'cancelled'})['turns'][0]['error']
        assert c.post(f'/api/bot-dms/{dm}/messages',json={'content':'Blocked'}).status_code==423
        c.put('/api/control/pause',json={'paused':False});c.put('/api/budget/limits/account',json={'daily':'0','monthly':None});FakeClient.responses=[response('never')]
        c.post(f'/api/bot-dms/{dm}/messages',json={'content':'Budget'});r=wait(c,dm,{'failed'});assert 'budget' in r['turns'][0]['error'].lower() and len(FakeClient.responses)==1


def test_dm_validation_missing_participant_and_restart():
    with TestClient(service.app) as c:
        a,b,dm=prepare(c)
        assert c.post('/api/bot-dms',json={'name':'same','sender_id':a,'receiver_id':a}).status_code==400
        assert c.post('/api/bot-dms',json={'name':'missing','sender_id':a,'receiver_id':'missing'}).status_code==404
        assert c.post(f'/api/bot-dms/{dm}/messages',json={'content':'   '}).status_code==400
        with service.db() as db: db.execute("INSERT INTO bot_dm_turns VALUES ('t',?,'running',NULL,NULL,1,1)",(dm,))
        service.mark_interrupted_runs();assert c.get('/api/bot-dms/'+dm).json()['turns'][0]['status']=='failed'
        assert c.delete(f'/api/bots/{b}').status_code==200
        assert c.post(f'/api/bot-dms/{dm}/messages',json={'content':'No receiver'}).status_code==409
        assert c.get('/api/bot-dms/'+dm).json()['dm']['receiver_id'] is None


def test_bot_dm_migration_preserves_workflows(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    engine=create_engine('sqlite:///'+str(tmp_path/'old.db'))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0022_workflows');c.commit()
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Kept','Editor','prompt','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO workflows VALUES ('w',NULL,1,1,1)")
        c.exec_driver_sql("INSERT INTO workflow_versions VALUES ('w',1,'Kept','b','[\"work\"]','',1)");c.commit()
        command.upgrade(cfg,'head');c.commit()
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0025_computer_permissions'
        assert c.exec_driver_sql("SELECT steps FROM workflow_versions WHERE workflow_id='w'").scalar()=='["work"]'
        assert c.exec_driver_sql('SELECT count(*) FROM bot_dms').scalar()==0


def test_receiver_requires_separate_tool_approval_and_own_budget(monkeypatch):
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        a,b,dm=prepare(c);FakeClient.responses=[response('Please help'),tool_reply(),response('Could not write')]
        c.post(f'/api/bot-dms/{dm}/messages',json={'content':'Please coordinate'})
        for _ in range(150):
            approvals=c.get('/api/tool-approvals').json()
            if approvals: break
            time.sleep(.02)
        else: raise AssertionError('Receiver approval missing')
        assert approvals[0]['bot_id']==b and approvals[0]['tool_name']=='write_note'
        assert c.post(f'/api/jobs/{approvals[0]["run_id"]}/tool-calls/{approvals[0]["id"]}/decision',json={'decision':'deny'}).status_code==200
        assert wait(c,dm,{'done'})['messages'][-1]['content']=='Could not write'
        assert not (service.DATA/'workspaces'/b/'approved.txt').exists()
        c.put(f'/api/budget/limits/bot:{b}',json={'daily':'0','monthly':None});FakeClient.responses=[response('Sender can run'),response('must not send')]
        c.post(f'/api/bot-dms/{dm}/messages',json={'content':'Try another'})
        failed=wait(c,dm,{'failed'});assert 'budget' in failed['turns'][0]['error'].lower() and failed['messages'][-1]['content']=='Sender can run' and len(FakeClient.responses)==1
