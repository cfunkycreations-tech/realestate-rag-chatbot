import asyncio
import os
import socket
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from funkbot import tools


def test_registry_is_typed():
    assert set(tools.REGISTRY)=={'remember_fact','notify_owner','web_fetch','write_note','create_followup','mcp_call','create_handoff','attach_mission_result','read_work_file','web_search','computer_shell','computer_action'}
    assert tools.REGISTRY['web_fetch'].risk=='read'
    assert tools.REGISTRY['write_note'].risk=='write'
    with pytest.raises(ValidationError): tools.WebFetchArgs(url='https://example.com',extra='not allowed')


@pytest.mark.parametrize('url',[
    'http://127.0.0.1/', 'http://localhost/', 'http://10.2.3.4/', 'http://169.254.169.254/',
    'http://[::1]/', 'http://[::ffff:127.0.0.1]/', 'http://192.168.1.1/', 'http://100.64.0.1/',
    'http://224.0.0.1/', 'http://user:pass@example.com/', 'file:///etc/passwd',
])
def test_rejects_private_addresses_and_disallowed_urls(url):
    with pytest.raises(tools.ToolError): tools.validate_target(url,['127.0.0.1','localhost','10.2.3.4','169.254.169.254','::1','::ffff:127.0.0.1','192.168.1.1','100.64.0.1','224.0.0.1','example.com'],[])


def test_allowlist_default_deny_and_denylist_precedence():
    assert tools.validate_target('https://www.example.com/a?x=1',['.example.com'],[])[1:] == ('www.example.com',443,'/a?x=1')
    for allow,deny,url in [([],[],'https://example.com'),(['example.com'],[],'https://sub.example.com'),(['.example.com'],['private.example.com'],'https://private.example.com'),(['.example.com'],[],'https://evil-example.com')]:
        with pytest.raises(tools.ToolError): tools.validate_target(url,allow,deny)


class Writer:
    def __init__(self): self.data=b''
    def write(self, value): self.data += value
    async def drain(self): pass
    def close(self): pass
    async def wait_closed(self): pass


@pytest.mark.asyncio
async def test_dns_mixed_private_results_are_blocked_before_connect(monkeypatch):
    loop=asyncio.get_running_loop()
    async def resolve(*args,**kwargs):
        return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443)),(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
    async def connect(*args,**kwargs): pytest.fail('must not connect to mixed public/private DNS')
    monkeypatch.setattr(loop,'getaddrinfo',resolve);monkeypatch.setattr(asyncio,'open_connection',connect)
    with pytest.raises(tools.ToolError,match='Private'): await tools.web_fetch(tools.WebFetchArgs(url='https://example.com'),['example.com'],[])


@pytest.mark.asyncio
async def test_fetch_pins_validated_ip_and_tls_hostname(monkeypatch):
    loop=asyncio.get_running_loop();calls=[];writer=Writer()
    async def resolve(*args,**kwargs): return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))]
    async def connect(ip,port,**kwargs):
        calls.append((ip,port,kwargs));reader=asyncio.StreamReader();reader.feed_data(b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\nContent-Type: text/plain\r\n\r\nhello');reader.feed_eof();return reader,writer
    monkeypatch.setattr(loop,'getaddrinfo',resolve);monkeypatch.setattr(asyncio,'open_connection',connect)
    result=await tools.web_fetch(tools.WebFetchArgs(url='https://example.com/hello'),['example.com'],[])
    assert result['text']=='hello' and result['status']==200
    assert calls[0][0]=='93.184.216.34' and calls[0][2]['server_hostname']=='example.com'
    assert b'Host: example.com' in writer.data


@pytest.mark.asyncio
@pytest.mark.parametrize('response,reason',[
    (b'HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/\r\nContent-Length: 0\r\n\r\n','redirects'),
    (b'HTTP/1.1 200 OK\r\nContent-Length: 262145\r\n\r\n','too large'),
    (b'HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 0\r\n\r\n','Compressed'),
])
async def test_fetch_refuses_redirects_oversized_or_compressed_responses(monkeypatch,response,reason):
    loop=asyncio.get_running_loop()
    async def resolve(*args,**kwargs): return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',80))]
    async def connect(*args,**kwargs):
        reader=asyncio.StreamReader();reader.feed_data(response);reader.feed_eof();return reader,Writer()
    monkeypatch.setattr(loop,'getaddrinfo',resolve);monkeypatch.setattr(asyncio,'open_connection',connect)
    with pytest.raises(tools.ToolError,match=reason): await tools.web_fetch(tools.WebFetchArgs(url='http://example.com'),['example.com'],[])


@pytest.mark.asyncio
async def test_fetch_deadline_covers_dns(monkeypatch):
    loop=asyncio.get_running_loop()
    async def resolve(*args,**kwargs): await asyncio.sleep(10)
    monkeypatch.setattr(loop,'getaddrinfo',resolve);monkeypatch.setattr(tools,'FETCH_TIMEOUT',0.01)
    with pytest.raises(tools.ToolError,match='timed out'): await tools.web_fetch(tools.WebFetchArgs(url='https://example.com'),['example.com'],[])


def test_notes_are_isolated_create_only_and_reject_symlinks(tmp_path):
    a,b=str(uuid.uuid4()),str(uuid.uuid4())
    note=tools.NotesArgs(filename='idea.txt',content='An actual note')
    assert tools.write_note(tmp_path,a,note)['bytes']==14
    assert (tmp_path/'workspaces'/a/'idea.txt').read_text()=='An actual note'
    assert tools.write_note(tmp_path,b,note)['bytes']==14
    with pytest.raises(tools.ToolError,match='already exists'): tools.write_note(tmp_path,a,note)
    for name in ['../escape.txt','/tmp/escape.txt','..\\escape.txt']:
        with pytest.raises(tools.ToolError): tools.write_note(tmp_path,a,tools.NotesArgs(filename=name,content='x'))
    outside=tmp_path/'outside';outside.mkdir();c=str(uuid.uuid4());(tmp_path/'workspaces'/c).symlink_to(outside,target_is_directory=True)
    with pytest.raises(tools.ToolError,match='safely'): tools.write_note(tmp_path,c,note)
    assert list(outside.iterdir())==[]
    d=str(uuid.uuid4());directory=tmp_path/'workspaces'/d;directory.mkdir();(directory/'idea.txt').symlink_to(outside/'target')
    with pytest.raises(tools.ToolError): tools.write_note(tmp_path,d,note)
    assert not (outside/'target').exists()
