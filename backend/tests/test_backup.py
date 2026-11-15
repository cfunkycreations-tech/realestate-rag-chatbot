import base64
import io
import json
import os
import sqlite3
import zipfile
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import app as service
from test_app import setup


def keys():
    key=base64.urlsafe_b64encode(service.cipher._signing_key+service.cipher._encryption_key)
    (service.DATA/'vault.key').write_bytes(key)
    (service.DATA/'session.key').write_text('test-session-key')


def pause(c):
    assert c.put('/api/control/pause',json={'paused':True}).status_code==200


def test_backup_restore_roundtrip_is_staged_and_preserves_current_installation():
    with TestClient(service.app) as c:
        assert c.get('/api/workspace/backup').status_code==401
        setup(c);keys()
        bot=c.post('/api/bots',json={'name':'Original'}).json()['id']
        assert c.put('/api/settings/gateways/openrouter',json={'url':'https://example.com/v1','key':'private-key-abcdefgh12345'}).status_code==200
        assert c.put('/api/connectors/new',json={'name':'MCP','url':'https://example.com/mcp','key':'connector-token-abcdefgh','enabled':True,'allowed_tools':['read']}).status_code==200
        workspace=service.DATA/'workspaces'/bot;workspace.mkdir(parents=True);(workspace/'note.txt').write_text('precious note')
        (service.DATA/'vault').mkdir();(service.DATA/'vault'/'sprite.png').write_bytes(b'sprite')
        (service.DATA/'banner.png').write_bytes(b'banner')
        assert c.get('/api/workspace/backup').status_code==409
        pause(c)
        response=c.get('/api/workspace/backup');assert response.status_code==200
        assert response.headers['cache-control']=='no-store'
        archive=response.content
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            assert set(z.namelist())=={'funk.db','vault.key','session.key','banner.png','vault/sprite.png',f'workspaces/{bot}/note.txt','manifest.json'}
        c.post('/api/bots',json={'name':'Later'})
        result=c.post('/api/workspace/restore',content=archive,headers={'content-type':'application/zip'});assert result.status_code==200, result.text
        stage=service.DATA/'restores'/result.json()['staged_id']
        assert (workspace/'note.txt').read_text()=='precious note'
        assert (stage/'workspaces'/bot/'note.txt').read_text()=='precious note'
        with sqlite3.connect(stage/'funk.db') as db:
            assert db.execute('select name from bots').fetchall()==[('Original',)]
            gateways=json.loads(db.execute("select value from config where key='gateways'").fetchone()[0])
            assert Fernet((stage/'vault.key').read_bytes()).decrypt(gateways['openrouter']['key'].encode())==b'private-key-abcdefgh12345'
            connectors=json.loads(db.execute("select value from config where key='mcp_connectors'").fetchone()[0])
            assert Fernet((stage/'vault.key').read_bytes()).decrypt(next(iter(connectors.values()))['key'].encode())==b'connector-token-abcdefgh'
        assert len(c.get('/api/bots').json())==2
        assert c.delete('/api/workspace/restore/'+result.json()['staged_id']).status_code==200
        assert not stage.exists() and workspace.exists()


def test_malicious_archives_and_symlinks_are_rejected_without_touching_data(tmp_path):
    with TestClient(service.app) as c:
        setup(c);keys();pause(c)
        bot=c.post('/api/bots',json={'name':'Keep'}).json()['id']
        original=c.get('/api/workspace/backup').content
        def altered(replace=None, extra=None):
            out=io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(original)) as src,zipfile.ZipFile(out,'w') as dst:
                for entry in src.infolist(): dst.writestr(entry.filename,(replace if replace is not None and entry.filename=='funk.db' else src.read(entry)))
                if extra: dst.writestr(extra,b'evil')
            return out.getvalue()
        for archive in [b'bad',altered(replace=b'broken'),altered(extra='../escape')]:
            assert c.post('/api/workspace/restore',content=archive,headers={'content-type':'application/zip'}).status_code==400
        assert not (service.DATA/'escape').exists()
        assert not list((service.DATA/'restores').iterdir())
        assert c.get('/api/bots').json()[0]['id']==bot
        (service.DATA/'banner.png').symlink_to(tmp_path/'outside')
        assert c.get('/api/workspace/backup').status_code==400
        assert c.delete('/api/workspace/restore/../../vault').status_code in (404,405)


def test_restore_rejects_traversal_compression_wrong_key_and_schema():
    import hashlib
    with TestClient(service.app) as c:
        setup(c);keys();pause(c)
        c.put('/api/settings/gateways/openrouter',json={'url':'https://example.com/v1','key':'private-key-abcdefgh12345'})
        original=c.get('/api/workspace/backup').content
        with zipfile.ZipFile(io.BytesIO(original)) as z:
            content={name:z.read(name) for name in z.namelist() if name!='manifest.json'}
        def make(files,compression=zipfile.ZIP_STORED):
            meta={name:{'size':len(value),'sha256':hashlib.sha256(value).hexdigest()} for name,value in files.items()}
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w',compression=compression) as z:
                for name,value in files.items(): z.writestr(name,value)
                z.writestr('manifest.json',json.dumps({'format':'funkbot-workspace','version':1,'files':meta}))
            return out.getvalue()
        badkey={**content,'vault.key':Fernet.generate_key()}
        traversal={**content,'workspaces/../../escaped':b'oops'}
        dbfile=service.DATA/'other.db';dbfile.write_bytes(content['funk.db'])
        db=sqlite3.connect(dbfile);db.execute("update alembic_version set version_num='old'");db.commit();db.close()
        wrongversion={**content,'funk.db':dbfile.read_bytes()}
        for archive in (make(badkey),make(traversal),make(wrongversion),make(content,zipfile.ZIP_DEFLATED)):
            r=c.post('/api/workspace/restore',content=archive,headers={'content-type':'application/zip'})
            assert r.status_code==400,r.text
        assert c.get('/api/workspace/restores').json()==[]
        assert not (service.DATA/'escaped').exists()
        assert c.post('/api/workspace/restore',content=original).status_code==415


def test_restore_upgrades_older_snapshot_only_in_isolated_stage(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for
    from funkbot.backup import create
    with TestClient(service.app) as c:
        setup(c);keys();pause(c)
        old=tmp_path/'old';old.mkdir()
        (old/'vault.key').write_bytes((service.DATA/'vault.key').read_bytes())
        (old/'session.key').write_bytes((service.DATA/'session.key').read_bytes())
        engine=engine_for(str(old/'funk.db'))
        with engine.connect() as conn:
            cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=conn
            command.upgrade(cfg,'0019_attachments');conn.commit()
            conn.exec_driver_sql("INSERT INTO config VALUES ('gateways','{}')")
            conn.exec_driver_sql("INSERT INTO bots VALUES ('b','Preserved','Editor','prompt','mint','round','smart',1)")
            conn.commit()
        out=io.BytesIO();create(old,old/'funk.db',out)
        r=c.post('/api/workspace/restore',content=out.getvalue(),headers={'content-type':'application/zip'});assert r.status_code==200,r.text
        stage=service.DATA/'restores'/r.json()['staged_id']
        with sqlite3.connect(stage/'funk.db') as db:
            assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0020_group_chats'
            assert db.execute('SELECT name FROM bots').fetchone()[0]=='Preserved'
        with sqlite3.connect(old/'funk.db') as db: assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0019_attachments'
