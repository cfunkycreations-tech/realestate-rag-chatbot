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
from test_tool_runtime import make_context as make_base_context
from test_app import FakeClient, setup, configure_budget
from test_live_tools import tool_reply, final_reply, until_calls, get_events


def make_context(tmp_path):
    ctx,events=make_base_context(tmp_path)
    with service.db() as db: db.execute('INSERT INTO computer_permissions VALUES (?,1,1,?)',(ctx.bot_id,1))
    return ctx,events


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
    async def worker(context,command,revision):
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
        assert (await computer.execute(ctx,'printf ok',1))['output']=='ok'
        assert received==[{'command':'printf ok','workspace':{'dirs':[],'files':{}}}]
    monkeypatch.setattr(computer,'SOCKET',str(tmp_path/'missing'))
    async def unavailable(): raise tools.ToolError('Computer sandbox is unavailable; no command was sent.')
    monkeypatch.setattr(computer,'ready_connection',unavailable)
    with pytest.raises(tools.ToolError,match='no command was sent'): await computer.execute(ctx,'pwd',1)


def test_live_approval_is_individual_and_audited(monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1')
    calls=[]
    async def worker(context,command,revision):
        calls.append(command);return {'output':'done','truncated':False,'exit_code':0,'timed_out':False}
    monkeypatch.setattr(computer,'execute',worker)
    FakeClient.responses=[tool_reply('computer_shell',{'command':'echo hello'}),final_reply()]
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as client:
        setup(client);configure_budget(client)
        bot=client.post('/api/bots',json={'name':'Computer user'}).json()['id']
        assert client.put(f'/api/bots/{bot}/computer/permission',json={'allowed':True,'expected_revision':0}).status_code==200
        run=client.post(f'/api/bots/{bot}/chat',json={'content':'Run a command'}).json()['job_id']
        call=until_calls(client,run)[0]
        assert call['status']=='pending' and call['arguments']=={'command':'echo hello','permission_revision':1} and not calls
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
        assert (await computer.execute(bot1,'mkdir folder; echo hello > folder/note.txt',1))['exit_code']==0
        assert (await computer.execute(bot1,'cat folder/note.txt',1))['output']=='hello\n'
        assert (await computer.execute(bot2,'test ! -e folder && echo separate',1))['output']=='separate\n'
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
        with pytest.raises(tools.ToolError,match='previous workspace was retained'): await computer.execute(ctx,'pwd',1)
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
        with pytest.raises(tools.ToolError,match='policy changed'): await computer.execute(ctx,'must not run',1)
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


def test_worker_disconnect_interrupts_running_shell(tmp_path,monkeypatch):
    import socket
    import threading
    import time
    monkeypatch.setitem(sys.modules,'computer_snapshot',snapshots)
    spec=importlib.util.spec_from_file_location('computer_worker',Path(__file__).resolve().parents[2]/'computer'/'worker.py')
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    monkeypatch.setattr(worker,'WORKSPACE',str(tmp_path));monkeypatch.setattr(worker,'TEMP',str(tmp_path))
    monkeypatch.setattr(worker,'drop_privileges',lambda:None)
    spawned=threading.Event();finished=threading.Event();outcome=[]
    original=worker.subprocess.Popen
    def launch(*args,**kwargs):
        process=original(*args,**kwargs);spawned.set();return process
    monkeypatch.setattr(worker.subprocess,'Popen',launch)
    server,client=socket.socketpair()
    def execute():
        try: worker.execute('sleep 10; echo late > late.txt',server)
        except BaseException as exc: outcome.append(exc)
        finally: finished.set()
    thread=threading.Thread(target=execute,daemon=True);thread.start()
    try:
        assert spawned.wait(5)
        start=time.monotonic();client.close()
        assert finished.wait(3) and time.monotonic()-start<3
        assert len(outcome)==1 and isinstance(outcome[0],worker.CommandCancelled)
        assert not (tmp_path/'late.txt').exists()
    finally: client.close();server.close();thread.join(timeout=3)


@pytest.mark.parametrize('mode',['computer','job','pause','revoke'])
def test_stop_disconnects_inflight_worker_and_preserves_snapshot(tmp_path,monkeypatch,mode):
    import socket
    import threading
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1');monkeypatch.setattr(computer,'SOCKET',str(tmp_path/'worker.sock'))
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(computer.SOCKET);listener.listen(1);listener.settimeout(10)
    received=threading.Event();disconnected=threading.Event();errors=[]
    def fake_worker():
        try:
            conn,_=listener.accept()
            with conn:
                conn.settimeout(10);conn.sendall(b'{"ready":1}\n')
                stream=conn.makefile('rb');request=json.loads(stream.readline());assert request['command']=='sleep 30'
                received.set();assert stream.read()==b'';disconnected.set()
        except BaseException as exc: errors.append(exc)
    thread=threading.Thread(target=fake_worker,daemon=True);thread.start()
    FakeClient.responses=[tool_reply('computer_shell',{'command':'sleep 30'}),final_reply()]
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    try:
        with TestClient(service.app) as client:
            assert client.get('/api/control/computer').status_code==401
            assert client.post('/api/control/computer/stop',json={'run_id':'x'}).status_code==401
            setup(client);configure_budget(client)
            bot=client.post('/api/bots',json={'name':'Stopper'}).json()['id']
            assert client.put(f'/api/bots/{bot}/computer/permission',json={'allowed':True,'expected_revision':0}).status_code==200
            assert client.post(f'/api/bots/{bot}/computer/files',files={'file':('before.txt',b'kept')}).status_code==200
            run=client.post(f'/api/bots/{bot}/chat',json={'content':'Run'}).json()['job_id'];call=until_calls(client,run)[0]
            assert client.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'}).status_code==200
            assert received.wait(5)
            assert client.get('/api/control/computer').json()['active']=={'run_id':run,'bot_id':bot}
            assert client.post('/api/control/computer/stop',json={'run_id':'stale'}).json()=={'requested':False}
            assert not disconnected.is_set()
            if mode=='computer': assert client.post('/api/control/computer/stop',json={'run_id':run}).json()=={'requested':True}
            elif mode=='job': assert client.post(f'/api/jobs/{run}/stop').status_code==200
            elif mode=='revoke':
                other=client.post('/api/bots',json={'name':'Other'}).json()['id'];other_path=f'/api/bots/{other}/computer/permission'
                assert client.put(other_path,json={'allowed':True,'expected_revision':0}).status_code==200
                assert client.put(other_path,json={'allowed':False,'expected_revision':1}).json()['stop_requested'] is False
                assert not disconnected.is_set()
                revoke=client.put(f'/api/bots/{bot}/computer/permission',json={'allowed':False,'expected_revision':1})
                assert revoke.status_code==200 and revoke.json()['stop_requested'] is True
            else: assert client.put('/api/control/pause',json={'paused':True}).status_code==200
            assert disconnected.wait(5)
            assert get_events(client,run)[-1]['type']=='error'
            assert client.get('/api/control/computer').json()['active'] is None
            assert client.get(f'/api/bots/{bot}/computer/download',params={'path':'before.txt'}).content==b'kept'
            call=client.get(f'/api/jobs/{run}/tool-calls').json()[0]
            assert call['status']=='failed' and 'interrupted' in [a['action'] for a in call['audit']]
            assert client.post('/api/control/computer/stop',json={'run_id':run}).json()=={'requested':False}
    finally:
        listener.close();thread.join(timeout=10)
    assert errors==[]


def test_per_bot_computer_permissions_default_deny_revisioned_and_audited(monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1')
    with TestClient(service.app) as client:
        assert client.get('/api/bots/no/computer/permission').status_code==401
        setup(client)
        bot=client.post('/api/bots',json={'name':'First'}).json()['id']
        other=client.post('/api/bots',json={'name':'Second'}).json()['id']
        path=f'/api/bots/{bot}/computer/permission'
        assert client.get(path).json()=={'allowed':False,'revision':0,'service_enabled':True}
        granted=client.put(path,json={'allowed':True,'expected_revision':0})
        assert granted.json()=={'allowed':True,'revision':1,'service_enabled':True,'stop_requested':False}
        assert client.get(f'/api/bots/{other}/computer/permission').json()['allowed'] is False
        assert client.put(path,json={'allowed':False,'expected_revision':0}).status_code==409
        assert client.put(path,json={'allowed':'true','expected_revision':1}).status_code==422
        assert client.put(path,json={'allowed':True,'expected_revision':1,'other':'bad'}).status_code==422
        assert client.put(path,json={'allowed':True,'expected_revision':1}).json()['revision']==1
        assert client.put(path,json={'allowed':False,'expected_revision':1}).json()['revision']==2
        events=client.get('/api/events?since=0').json()['events']
        changes=[e for e in events if e['type']=='computer.permission_changed']
        assert [e['payload'] for e in changes]==[{'allowed':True,'revision':1},{'allowed':False,'revision':2}]
        duplicate=client.post(f'/api/bots/{bot}/duplicate').json()['id']
        assert client.get(f'/api/bots/{duplicate}/computer/permission').json()['allowed'] is False
        assert client.delete(f'/api/bots/{bot}').status_code==200
        with service.db() as db: assert not db.execute('SELECT 1 FROM computer_permissions WHERE bot_id=?',(bot,)).fetchone()


@pytest.mark.asyncio
async def test_unauthorized_bot_denied_even_if_model_invents_tool(tmp_path,monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1')
    ctx,events=make_base_context(tmp_path)
    async def never(*_): pytest.fail('Unpermitted Bot must not request approval or execute.')
    monkeypatch.setattr(computer,'execute',never)
    result=await execute(ctx,'computer_shell',{'command':'pwd'},never)
    assert result['status']=='denied' and events[0]['arguments']['permission_revision']==0


def test_revoke_then_reallow_invalidates_pending_command(monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1')
    calls=[]
    async def worker(context,command,revision): calls.append(command)
    monkeypatch.setattr(computer,'execute',worker)
    FakeClient.responses=[tool_reply('computer_shell',{'command':'pwd'}),final_reply()]
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as client:
        setup(client);configure_budget(client)
        bot=client.post('/api/bots',json={'name':'Restricted'}).json()['id'];path=f'/api/bots/{bot}/computer/permission'
        assert client.put(path,json={'allowed':True,'expected_revision':0}).status_code==200
        run=client.post(f'/api/bots/{bot}/chat',json={'content':'Use the computer'}).json()['job_id'];call=until_calls(client,run)[0]
        assert call['status']=='pending' and call['arguments']['permission_revision']==1
        assert client.put(path,json={'allowed':False,'expected_revision':1}).status_code==200
        assert client.put(path,json={'allowed':True,'expected_revision':2}).status_code==200
        assert client.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'}).status_code==200
        assert get_events(client,run)[-1]['type']=='done'
        call=client.get(f'/api/jobs/{run}/tool-calls').json()[0]
        assert call['status']=='denied' and 'policy_denied' in [e['action'] for e in call['audit']] and calls==[]


@pytest.mark.asyncio
async def test_permission_rechecked_after_handshake(tmp_path,monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1');monkeypatch.setattr(computer,'SOCKET',str(tmp_path/'socket'))
    ctx,_=make_context(tmp_path);received=[]
    async def handler(reader,writer):
        with service.db() as db: db.execute('UPDATE computer_permissions SET allowed=0,revision=2 WHERE bot_id=?',(ctx.bot_id,))
        writer.write(b'{"ready":1}\n');await writer.drain();received.append(await reader.read());writer.close();await writer.wait_closed()
    server=await asyncio.start_unix_server(handler,computer.SOCKET)
    async with server:
        with pytest.raises(tools.ToolError,match='policy changed'): await computer.execute(ctx,'never sent',1)
        await asyncio.sleep(.01)
    assert received==[b'']


def test_tool_declaration_reflects_bot_permission(monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1');captured=[]
    class Client(FakeClient):
        def stream(self,*args,**kwargs):
            captured.append(kwargs['json'])
            return super().stream(*args,**kwargs)
    FakeClient.responses=[tool_reply('computer_shell',{'command':'pwd'}),final_reply(),final_reply()]
    monkeypatch.setattr(service.httpx,'AsyncClient',Client)
    with TestClient(service.app) as client:
        setup(client);configure_budget(client)
        bot=client.post('/api/bots',json={'name':'Tools'}).json()['id']
        first=client.post(f'/api/bots/{bot}/chat',json={'content':'Try'}).json()['job_id']
        get_events(client,first)
        assert client.get(f'/api/jobs/{first}/tool-calls').json()[0]['status']=='denied'
        assert 'computer_shell' not in [t['function']['name'] for t in captured[0]['tools']]
        assert client.put(f'/api/bots/{bot}/computer/permission',json={'allowed':True,'expected_revision':0}).status_code==200
        second=client.post(f'/api/bots/{bot}/chat',json={'content':'Again'}).json()['job_id']
        get_events(client,second)
        computer_tool=next(t['function'] for t in captured[-1]['tools'] if t['function']['name']=='computer_shell')
        assert set(computer_tool['parameters']['properties'])=={'command'}


def test_permission_migration_preserves_existing_computer_workspace(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for
    engine=engine_for(str(tmp_path/'old-computer.db'))
    with engine.connect() as conn:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=conn
        command.upgrade(cfg,'0024_computer_workspaces');conn.commit()
        conn.exec_driver_sql("INSERT INTO bots VALUES ('b','Existing','Editor','instructions','mint','round','smart',1)")
        conn.exec_driver_sql("INSERT INTO computer_workspaces VALUES ('b',?,1)",(json.dumps({'dirs':[],'files':{}}),));conn.commit()
        command.upgrade(cfg,'head');conn.commit()
        assert conn.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0037_model_pin'
        assert conn.exec_driver_sql('SELECT COUNT(*) FROM computer_workspaces').scalar()==1
        assert conn.exec_driver_sql('SELECT COUNT(*) FROM computer_permissions').scalar()==0


def test_model_cannot_set_internal_permission_revision():
    from funkbot.tool_protocol import CallAccumulator
    acc=CallAccumulator()
    acc.feed({'tool_calls':[{'index':0,'id':'call','function':{'name':'computer_shell','arguments':json.dumps({'command':'pwd','permission_revision':999})}}]})
    with pytest.raises(tools.ToolError,match='Invalid tool arguments'): acc.finalize()


@pytest.mark.asyncio
async def test_desktop_stream_and_input_are_bound_to_active_run(tmp_path,monkeypatch):
    import base64
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1');monkeypatch.setenv('FUNK_COMPUTER_DESKTOP_ENABLED','1')
    monkeypatch.setattr(computer,'SOCKET',str(tmp_path/'desktop.sock'))
    ctx,_=make_context(tmp_path);received=[];ready=asyncio.Event()
    png=b'\x89PNG\r\n\x1a\nfixture'
    async def handler(reader,writer):
        writer.write(b'{"ready":1}\n');await writer.drain()
        req=json.loads(await reader.readline());assert req['desktop'] is True
        writer.write(json.dumps({'frame':base64.b64encode(png).decode()}).encode()+b'\n');await writer.drain();ready.set()
        received.append(json.loads(await reader.readline()))
        writer.write(json.dumps({'output':'done','truncated':False,'exit_code':0,'timed_out':False,'workspace':{'dirs':[],'files':{}}}).encode()+b'\n');await writer.drain();writer.close();await writer.wait_closed()
    server=await asyncio.start_unix_server(handler,computer.SOCKET)
    async with server:
        task=asyncio.create_task(computer.execute(ctx,'show desktop',1));await ready.wait()
        for _ in range(20):
            if computer.frame(ctx.run_id): break
            await asyncio.sleep(.01)
        assert computer.frame(ctx.run_id)==png and computer.frame('other') is None
        await computer.send_input(ctx.run_id,{'type':'key','key':'Return'})
        assert (await task)['output']=='done'
        assert received==[{'type':'key','key':'Return'}] and computer.frame(ctx.run_id) is None


def test_owner_desktop_endpoints_require_auth_and_do_not_log_text(monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1');monkeypatch.setenv('FUNK_COMPUTER_DESKTOP_ENABLED','1')
    with TestClient(service.app) as client:
        assert client.get('/api/control/computer/frame?run_id=r').status_code==401
        assert client.post('/api/control/computer/input',json={'run_id':'r','type':'text','text':'hello'}).status_code==401
        setup(client)
        bot=client.post('/api/bots',json={'name':'Desktop'}).json()['id']
        client.put(f'/api/bots/{bot}/computer/permission',json={'allowed':True,'expected_revision':0})
        with service.db() as db: db.execute('INSERT INTO runs VALUES (?,?,?,?,?)',('run',bot,'running',1,1))
        monkeypatch.setattr(computer,'_active',{'bot_id':bot,'run_id':'run'})
        monkeypatch.setattr(computer,'_frame',b'\x89PNG\r\n\x1a\nfixture')
        sent=[]
        async def send(run_id,event): sent.append((run_id,event))
        monkeypatch.setattr(computer,'send_input',send)
        assert client.get('/api/control/computer/frame?run_id=other').status_code==404
        assert client.get('/api/control/computer/frame?run_id=run').headers['cache-control']=='no-store'
        assert client.post('/api/control/computer/input',json={'run_id':'other','type':'text','text':'password'}).status_code==409
        assert client.post('/api/control/computer/input',json={'run_id':'run','type':'click','x':1024,'y':1,'button':1}).status_code==422
        assert client.post('/api/control/computer/input',json={'run_id':'run','type':'text','text':'password'}).status_code==200
        assert sent==[('run',{'type':'text','text':'password'})]
        events=client.get('/api/events?since=0').json()['events']
        assert [x['payload'] for x in events if x['type']=='computer.owner_input']==[{'input_type':'text'}]
