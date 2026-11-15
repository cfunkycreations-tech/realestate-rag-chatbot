import asyncio
import pytest
from funkbot.tool_bridge import ToolBridge
from funkbot.tools import ToolError
from test_tool_runtime import make_context


@pytest.mark.asyncio
async def test_live_approval_card_can_be_answered_immediately_and_is_audited(tmp_path):
    ctx,_=make_context(tmp_path);events=[];holder={}
    def emit(event):
        events.append(event)
        if event['type']=='tool.proposed': holder['bridge'].submit(event['call_id'],'approve_once')
    bridge=ToolBridge(ctx,emit);holder['bridge']=bridge
    result=await bridge.execute('write_note',{'filename':'ok.txt','content':'safe'})
    assert result['status']=='completed' and (tmp_path/'workspaces'/ctx.bot_id/'ok.txt').read_text()=='safe'
    assert [e['type'] for e in events]==['tool.proposed','tool.decision','tool.finished']
    with pytest.raises(ToolError): bridge.submit(events[0]['call_id'],'approve')


@pytest.mark.asyncio
async def test_run_grant_never_leaves_an_unanswered_waiter(tmp_path):
    ctx,_=make_context(tmp_path);events=[];holder={}
    def emit(event):
        events.append(event)
        if event['type']=='tool.proposed' and not ctx.run_grants: holder['bridge'].submit(event['call_id'],'approve')
    bridge=ToolBridge(ctx,emit);holder['bridge']=bridge
    await bridge.execute('write_note',{'filename':'first.txt','content':'one'})
    await bridge.execute('write_note',{'filename':'second.txt','content':'two'})
    assert [e['decision'] for e in events if e['type']=='tool.decision']==['approve','run_grant']
    assert bridge.broker.pending=={}


@pytest.mark.asyncio
async def test_cancelling_live_approval_prevents_execution(tmp_path):
    ctx,_=make_context(tmp_path);events=[];bridge=ToolBridge(ctx,events.append)
    task=asyncio.create_task(bridge.execute('write_note',{'filename':'cancel.txt','content':'no'}))
    await asyncio.sleep(0);assert events[0]['type']=='tool.proposed'
    bridge.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert not (tmp_path/'workspaces').exists()
    with pytest.raises(ToolError): bridge.submit(events[0]['call_id'],'approve')


@pytest.mark.asyncio
async def test_failed_event_delivery_removes_waiter_and_aborts_call(tmp_path):
    ctx,_=make_context(tmp_path)
    def broken(_): raise RuntimeError('disconnected')
    bridge=ToolBridge(ctx,broken)
    with pytest.raises(RuntimeError): await bridge.execute('write_note',{'filename':'cancel.txt','content':'no'})
    assert bridge.broker.pending=={} and not (tmp_path/'workspaces').exists()
    with ctx.db() as c: assert c.execute('SELECT status FROM tool_calls').fetchone()['status']=='failed'
