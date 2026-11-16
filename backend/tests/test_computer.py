import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app as service
from funkbot import computer, tool_protocol, tools
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
    async def worker(command):
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
    received=[]
    async def handler(reader,writer):
        received.append(json.loads(await reader.readline()))
        writer.write(b'{"output":"ok","truncated":false,"exit_code":0,"timed_out":false}\n')
        await writer.drain();writer.close();await writer.wait_closed()
    server=await asyncio.start_unix_server(handler,computer.SOCKET)
    async with server:
        assert (await computer.execute('printf ok'))['output']=='ok'
        assert received==[{'command':'printf ok'}]
    monkeypatch.setattr(computer,'SOCKET',str(tmp_path/'missing'))
    with pytest.raises(tools.ToolError,match='may have run'): await computer.execute('pwd')


def test_live_approval_is_individual_and_audited(monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1')
    calls=[]
    async def worker(command):
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
