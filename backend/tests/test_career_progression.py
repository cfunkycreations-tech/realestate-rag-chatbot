import json
import time

import pytest
from fastapi.testclient import TestClient

import app as service
from funkbot import economy, progression
from test_app import setup

DAY = 86400


def bots(c, *names):
    return [c.post('/api/bots', json={'name': n, 'title': 'Helper'}).json()['id'] for n in names]


def finish(db, bot_id, n=1, status='done', verdict=None, at=None, partner=None, tag=''):
    """Seed finished missions the way the mission runner leaves them. Returns the mission ids."""
    at = time.time() if at is None else at
    ids = []
    for i in range(n):
        mid = f'm{tag}{bot_id[:6]}{status}{len(ids)}{int(at)}{i}'
        db.execute('INSERT INTO missions VALUES (?,?,?,?,?,?,?,?,?)', (mid, 'Seeded ' + mid[-6:], 'x', None, status, None, None, at, at))
        db.execute('INSERT INTO mission_runs VALUES (?,?,?,?,?,?,?,?,?,?)', (mid + 'r', mid, bot_id, None, 'member', status, None, None, at, at))
        db.execute('INSERT INTO mission_assignees VALUES (?,?,?)', (mid, 0, bot_id))
        if partner:
            db.execute('INSERT INTO mission_assignees VALUES (?,?,?)', (mid, 1, partner))
        if verdict:
            db.execute('INSERT INTO mission_verifications VALUES (?,?,?,?)', (mid, verdict, '', at))
        ids.append(mid)
    return ids


def dump(db, skip):
    out = {}
    for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
        name = row['name']
        if name in skip:
            continue
        out[name] = [tuple(r.values()) for r in db.execute(f'SELECT * FROM "{name}"').fetchall()]
    return out


def test_requires_auth_and_new_bot_starts_as_trainee_with_nothing_invented():
    with TestClient(service.app) as c:
        assert c.get('/api/career').status_code == 401
        setup(c)
        (a,) = bots(c, 'Ava')
        d = c.get(f'/api/career/{a}').json()
        assert (d['level'], d['source'], d['next']) == ('trainee', 'default', 'junior')
        assert d['metrics']['completed'] == 0 and d['metrics']['reliability_percent'] is None and d['metrics']['quality_percent'] is None
        assert d['eligibility']['eligible'] is False and d['history'] == [] and d['reviews'] == []
        assert c.get('/api/career/nobody').status_code == 404


def test_preset_level_maps_onto_the_six_step_ladder():
    with TestClient(service.app) as c:
        setup(c)
        (a,) = bots(c, 'Ava')
        with service.db() as db:
            db.execute("INSERT INTO bot_careers VALUES (?,?,?,?,?,?,?,NULL,?)", (a, 'p', 1, '{}', 'mid', 'Eng', 'STANDARD', time.time() - 5))
            assert progression.current(db, a)['level'] == 'specialist'
            assert progression.current(db, a)['source'] == 'role preset'


def test_done_is_not_verified_and_only_the_owner_can_verify_a_completed_mission():
    with TestClient(service.app) as c:
        setup(c)
        (a,) = bots(c, 'Ava')
        with service.db() as db:
            ok = finish(db, a, 2)
            bad = finish(db, a, 1, status='failed')
        m = c.get(f'/api/career/{a}').json()['metrics']
        assert (m['completed'], m['failed'], m['verified'], m['reliability_percent']) == (2, 1, 0, 67)
        assert c.put(f'/api/missions/{bad[0]}/verification', json={'verdict': 'verified'}).status_code == 400
        assert c.put(f'/api/missions/{ok[0]}/verification', json={'verdict': 'verified', 'note': 'checked'}).status_code == 200
        assert c.put(f'/api/missions/{ok[1]}/verification', json={'verdict': 'rejected'}).status_code == 200
        m = c.get(f'/api/career/{a}').json()['metrics']
        assert (m['verified'], m['rejected'], m['quality_percent']) == (1, 1, 50)
        assert [x['id'] for x in c.get('/api/career/unverified').json()] == []
        assert c.delete(f'/api/missions/{ok[0]}/verification').status_code == 200
        assert [x['id'] for x in c.get('/api/career/unverified').json()] == [ok[0]]


def eligible_trainee(c):
    (a, p) = bots(c, 'Ava', 'Pia')
    with service.db() as db:
        finish(db, a, 3, verdict='verified', partner=p)
    return a, p


def test_system_recommendation_needs_evidence_and_promotion_is_one_step_owner_only():
    with TestClient(service.app) as c:
        setup(c)
        (a,) = bots(c, 'Ava')
        r = c.post(f'/api/career/{a}/recommendations', json={'to_level': 'junior'})
        assert r.status_code == 400 and 'evidence' in r.json()['detail']
        with service.db() as db:
            finish(db, a, 3, verdict='verified')
        assert c.post(f'/api/career/{a}/recommendations', json={'to_level': 'senior'}).status_code == 400  # no skipping levels
        rid = c.post(f'/api/career/{a}/recommendations', json={'to_level': 'junior'}).json()['id']
        assert c.get(f'/api/career/{a}').json()['level'] == 'trainee'  # a recommendation changes nothing by itself
        assert c.post(f'/api/career/{a}/recommendations', json={'to_level': 'junior'}).status_code == 400  # one pending at a time
        assert c.post(f'/api/career/recommendations/{rid}/decision', json={'approve': True, 'note': 'Good work'}).status_code == 200
        d = c.get(f'/api/career/{a}').json()
        assert (d['level'], d['source']) == ('junior', 'recorded')
        assert [h['event'] for h in d['history']] == ['promotion', 'promotion_recommended']
        assert 'No permissions' in d['history'][0]['detail']
        assert c.post(f'/api/career/recommendations/{rid}/decision', json={'approve': True}).status_code == 400  # already decided
        # Work done before the promotion does not count towards the next level.
        assert d['metrics']['completed'] == 0 and d['eligibility']['eligible'] is False


def test_owner_can_decline_and_a_stale_recommendation_cannot_be_approved():
    with TestClient(service.app) as c:
        setup(c)
        (a,) = bots(c, 'Ava')
        with service.db() as db:
            finish(db, a, 3, verdict='verified')
        rid = c.post(f'/api/career/{a}/recommendations', json={'to_level': 'junior'}).json()['id']
        assert c.post(f'/api/career/recommendations/{rid}/decision', json={'approve': False, 'note': 'Not yet'}).status_code == 200
        assert c.get(f'/api/career/{a}').json()['level'] == 'trainee'
        # Owner-sourced recommendation, then the level changes underneath it.
        r1 = c.post(f'/api/career/{a}/recommendations', json={'to_level': 'junior', 'source': 'owner', 'rationale': 'Fast learner'}).json()['id']
        with service.db() as db:
            db.execute("INSERT INTO career_levels VALUES (?,?,?)", (a, 'junior', time.time()))
        assert c.post(f'/api/career/recommendations/{r1}/decision', json={'approve': True}).status_code == 400
        assert c.delete(f'/api/career/recommendations/{r1}').status_code == 200


def test_promotion_changes_no_authority_anywhere():
    """The core safety promise: every table except the career records is byte-identical after a promotion."""
    with TestClient(service.app) as c:
        setup(c)
        a, p = eligible_trainee(c)
        pol = c.get('/api/settings/tool-policies').json()
        assert c.put('/api/settings/tool-policies', json={**pol, 'web_fetch': 'ask'}).status_code == 200
        skip = {'career_levels', 'career_history', 'promotion_recommendations', 'events'}
        with service.db() as db:
            db.execute("INSERT INTO bot_careers VALUES (?,?,?,?,?,?,?,NULL,?)", (a, 'p', 1, '{}', 'junior', 'Eng', 'LIGHT', time.time() - 400 * DAY))
            finish(db, a, 5, tag='y')
            before = dump(db, skip)
            profile_before = economy.choose_profile(db, dict(db.execute('SELECT * FROM bots WHERE id=?', (a,)).fetchone()), None, False)
        policies_before = c.get('/api/settings/tool-policies').json()
        rid = c.post(f'/api/career/{a}/recommendations', json={'to_level': 'specialist'}).json()['id']
        assert rid and c.post(f'/api/career/recommendations/{rid}/decision', json={'approve': True}).status_code == 200
        assert c.get(f'/api/career/{a}').json()['level'] == 'specialist'
        with service.db() as db:
            assert dump(db, skip) == before
            assert economy.choose_profile(db, dict(db.execute('SELECT * FROM bots WHERE id=?', (a,)).fetchone()), None, False) == profile_before
            assert db.execute('SELECT model_tier FROM bot_careers WHERE bot_id=?', (a,)).fetchone()['model_tier'] == 'LIGHT'
        assert c.get('/api/settings/tool-policies').json() == policies_before


def test_a_bot_can_only_recommend_a_real_collaborator_and_never_itself():
    with TestClient(service.app) as c:
        setup(c)
        a, p = eligible_trainee(c)
        (stranger,) = bots(c, 'Sam')
        with service.db() as db:
            for who, msg in ((a, 'cannot recommend itself'), (stranger, 'no shared work')):
                with pytest.raises(progression.ProgressionError):
                    progression.recommend(db, a, 'junior', 'bot', 'I think they are great', proposer_bot_id=who)
            rid = progression.recommend(db, a, 'junior', 'bot', 'We shipped three missions together.', proposer_bot_id=p)
            row = db.execute('SELECT status,source,proposer_bot_id FROM promotion_recommendations WHERE id=?', (rid,)).fetchone()
            assert (row['status'], row['source'], row['proposer_bot_id']) == ('pending', 'bot', p)
            assert db.execute('SELECT level FROM bot_careers WHERE bot_id=?', (a,)).fetchone() is None  # nothing promoted
            assert progression.current(db, a)['level'] == 'trainee'


def test_reviews_are_deterministic_cached_and_evidence_linked():
    with TestClient(service.app) as c:
        setup(c)
        a, p = eligible_trainee(c)
        r1 = c.post(f'/api/career/{a}/reviews', json={}).json()
        assert r1['kind'] == 'periodic' and r1['metrics']['completed'] == 3 and r1['metrics']['verified'] == 3
        assert len(r1['evidence']) == 3 and all(e['verdict'] == 'verified' for e in r1['evidence'])
        assert r1['eligibility']['eligible'] is True and r1['feedback']['counted_in_eligibility'] is False
        with service.db() as db:
            finish(db, a, 2, status='failed', tag='x')
        r2 = c.post(f'/api/career/{a}/reviews', json={}).json()
        assert r2['id'] == r1['id'] and r2['metrics']['failed'] == 0  # cached: same period, same row
        built = c.post('/api/career/reviews/run').json()['built']
        assert built == 0  # Ava is already reviewed this period and Pia has finished nothing
        mission_id = r1['evidence'][0]['mission_id']
        mr = c.post(f'/api/career/{a}/reviews', json={'kind': 'mission', 'key': mission_id}).json()
        assert mr['kind'] == 'mission' and mr['metrics']['verified'] == 1 and [e['mission_id'] for e in mr['evidence']] == [mission_id]
        assert c.post(f'/api/career/{a}/reviews', json={'kind': 'mission', 'key': 'nope'}).status_code == 400
        assert c.get(f"/api/career/reviews/{r1['id']}").json()['id'] == r1['id']


def test_feedback_is_restricted_visible_and_never_inflates_eligibility():
    with TestClient(service.app) as c:
        setup(c)
        a, p = eligible_trainee(c)
        (stranger,) = bots(c, 'Sam')
        review = c.post(f'/api/career/{a}/reviews', json={}).json()
        rid = review['id']
        before = c.get(f'/api/career/{a}').json()['eligibility']
        with service.db() as db:
            for who, role in ((a, 'peer'), (stranger, 'peer'), (p, 'mentor')):
                with pytest.raises(progression.ProgressionError):
                    progression.add_feedback(db, rid, who, role, 5, 'Great')
            for bad in (0, 6, True, '5'):
                with pytest.raises(progression.ProgressionError):
                    progression.add_feedback(db, rid, p, 'peer', bad, 'Great')
            progression.add_feedback(db, rid, p, 'peer', 5, 'Reliable teammate.')
            with pytest.raises(progression.ProgressionError):
                progression.add_feedback(db, rid, p, 'peer', 5, 'Twice')
        assert c.post(f'/api/career/reviews/{rid}/feedback', json={'rating': 4, 'comment': 'Owner view'}).status_code == 200
        fb = c.get(f'/api/career/reviews/{rid}').json()['feedback']
        assert fb['count'] == 2 and fb['mean'] == 4.5 and fb['counted_in_eligibility'] is False
        assert {i['role'] for i in fb['items']} == {'peer', 'owner'}
        assert c.get(f'/api/career/{a}').json()['eligibility'] == before  # feedback cannot move the arithmetic


def test_only_a_real_mentor_may_give_mentor_feedback():
    with TestClient(service.app) as c:
        setup(c)
        a, p = eligible_trainee(c)
        review = c.post(f'/api/career/{a}/reviews', json={}).json()
        with service.db() as db:
            db.execute("INSERT INTO mentorships VALUES ('mm',?,?,'active','[]','{}','',?,NULL)", (p, a, time.time()))
            progression.add_feedback(db, review['id'], p, 'mentor', 4, 'Improving steadily.')
            assert db.execute('SELECT role FROM review_feedback').fetchone()['role'] == 'mentor'


def test_overview_lists_every_bot_with_real_numbers_and_the_authority_note():
    with TestClient(service.app) as c:
        setup(c)
        a, p = eligible_trainee(c)
        d = c.get('/api/career').json()
        by = {b['bot_id']: b for b in d['bots']}
        assert by[a]['eligible'] is True and by[a]['completed'] == 3 and by[p]['completed'] == 0 and by[p]['reliability_percent'] is None
        assert [x['label'] for x in d['levels']] == ['Trainee', 'Junior', 'Specialist', 'Senior', 'Lead', 'Principal']
        assert 'never changes tool permissions' in d['authority_note']
