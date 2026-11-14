import json
import sqlite3

import app as service


def test_slice2_database_migrates_without_data_loss(tmp_path, monkeypatch):
    path = tmp_path / 'slice2.db'
    secret = 'opaque-existing-gateway-secret'
    encrypted = service.cipher.encrypt(secret.encode()).decode()
    gateways = {'openrouter': {'url': 'https://openrouter.ai/api/v1', 'key': encrypted},
                'omniroute': {'url': 'http://localhost:20128/v1', 'key': ''},
                'custom': {'url': '', 'key': ''}}
    # Real slice-2 schema, with no Alembic version table.
    with sqlite3.connect(path) as c:
        c.executescript('''
        CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE bots (id TEXT PRIMARY KEY, name TEXT NOT NULL, title TEXT NOT NULL, personality TEXT NOT NULL, color TEXT NOT NULL, shape TEXT NOT NULL, profile TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE messages (id TEXT PRIMARY KEY, bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE usage (id INTEGER PRIMARY KEY, bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL, gateway TEXT, model TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, cost REAL, created_at REAL NOT NULL);
        CREATE TABLE login_guard (id INTEGER PRIMARY KEY CHECK (id=1), failures INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0);
        CREATE TABLE runs (id TEXT PRIMARY KEY, bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE, status TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE run_events (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE, event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL);
        ''')
        c.execute('INSERT INTO config VALUES (?,?)', ('gateways',json.dumps(gateways)))
        c.execute('INSERT INTO bots VALUES (?,?,?,?,?,?,?,?)', ('b','Original','Helper','Be helpful','mint','round','smart',1))
        c.execute('INSERT INTO messages VALUES (?,?,?,?,?)', ('m','b','user','Prior message',2))
        c.execute('INSERT INTO runs VALUES (?,?,?,?,?)', ('r','b','done',3,4))
        c.execute('INSERT INTO run_events (run_id,event_type,payload,created_at) VALUES (?,?,?,?)', ('r','done','{}',4))
        c.execute('INSERT INTO usage VALUES (?,?,?,?,?,?,?,?)', (1,'b','openrouter','model',5,7,0.01,4))
    monkeypatch.setattr(service, 'DB', path)
    service.init_db()
    service.init_db()  # idempotent startup
    with service.db() as c:
        assert c.execute('SELECT name FROM bots WHERE id=?',('b',)).fetchone()['name'] == 'Original'
        assert c.execute('SELECT content FROM messages WHERE id=?',('m',)).fetchone()['content'] == 'Prior message'
        assert c.execute('SELECT status FROM runs WHERE id=?',('r',)).fetchone()['status'] == 'done'
        assert c.execute('SELECT event_type FROM run_events WHERE run_id=?',('r',)).fetchone()['event_type'] == 'done'
        assert c.execute('SELECT completion_tokens FROM usage').fetchone()['completion_tokens'] == 7
        assert c.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0002_event_log'
    assert json.loads(service.config('gateways'))['openrouter']['key'] == encrypted
    assert service.gateway_config('openrouter')[1]['Authorization'] == 'Bearer ' + secret
