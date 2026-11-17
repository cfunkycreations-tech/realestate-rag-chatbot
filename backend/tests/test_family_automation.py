import json
import time

from fastapi.testclient import TestClient

import app as service
from funkbot import automation
from test_app import FakeClient, setup
from test_career_progression import bots, dump, finish
from test_council import enable, propose, roomy, run_meeting, text_reply, votes_json
from test_live_tools import final_reply, get_events, tool_reply, until_calls
from test_bot_comms import REPLY_MARK, message_args, two_bots

ALL_ON = {'auto_mission_reviews': True, 'auto_system_recommendations': True, 'auto_periodic_reviews': True, 'scheduled_meetings': True,
          'bots_may_propose': True, 'bots_may_give_feedback': True, 'bots_may_request': True}


def turn_on(c, **extra):
    r = c.put('/api/family/automation', json={**ALL_ON, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def tick(now=None):
    with service.db() as db:
        db.execute('BEGIN IMMEDIATE')
        return automation.tick(db, now)


def count(table, where='1=1'):
    with service.db() as db:
        return db.execute(f'SELECT COUNT(*) FROM {table} WHERE {where}').fetchone()[0]


def test_everything_is_off_by_default_validated_and_owner_only():
    with TestClient(service.app) as c:
        assert c.get('/api/family/automation').status_code == 401
        assert c.put('/api/family/automation', json={}).status_code == 401
        setup(c)
        d = c.get('/api/family/automation').json()
        assert not any(v for k, v in d['settings'].items() if isinstance(v, bool)), d['settings']
        assert c.put('/api/family/automation', json={'scheduled_meetings': 'yes'}).status_code == 400
        assert c.put('/api/family/automation', json={'bot_daily_limit': 99}).status_code == 400
        assert c.put('/api/family/automation', json={'meeting_cooldown_hours': 1}).status_code == 400
        # With everything off a tick changes nothing at all, even with finished work waiting.
        (a,) = bots(c, 'Ava')
        with service.db() as db:
            finish(db, a, 3, verdict='verified')
        assert tick() == {'reviews': 0, 'recommendations': 0, 'periodic': 0, 'meeting_id': None}
        assert count('reviews') == 0 and count('promotion_recommendations') == 0 and count('council_meetings') == 0


def test_mission_reviews_are_built_once_never_backfilled_and_stop_when_paused():
    with TestClient(service.app) as c:
        setup(c)
        (a,) = bots(c, 'Ava')
        with service.db() as db:
            finish(db, a, 2)
            finish(db, a, 1, at=time.time() - 40 * 86400, tag='old')
        turn_on(c, auto_system_recommendations=False, auto_periodic_reviews=False, scheduled_meetings=False)
        assert c.put('/api/control/pause', json={'paused': True}).status_code == 200
        assert tick()['reviews'] == 0
        assert c.put('/api/control/pause', json={'paused': False}).status_code == 200
        assert tick()['reviews'] == 2                       # the 40-day-old mission is not back-filled
        assert tick()['reviews'] == 0                       # idempotent: firing twice gives one result
        assert count('reviews', "kind='mission'") == 2


def test_system_recommendations_need_evidence_never_duplicate_and_never_promote():
    with TestClient(service.app) as c:
        setup(c)
        a, p, q = bots(c, 'Ava', 'Pia', 'Quin')
        with service.db() as db:
            finish(db, a, 3, verdict='verified', partner=p)
            finish(db, q, 1)
        turn_on(c, auto_mission_reviews=False, auto_periodic_reviews=False, scheduled_meetings=False)
        with service.db() as db:
            before = dump(db, {'promotion_recommendations', 'career_history', 'events', 'config'})
        assert tick()['recommendations'] == 1               # only the Bot that meets the written requirements
        assert tick()['recommendations'] == 0               # and only once while it waits
        recs = c.get('/api/career').json()
        assert c.get(f'/api/career/{a}').json()['level'] == 'trainee'   # a recommendation never changes a level
        with service.db() as db:
            assert dump(db, {'promotion_recommendations', 'career_history', 'events', 'config'}) == before
            rid = db.execute("SELECT id FROM promotion_recommendations WHERE status='pending'").fetchone()['id']
            assert db.execute("SELECT source FROM promotion_recommendations WHERE id=?", (rid,)).fetchone()['source'] == 'system'
        assert recs
        assert c.post(f'/api/career/recommendations/{rid}/decision', json={'approve': False, 'note': 'Not yet'}).status_code == 200
        assert tick()['recommendations'] == 0               # a declined recommendation is not re-suggested for a week
        assert tick(time.time() + 8 * 86400)['recommendations'] == 1


def test_scheduled_meetings_are_gated_rate_limited_and_never_chain(monkeypatch):
    FakeClient.responses = []
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as c:
        setup(c)
        ids = enable(c)
        turn_on(c, auto_mission_reviews=False, auto_system_recommendations=False, auto_periodic_reviews=False, meeting_cooldown_hours=6)
        t0 = time.time()
        assert tick(t0)['meeting_id'] is None               # no open proposals: nothing to meet about
        propose(c)
        assert tick(t0 + 1)['meeting_id'] is None           # members have no configured price: refused and logged
        assert 'price' in c.get('/api/family/automation').json()['state']['last_meeting_result']
        assert count('council_meetings') == 0
        roomy(c)
        assert tick(t0 + 2)['meeting_id'] is None           # the refusal also used up the cooldown, so it does not retry every few seconds
        mid = tick(t0 + 7 * 3600)['meeting_id']
        assert mid and count('council_meetings', "trigger='scheduled' AND status='planned'") == 1
        assert tick(t0 + 14 * 3600)['meeting_id'] is None   # one planned meeting at a time
        FakeClient.responses = [text_reply(votes_json([c.get('/api/council').json()['proposals'][0]['id']], ['approve'])) for _ in ids]
        assert c.post(f'/api/council/meetings/{mid}/start').status_code == 200
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and c.get(f'/api/council/meetings/{mid}').json()['status'] not in ('done', 'failed'):
            time.sleep(.02)
        assert c.get(f'/api/council/meetings/{mid}').json()['status'] == 'done'
        assert tick(t0 + 40 * 3600)['meeting_id'] is None   # the result is a decision, not a new open proposal: no chaining
        assert count('council_meetings') == 1


def test_scheduled_meetings_respect_pause_and_the_council_switch():
    with TestClient(service.app) as c:
        setup(c)
        enable(c)
        roomy(c)
        propose(c)
        turn_on(c, auto_mission_reviews=False, auto_system_recommendations=False, auto_periodic_reviews=False)
        assert c.put('/api/control/pause', json={'paused': True}).status_code == 200
        assert tick()['meeting_id'] is None
        assert c.put('/api/control/pause', json={'paused': False}).status_code == 200
        assert c.put('/api/council/settings', json={'enabled': False}).status_code == 200
        assert tick()['meeting_id'] is None and count('council_meetings') == 0
        assert c.put('/api/council/settings', json={'enabled': True, 'meeting_max_usd': '0.0000001'}).status_code == 200
        assert tick(time.time() + 99 * 3600)['meeting_id'] is None   # the cost cap is enforced exactly as for a manual meeting
        assert count('council_meetings') == 0


def test_bot_feedback_is_limited_honest_and_never_counts_towards_promotion():
    with TestClient(service.app) as c:
        setup(c)
        a, b = bots(c, 'Ava', 'Ben')
        with service.db() as db:
            finish(db, a, 1, partner=b)
        with service.db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                automation.bot_feedback(db, b, a, 5, 'Great')
                raise AssertionError('allowed while off')
            except automation.AutomationError as exc:
                assert 'not allowed' in str(exc)
        turn_on(c, bot_daily_limit=2)
        elig = c.get(f'/api/career/{a}').json()['eligibility']
        with service.db() as db:
            db.execute('BEGIN IMMEDIATE')
            assert automation.bot_feedback(db, b, a, 5, 'Clear and careful work.')
        with service.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for who, about in ((a, a), (b, a)):   # no self-review; one piece of feedback per review
                try:
                    automation.bot_feedback(db, who, about, 5, 'Again')
                    raise AssertionError('allowed')
                except (automation.AutomationError, service.progression.ProgressionError):
                    pass
        assert c.get(f'/api/career/{a}').json()['eligibility'] == elig   # feedback never changes eligibility
        assert count('review_feedback') == 1


def tool_mock(monkeypatch, tool, args):
    class Dynamic(FakeClient):
        def stream(self, *a, **k):
            payload = k['json']
            self.seen.append(sorted(t['function']['name'] for t in payload.get('tools', [])))
            last = payload['messages'][-1]
            if last['role'] == 'user' and 'Start' in str(last['content']):
                return tool_reply(tool, args)
            return final_reply()
    Dynamic.seen = []
    monkeypatch.setattr(service.httpx, 'AsyncClient', Dynamic)
    return Dynamic


def test_bot_proposal_tool_is_hidden_unless_allowed_needs_owner_approval_and_creates_only_a_recommendation(monkeypatch):
    mock = tool_mock(monkeypatch, 'propose_to_council', {'title': 'Share a review checklist', 'body': 'We repeat the same review mistakes.', 'kind': 'workflow'})
    with TestClient(service.app) as c:
        setup(c)
        roomy(c)
        (a,) = bots(c, 'Ava')
        c.post(f'/api/bots/{a}/chat', json={'content': 'Start please'})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not mock.seen:
            time.sleep(.02)
        assert mock.seen and 'propose_to_council' not in mock.seen[0]       # off: the Bot is never even offered the tool
        turn_on(c)
        mock.seen.clear()
        run = c.post(f'/api/bots/{a}/chat', json={'content': 'Start now'}).json()['job_id']
        card = until_calls(c, run)[0]
        assert card['tool_name'] == 'propose_to_council' and card['status'] == 'pending'
        assert count('council_proposals') == 0                              # nothing exists before the owner approves
        assert c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision', json={'decision': 'approve'}).status_code == 400  # no run-wide grant
        assert c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision', json={'decision': 'approve_once'}).status_code == 200
        assert get_events(c, run)[-1]['type'] == 'done'
        with service.db() as db:
            p = db.execute('SELECT proposer,proposer_bot_id,status FROM council_proposals').fetchone()
        assert p, json.dumps(c.get(f'/api/jobs/{run}/tool-calls').json())[:900]
        assert (p['proposer'], p['proposer_bot_id'], p['status']) == ('bot', a, 'open')


def test_vote_and_dm_reply_runs_never_get_family_tools(monkeypatch):
    FakeClient.responses = []
    seen = []

    class Spy(FakeClient):
        def stream(self, *a, **k):
            seen.append(k['json'].get('tools'))
            return super().stream(*a, **k)
    monkeypatch.setattr(service.httpx, 'AsyncClient', Spy)
    with TestClient(service.app) as c:
        setup(c)
        roomy(c)
        ids = enable(c)
        turn_on(c)
        pid = propose(c)
        FakeClient.responses = [text_reply(votes_json([pid], ['approve'])) for _ in ids]
        assert run_meeting(c, [pid])['status'] == 'done'
    family = {'propose_to_council', 'give_peer_feedback', 'suggest_training'}
    assert seen and all(not family & {x['function']['name'] for x in (t or [])} for t in seen)


def test_bot_messages_can_only_create_owner_waiting_requests_and_approval_follows_the_normal_rules(monkeypatch):
    box = {}

    class Dynamic(FakeClient):
        def stream(self, *a, **k):
            last = k['json']['messages'][-1]
            text = str(last['content'])
            if last['role'] == 'user' and REPLY_MARK in text:
                return final_reply()
            if last['role'] == 'user':
                return tool_reply('send_bot_message', message_args(box['to'], 'Mentor me ' + box['n'], 'Could you mentor me in security reviews? ' + box['n'], 'request_mentorship'))
            return final_reply()
    monkeypatch.setattr(service.httpx, 'AsyncClient', Dynamic)
    with TestClient(service.app) as c:
        setup(c)
        roomy(c)
        a, b = two_bots(c)
        box['to'] = b

        def send(n):
            box['n'] = n
            run = c.post(f'/api/bots/{a}/chat', json={'content': 'Ask Sec for a mentor'}).json()['job_id']
            card = until_calls(c, run)[0]
            assert c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision', json={'decision': 'approve_once'}).status_code == 200
            assert get_events(c, run)[-1]['type'] == 'done'
        send('first')
        assert count('family_requests') == 0                      # switch is off: the message is just a message
        turn_on(c)
        assert c.put('/api/settings/bot-comms', json={'enabled': True, 'pair_cooldown_seconds': 0}).status_code == 200
        send('second')
        reqs = c.get('/api/family/automation').json()['requests']
        assert len(reqs) == 1 and reqs[0]['kind'] == 'mentorship' and (reqs[0]['bot_name'], reqs[0]['other_name']) == ('Dev', 'Sec')
        assert count('mentorships') == 0                           # waiting for the owner
        rid = reqs[0]['id']
        assert c.post(f'/api/family/requests/{rid}/decision', json={'approve': True, 'objectives': ['Security reviews']}).status_code == 400   # Sec is not above Dev yet
        assert count('family_requests', "status='pending'") == 1
        with service.db() as db:
            db.execute("INSERT INTO career_levels VALUES (?,?,?)", (b, 'senior', time.time()))
            tools_before = c.get('/api/settings/tool-policies').json()
        assert c.post(f'/api/family/requests/{rid}/decision', json={'approve': True}).status_code == 400   # needs at least one skill objective
        assert c.post(f'/api/family/requests/{rid}/decision', json={'approve': True, 'objectives': ['Security reviews']}).status_code == 200
        assert count('mentorships', "status='active'") == 1
        assert c.get('/api/settings/tool-policies').json() == tools_before
        assert c.get(f'/api/career/{a}').json()['level'] == 'trainee'   # a mentorship promotes nobody
        assert c.post(f'/api/family/requests/{rid}/decision', json={'approve': True, 'objectives': ['x']}).status_code == 404


def test_mentor_training_suggestion_needs_the_owner_to_accept_the_worst_case_cost(monkeypatch):
    FakeClient.responses = []
    monkeypatch.setattr(service.httpx, 'AsyncClient', FakeClient)
    with TestClient(service.app) as c:
        setup(c)
        roomy(c)
        a, b, x = bots(c, 'Mentor', 'Trainee', 'Other')
        with service.db() as db:
            db.execute("INSERT INTO career_levels VALUES (?,?,?)", (a, 'senior', time.time()))
        assert c.post('/api/mentorships', json={'mentor_id': a, 'trainee_id': b, 'objectives': [{'skill': 'Proofreading', 'target_missions': 2}]}).status_code == 200
        mid = c.get('/api/mentorships').json()['mentorships'][0]['id']
        with service.db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                automation.check_bot_allowed(db, a, 'bots_may_request')
                raise AssertionError('allowed while off')
            except automation.AutomationError:
                pass
        turn_on(c)
        with service.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for who in (x, b):   # only the mentor of that mentorship may suggest training
                try:
                    automation.propose_training(db, who, mid, 0, 'Practice', 'Proofread a page.')
                    raise AssertionError('non-mentor suggested training')
                except automation.AutomationError:
                    pass
            automation.propose_training(db, a, mid, 0, 'Practice', 'Proofread a page.')
        req = c.get('/api/family/automation').json()['requests'][0]
        assert req['kind'] == 'training_mission' and count('missions') == 0       # nothing starts by itself
        assert c.post(f"/api/family/requests/{req['id']}/decision", json={'approve': True}).status_code == 400            # the cost must be accepted
        assert c.post(f"/api/family/requests/{req['id']}/decision", json={'approve': True, 'accept_max_usd': '0'}).status_code == 400
        assert count('missions') == 0 and count('family_requests', "status='pending'") == 1
        est = c.get(f'/api/mentorships/{mid}/estimate').json()['max_usd']
        assert c.post(f"/api/family/requests/{req['id']}/decision", json={'approve': True, 'accept_max_usd': est}).status_code == 200
        assert count('missions') == 1 and count('training_missions') == 1 and count('family_requests', "status='approved'") == 1
