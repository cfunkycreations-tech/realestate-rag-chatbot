import json
import time

import pytest
from fastapi.testclient import TestClient

import app as service
from funkbot import mentorship, progression
from test_app import FakeClient, configure_budget, setup
from test_career_progression import bots, dump, finish
from test_live_tools import final_reply
from test_missions_api import wait_mission


def ranks(db, name_level):
    """Put Bots on specific career levels the way an owner approval would."""
    for bot, level in name_level.items():
        db.execute('INSERT INTO career_levels VALUES (?,?,?) ON CONFLICT(bot_id) DO UPDATE SET level=excluded.level', (bot, level, time.time() - 90 * 86400))


OBJ = [{'skill': 'Proofreading', 'target_missions': 2}]


def test_start_rules_mentor_must_outrank_trainee_one_mentor_and_a_cap():
    with TestClient(service.app) as c:
        assert c.get('/api/mentorships').status_code == 401
        setup(c)
        mentor, t1, t2, t3, t4, peer = bots(c, 'Mia', 'T1', 'T2', 'T3', 'T4', 'Peer')
        with service.db() as db:
            ranks(db, {mentor: 'senior'})
        assert c.post('/api/mentorships', json={'mentor_id': mentor, 'trainee_id': mentor, 'objectives': OBJ}).status_code == 400
        assert c.post('/api/mentorships', json={'mentor_id': peer, 'trainee_id': t1, 'objectives': OBJ}).status_code == 400  # both trainees
        assert c.post('/api/mentorships', json={'mentor_id': mentor, 'trainee_id': t1}).status_code == 400  # no objectives, no DNA skills
        assert c.post('/api/mentorships', json={'mentor_id': mentor, 'trainee_id': t1, 'objectives': [{'skill': ' ', 'target_missions': 1}]}).status_code == 400
        ids = [c.post('/api/mentorships', json={'mentor_id': mentor, 'trainee_id': t, 'objectives': OBJ}) for t in (t1, t2, t3)]
        assert [r.status_code for r in ids] == [200, 200, 200]
        assert c.post('/api/mentorships', json={'mentor_id': mentor, 'trainee_id': t4, 'objectives': OBJ}).status_code == 400  # at most 3 trainees
        assert c.post('/api/mentorships', json={'mentor_id': mentor, 'trainee_id': t1, 'objectives': OBJ}).status_code == 400  # already has a mentor
        listing = c.get('/api/mentorships').json()
        assert len(listing['mentorships']) == 3 and 'grants no permissions' in listing['authority_note']
        assert [h['event'] for h in c.get(f'/api/career/{t1}').json()['history']] == ['mentorship_started']


def test_objectives_are_suggested_from_employee_dna_skills():
    with TestClient(service.app) as c:
        setup(c)
        mentor, trainee = bots(c, 'Mia', 'Tom')
        with service.db() as db:
            ranks(db, {mentor: 'lead'})
            db.execute('INSERT INTO bot_careers VALUES (?,?,?,?,?,?,?,NULL,?)', (trainee, 'p', 1, json.dumps({'skills': ['SQL', 'Reporting', 'Charts', 'Extra']}), 'junior', 'Data', 'LIGHT', time.time() - 5))
            db.execute("UPDATE career_levels SET level='trainee' WHERE bot_id=?", (trainee,))
            db.execute('INSERT INTO career_levels VALUES (?,?,?)', (trainee, 'trainee', time.time()))
        sug = c.get('/api/mentorships/suggest', params={'trainee_id': trainee}).json()['objectives']
        assert [o['skill'] for o in sug] == ['SQL', 'Reporting', 'Charts'] and all(o['source'] == 'employee_dna' for o in sug)
        mid = c.post('/api/mentorships', json={'mentor_id': mentor, 'trainee_id': trainee}).json()['id']  # defaults to the DNA suggestions
        m = [x for x in c.get('/api/mentorships').json()['mentorships'] if x['id'] == mid][0]
        assert [o['skill'] for o in m['objectives']] == ['SQL', 'Reporting', 'Charts']
        with service.db() as db:
            assert db.execute('SELECT mentor_bot_id FROM bot_careers WHERE bot_id=?', (trainee,)).fetchone()['mentor_bot_id'] == mentor


def test_training_mission_needs_cost_acknowledgement_and_progress_is_counted(monkeypatch):
    FakeClient.responses = [final_reply(), final_reply()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as c:
        setup(c)
        configure_budget(c)
        mentor, trainee = bots(c, 'Mia', 'Tom')
        with service.db() as db:
            ranks(db, {mentor: 'senior'})
        mid = c.post('/api/mentorships', json={'mentor_id': mentor, 'trainee_id': trainee, 'objectives': OBJ, 'min_verified': 1, 'min_reliability': 50}).json()['id']
        est = c.get(f'/api/mentorships/{mid}/estimate').json()
        assert float(est['max_usd']) > 0 and 'Worst case' in est['basis']
        body = {'objective_index': 0, 'title': 'Proofread memo', 'instructions': 'Fix typos.', 'accept_max_usd': '0'}
        assert c.post(f'/api/mentorships/{mid}/training-missions', json=body).status_code == 400  # must accept at least the worst case
        assert c.post(f'/api/mentorships/{mid}/training-missions', json={**body, 'accept_max_usd': 'lots'}).status_code == 400
        assert c.post(f'/api/mentorships/{mid}/training-missions', json={**body, 'objective_index': 3, 'accept_max_usd': est['max_usd']}).status_code == 400
        first = c.post(f'/api/mentorships/{mid}/training-missions', json={**body, 'accept_max_usd': est['max_usd']}).json()
        assert wait_mission(c, first['id'], {'done', 'failed'})['status'] == 'done'
        p = [x for x in c.get('/api/mentorships').json()['mentorships'] if x['id'] == mid][0]
        assert p['objectives'][0]['completed'] == 1 and p['objectives'][0]['met'] is False and p['ready_to_graduate'] is False
        assert c.post(f'/api/mentorships/{mid}/graduate').status_code == 400
        second = c.post(f'/api/mentorships/{mid}/training-missions', json={**body, 'title': 'Proofread memo 2', 'accept_max_usd': est['max_usd']}).json()
        wait_mission(c, second['id'], {'done', 'failed'})
        p = [x for x in c.get('/api/mentorships').json()['mentorships'] if x['id'] == mid][0]
        assert p['objectives'][0]['met'] is True and p['ready_to_graduate'] is False  # completed is not verified
        assert [k['met'] for k in p['checks']] == [True, False, True]
        assert c.put(f"/api/missions/{first['id']}/verification", json={'verdict': 'verified'}).status_code == 200
        before_level = c.get(f'/api/career/{trainee}').json()['level']
        assert [x for x in c.get('/api/mentorships').json()['mentorships'] if x['id'] == mid][0]['ready_to_graduate'] is True
        assert c.post(f'/api/mentorships/{mid}/graduate').status_code == 200
        assert c.post(f'/api/mentorships/{mid}/graduate').status_code == 400
        d = c.get(f'/api/career/{trainee}').json()
        assert d['level'] == before_level  # graduating never promotes
        assert 'mentorship_graduated' in [h['event'] for h in d['history']]
        assert 'mentee_graduated' in [h['event'] for h in c.get(f'/api/career/{mentor}').json()['history']]
        assert c.get(f'/api/career/{mentor}').json()['metrics']['mentees_graduated'] == 1
        assert c.post(f'/api/mentorships/{mid}/training-missions', json={**body, 'accept_max_usd': est['max_usd']}).status_code == 404  # no longer active


def test_training_mission_respects_global_pause_and_unpriced_profile(monkeypatch):
    FakeClient.responses = [final_reply()]
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as c:
        setup(c)
        mentor, trainee = bots(c, 'Mia', 'Tom')
        with service.db() as db:
            ranks(db, {mentor: 'senior'})
        mid = c.post('/api/mentorships', json={'mentor_id': mentor, 'trainee_id': trainee, 'objectives': OBJ}).json()['id']
        body = {'objective_index': 0, 'title': 'T', 'instructions': 'x', 'accept_max_usd': '100'}
        assert c.post(f'/api/mentorships/{mid}/training-missions', json=body).status_code == 400  # no configured price, so no estimate and no run
        configure_budget(c)
        assert c.put('/api/control/pause', json={'paused': True}).status_code == 200
        paused = c.post(f'/api/mentorships/{mid}/training-missions', json=body)
        assert paused.status_code == 423 and 'paused' in paused.json()['detail']
        assert c.get('/api/missions').json() == []  # nothing was started
        assert c.put('/api/control/pause', json={'paused': False}).status_code == 200


def test_ending_a_mentorship_frees_the_trainee_and_changes_no_authority():
    with TestClient(service.app) as c:
        setup(c)
        mentor, trainee, other = bots(c, 'Mia', 'Tom', 'Olive')
        with service.db() as db:
            ranks(db, {mentor: 'lead', other: 'senior'})
        mid = c.post('/api/mentorships', json={'mentor_id': mentor, 'trainee_id': trainee, 'objectives': OBJ}).json()['id']
        with service.db() as db:
            before = dump(db, {'mentorships', 'career_history', 'events', 'bot_careers'})
        assert c.post(f'/api/mentorships/{mid}/end').status_code == 200
        assert c.post(f'/api/mentorships/{mid}/end').status_code == 400
        with service.db() as db:
            assert dump(db, {'mentorships', 'career_history', 'events', 'bot_careers'}) == before
        assert c.post('/api/mentorships', json={'mentor_id': other, 'trainee_id': trainee, 'objectives': OBJ}).status_code == 200  # free to be mentored again
        with service.db() as db:
            assert progression.collaborated(db, other, trainee) and progression.collaborated(db, mentor, trainee)
