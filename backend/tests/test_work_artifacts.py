import io
import time
from pathlib import Path
from fastapi.testclient import TestClient
import app as service
from test_app import setup,configure_budget,FakeClient
from test_live_tools import tool_reply,final_reply,until_calls
from test_missions_api import wait_mission


def test_owner_files_are_scoped_bounded_and_survive_unlink(monkeypatch):
    FakeClient.responses=[final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        assert c.get('/api/projects/no/artifacts').status_code==401
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Owner'}).json()['id']
        mid=c.post('/api/missions',json={'title':'Mission','instructions':'Work','bot_id':bot}).json()['id'];wait_mission(c,mid,{'done'})
        p=c.post('/api/projects',json={'name':'P'}).json()['id'];other=c.post('/api/projects',json={'name':'Other'}).json()['id']
        data=b'\x00binary\xff<script>data</script>'
        r=c.post(f'/api/missions/{mid}/artifacts',files={'file':('test.bin',data,'text/html')});assert r.status_code==200;fid=r.json()['id']
        assert c.post(f'/api/projects/{p}/artifacts',files={'file':('project.txt',b'project','text/plain')}).status_code==200
        assert c.post(f'/api/projects/{p}/artifacts',files={'file':('../bad',b'bad')}).status_code==400
        assert c.post(f'/api/projects/{p}/artifacts',files={'file':('zero',b'')}).status_code==400
        assert c.post(f'/api/projects/{p}/artifacts',files={'file':('large',b'x'*(service.MAX_WORK_ARTIFACT+1))}).status_code==400
        assert c.get(f'/api/projects/{p}/artifacts/{fid}').status_code==404
        assert c.put(f'/api/projects/{p}/missions/{mid}').status_code==200
        items=c.get(f'/api/projects/{p}/artifacts').json();assert len(items)==2 and any(x['id']==fid and x['mission_id']==mid for x in items)
        result=c.get(f'/api/projects/{p}/artifacts/{fid}');assert result.content==data and result.headers['content-type']=='application/octet-stream' and result.headers['x-content-type-options']=='nosniff' and result.headers['content-disposition'].startswith('attachment;')
        assert c.get(f'/api/projects/{other}/artifacts/{fid}').status_code==404
        assert c.delete(f'/api/projects/{p}/artifacts/{fid}').status_code==404
        assert c.delete(f'/api/projects/{p}/missions/{mid}').status_code==200
        assert c.get(f'/api/projects/{p}/artifacts/{fid}').status_code==404 and c.get(f'/api/missions/{mid}/artifacts/{fid}').content==data
        assert c.delete(f'/api/missions/{mid}/artifacts/{fid}').status_code==200
        assert c.get(f'/api/missions/{mid}/artifacts/{fid}').status_code==404


def test_bot_result_is_individually_approved_scoped_and_linked_to_project(monkeypatch):
    FakeClient.responses=[tool_reply('attach_mission_result',{'name':'draft.md','content':'# Draft\nHello'}),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Editor'}).json()['id'];p=c.post('/api/projects',json={'name':'P'}).json()['id']
        mid=c.post('/api/missions',json={'title':'Draft','instructions':'Write a draft','bot_id':bot}).json()['id']
        for _ in range(100):
            runs=c.get(f'/api/missions/{mid}').json()['runs']
            if runs: break
            time.sleep(.02)
        run=runs[0]['run_id'];card=until_calls(c,run)[0]
        assert card['tool_name']=='attach_mission_result' and card['arguments']=={'name':'draft.md','content':'# Draft\nHello'}
        assert c.get(f'/api/missions/{mid}/artifacts').json()==[]
        assert c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision',json={'decision':'approve'}).status_code==400
        assert c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision',json={'decision':'approve_once'}).status_code==200
        wait_mission(c,mid,{'done'});files=c.get(f'/api/missions/{mid}/artifacts').json();assert len(files)==1 and files[0]['bot_id']==bot and files[0]['run_id']==run
        assert c.get(f'/api/missions/{mid}/artifacts/{files[0]["id"]}').content==b'# Draft\nHello'
        c.put(f'/api/projects/{p}/missions/{mid}');assert c.get(f'/api/projects/{p}/artifacts').json()[0]['id']==files[0]['id']
        call=c.get(f'/api/jobs/{run}/tool-calls').json()[0];assert call['status']=='completed' and call['result']['id']==files[0]['id']


def test_bot_result_denied_or_stopped_never_attaches(monkeypatch):
    FakeClient.responses=[tool_reply('attach_mission_result',{'name':'out.txt','content':'Result'}),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Editor'}).json()['id'];mid=c.post('/api/missions',json={'title':'Draft','instructions':'Write','bot_id':bot}).json()['id']
        for _ in range(100):
            runs=c.get(f'/api/missions/{mid}').json()['runs']
            if runs: break
            time.sleep(.02)
        run=runs[0]['run_id'];card=until_calls(c,run)[0]
        c.put('/api/settings/tool-policies',json={'web_fetch':'auto','write_note':'ask','create_followup':'ask','attach_mission_result':'deny'})
        c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision',json={'decision':'approve_once'});wait_mission(c,mid,{'done'})
        assert c.get(f'/api/jobs/{run}/tool-calls').json()[0]['status']=='denied' and c.get(f'/api/missions/{mid}/artifacts').json()==[]
        c.put('/api/settings/tool-policies',json={'web_fetch':'auto','write_note':'ask','create_followup':'ask'})
        assert c.get('/api/settings/tool-policies').json()['attach_mission_result']=='deny'


def test_upgrade_from_group_chats_preserves_existing_content(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    engine=create_engine('sqlite:///'+str(tmp_path/'old.db'))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0020_group_chats');c.commit()
        c.exec_driver_sql("INSERT INTO bots (id,name,title,personality,color,shape,profile,created_at) VALUES ('legacy','Old Bot','Editor','Helpful','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO projects VALUES ('p','Existing project','Keep me','legacy',1,1)");c.commit()
        command.upgrade(cfg,'head');c.commit()
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0021_work_artifacts'
        assert c.exec_driver_sql("SELECT name FROM bots WHERE id='legacy'").scalar()=='Old Bot'
        assert c.exec_driver_sql("SELECT description FROM projects WHERE id='p'").scalar()=='Keep me'
        assert c.exec_driver_sql('SELECT COUNT(*) FROM work_artifacts').scalar()==0


def test_invalid_or_stopped_bot_output_cannot_write(monkeypatch):
    FakeClient.responses=[tool_reply('attach_mission_result',{'name':'../escape.txt','content':'unsafe'}),final_reply(),tool_reply('attach_mission_result',{'name':'result.txt','content':'stopped'})];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Editor'}).json()['id']
        def start():
            mid=c.post('/api/missions',json={'title':'Draft','instructions':'Write','bot_id':bot}).json()['id']
            for _ in range(100):
                runs=c.get(f'/api/missions/{mid}').json()['runs']
                if runs: break
                time.sleep(.02)
            run=runs[0]['run_id'];return mid,run,until_calls(c,run)[0]
        mid,run,card=start();c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision',json={'decision':'approve_once'});wait_mission(c,mid,{'done'})
        assert c.get(f'/api/jobs/{run}/tool-calls').json()[0]['status']=='failed' and c.get(f'/api/missions/{mid}/artifacts').json()==[]
        mid,run,card=start();c.post(f'/api/missions/{mid}/cancel');wait_mission(c,mid,{'cancelled'})
        assert c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision',json={'decision':'approve_once'}).status_code==409
        assert c.get(f'/api/missions/{mid}/artifacts').json()==[]


def test_backup_snapshot_contains_artifacts_and_restore_migrates_them(tmp_path):
    import sqlite3
    from test_backup import keys
    from funkbot.backup import create,restore
    with TestClient(service.app) as c:
        setup(c);keys();p=c.post('/api/projects',json={'name':'P'}).json()['id'];payload=b'archive-test\x00bytes'
        fid=c.post(f'/api/projects/{p}/artifacts',files={'file':('snapshot.bin',payload)}).json()['id']
        output=io.BytesIO();create(service.DATA,service.DB,output);archive=tmp_path/'backup.zip';archive.write_bytes(output.getvalue())
        head,old=service.migration_revisions();stage=restore(archive,service.DATA,head,old)
        # Restore returns metadata; inspect the staged copy rather than the live database.
        with sqlite3.connect(stage/'funk.db') as restored:
            assert restored.execute('SELECT data FROM work_artifacts WHERE id=?',(fid,)).fetchone()[0]==payload


def test_direct_chat_cannot_attach_result_even_if_gateway_invents_tool(monkeypatch):
    from test_live_tools import get_events
    FakeClient.responses=[tool_reply('attach_mission_result',{'name':'no.txt','content':'unsafe'}),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Editor'}).json()['id']
        run=c.post(f'/api/bots/{bot}/chat',json={'content':'hello'}).json()['job_id'];get_events(c,run)
        call=c.get(f'/api/jobs/{run}/tool-calls').json()[0]
        assert call['status']=='denied' and not c.get('/api/tool-approvals').json()
        with service.db() as db: assert db.execute('SELECT count(*) FROM work_artifacts').fetchone()[0]==0


def test_tool_review_contains_the_exact_normalized_filename_and_redacted_text(monkeypatch):
    FakeClient.responses=[tool_reply('attach_mission_result',{'name':'  report.txt  ','content':'key private-token-abcdefgh123456'}),final_reply()];monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c);c.put('/api/settings/gateways/openrouter',json={'url':'https://example.com/v1','key':'private-token-abcdefgh123456'})
        bot=c.post('/api/bots',json={'name':'Editor'}).json()['id'];mid=c.post('/api/missions',json={'title':'Draft','instructions':'Write','bot_id':bot}).json()['id']
        for _ in range(100):
            runs=c.get(f'/api/missions/{mid}').json()['runs']
            if runs: break
            time.sleep(.02)
        run=runs[0]['run_id'];card=until_calls(c,run)[0];assert card['arguments']['name']=='report.txt' and 'private-token' not in card['arguments']['content']
        c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision',json={'decision':'approve_once'});wait_mission(c,mid,{'done'})
        item=c.get(f'/api/missions/{mid}/artifacts').json()[0];assert item['name']==card['arguments']['name']
        assert c.get(f'/api/missions/{mid}/artifacts/{item["id"]}').text==card['arguments']['content']


def test_artifact_quota_is_shared_and_atomic(monkeypatch):
    monkeypatch.setattr(service,'MAX_WORK_TOTAL',8)
    with TestClient(service.app) as c:
        setup(c);p=c.post('/api/projects',json={'name':'P'}).json()['id'];q=c.post('/api/projects',json={'name':'Q'}).json()['id']
        a=c.post(f'/api/projects/{p}/artifacts',files={'file':('a.txt',b'12345')}).json()['id']
        assert c.post(f'/api/projects/{q}/artifacts',files={'file':('b.txt',b'6789')}).status_code==400
        assert c.get(f'/api/projects/{q}/artifacts').json()==[]
        assert c.delete(f'/api/projects/{p}/artifacts/{a}').status_code==200
        assert c.post(f'/api/projects/{q}/artifacts',files={'file':('b.txt',b'6789')}).status_code==200
