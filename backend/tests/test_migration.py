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
        assert c.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0033_bot_comms'
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
        assert connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == '0033_bot_comms'
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
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == '0033_bot_comms'
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
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == '0033_bot_comms'
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
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
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
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
        assert c.exec_driver_sql("SELECT rowid FROM tool_calls WHERE id='call'").scalar()==42
        assert c.exec_driver_sql("SELECT action FROM tool_audit WHERE call_id='call'").scalar()=='proposed'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar()=='saved-encrypted-gateway'
        assert c.exec_driver_sql("SELECT character_id FROM bot_characters WHERE bot_id='b'").scalar()=='c'
        assert c.exec_driver_sql("SELECT name FROM bots WHERE id='b'").scalar()=='Original'
        c.exec_driver_sql("INSERT INTO tool_calls VALUES ('send','run','b','test','send','{}','pending',NULL,2,2)")
        c.exec_driver_sql("INSERT INTO tool_calls VALUES ('spend','run','b','test','spend','{}','pending',NULL,3,3)")


def test_mission_migration_from_previous_schema_keeps_existing_data(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path=tmp_path/'before-missions.db';engine=engine_for(str(path))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0009_tool_risks');c.commit()
        c.exec_driver_sql("INSERT INTO config VALUES ('gateways','existing-encrypted-keys')")
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Existing','Editor','instructions','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO characters VALUES ('c','hash','Sprite','sprite','role','[]','note','common',1,1)")
        c.exec_driver_sql("INSERT INTO bot_characters VALUES ('b','c',1)")
        c.exec_driver_sql("INSERT INTO messages VALUES ('m','b','user','Keep me',1)")
        c.exec_driver_sql("INSERT INTO runs VALUES ('r','b','done',1,2)")
        c.exec_driver_sql("INSERT INTO tool_calls VALUES ('call','r','b','write_note','write','{}','completed','{}',1,2)")
        c.exec_driver_sql("INSERT INTO tool_audit (call_id,action,created_at) VALUES ('call','completed',2)")
        c.exec_driver_sql("INSERT INTO budget_reservations (run_id,bot_id,profile,created_at,reserved_nanos,prompt_usd_per_million,completion_usd_per_million,max_prompt_tokens,max_completion_tokens,status,parent_run_id) VALUES ('r','b','smart',1,100,'1','2',100,100,'settled','r')")
        c.commit()
    migrate(path);migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar()=='existing-encrypted-keys'
        assert c.exec_driver_sql("SELECT name FROM bots WHERE id='b'").scalar()=='Existing'
        assert c.exec_driver_sql("SELECT character_id FROM bot_characters WHERE bot_id='b'").scalar()=='c'
        assert c.exec_driver_sql("SELECT content FROM messages WHERE id='m'").scalar()=='Keep me'
        assert c.exec_driver_sql("SELECT status FROM budget_reservations WHERE run_id='r'").scalar()=='settled'
        assert c.exec_driver_sql("SELECT action FROM tool_audit WHERE call_id='call'").scalar()=='completed'
        for table in ('bot_groups','bot_group_members','missions','mission_assignees','mission_runs'):
            assert c.exec_driver_sql('SELECT count(*) FROM '+table).scalar()==0


def test_projects_migration_from_missions_schema_preserves_data(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path=tmp_path/'before-projects.db'; engine=engine_for(str(path))
    with engine.connect() as c:
        cfg=Config(); cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations')); cfg.attributes['connection']=c
        command.upgrade(cfg,'0010_missions'); c.commit()
        c.exec_driver_sql("INSERT INTO config VALUES ('gateways','encrypted-keep')")
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Existing','Editor','instructions','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO missions VALUES ('m','Mission','Do work',NULL,'done','Result',NULL,1,2)")
        c.exec_driver_sql("INSERT INTO mission_assignees VALUES ('m',0,'b')")
        c.commit()
    migrate(path); migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar()=='encrypted-keep'
        assert c.exec_driver_sql("SELECT result FROM missions WHERE id='m'").scalar()=='Result'
        assert c.exec_driver_sql("SELECT bot_id FROM mission_assignees WHERE mission_id='m'").scalar()=='b'
        assert c.exec_driver_sql('SELECT count(*) FROM projects').scalar()==0
        assert c.exec_driver_sql('SELECT count(*) FROM project_notes').scalar()==0
        assert c.exec_driver_sql('SELECT count(*) FROM project_missions').scalar()==0


def test_lab_memory_migration_from_projects_schema(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path=tmp_path/'before-lab.db';engine=engine_for(str(path))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0011_projects');c.commit()
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Kept','Editor','prompt','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO projects VALUES ('p','Kept project','Description','b',1,1)")
        c.exec_driver_sql("INSERT INTO project_notes VALUES ('n','p','Kept note',1,1)")
        c.exec_driver_sql("INSERT INTO config VALUES ('gateways','encrypted-keep')")
        c.commit()
    migrate(path);migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
        assert c.exec_driver_sql("SELECT content FROM project_notes WHERE id='n'").scalar()=='Kept note'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar()=='encrypted-keep'
        for table in ('bot_memories','lab_experiments','lab_runs'): assert c.exec_driver_sql('SELECT count(*) FROM '+table).scalar()==0


def test_memory_layers_migrate_previous_data_without_loss(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path=tmp_path/'before-memory-layers.db';engine=engine_for(str(path))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0012_lab_memory');c.commit()
        c.exec_driver_sql("INSERT INTO config VALUES ('gateways','encrypted-keep')")
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Kept','Editor','prompt','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO projects VALUES ('p','Project','Details','b',1,1)")
        c.exec_driver_sql("INSERT INTO bot_memories VALUES ('m','b','Keep preference',1,1,2)")
        c.exec_driver_sql("INSERT INTO lab_experiments VALUES ('e','b','question','prompt','done',NULL,1,2)")
        c.commit()
    migrate(path);migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar()=='encrypted-keep'
        assert c.exec_driver_sql("SELECT content FROM bot_memories WHERE id='m'").scalar()=='Keep preference'
        assert c.exec_driver_sql("SELECT source FROM bot_memories WHERE id='m'").scalar()=='owner'
        assert c.exec_driver_sql("SELECT prompt FROM lab_experiments WHERE id='e'").scalar()=='question'
        assert c.exec_driver_sql('SELECT count(*) FROM shared_memories').scalar()==0
        assert c.exec_driver_sql('SELECT count(*) FROM project_memories').scalar()==0


def test_skills_migration_preserves_previous_schema(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path=tmp_path/'before-skills.db';engine=engine_for(str(path))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0013_memory_layers');c.commit()
        c.exec_driver_sql("INSERT INTO config VALUES ('gateways','encrypted-keep')")
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Kept','Editor','prompt','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO messages VALUES ('msg','b','user','History',1)")
        c.exec_driver_sql("INSERT INTO bot_memories VALUES ('m','b','Preference',1,1,2,'owner',NULL)")
        c.exec_driver_sql("INSERT INTO shared_memories VALUES ('s','Shared','owner',NULL,1,1)")
        c.commit()
    migrate(path);migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar()=='encrypted-keep'
        assert c.exec_driver_sql("SELECT content FROM messages WHERE id='msg'").scalar()=='History'
        assert c.exec_driver_sql("SELECT content FROM bot_memories WHERE id='m'").scalar()=='Preference'
        assert c.exec_driver_sql("SELECT content FROM shared_memories WHERE id='s'").scalar()=='Shared'
        assert c.exec_driver_sql('SELECT count(*) FROM skills').scalar()==0


def test_followups_migration_preserves_previous_data(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path=tmp_path/'before-followups.db';engine=engine_for(str(path))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0014_skills');c.commit()
        c.exec_driver_sql("INSERT INTO config VALUES ('gateways','encrypted-keep')")
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Kept','Editor','prompt','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO skills VALUES ('s','review','Review','Use','Input','Steps','Check',1,2)")
        c.exec_driver_sql("INSERT INTO bot_memories VALUES ('m','b','Keep',1,1,2,'owner',NULL)")
        c.commit()
    migrate(path);migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar()=='encrypted-keep'
        assert c.exec_driver_sql("SELECT steps FROM skills WHERE id='s'").scalar()=='Steps'
        assert c.exec_driver_sql("SELECT content FROM bot_memories WHERE id='m'").scalar()=='Keep'
        assert c.exec_driver_sql('SELECT count(*) FROM followups').scalar()==0


def test_handoff_migration_preserves_existing_records(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path=tmp_path/'before-handoffs.db';engine=engine_for(str(path))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0015_followups');c.commit()
        c.exec_driver_sql("INSERT INTO config VALUES ('gateways','encrypted-keep')")
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Kept','Editor','prompt','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO missions VALUES ('mission','Work','Instructions',NULL,'done','Result',NULL,1,2)")
        c.exec_driver_sql("INSERT INTO followups VALUES ('f','b',NULL,'Finish',4,'open',1,2)")
        c.commit()
    migrate(path);migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar()=='encrypted-keep'
        assert c.exec_driver_sql("SELECT result FROM missions WHERE id='mission'").scalar()=='Result'
        assert c.exec_driver_sql("SELECT summary FROM followups WHERE id='f'").scalar()=='Finish'
        assert c.exec_driver_sql('SELECT count(*) FROM handoffs').scalar()==0


def test_routines_migration_preserves_handoffs(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path=tmp_path/'before-routines.db';engine=engine_for(str(path))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0016_handoffs');c.commit()
        c.exec_driver_sql("INSERT INTO config VALUES ('gateways','encrypted-keep')")
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Kept','Editor','prompt','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO bots VALUES ('c','Other','Editor','prompt','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO missions VALUES ('mission','Work','Instructions',NULL,'done','Result',NULL,1,2)")
        c.exec_driver_sql("INSERT INTO handoffs VALUES ('h','b','c','mission','Reason','Context',1)")
        c.commit()
    migrate(path);migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar()=='encrypted-keep'
        assert c.exec_driver_sql("SELECT context FROM handoffs WHERE id='h'").scalar()=='Context'
        assert c.exec_driver_sql('SELECT count(*) FROM routines').scalar()==0


def test_chat_migration_keeps_all_prior_messages_and_routines(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path=tmp_path/'before-chats.db';engine=engine_for(str(path))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0017_routines');c.commit()
        c.exec_driver_sql("INSERT INTO config VALUES ('gateways','encrypted-keep')")
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Kept','Editor','prompt','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO messages VALUES ('msg','b','user','History',2)")
        c.exec_driver_sql("INSERT INTO runs VALUES ('r','b','done',2,2)")
        c.exec_driver_sql("INSERT INTO routines VALUES ('rt','Work','Do','b','0 9 * * *','UTC',1,4,1,1)")
        c.commit()
    migrate(path);migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar()=='encrypted-keep'
        assert c.exec_driver_sql("SELECT content FROM messages WHERE id='msg'").scalar()=='History'
        assert c.exec_driver_sql("SELECT chat_id FROM chat_messages WHERE message_id='msg'").scalar()=='legacy-b'
        assert c.exec_driver_sql("SELECT chat_id FROM chat_runs WHERE run_id='r'").scalar()=='legacy-b'
        assert c.exec_driver_sql("SELECT title FROM routines WHERE id='rt'").scalar()=='Work'


def test_attachments_migration_preserves_chat_history(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path=tmp_path/'before-attachments.db';engine=engine_for(str(path))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0018_chats');c.commit()
        c.exec_driver_sql("INSERT INTO config VALUES ('gateways','encrypted-keep')")
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Kept','Editor','prompt','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO chats VALUES ('chat','b','Research',1,1)")
        c.exec_driver_sql("INSERT INTO messages VALUES ('msg','b','user','History',2)")
        c.exec_driver_sql("INSERT INTO chat_messages VALUES ('chat','msg')")
        c.commit()
    migrate(path);migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar()=='encrypted-keep'
        assert c.exec_driver_sql("SELECT content FROM messages WHERE id='msg'").scalar()=='History'
        assert c.exec_driver_sql("SELECT chat_id FROM chat_messages WHERE message_id='msg'").scalar()=='chat'
        assert c.exec_driver_sql('SELECT count(*) FROM chat_attachments').scalar()==0


def test_group_chat_migration_preserves_attachments_and_prior_workspace(tmp_path):
    from alembic import command
    from alembic.config import Config
    from funkbot.database import engine_for, migrate
    from pathlib import Path
    path=tmp_path/'before-group-chat.db';engine=engine_for(str(path))
    with engine.connect() as c:
        cfg=Config();cfg.set_main_option('script_location',str(Path(service.__file__).parent/'funkbot'/'migrations'));cfg.attributes['connection']=c
        command.upgrade(cfg,'0019_attachments');c.commit()
        c.exec_driver_sql("INSERT INTO config VALUES ('gateways','encrypted-keep')")
        c.exec_driver_sql("INSERT INTO bots VALUES ('b','Kept','Editor','prompt','mint','round','smart',1)")
        c.exec_driver_sql("INSERT INTO chats VALUES ('c','b','Chat',1,1)")
        c.exec_driver_sql("INSERT INTO chat_attachments VALUES ('a','c',NULL,'file.txt','text/plain',X'6869','hi',1)")
        c.commit()
    migrate(path);migrate(path)
    with engine.connect() as c:
        assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0033_bot_comms'
        assert c.exec_driver_sql("SELECT value FROM config WHERE key='gateways'").scalar()=='encrypted-keep'
        assert c.exec_driver_sql("SELECT data FROM chat_attachments WHERE id='a'").scalar()==b'hi'
        assert c.exec_driver_sql('SELECT count(*) FROM group_chat_messages').scalar()==0
