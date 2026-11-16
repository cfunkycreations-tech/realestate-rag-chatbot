import asyncio
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app as service
from funkbot import computer, computer_snapshot as snapshots, tool_protocol, tools
from funkbot.tool_runtime import execute
from test_tool_runtime import make_context
from test_app import FakeClient, setup, configure_budget
from test_live_tools import tool_reply, final_reply, until_calls, get_events


def test_opt_in_and_command_validation(monkeypatch):
    monkeypatch.delenv('FUNK_COMPUTER_ENABLED', raising=False)
    assert 'computer_shell' not in [x['function']['name'] for x in tool_protocol.declarations()]
    assert 'computer_shell' in [x['function']['name'] for x in tool_protocol.declarations(include_computer=True)]
    with pytest.raises(ValidationError): tools.ComputerArgs(command='x\x00y')
    with pytest.raises(ValidationError): tools.ComputerArgs(command='x', extra='bad')


@pytest.mark.asyncio
async def test_individual_approval_and_policy_recheck(tmp_path,monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1')
    ctx,events=make_context(tmp_path);calls=[];decisions=[]
    async def worker(context,command):
        calls.append(command)
        return {'output':'secret output','truncated':False,'exit_code':0,'timed_out':False}
    monkeypatch.setattr(computer,'execute',worker)
    async def approve(call): decisions.append(call);return 'approve'
    ctx.run_grants.add('computer_shell')
    one=await execute(ctx,'computer_shell',{'command':'echo secret'},approve)
    two=await execute(ctx,'computer_shell',{'command':'pwd'},approve)
    assert len(decisions)==2 and calls==['echo [redacted]','pwd']
    assert one['result']['output']=='[redacted] output' and two['status']=='completed'
    async def deny(_): return 'deny'
    assert (await execute(ctx,'computer_shell',{'command':'danger'},deny))['status']=='denied'
    assert len(calls)==2
    async def disable(_):
        monkeypatch.setenv('FUNK_COMPUTER_ENABLED','0')
        return 'approve_once'
    assert (await execute(ctx,'computer_shell',{'command':'blocked'},disable))['status']=='denied'
    assert len(calls)==2


@pytest.mark.asyncio
async def test_unix_client_protocol_and_failure(tmp_path,monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1')
    monkeypatch.setattr(computer,'SOCKET',str(tmp_path/'sock'))
    ctx,_=make_context(tmp_path)
    received=[]
    async def handler(reader,writer):
        writer.write(b'{"ready":1}\n');await writer.drain()
        received.append(json.loads(await reader.readline()))
        writer.write(b'{"output":"ok","truncated":false,"exit_code":0,"timed_out":false,"workspace":{"dirs":[],"files":{}}}\n')
        await writer.drain();writer.close();await writer.wait_closed()
    server=await asyncio.start_unix_server(handler,computer.SOCKET)
    async with server:
        assert (await computer.execute(ctx,'printf ok'))['output']=='ok'
        assert received==[{'command':'printf ok','workspace':{'dirs':[],'files':{}}}]
    monkeypatch.setattr(computer,'SOCKET',str(tmp_path/'missing'))
    async def unavailable(): raise tools.ToolError('Computer sandbox is unavailable; no command was sent.')
    monkeypatch.setattr(computer,'ready_connection',unavailable)
    with pytest.raises(tools.ToolError,match='no command was sent'): await computer.execute(ctx,'pwd')


def test_live_approval_is_individual_and_audited(monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1')
    calls=[]
    async def worker(context,command):
        calls.append(command);return {'output':'done','truncated':False,'exit_code':0,'timed_out':False}
    monkeypatch.setattr(computer,'execute',worker)
    FakeClient.responses=[tool_reply('computer_shell',{'command':'echo hello'}),final_reply()]
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as client:
        setup(client);configure_budget(client)
        bot=client.post('/api/bots',json={'name':'Computer user'}).json()['id']
        run=client.post(f'/api/bots/{bot}/chat',json={'content':'Run a command'}).json()['job_id']
        call=until_calls(client,run)[0]
        assert call['status']=='pending' and call['arguments']=={'command':'echo hello'} and not calls
        assert client.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve'}).status_code==400
        assert client.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'}).status_code==200
        assert get_events(client,run)[-1]['type']=='done' and calls==['echo hello']
        call=client.get(f'/api/jobs/{run}/tool-calls').json()[0]
        assert call['status']=='completed' and [a['action'] for a in call['audit']]==['proposed','approve_once','started','completed']


def test_worker_runs_shell_and_bounds_output_without_claiming_container_isolation(tmp_path,monkeypatch):
    path=Path(__file__).resolve().parents[2]/'computer'/'worker.py'
    monkeypatch.setitem(sys.modules,'computer_snapshot',snapshots)
    spec=importlib.util.spec_from_file_location('computer_worker',path)
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    monkeypatch.setattr(worker,'WORKSPACE',str(tmp_path));monkeypatch.setattr(worker,'TEMP',str(tmp_path))
    # This exercises worker behavior only. It does not test Docker privileges.
    monkeypatch.setattr(worker,'drop_privileges',lambda: None)
    result=worker.execute("printf hello; printf error >&2")
    assert result=={'output':'helloerror','truncated':False,'exit_code':0,'timed_out':False}
    assert worker.execute("python -c 'print(\"x\"*20000)'")['truncated']


def test_status_requires_auth_and_disabled_by_default(monkeypatch):
    monkeypatch.delenv('FUNK_COMPUTER_ENABLED',raising=False)
    with TestClient(service.app) as client:
        assert client.get('/api/settings/computer').status_code==401
        setup(client)
        assert client.get('/api/settings/computer').json()=={'enabled':False}
        assert client.put('/api/settings/tool-policies',json={'web_fetch':'auto','write_note':'ask','create_followup':'ask','computer_shell':'auto'}).status_code==422


@pytest.mark.asyncio
async def test_disabled_never_requests_approval_or_executes(tmp_path,monkeypatch):
    monkeypatch.delenv('FUNK_COMPUTER_ENABLED',raising=False)
    ctx,events=make_context(tmp_path)
    async def never(*_): pytest.fail('Disabled command must not run or request approval')
    monkeypatch.setattr(computer,'execute',never)
    result=await execute(ctx,'computer_shell',{'command':'pwd'},never)
    assert result['status']=='denied' and events[0]['status']=='denied'


@pytest.mark.asyncio
async def test_cancelled_pending_computer_approval_never_runs(tmp_path,monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1')
    ctx,_=make_context(tmp_path);waiting=asyncio.Event()
    async def never(*_): pytest.fail('Cancelled command must not run')
    monkeypatch.setattr(computer,'execute',never)
    async def wait(_): waiting.set();await asyncio.Event().wait()
    task=asyncio.create_task(execute(ctx,'computer_shell',{'command':'pwd'},wait))
    await waiting.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    with service.db() as db: assert db.execute('SELECT status FROM tool_calls').fetchone()['status']=='failed'


def test_snapshot_rejects_unsafe_entries_and_limits(tmp_path):
    for path in ('../x','/absolute','a//b','a/../x','bad\\name','a/./b','x\x00'):
        assert not snapshots.valid_path(path)
    tmp_path=tmp_path/'workspace';tmp_path.mkdir()
    (tmp_path/'dir').mkdir();(tmp_path/'dir'/'test.txt').write_text('hello')
    (tmp_path/'run.sh').write_text('echo ok');(tmp_path/'run.sh').chmod(0o700)
    saved=snapshots.collect(str(tmp_path))
    with tempfile.TemporaryDirectory() as destination:
        snapshots.restore(saved,destination)
        assert (Path(destination)/'dir'/'test.txt').read_text()=='hello'
        assert (Path(destination)/'run.sh').stat().st_mode & 0o100
    (tmp_path/'link').symlink_to('/etc/passwd')
    with pytest.raises(snapshots.SnapshotError,match='links'): snapshots.collect(str(tmp_path))
    (tmp_path/'link').unlink();(tmp_path/'huge').write_bytes(b'x'*(snapshots.MAX_FILE+1))
    with pytest.raises(snapshots.SnapshotError,match='512 KiB'): snapshots.collect(str(tmp_path))
    with pytest.raises(snapshots.SnapshotError): snapshots.validate({'dirs':[],'files':{'a/b':{'data':'','executable':False}}})


@pytest.mark.asyncio
async def test_persistent_per_bot_snapshots_through_mock_worker(tmp_path,monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1')
    monkeypatch.setattr(computer,'SOCKET',str(tmp_path/'sock'))
    monkeypatch.setitem(sys.modules,'computer_snapshot',snapshots)
    spec=importlib.util.spec_from_file_location('computer_worker',Path(__file__).resolve().parents[2]/'computer'/'worker.py')
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    monkeypatch.setattr(worker,'drop_privileges',lambda: None)
    calls=[]
    async def handler(reader,writer):
        writer.write(b'{"ready":1}\n');await writer.drain()
        request=json.loads(await reader.readline());calls.append(request['command'])
        with tempfile.TemporaryDirectory() as directory:
            snapshots.restore(request['workspace'],directory)
            monkeypatch.setattr(worker,'WORKSPACE',directory);monkeypatch.setattr(worker,'TEMP',directory)
            result=worker.execute(request['command']);result['workspace']=snapshots.collect(directory)
        writer.write(json.dumps(result).encode()+b'\n');await writer.drain();writer.close();await writer.wait_closed()
    server=await asyncio.start_unix_server(handler,computer.SOCKET,limit=snapshots.MAX_JSON+100000)
    bot1,_=make_context(tmp_path);bot2,_=make_context(tmp_path)
    async with server:
        assert (await computer.execute(bot1,'mkdir folder; echo hello > folder/note.txt'))['exit_code']==0
        assert (await computer.execute(bot1,'cat folder/note.txt'))['output']=='hello\n'
        assert (await computer.execute(bot2,'test ! -e folder && echo separate'))['output']=='separate\n'
    assert len(calls)==3
    with service.db() as c:
        assert c.execute('SELECT COUNT(*) FROM computer_workspaces').fetchone()[0]==2
        c.execute('DELETE FROM bots WHERE id=?',(bot1.bot_id,))
        assert c.execute('SELECT COUNT(*) FROM computer_workspaces').fetchone()[0]==1


def test_owner_computer_files_upload_download_delete_and_active_guard():
    with TestClient(service.app) as client:
        assert client.get('/api/bots/no/computer/files').status_code==401
        setup(client)
        bot=client.post('/api/bots',json={'name':'Files'}).json()['id']
        other=client.post('/api/bots',json={'name':'Other'}).json()['id']
        base=f'/api/bots/{bot}/computer'
        assert client.post(base+'/files',files={'file':('../evil',b'bad')}).status_code==400
        assert client.post(base+'/files',files={'file':('test.txt',b'hello')}).json()=={'path':'test.txt','size':5}
        assert client.post(base+'/files',files={'file':('test.txt',b'replace')}).status_code==409
        assert client.post(base+'/files',files={'file':('large',b'x'*(snapshots.MAX_FILE+1))}).status_code==400
        assert client.get(base+'/files').json()==[{'path':'test.txt','size':5,'executable':False}]
        assert client.get(f'/api/bots/{other}/computer/files').json()==[]
        download=client.get(base+'/download',params={'path':'test.txt'})
        assert download.content==b'hello' and download.headers['content-type']=='application/octet-stream'
        assert 'attachment' in download.headers['content-disposition']
        assert client.get(base+'/download',params={'path':'../test.txt'}).status_code==404
        with service.db() as db: db.execute('INSERT INTO runs VALUES (?,?,?,?,?)',('active',bot,'running',1,1))
        assert client.delete(base+'/workspace').status_code==409
        assert client.delete(base+'/files',params={'path':'test.txt'}).status_code==409
        assert client.post(base+'/files',files={'file':('other.txt',b'no')}).status_code==409
        with service.db() as db: db.execute("UPDATE runs SET status='done' WHERE id='active'")
        assert client.delete(base+'/files',params={'path':'test.txt'}).status_code==200
        assert client.get(base+'/files').json()==[]
        assert client.delete(base+'/workspace').status_code==200
        assert client.get('/api/bots/missing/computer/files').status_code==404


@pytest.mark.asyncio
async def test_bad_worker_snapshot_preserves_previous_state(tmp_path,monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1');monkeypatch.setattr(computer,'SOCKET',str(tmp_path/'sock'))
    ctx,_=make_context(tmp_path)
    original={'dirs':[],'files':{'saved':{'data':'aGk=','executable':False}}}
    with service.db() as db: computer.persist_workspace(db,ctx.bot_id,original)
    async def handler(reader,writer):
        writer.write(b'{"ready":1}\n');await writer.drain();await reader.readline()
        result={'output':'x','truncated':False,'exit_code':0,'timed_out':False,'workspace':{'dirs':[],'files':{'../bad':{'data':'','executable':False}}}}
        writer.write(json.dumps(result).encode()+b'\n');await writer.drain();writer.close();await writer.wait_closed()
    server=await asyncio.start_unix_server(handler,computer.SOCKET,limit=snapshots.MAX_JSON+100000)
    async with server:
        with pytest.raises(tools.ToolError,match='previous workspace was retained'): await computer.execute(ctx,'pwd')
    with service.db() as db: assert computer.read_workspace(db,ctx.bot_id)==original


def test_cleanup_signal_handles_no_remaining_processes(monkeypatch):
    monkeypatch.setitem(sys.modules,'computer_snapshot',snapshots)
    spec=importlib.util.spec_from_file_location('computer_worker',Path(__file__).resolve().parents[2]/'computer'/'worker.py')
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    sent=[]
    def no_processes(pid,sig):
        sent.append((pid,sig));raise ProcessLookupError()
    monkeypatch.setattr(worker.os,'kill',no_processes)
    worker.signal_command_processes()
    assert [x[1] for x in sent]==[worker.signal.SIGSTOP,worker.signal.SIGKILL]


@pytest.mark.asyncio
async def test_policy_is_checked_after_worker_handshake(tmp_path,monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1');monkeypatch.setattr(computer,'SOCKET',str(tmp_path/'sock'))
    ctx,_=make_context(tmp_path);received=[]
    async def handler(reader,writer):
        ctx.policy_for=lambda c,name,risk:'deny'
        writer.write(b'{"ready":1}\n');await writer.drain()
        received.append(await reader.read())
        writer.close();await writer.wait_closed()
    server=await asyncio.start_unix_server(handler,computer.SOCKET)
    async with server:
        with pytest.raises(tools.ToolError,match='policy changed'): await computer.execute(ctx,'must not run')
        await asyncio.sleep(.01)
    assert received==[b'']


def test_total_snapshot_limit_preserves_existing_workspace(tmp_path,monkeypatch):
    ctx,_=make_context(tmp_path)
    saved={'dirs':[],'files':{'x':{'data':'eA==','executable':False}}}
    with service.db() as db: computer.persist_workspace(db,ctx.bot_id,saved)
    monkeypatch.setattr(computer,'MAX_STORED',2)
    with pytest.raises(tools.ToolError,match='limit'):
        with service.db() as db: computer.persist_workspace(db,ctx.bot_id,{'dirs':[],'files':{}})
    with service.db() as db: assert computer.read_workspace(db,ctx.bot_id)==saved
