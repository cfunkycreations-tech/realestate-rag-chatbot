import asyncio
import json
import uuid
import pytest
import app as service
from funkbot.tool_runtime import ToolContext, execute
from funkbot.tools import ToolError


def make_context(tmp_path):
    bot_id=str(uuid.uuid4());run_id=str(uuid.uuid4());events=[]
    with service.db() as c:
        c.execute('INSERT INTO bots VALUES (?,?,?,?,?,?,?,?)',(bot_id,'Bot','Editor','instructions','mint','round','smart',1))
        c.execute('INSERT INTO runs VALUES (?,?,?,?,?)',(run_id,bot_id,'running',1,1))
    ctx=ToolContext(service.db,tmp_path,run_id,bot_id,lambda text:text.replace('secret','[redacted]'),['example.com'],[],events.append)
    return ctx,events


@pytest.mark.asyncio
async def test_deny_and_approve_once_never_create_unapproved_notes(tmp_path):
    ctx,events=make_context(tmp_path);decisions=[]
    async def deny(call): decisions.append(call);return 'deny'
    result=await execute(ctx,'write_note',{'filename':'denied.txt','content':'no'},deny)
    assert result['status']=='denied' and not (tmp_path/'workspaces'/ctx.bot_id/'denied.txt').exists()
    async def once(call): decisions.append(call);return 'approve_once'
    result=await execute(ctx,'write_note',{'filename':'one.txt','content':'my secret'},once)
    assert result['status']=='completed' and (tmp_path/'workspaces'/ctx.bot_id/'one.txt').read_text()=='my [redacted]'
    result=await execute(ctx,'write_note',{'filename':'two.txt','content':'two'},once)
    assert result['status']=='completed' and len(decisions)==3
    assert len([e for e in events if e['type']=='tool.proposed'])==3
    with service.db() as c:
        assert c.execute("SELECT COUNT(*) FROM tool_audit WHERE action='approve_once'").fetchone()[0]==2


@pytest.mark.asyncio
async def test_approve_is_run_scoped_and_every_call_is_surfaced_and_audited(tmp_path):
    ctx,events=make_context(tmp_path);decisions=[]
    async def grant(call): decisions.append(call);return 'approve'
    await execute(ctx,'write_note',{'filename':'one.txt','content':'one'},grant)
    await execute(ctx,'write_note',{'filename':'two.txt','content':'two'},grant)
    assert len(decisions)==1
    assert [e['decision'] for e in events if e['type']=='tool.decision']==['approve','run_grant']
    with service.db() as c:
        assert c.execute("SELECT COUNT(*) FROM tool_audit WHERE action='run_grant'").fetchone()[0]==1
    other,other_events=make_context(tmp_path)
    await execute(other,'write_note',{'filename':'other.txt','content':'other'},grant)
    assert len(decisions)==2 and other_events[1]['decision']=='approve'


@pytest.mark.asyncio
async def test_read_only_runs_automatically_but_enforces_web_policy(tmp_path):
    ctx,events=make_context(tmp_path);ctx.allow.append('127.0.0.1')
    async def never(_): pytest.fail('read tool should not prompt')
    result=await execute(ctx,'web_fetch',{'url':'http://127.0.0.1'},never)
    assert result['status']=='failed' and 'Private' in result['result']['error']
    assert events[0]['status']=='approved'
    with service.db() as c:
        assert [r['action'] for r in c.execute('SELECT action FROM tool_audit ORDER BY id')]==['proposed','read_auto_approved','started','failed']


@pytest.mark.asyncio
async def test_wrong_bot_or_finished_run_never_executes(tmp_path):
    ctx,_=make_context(tmp_path);ctx.bot_id=str(uuid.uuid4())
    async def approve(_): return 'approve_once'
    with pytest.raises(ToolError,match='no longer active'): await execute(ctx,'write_note',{'filename':'x.txt','content':'x'},approve)
    assert not (tmp_path/'workspaces').exists()


@pytest.mark.asyncio
async def test_cancelled_pending_approval_does_not_write(tmp_path):
    ctx,_=make_context(tmp_path);waiting=asyncio.Event()
    async def wait(_): waiting.set();await asyncio.Event().wait()
    task=asyncio.create_task(execute(ctx,'write_note',{'filename':'x.txt','content':'x'},wait))
    await waiting.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    with service.db() as c:
        assert c.execute('SELECT status FROM tool_calls').fetchone()['status']=='failed'
    assert not (tmp_path/'workspaces').exists()


@pytest.mark.asyncio
async def test_notifier_failure_is_audited_and_does_not_write(tmp_path):
    ctx,_=make_context(tmp_path)
    def fail(_): raise RuntimeError('Client unavailable')
    ctx.notify=fail
    async def approve(_): return 'approve_once'
    with pytest.raises(RuntimeError): await execute(ctx,'write_note',{'filename':'x.txt','content':'x'},approve)
    with service.db() as c:
        assert c.execute('SELECT status FROM tool_calls').fetchone()['status']=='failed'
        assert [r['action'] for r in c.execute('SELECT action FROM tool_audit ORDER BY id')]==['proposed','interrupted']
    assert not (tmp_path/'workspaces').exists()
