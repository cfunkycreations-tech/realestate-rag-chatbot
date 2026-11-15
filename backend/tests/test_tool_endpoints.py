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
