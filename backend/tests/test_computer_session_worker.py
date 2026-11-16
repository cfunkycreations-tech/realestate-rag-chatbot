import importlib.util
import json
import socket
import subprocess
import sys
import threading
import types
from pathlib import Path

import pytest
from funkbot import computer_snapshot

ROOT=Path(__file__).resolve().parents[2]


def load_worker(monkeypatch):
    monkeypatch.setitem(sys.modules,'computer_snapshot',computer_snapshot)
    spec=importlib.util.spec_from_file_location('session_worker_fixture',ROOT/'computer'/'worker.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_browser_actions_are_bounded_and_network_denied(monkeypatch):
    monkeypatch.setitem(sys.modules,'playwright',types.ModuleType('playwright'))
    fake=types.ModuleType('playwright.sync_api');fake.sync_playwright=lambda: None
    monkeypatch.setitem(sys.modules,'playwright.sync_api',fake)
    spec=importlib.util.spec_from_file_location('session_browser_fixture',ROOT/'computer'/'session_browser.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.allowed_url('file:///workspace/example.html')
    assert not module.allowed_url('file:///workspace/../etc/passwd')
    assert not module.allowed_url('https://example.com/')
    class Mouse:
        def __init__(self): self.events=[]
        def click(self,x,y): self.events.append((x,y))
        def wheel(self,x,y): self.events.append((x,y))
    page=types.SimpleNamespace(mouse=Mouse())
    clicks=[]
    monkeypatch.setattr(module.subprocess,'run',lambda args,**kw:clicks.append(args))
    assert module.perform(page,{'type':'click','x':1,'y':2})=={}
    assert clicks==[['xdotool','mousemove','--sync','1','2','click','1']]
    with pytest.raises(ValueError): module.perform(page,{'type':'click','x':1024,'y':2})
    with pytest.raises(ValueError): module.perform(page,{'type':'open_url','url':'http://example.com'})


def test_session_persists_actions_and_exclusive_takeover(monkeypatch):
    worker=load_worker(monkeypatch);processes=[];inputs=[]
    monkeypatch.setattr(worker,'restore_as_user',lambda _:None)
    monkeypatch.setattr(worker,'start_desktop',lambda _:None)
    monkeypatch.setattr(worker,'start_browser_proxy',lambda:(12345,None))
    monkeypatch.setattr(worker,'stop_browser_proxy',lambda _:None)
    monkeypatch.setattr(worker,'desktop_frame',lambda:b'\x89PNG\r\n\x1a\nfixture')
    monkeypatch.setattr(worker,'desktop_input',lambda event:inputs.append(event))
    monkeypatch.setattr(worker,'collect_as_user',lambda:{'dirs':[],'files':{}})
    original=subprocess.Popen
    def start(*args,**kwargs):
        code='import sys,json;print(json.dumps({"ready":True}),flush=True)\nfor line in sys.stdin:\n print(json.dumps({"ok":True,"result":{"action":json.loads(line)["type"]}}),flush=True)'
        p=original([sys.executable,'-u','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL);processes.append(p);return p
    monkeypatch.setattr(worker.subprocess,'Popen',start)
    def cleanup():
        for p in processes: p.terminate();p.wait(timeout=5)
    monkeypatch.setattr(worker,'stop_unprivileged_processes',cleanup)
    a,b=socket.socketpair();a.settimeout(5);b.settimeout(5)
    thread=threading.Thread(target=worker.serve_session,args=(b,{'dirs':[],'files':{}}),daemon=True);thread.start();stream=a.makefile('rb')
    def get():
        while True:
            obj=json.loads(stream.readline())
            if set(obj)!={'frame'}: return obj
    def send(obj): a.sendall(json.dumps(obj).encode()+b'\n')
    assert get()=={'session':'started'}
    send({'type':'action','id':'a','action':{'type':'click','x':1,'y':2}});r=get()
    assert r['id']=='a' and r['ok'] and r['result']=={'action':'click'} and 'frame' in r
    send({'type':'takeover','id':'t','enabled':True});assert get()=={'id':'t','ok':True,'takeover':True}
    send({'type':'action','id':'b','action':{'type':'click','x':3,'y':4}});assert not get()['ok']
    send({'type':'owner_input','event':{'type':'key','key':'Return'}})
    send({'type':'takeover','id':'u','enabled':False});assert not get()['takeover']
    send({'type':'action','id':'c','action':{'type':'scroll','delta_x':0,'delta_y':2}});assert get()['result']=={'action':'scroll'}
    send({'type':'close'});assert get()['session']=='ended'
    thread.join(5);a.close();b.close();assert not thread.is_alive() and inputs==[{'type':'key','key':'Return'}]


@pytest.mark.asyncio
async def test_backend_session_reuses_worker_and_waits_for_handback(tmp_path,monkeypatch):
    import asyncio
    import base64
    from funkbot import computer
    from test_computer import make_context
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1');monkeypatch.setenv('FUNK_COMPUTER_DESKTOP_ENABLED','1')
    monkeypatch.setattr(computer,'SOCKET',str(tmp_path/'session.sock'))
    ctx,_=make_context(tmp_path);messages=[];image=b'\x89PNG\r\n\x1a\nfixture'
    async def server(reader,writer):
        writer.write(b'{"ready":1}\n');await writer.drain()
        assert json.loads(await reader.readline())['mode']=='session'
        writer.write(b'{"session":"started"}\n');await writer.drain()
        while line:=await reader.readline():
            body=json.loads(line);messages.append(body)
            if body['type']=='action':
                result={'id':body['id'],'ok':True,'result':{'type':body['action']['type']},'frame':base64.b64encode(image).decode()}
            elif body['type']=='takeover': result={'id':body['id'],'ok':True,'takeover':body['enabled']}
            elif body['type']=='close':
                result={'session':'ended','reason':'closed','workspace':{'dirs':[],'files':{}}}
                writer.write(json.dumps(result).encode()+b'\n');await writer.drain();break
            else: continue
            writer.write(json.dumps(result).encode()+b'\n');await writer.drain()
        writer.close();await writer.wait_closed()
    listener=await asyncio.start_unix_server(server,computer.SOCKET)
    async with listener:
        one,shot=await computer.desktop_action(ctx,1,{'type':'screenshot'})
        assert one=={'type':'screenshot'} and shot==image
        await computer.set_takeover(ctx.run_id,True)
        waiting=asyncio.create_task(computer.desktop_action(ctx,1,{'type':'click','x':1,'y':2}))
        await asyncio.sleep(.02);assert not waiting.done() and [x['type'] for x in messages]==['action','takeover']
        await computer.set_takeover(ctx.run_id,False)
        assert (await waiting)[0]=={'type':'click'}
        await computer.end_session(ctx.run_id,True)
        assert computer.active_info() is None
    assert [x['type'] for x in messages]==['action','takeover','takeover','action','close']


def test_vision_action_is_individually_approved_and_screenshot_goes_to_model(monkeypatch):
    import copy
    import io
    from PIL import Image
    import app as service
    from funkbot import computer
    from fastapi.testclient import TestClient
    from test_app import FakeClient,setup
    from test_live_tools import tool_reply,final_reply,until_calls,get_events
    monkeypatch.setenv('FUNK_COMPUTER_ENABLED','1');monkeypatch.setenv('FUNK_COMPUTER_DESKTOP_ENABLED','1')
    image=io.BytesIO();Image.new('RGB',(10,10),'blue').save(image,format='PNG');calls=[];captured=[]
    async def action(ctx,revision,body,host,domain_revision): calls.append((revision,body));return {'ok':True},image.getvalue()
    monkeypatch.setattr(computer,'desktop_action',action)
    class Client(FakeClient):
        def stream(self,*args,**kwargs): captured.append(copy.deepcopy(kwargs['json']));return super().stream(*args,**kwargs)
    FakeClient.responses=[tool_reply('computer_action',{'type':'click','x':5,'y':5}),final_reply()]
    monkeypatch.setattr(service.httpx,'AsyncClient',Client)
    with TestClient(service.app) as client:
        setup(client)
        assert client.put('/api/budget/prices/vision',json={'prompt':'1','completion':'2','max_prompt_tokens':100000,'max_completion_tokens':512}).status_code==200
        bot=client.post('/api/bots',json={'name':'Viewer','profile':'vision'}).json()['id']
        client.put(f'/api/bots/{bot}/computer/permission',json={'allowed':True,'expected_revision':0})
        run=client.post(f'/api/bots/{bot}/chat',json={'content':'Click'}).json()['job_id'];call=until_calls(client,run)[0]
        assert call['status']=='pending' and not calls
        assert client.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve'}).status_code==400
        assert client.post(f'/api/jobs/{run}/tool-calls/{call["id"]}/decision',json={'decision':'approve_once'}).status_code==200
        assert get_events(client,run)[-1]['type']=='done'
        assert calls==[(1,{'type':'click','x':5,'y':5})]
        assert 'computer_action' in [tool['function']['name'] for tool in captured[0]['tools']]
        assert captured[1]['messages'][-1]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,')
        audit=client.get(f'/api/jobs/{run}/tool-calls').json()[0]
        assert audit['result']=={'ok':True} and 'base64' not in json.dumps(audit)


def test_desktop_screenshot_fits_safety_bound():
    import io
    from PIL import Image
    from funkbot.budget import BudgetError
    import app as service
    img=io.BytesIO();Image.effect_noise((1024,768),80).convert('RGB').save(img,format='PNG')
    encoded=service.desktop_image_for_model(img.getvalue(),5000)
    assert len(encoded)<=5000
    with pytest.raises(BudgetError): service.desktop_image_for_model(img.getvalue(),10)
