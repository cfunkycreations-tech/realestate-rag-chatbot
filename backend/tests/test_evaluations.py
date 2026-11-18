import json

from fastapi.testclient import TestClient

import app as service
from funkbot import careers, evaluations
from test_app import setup
from test_career_progression import bots, finish, dump

PRESET = {'id': 'writer', 'title': 'Writer', 'department': 'Content', 'level': 'junior', 'model_tier': 'light', 'personality': 'Warm.',
          'instructions': 'Write clearly.', 'permission_boundaries': ['Never publish without approval'], 'escalation': ['Legal questions']}


def hired(c):
    (a,) = bots(c, 'Ava')
    with service.db() as db:
        careers.import_presets(db, [PRESET])
    assert c.post('/api/career/attach', json={'assignments': [{'bot_id': a, 'preset_id': 'writer'}], 'confirm': True}).status_code == 200
    # attach leaves the Bot's own text alone, so give it the role rules the way a hired Bot has them
    with service.db() as db:
        preset = careers.get_preset(db, 'writer')
        db.execute('UPDATE bots SET personality=? WHERE id=?', (careers.compose_personality(preset), a))
    return a


def test_requires_auth_and_too_little_evidence_is_not_evaluated_not_failed():
    with TestClient(service.app) as c:
        assert c.get('/api/evaluations').status_code == 401
        assert c.post('/api/evaluations/run', json={}).status_code == 401
        setup(c)
        (a,) = bots(c, 'Ava')
        r = c.post('/api/evaluations/run', json={'bot_ids': [a]}).json()['runs'][0]
        assert r['certification'] == 'not_evaluated' and r['cost_usd'] == 0
        assert {x['status'] for x in r['results']} == {'not_evaluated'} and not any(x['recorded'] for x in r['results'])
        assert c.get(f'/api/evaluations/{a}').json()['history'] == []             # nothing was invented
        assert c.post('/api/evaluations/run', json={'bot_ids': [a], 'suites': ['nope']}).status_code == 400
        assert c.get('/api/evaluations/ghost').status_code == 404


def test_results_are_scored_from_records_recorded_and_certification_follows_only_counted_passes():
    with TestClient(service.app) as c:
        setup(c)
        a = hired(c)
        with service.db() as db:
            finish(db, a, n=6, status='done', verdict='verified')
            finish(db, a, n=1, status='failed', tag='f')
        run = c.post('/api/evaluations/run', json={'bot_ids': [a], 'suites': ['skill', 'compliance', 'reliability']}).json()['runs'][0]
        by = {x['suite']: x for x in run['results']}
        assert by['skill']['status'] == 'passed' and by['skill']['score'] == 100
        assert by['compliance']['status'] == 'passed' and by['compliance']['score'] == 100
        assert by['reliability']['status'] == 'passed' and by['reliability']['score'] == 86      # 6 of 7 finished
        assert run['certification'] == 'competent' and run['changed'] is True
        hist = c.get(f'/api/bots/{a}/career').json()['career']['history']
        assert hist[-1]['event'] == 'certified' and hist[-1]['detail']['label_only'] is True
        rep = c.get(f'/api/evaluations/{a}').json()
        assert rep['label'] == 'Competent' and len(rep['history']) == 3 and all(h['counts'] == 1 for h in rep['history'])

        # a regression is recorded as a failure with a cause, shows the change, and the label moves down
        with service.db() as db:
            db.execute('UPDATE bots SET personality=? WHERE id=?', ('You are a bot.', a))
        r2 = c.post('/api/evaluations/run', json={'bot_ids': [a], 'suites': ['compliance']}).json()['runs'][0]['results'][0]
        assert r2['status'] == 'failed' and r2['score'] == 0 and r2['previous_score'] == 100 and r2['delta'] == -100 and 'instructions' in r2['cause']
        assert c.get(f'/api/evaluations/{a}').json()['certification'] == 'training'


def test_simulated_results_never_count_toward_certification():
    with TestClient(service.app) as c:
        setup(c)
        a = hired(c)
        with service.db() as db:
            for suite in evaluations.CORE:
                db.execute("INSERT INTO evaluation_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (f's{suite}', a, suite, 1, 'simulated', 'passed', 100, 50, 0, '{}', '', 0, 1.0))
            assert evaluations.certification(db, a) == 'not_evaluated'


def test_evaluating_and_certifying_never_touches_permissions_budgets_or_tiers():
    with TestClient(service.app) as c:
        setup(c)
        a = hired(c)
        with service.db() as db:
            finish(db, a, n=6, status='done', verdict='verified')
            before = dump(db, skip={'evaluation_results', 'evaluation_certs', 'career_history'})
        c.post('/api/evaluations/run', json={})
        with service.db() as db:
            after = dump(db, skip={'evaluation_results', 'evaluation_certs', 'career_history'})
        assert before == after            # not one other table changed (policies, caps, tiers, wallets, secrets)


def test_instruction_changes_keep_the_old_text_and_can_be_rolled_back_even_twice():
    with TestClient(service.app) as c:
        setup(c)
        a = hired(c)
        with service.db() as db:
            original = db.execute('SELECT personality FROM bots WHERE id=?', (a,)).fetchone()['personality']
        bot = [b for b in c.get('/api/bots').json() if b['id'] == a][0]
        edit = {k: bot[k] for k in ('name', 'title', 'color', 'shape', 'profile')} | {'personality': 'Short and wrong.'}
        assert c.put(f'/api/bots/{a}', json=edit).status_code == 200
        vs = c.get(f'/api/bots/{a}/instructions').json()['versions']
        assert len(vs) == 1 and vs[0]['source'] == 'editor'
        assert c.post(f'/api/bots/{a}/instructions/rollback', json={'version_id': 'ghost'}).status_code == 404
        assert c.post(f'/api/bots/{a}/instructions/rollback', json={'version_id': vs[0]['id']}).status_code == 200
        with service.db() as db:
            assert db.execute('SELECT personality FROM bots WHERE id=?', (a,)).fetchone()['personality'] == original
        sources = [v['source'] for v in c.get(f'/api/bots/{a}/instructions').json()['versions']]
        assert 'before-rollback' in sources            # the rolled-back text itself is kept, so the undo can be undone
