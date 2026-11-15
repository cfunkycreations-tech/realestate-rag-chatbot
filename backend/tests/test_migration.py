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
        assert c.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0009_tool_risks'
    assert json.loads(service.config('gateways'))['openrouter']['key'] == encrypted
    assert service.gateway_config('openrouter')[1]['Authorization'] == 'Bearer ' + secret


def test_budget_migration_from_previous_schema_preserves_existing_data(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path

    path = tmp_path / 'previous.db'
    engine = engine_for(str(path))
    with engine.connect() as connection:
        cfg = Config()
        cfg.set_main_option('script_location', str(Path(service.__file__).parent / 'funkbot' / 'migrations'))
        cfg.attributes['connection'] = connection
        command.upgrade(cfg, '0004_team_indexes')
        connection.commit()
        connection.exec_driver_sql("INSERT INTO config VALUES ('gateways','encrypted-existing-value')")
        connection.exec_driver_sql("INSERT INTO bots VALUES ('b','Original','Editor','instructions','mint','round','smart',1)")
        connection.exec_driver_sql("INSERT INTO characters VALUES ('c','hash','Sprite','sprite','role','[]','note','common',1,1)")
        connection.exec_driver_sql("INSERT INTO bot_characters VALUES ('b','c',1)")
        connection.exec_driver_sql("INSERT INTO messages VALUES ('m','b','user','keep',1)")
        connection.commit()
    migrate(path)
    migrate(path)
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == '0009_tool_risks'
        assert connection.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar() == 'encrypted-existing-value'
        assert connection.exec_driver_sql("SELECT name FROM bots WHERE id='b'").scalar() == 'Original'
        assert connection.exec_driver_sql("SELECT character_id FROM bot_characters WHERE bot_id='b'").scalar() == 'c'
        assert connection.exec_driver_sql("SELECT content FROM messages WHERE id='m'").scalar() == 'keep'
        assert connection.exec_driver_sql('SELECT count(*) FROM budget_reservations').scalar() == 0


def test_budget_reconciliation_migration_from_previous_schema(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path = tmp_path / 'budget-v1.db'
    engine = engine_for(str(path))
    with engine.connect() as c:
        cfg = Config()
        cfg.set_main_option('script_location', str(Path(service.__file__).parent / 'funkbot' / 'migrations'))
        cfg.attributes['connection'] = c
        command.upgrade(cfg, '0005_budget_foundation')
        c.commit()
        c.exec_driver_sql("INSERT INTO budget_limits VALUES ('account',123456789,NULL)")
        c.exec_driver_sql("INSERT INTO budget_prices VALUES ('smart','1.2','2.3',10000,1000)")
        c.exec_driver_sql("INSERT INTO budget_reservations (run_id,bot_id,profile,created_at,reserved_nanos,prompt_usd_per_million,completion_usd_per_million,max_prompt_tokens,max_completion_tokens,status) VALUES ('run','bot','smart',1,100,'1.2','2.3',10000,1000,'uncertain')")
        c.commit()
    migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == '0009_tool_risks'
        assert c.exec_driver_sql("SELECT daily_nanos FROM budget_limits WHERE scope='account'").scalar() == 123456789
        assert c.exec_driver_sql("SELECT prompt_usd_per_million FROM budget_prices WHERE profile='smart'").scalar() == '1.2'
        assert c.exec_driver_sql("SELECT status FROM budget_reservations WHERE run_id='run'").scalar() == 'uncertain'
        assert c.exec_driver_sql('SELECT count(*) FROM budget_reconciliations').scalar() == 0


def test_tool_audit_migration_from_previous_schema(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path = tmp_path / 'before-tools.db'
    engine = engine_for(str(path))
    with engine.connect() as c:
        cfg = Config()
        cfg.set_main_option('script_location', str(Path(service.__file__).parent / 'funkbot' / 'migrations'))
        cfg.attributes['connection'] = c
        command.upgrade(cfg, '0006_budget_reconciliation')
        c.commit()
        c.exec_driver_sql("INSERT INTO config VALUES ('gateways','existing-encrypted-gateways')")
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Kept','Editor','instructions','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO characters VALUES ('c','hash','Sprite','sprite','role','[]','note','common',1,1)")
        c.exec_driver_sql("INSERT INTO bot_characters VALUES ('b','c',1)")
        c.exec_driver_sql("INSERT INTO budget_limits VALUES ('account',5000000000,NULL)")
        c.commit()
    migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == '0009_tool_risks'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar() == 'existing-encrypted-gateways'
        assert c.exec_driver_sql("SELECT name FROM bots WHERE id='b'").scalar() == 'Kept'
        assert c.exec_driver_sql("SELECT character_id FROM bot_characters WHERE bot_id='b'").scalar() == 'c'
        assert c.exec_driver_sql("SELECT daily_nanos FROM budget_limits WHERE scope='account'").scalar() == 5000000000
        assert c.exec_driver_sql('SELECT count(*) FROM tool_calls').scalar() == 0
        assert c.exec_driver_sql('SELECT count(*) FROM tool_audit').scalar() == 0


def test_budget_round_migration_from_previous_schema(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path=tmp_path/'before-rounds.db';engine=engine_for(str(path))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0007_tool_audit');c.commit()
        c.exec_driver_sql("INSERT INTO budget_reservations (run_id,bot_id,profile,created_at,reserved_nanos,prompt_usd_per_million,completion_usd_per_million,max_prompt_tokens,max_completion_tokens,status) VALUES ('r','b','smart',1,100,'1','2',100,100,'uncertain')")
        c.exec_driver_sql("INSERT INTO tool_calls VALUES ('call','r','b','write_note','write','{}','pending',NULL,1,1)")
        c.exec_driver_sql("INSERT INTO tool_audit (call_id,action,created_at) VALUES ('call','proposed',1)")
        c.commit()
    migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0009_tool_risks'
        assert c.exec_driver_sql("SELECT parent_run_id FROM budget_reservations WHERE run_id='r'").scalar()=='r'
        assert c.exec_driver_sql("SELECT status FROM budget_reservations WHERE run_id='r'").scalar()=='uncertain'
        assert c.exec_driver_sql("SELECT status FROM tool_calls WHERE id='call'").scalar()=='pending'
        assert c.exec_driver_sql("SELECT action FROM tool_audit WHERE call_id='call'").scalar()=='proposed'


def test_tool_risk_migration_from_previous_schema_preserves_history(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path=tmp_path/'before-risk-categories.db';engine=engine_for(str(path))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0008_budget_rounds');c.commit()
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Original','Editor','instructions','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO characters VALUES ('c','hash','Sprite','sprite','role','[]','note','common',1,1)")
        c.exec_driver_sql("INSERT INTO bot_characters VALUES ('b','c',1)")
        c.exec_driver_sql("INSERT INTO config VALUES ('gateways','saved-encrypted-gateway')")
        c.exec_driver_sql("INSERT INTO tool_calls (rowid,id,run_id,bot_id,tool_name,risk,arguments,status,created_at,updated_at) VALUES (42,'call','run','b','write_note','write','{}','pending',1,1)")
        c.exec_driver_sql("INSERT INTO tool_audit (call_id,action,created_at) VALUES ('call','proposed',1)")
        c.commit()
    migrate(path);migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0009_tool_risks'
        assert c.exec_driver_sql("SELECT rowid FROM tool_calls WHERE id='call'").scalar()==42
        assert c.exec_driver_sql("SELECT action FROM tool_audit WHERE call_id='call'").scalar()=='proposed'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar()=='saved-encrypted-gateway'
        assert c.exec_driver_sql("SELECT character_id FROM bot_characters WHERE bot_id='b'").scalar()=='c'
        assert c.exec_driver_sql("SELECT name FROM bots WHERE id='b'").scalar()=='Original'
        c.exec_driver_sql("INSERT INTO tool_calls VALUES ('send','run','b','test','send','{}','pending',NULL,2,2)")
        c.exec_driver_sql("INSERT INTO tool_calls VALUES ('spend','run','b','test','spend','{}','pending',NULL,3,3)")
