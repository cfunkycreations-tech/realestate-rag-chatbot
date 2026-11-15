import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest
from funkbot import workspace_pointer as pointer
from fastapi.testclient import TestClient
import app as service
from test_app import setup


def test_pointer_fails_closed_and_never_follows_links(tmp_path):
    root=tmp_path/'root';root.mkdir();identifier=str(uuid.uuid4())
    assert pointer.read(root)=={'active':'','previous':None}
    (root/'restores').mkdir();stage=root/'restores'/identifier;stage.mkdir()
    pointer.write(root,'restores/'+identifier,'')
    assert pointer.resolve(root,pointer.read(root)['active'])==stage
    for path in ('../escape','restores/../outside','restores/not-a-uuid','/restores/'+identifier,'restores/'+identifier+'/x'):
        with pytest.raises(pointer.PointerError): pointer.resolve(root,path)
    (root/pointer.POINTER).write_text('{bad')
    with pytest.raises(pointer.PointerError): pointer.read(root)
    (root/pointer.POINTER).unlink();(root/pointer.POINTER).symlink_to(tmp_path/'outside')
    with pytest.raises(pointer.PointerError): pointer.read(root)
    (root/pointer.POINTER).unlink();stage.rmdir();stage.symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(pointer.PointerError): pointer.resolve(root,'restores/'+identifier)


def test_automatic_restore_disabled_fails_before_staging(monkeypatch):
    monkeypatch.delenv('FUNK_ENABLE_RESTORE_RESTART',raising=False)
    with TestClient(service.app) as client:
        setup(client)
        assert client.put('/api/control/pause',json={'paused':True}).status_code==200
        response=client.post('/api/workspace/restore?activate=true',content=b'not a zip',headers={'content-type':'application/zip'})
        assert response.status_code==503
        assert client.get('/api/workspace/restores').json()==[]


def test_real_process_restart_restores_account_and_keeps_original(tmp_path):
    root=tmp_path/'data';backend=Path(service.__file__).parent
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env={**os.environ,'FUNK_DATA_DIR':str(root),'FUNK_ENABLE_RESTORE_RESTART':'1','FUNK_SESSION_SECRET':''}
    args=[sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port',str(port)]
    process=subprocess.Popen(args,cwd=backend,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    url=f'http://127.0.0.1:{port}'
    def wait(predicate,seconds=20):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if process.poll() is not None: raise AssertionError('Backend exited unexpectedly')
            try:
                result=predicate()
                if result: return result
            except (httpx.HTTPError,FileNotFoundError): pass
            time.sleep(.1)
        raise AssertionError('Backend did not become ready')
    try:
        with httpx.Client(base_url=url,timeout=5) as client:
            wait(lambda: (root/'setup.token').read_text().strip())
            token=(root/'setup.token').read_text().strip()
            assert client.post('/api/auth/setup',json={'password':'original-test-password','setup_token':token}).status_code==200
            bot=client.post('/api/bots',json={'name':'Backed up'}).json()['id']
            assert client.put('/api/settings/gateways/openrouter',json={'url':'https://example.com/v1','key':'backup-secret-123456789'}).status_code==200
            assert client.put('/api/control/pause',json={'paused':True}).status_code==200
            archive=client.get('/api/workspace/backup').content
            assert client.post('/api/bots',json={'name':'Later'}).status_code==200
            original_session=client.cookies.get('funk_session')
            result=client.post('/api/workspace/restore?activate=true',content=archive,headers={'content-type':'application/zip'})
            assert result.status_code==200,result.text
            stage=result.json()['staged_id'];assert result.json()['restarting']
            wait(lambda: client.get('/api/bots').status_code==401)
            assert client.cookies.get('funk_session')==original_session
            assert client.post('/api/auth/login',json={'password':'original-test-password'}).status_code==200
            assert [b['id'] for b in client.get('/api/bots').json()]==[bot]
            assert client.get('/api/control/pause').json()=={'paused':True}
            assert client.get('/api/settings').json()['gateways']['openrouter']['has_key']
            state=client.get('/api/workspace/restore-status').json()
            assert state['active']=='restores/'+stage and state['previous']==''
            assert pointer.read(root)['active']==state['active']
            import sqlite3
            with sqlite3.connect(root/'funk.db') as db:
                assert db.execute('SELECT count(*) FROM bots').fetchone()[0]==2
            with sqlite3.connect(root/'restores'/stage/'funk.db') as db:
                from cryptography.fernet import Fernet
                encrypted=json.loads(db.execute("SELECT value FROM config WHERE key='gateways'").fetchone()[0])['openrouter']['key']
                assert Fernet((root/'restores'/stage/'vault.key').read_bytes()).decrypt(encrypted.encode())==b'backup-secret-123456789'
            # A completely new process must honor the persisted active pointer.
            process.terminate();process.wait(timeout=10)
            process=subprocess.Popen(args,cwd=backend,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            wait(lambda: client.get('/api/health').status_code==200)
            assert [b['id'] for b in client.get('/api/bots').json()]==[bot]
    finally:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill();process.wait(timeout=5)


def test_override_session_secret_prevents_automatic_restore(monkeypatch):
    monkeypatch.setenv('FUNK_ENABLE_RESTORE_RESTART','1')
    monkeypatch.setenv('FUNK_SESSION_SECRET','stable-override')
    with TestClient(service.app) as client:
        setup(client);client.put('/api/control/pause',json={'paused':True})
        assert not client.get('/api/workspace/restore-status').json()['automatic']
        result=client.post('/api/workspace/restore?activate=true',content=b'bad',headers={'content-type':'application/zip'})
        assert result.status_code==409 and client.get('/api/workspace/restores').json()==[]


def test_staged_symlink_is_rejected_before_activation(tmp_path):
    from funkbot.backup import validate_stage,BackupError
    stage=tmp_path/'stage';stage.mkdir()
    (stage/'funk.db').symlink_to(tmp_path/'secret')
    (stage/'vault.key').write_text('irrelevant')
    (stage/'session.key').write_text('irrelevant')
    with pytest.raises(BackupError,match='Unsafe'):
        validate_stage(stage,'0020_group_chats')


def test_switch_fails_closed_if_error_occurs_after_pointer_commit(monkeypatch):
    from test_backup import keys
    monkeypatch.setenv('FUNK_ENABLE_RESTORE_RESTART','1');monkeypatch.delenv('FUNK_SESSION_SECRET',raising=False)
    monkeypatch.setattr(service,'DATA_ROOT',service.DATA)
    monkeypatch.setattr(service,'_switching_workspace',False)
    async def no_restart(): pass
    monkeypatch.setattr(service,'restart_for_workspace',no_restart)
    original=pointer.write
    def commit_then_fail(*args):
        original(*args)
        raise OSError('simulated post-commit failure')
    monkeypatch.setattr(pointer,'write',commit_then_fail)
    with TestClient(service.app) as client:
        setup(client);keys();client.put('/api/control/pause',json={'paused':True})
        archive=client.get('/api/workspace/backup').content
        result=client.post('/api/workspace/restore?activate=true',content=archive,headers={'content-type':'application/zip'})
        assert result.status_code==503
        assert pointer.read(service.DATA)['active'].startswith('restores/')
        assert client.get('/api/health').status_code==503


def test_workspace_switch_blocks_new_requests_and_drains_accepted_handlers(monkeypatch):
    import asyncio
    import threading
    from test_backup import keys
    monkeypatch.setenv('FUNK_ENABLE_RESTORE_RESTART','1');monkeypatch.delenv('FUNK_SESSION_SECRET',raising=False)
    monkeypatch.setattr(service,'DATA_ROOT',service.DATA);monkeypatch.setattr(service,'_switching_workspace',False)
    async def no_restart(): pass
    monkeypatch.setattr(service,'restart_for_workspace',no_restart)
    entered=threading.Event();release=threading.Event();responses={}
    async def hold():
        entered.set();await asyncio.to_thread(release.wait);return {'ok':True}
    service.app.add_api_route('/api/test-restore-drain',hold,methods=['GET'])
    try:
        with TestClient(service.app) as client:
            setup(client);keys();client.put('/api/control/pause',json={'paused':True})
            archive=client.get('/api/workspace/backup').content
            pending=threading.Thread(target=lambda:responses.update(held=client.get('/api/test-restore-drain')))
            pending.start();assert entered.wait(3)
            activate=threading.Thread(target=lambda:responses.update(restore=client.post('/api/workspace/restore?activate=true',content=archive,headers={'content-type':'application/zip'})))
            activate.start()
            deadline=time.monotonic()+5
            while not service._switching_workspace and time.monotonic()<deadline: time.sleep(.01)
            assert service._switching_workspace and client.get('/api/health').status_code==503
            assert activate.is_alive()  # Cannot switch while the old request is accepted.
            release.set();pending.join(5);activate.join(5)
            assert not pending.is_alive() and not activate.is_alive()
            assert responses['held'].status_code==200 and responses['restore'].status_code==200
    finally:
        release.set()
        service.app.router.routes[:]=[route for route in service.app.router.routes if getattr(route,'path','')!='/api/test-restore-drain']
