import time
from fastapi.testclient import TestClient
import app as service
from funkbot import mission_control
from test_app import setup


def test_requires_auth_and_empty_workspace_has_no_invented_values():
    with TestClient(service.app) as c:
        assert c.get('/api/mission-control').status_code == 401
        setup(c)
        d = c.get('/api/mission-control').json()
        assert d['bots'] == {'configured': 0, 'active': 0, 'waiting_approval': 0}
        assert d['missions']['completion'] is None and d['workflow']['health'] is None
        assert d['activity'] == {'running': 0, 'queued': 0, 'active_runs': 0}
        assert d['attention']['total'] == 0 and d['paused'] is False
        assert d['spending']['spent'] == '0.0' and d['spending']['cap'] == '5.0' and d['spending']['percent'] == 0


def seed(db, now):
    for i in ('a', 'b', 'c'):
        db.execute('INSERT INTO bots VALUES (?,?,?,?,?,?,?,?)', (i, i, 'Helper', 'x', 'mint', 'round', 'smart', 1))
    db.execute("INSERT INTO runs VALUES ('r1','a','running',?,?)", (now, now))
    db.execute("INSERT INTO runs VALUES ('r2','b','waiting_approval',?,?)", (now, now))
    db.execute("INSERT INTO runs VALUES ('r3','c','failed',?,?)", (now, now))
    for mid, status in (('m1', 'done'), ('m2', 'done'), ('m3', 'failed'), ('m4', 'queued'), ('m5', 'running')):
        db.execute('INSERT INTO missions VALUES (?,?,?,?,?,?,?,?,?)', (mid, 't', 'i', None, status, None, None, now, now))
    db.execute("INSERT INTO routines VALUES ('rt','R','do',NULL,'0 9 * * *','UTC',0,?,?,?)", (now + 99, now, now))
    db.execute("INSERT INTO routine_runs VALUES ('rr','rt','m1',?,?,'approved',0,0)", (now, now))
    db.execute("INSERT INTO routine_runs VALUES ('rr2','rt','m3',?,?,'approved',0,0)", (now + 1, now))
    db.execute("INSERT INTO inbox_notices VALUES ('n1','a','x','t','b',NULL,NULL,?,NULL)", (now,))


def test_counts_distinguish_configured_from_active_and_use_real_rows():
    now = time.time()
    with TestClient(service.app) as c:
        setup(c)
        with service.db() as db:
            seed(db, now)
            d = mission_control.summary(db, now)
        assert d['bots'] == {'configured': 3, 'active': 2, 'waiting_approval': 1}
        assert (d['missions']['done'], d['missions']['failed'], d['missions']['completion']) == (2, 1, 67)
        assert (d['workflow']['done'], d['workflow']['failed'], d['workflow']['health'], d['workflow']['routines_scheduled']) == (1, 1, 50, 1)
        assert d['activity'] == {'running': 1, 'queued': 1, 'active_runs': 2}
        assert d['attention']['failures'] == 1 and d['attention']['messages'] == 1


def test_pause_spend_and_unverifiable_spend_are_reported_honestly():
    with TestClient(service.app) as c:
        setup(c)
        assert c.put('/api/control/pause', json={'paused': True}).status_code == 200
        assert c.get('/api/mission-control').json()['paused'] is True
        with service.db() as db:
            db.execute("INSERT INTO usage (bot_id,gateway,model,prompt_tokens,completion_tokens,cost,created_at) VALUES (NULL,'g','m',1,1,NULL,?)", (time.time(),))
        spend = c.get('/api/mission-control').json()['spending']
        assert 'cannot be verified' in spend['error'] and 'percent' not in spend
