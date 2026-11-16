import asyncio
import json
import socket

import pytest
from fastapi.testclient import TestClient
from funkbot import browser_network, computer, tools
from funkbot.tool_runtime import execute
from test_computer import make_context
import app as service
from test_app import setup


def test_domain_validation():
    assert browser_network.validate_domains(['Example.COM','example.com'])==['example.com']
    assert browser_network.target('https://Example.com/path')=='example.com'
    for value in ['http://example.com','https://127.0.0.1','https://example.com:444','https://a@example.com','https://example.local']:
        with pytest.raises((ValueError,tools.ToolError)): browser_network.target(value)
    for domains in [['.example.com'],['localhost'],['127.0.0.1'],['example.com/path']]:
        with pytest.raises(ValueError): browser_network.validate_domains(domains)


def test_domain_settings_are_owner_only_and_revisioned(tmp_path,monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_BROWSER_NETWORK','1');monkeypatch.setattr(browser_network,'SOCKET',str(tmp_path/'proxy.sock'))
    with TestClient(service.app) as client:
        assert client.get('/api/settings/computer-domains').status_code==401
        setup(client)
        assert client.get('/api/settings/computer-domains').json()=={'domains':[],'revision':0,'network_enabled':True,'broker_ready':True}
        assert client.put('/api/settings/computer-domains',json={'domains':['EXAMPLE.com'],'expected_revision':0}).json()['domains']==['example.com']
        assert client.put('/api/settings/computer-domains',json={'domains':[],'expected_revision':0}).status_code==409
        assert client.put('/api/settings/computer-domains',json={'domains':['.example.com'],'expected_revision':1}).status_code==422
        events=client.get('/api/events?since=0').json()['events']
        assert [e['payload'] for e in events if e['type']=='computer.domains_changed']==[{'domains':['example.com'],'revision':1}]


@pytest.mark.asyncio
async def test_each_domain_requires_approval_and_revision_recheck(tmp_path,monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1');monkeypatch.setenv('FUNK_COMPUTER_DESKTOP_ENABLED','1');monkeypatch.setenv('FUNK_COMPUTER_BROWSER_NETWORK','1')
    ctx,_=make_context(tmp_path);ctx.vision=True;calls=[];decisions=[]
    async def run(context,rev,action,host,domain_revision,control_revision):
        calls.append((action,host,domain_revision));return {'ok':True},b'PNG'
    monkeypatch.setattr(computer,'desktop_action',run)
    async def approve(call): decisions.append(call);return 'approve_once'
    denied=await execute(ctx,'computer_action',{'type':'open_url','url':'https://example.com/'},approve)
    assert denied['status']=='denied' and not decisions and not calls
    with service.db() as db: db.execute('INSERT OR REPLACE INTO config VALUES (?,?)',('computer_browser_domains',json.dumps({'domains':['example.com'],'revision':1})))
    ok=await execute(ctx,'computer_action',{'type':'open_url','url':'https://example.com/page'},approve)
    assert ok['status']=='completed' and calls==[({'type':'open_url','url':'https://example.com/page'},'example.com',1)] and len(decisions)==1
    async def changed(_):
        with service.db() as db: db.execute('UPDATE config SET value=? WHERE key=?',(json.dumps({'domains':['example.com'],'revision':2}),'computer_browser_domains'))
        return 'approve_once'
    denied=await execute(ctx,'computer_action',{'type':'open_url','url':'https://example.com/other'},changed)
    assert denied['status']=='denied' and len(calls)==1


@pytest.mark.asyncio
async def test_proxy_blocks_unapproved_and_private_addresses_and_relays_pinned_public(tmp_path,monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_BROWSER_NETWORK','1');monkeypatch.setattr(browser_network,'SOCKET',str(tmp_path/'broker.sock'))
    broker=browser_network.Broker(None);monkeypatch.setattr(broker,'permitted',lambda host:host=='example.com')
    from types import SimpleNamespace
    monkeypatch.setattr(computer,'_session',SimpleNamespace(network_bytes=0))
    await broker.start();loop=asyncio.get_running_loop()
    async def dns(host,port,**kwargs): return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
    monkeypatch.setattr(loop,'getaddrinfo',dns)
    async def request(host):
        reader,writer=await asyncio.open_unix_connection(browser_network.SOCKET)
        writer.write(f'CONNECT {host}:443 HTTP/1.1\r\nHost: {host}\r\n\r\n'.encode());await writer.drain()
        return reader,writer,await reader.readuntil(b'\r\n\r\n')
    try:
        _,writer,reply=await request('unapproved.example.com');assert b'403' in reply;writer.close()
        _,writer,reply=await request('example.com');assert b'403' in reply;writer.close()
        received=[]
        async def echo(reader,writer):
            data=await reader.read(100);received.append(data);writer.write(b'echo:'+data);await writer.drain();writer.close()
        local=await asyncio.start_server(echo,'127.0.0.1',0);port=local.sockets[0].getsockname()[1]
        original=asyncio.open_connection
        async def connect(host,port_requested):
            assert host=='127.0.0.1' and port_requested==443
            return await original('127.0.0.1',port)
        monkeypatch.setattr(browser_network,'public_address',lambda ip:True);monkeypatch.setattr(asyncio,'open_connection',connect)
        async with local:
            reader,writer,reply=await request('example.com');assert b'200' in reply
            writer.write(b'hello');await writer.drain();assert await reader.read(20)==b'echo:hello';writer.close()
        assert received==[b'hello']
    finally: await broker.close()


def test_kill_switch_pauses_work_and_requests_out_of_band_exit(monkeypatch):
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1')
    sent=[]
    async def kill(): sent.append(True);return True
    monkeypatch.setattr(computer,'request_container_kill',kill)
    with TestClient(service.app) as client:
        setup(client)
        bot=client.post('/api/bots',json={'name':'Kill'}).json()['id']
        monkeypatch.setattr(computer,'_active',{'bot_id':bot,'run_id':'run'})
        assert client.post('/api/control/computer/kill',json={'run_id':'old'}).status_code==409
        assert client.post('/api/control/computer/kill',json={'run_id':'run'}).json()=={'paused':True,'kill_requested':True}
        assert client.get('/api/control/pause').json()=={'paused':True} and sent==[True]
