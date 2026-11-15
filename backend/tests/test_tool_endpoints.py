import asyncio
import threading
from fastapi.testclient import TestClient
import app as service
from funkbot.tool_bridge import ToolBridge
from funkbot.tool_runtime import ToolContext
from test_app import setup
from test_tool_runtime import make_context


def test_authenticated_live_decisions_and_durable_audit(tmp_path):
    with TestClient(service.app) as client:
        assert client.get('/api/jobs/anything/tool-calls').status_code==401
        assert client.post('/api/jobs/anything/tool-calls/anything/decision',json={'decision':'approve'}).status_code==401
        setup(client)
        ctx,_=make_context(tmp_path)
        pending=threading.Event();done=threading.Event();events=[]
        def emit(item):
            events.append(item)
            if item['type']=='tool.proposed': pending.set()
        bridge=ToolBridge(ctx,emit)
        service.jobs[ctx.run_id]={'tool_bridge':bridge}
        async def launch():
            async def run():
                try: await bridge.execute('write_note',{'filename':'test.txt','content':'secret'})
                finally: done.set()
            asyncio.create_task(run())
        client.portal.call(launch)
        assert pending.wait(5)
        calls=client.get(f'/api/jobs/{ctx.run_id}/tool-calls').json()
        call=calls[0]['id']
        assert calls[0]['arguments']['content']=='[redacted]' and calls[0]['status']=='pending'
        assert client.post(f'/api/jobs/not-this-run/tool-calls/{call}/decision',json={'decision':'approve'}).status_code==404
        assert client.post(f'/api/jobs/{ctx.run_id}/tool-calls/{call}/decision',json={'decision':'unknown'}).status_code==422
        assert client.post(f'/api/jobs/{ctx.run_id}/tool-calls/{call}/decision',json={'decision':'approve_once'}).status_code==200
        assert done.wait(5)
        assert client.post(f'/api/jobs/{ctx.run_id}/tool-calls/{call}/decision',json={'decision':'approve'}).status_code==409
        saved=client.get(f'/api/jobs/{ctx.run_id}/tool-calls').json()[0]
        assert saved['status']=='completed'
        assert [row['action'] for row in saved['audit']]==['proposed','approve_once','started','completed']
        assert (tmp_path/'workspaces'/ctx.bot_id/'test.txt').read_text()=='[redacted]'
        assert client.get('/api/jobs/missing/tool-calls').status_code==404


def test_stale_pending_approval_cannot_execute_without_live_broker(tmp_path):
    from funkbot.tool_audit import propose
    with TestClient(service.app) as client:
        setup(client);ctx,_=make_context(tmp_path)
        with service.db() as db: call=propose(db,ctx.run_id,ctx.bot_id,'write_note',{'filename':'x.txt','content':'x'},lambda x:x)
        assert client.post(f'/api/jobs/{ctx.run_id}/tool-calls/{call}/decision',json={'decision':'approve'}).status_code==409
        assert not (tmp_path/'workspaces').exists()


def test_account_audit_pages_and_bot_delete_removes_its_recorded_activity(tmp_path):
    from funkbot.tool_audit import propose
    with TestClient(service.app) as client:
        assert client.get('/api/tool-audit').status_code==401
        setup(client);ctx,_=make_context(tmp_path)
        with service.db() as db:
            db.execute("UPDATE runs SET status='done' WHERE id=?",(ctx.run_id,))
            for n in range(23): propose(db,ctx.run_id,ctx.bot_id,'write_note',{'filename':f'{n}.txt','content':'safe'},lambda x:x)
        first=client.get('/api/tool-audit').json()
        assert len(first['calls'])==20 and first['next_before']
        second=client.get('/api/tool-audit',params={'before':first['next_before']}).json()
        assert len(second['calls'])==3 and second['next_before'] is None
        assert len({call['id'] for call in first['calls']+second['calls']})==23
        assert first['calls'][0]['audit'][0]['action']=='proposed'
        assert client.delete(f'/api/bots/{ctx.bot_id}').status_code==200
        assert client.get('/api/tool-audit').json()['calls']==[]
        with service.db() as db:
            assert db.execute('SELECT COUNT(*) FROM tool_audit').fetchone()[0]==0


def test_tool_audit_export_auth_snapshot_scope_redaction_and_csv(tmp_path):
    import csv, io, json
    from funkbot.tool_audit import propose
    with TestClient(service.app) as client:
        assert client.get('/api/tool-audit/export').status_code==401
        setup(client);ctx,_=make_context(tmp_path)
        secret='late-key-"with-escape-12345'
        with service.db() as db:
            call=propose(db,ctx.run_id,ctx.bot_id,'write_note',{'filename':'safe.txt','content':secret},lambda x:x)
            db.execute('UPDATE tool_calls SET result=? WHERE id=?',(json.dumps({'sensitive':secret}),call))
            db.execute('INSERT INTO tool_calls (id,run_id,bot_id,tool_name,risk,arguments,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                       ('=danger',ctx.run_id,ctx.bot_id,'mcp_call','send',json.dumps({'arguments_json':json.dumps({secret:secret})}),'denied',1,1))
            db.execute('INSERT INTO tool_audit (call_id,action,created_at) VALUES (?,?,?)',('=danger','policy_denied',1))
            db.execute('INSERT INTO tool_calls (id,run_id,bot_id,tool_name,risk,arguments,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                       ('file',ctx.run_id,ctx.bot_id,'read_work_file','send',json.dumps({'review_json':json.dumps({'content':secret})}),'denied',2,2))
        client.put('/api/settings/gateways/openrouter',json={'url':'https://example.com/v1','key':secret})
        response=client.get('/api/tool-audit/export',params={'bot_id':ctx.bot_id})
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        calls=response.json();assert len(calls)==3
        assert calls[0]['arguments']['content']=='[redacted]' and calls[0]['result']['sensitive']=='[redacted]'
        assert calls[0]['audit'][0]['action']=='proposed'
        assert json.loads(calls[1]['arguments']['arguments_json'])=={'[redacted]':'[redacted]'}
        assert json.loads(calls[2]['arguments']['review_json'])=={'content':'[redacted]'}
        assert client.get('/api/tool-audit/export?bot_id=other').json()==[]
        csv_response=client.get('/api/tool-audit/export?format=csv')
        rows=list(csv.DictReader(io.StringIO(csv_response.text)))
        assert rows[1]['id']=="'=danger" and json.loads(rows[0]['audit'])[0]['action']=='proposed'
        assert secret not in csv_response.text and client.get('/api/tool-audit/export?format=xml').status_code==422
