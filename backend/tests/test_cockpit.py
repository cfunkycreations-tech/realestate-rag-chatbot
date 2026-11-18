import json
import time

from fastapi.testclient import TestClient

import app as service
from test_app import setup
from test_career_progression import bots, finish, dump


def test_requires_auth_and_empty_install_shows_zeros_and_no_invented_figures():
    with TestClient(service.app) as c:
        assert c.get('/api/cockpit/workforce').status_code == 401
        assert c.get('/api/cockpit/sources').status_code == 401
        setup(c)
        w = c.get('/api/cockpit/workforce').json()
        assert w['bots'] == {'configured': 0, 'busy': 0, 'waiting_approval': 0, 'idle': 0, 'needing_attention': 0}
        assert w['missions'] == {'pending': 0, 'active': 0, 'blocked': 0, 'completed': 0, 'failed': 0, 'window_days': 7}
        assert w['council']['open_proposals'] == 0 and w['training']['results_recorded'] == 0 and w['spending']['by_bot'] == []


def test_workforce_counts_real_records_and_the_cockpit_writes_nothing():
    with TestClient(service.app) as c:
        setup(c)
        a, b = bots(c, 'Ava', 'Ben')
        now = time.time()
        with service.db() as db:
            finish(db, a, n=3, status='done')
            finish(db, a, n=1, status='failed', tag='f')
            db.execute("INSERT INTO runs VALUES ('r1',?,'running',?,?)", (b, now, now))
            before = dump(db, skip=set())
        w = c.get('/api/cockpit/workforce').json()
        assert w['bots']['configured'] == 2 and w['bots']['busy'] == 1 and w['bots']['idle'] == 1
        assert w['missions']['completed'] == 3 and w['missions']['failed'] == 1
        with service.db() as db:
            assert dump(db, skip=set()) == before         # read-only


def test_sources_are_not_connected_until_an_enabled_matching_connector_exists_and_never_invent_figures():
    with TestClient(service.app) as c:
        setup(c)
        s = c.get('/api/cockpit/sources').json()
        assert s['lyricist']['connected'] is False and s['business']['connected'] is False
        assert s['lyricist']['figures'] is None and 'Not connected' in s['lyricist']['note']
        with service.db() as db:
            db.execute('INSERT OR REPLACE INTO config VALUES (?,?)', ('mcp_connectors', json.dumps({'g1': {'name': 'GitHub', 'url': 'https://example.test/mcp', 'enabled': True, 'allowed_tools': []}})))
        s = c.get('/api/cockpit/sources').json()
        assert s['lyricist']['connected'] is True and s['lyricist']['figures'] is None   # connected, but nothing is made up
        assert s['business']['connected'] is False
