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
    assert module.perform(page,{'type':'click','x':1,'y':2})=={}
    assert page.mouse.events==[(1,2)]
    with pytest.raises(ValueError): module.perform(page,{'type':'click','x':1024,'y':2})
    with pytest.raises(ValueError,match='network access is disabled'): module.perform(page,{'type':'open_url','url':'https://example.com'})


def test_session_persists_actions_and_exclusive_takeover(monkeypatch):
    worker=load_worker(monkeypatch);processes=[];inputs=[]
    monkeypatch.setattr(worker,'restore_as_user',lambda _:None)
    monkeypatch.setattr(worker,'start_desktop',lambda _:None)
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
