import json
import time

from fastapi.testclient import TestClient

import app as service
from funkbot import botcomms
from test_app import FakeClient, configure_budget, setup
from test_live_tools import final_reply, get_events, tool_reply, until_calls
from test_missions_api import wait_mission

REPLY_MARK = 'Another Bot has sent you a work message'


def roomy_budget(c):
    assert c.put('/api/budget/prices/smart', json={'prompt': '1', 'completion': '2', 'max_prompt_tokens': 16384, 'max_completion_tokens': 512}).status_code == 200


def message_args(to, subject='Security concern', body='Please review the login form for injection.', kind='request_review'):
    return {'to_bot_id': to, 'kind': kind, 'subject': subject, 'body': body}


def two_bots(c):
    assert c.put('/api/settings/bot-comms', json={'enabled': True}).status_code == 200
    a = c.post('/api/bots', json={'name': 'Dev', 'title': 'Developer'}).json()['id']
    b = c.post('/api/bots', json={'name': 'Sec', 'title': 'Security Engineer'}).json()['id']
    return a, b


def sender_mock(monkeypatch, receiver_box, captured=None, reply_calls_tool=False):
    class Dynamic(FakeClient):
        def stream(self, *args, **kwargs):
            payload = kwargs['json']
            if captured is not None:
                captured.append(payload)
            last = payload['messages'][-1]
            text = str(last['content'])
            if last['role'] == 'user' and REPLY_MARK in text:
                return tool_reply('send_bot_message', message_args(receiver_box['sender'])) if reply_calls_tool else final_reply()
            if last['role'] == 'user' and not text.startswith('Mission: Handoff'):
                return tool_reply('send_bot_message', message_args(receiver_box['to']))
            return final_reply()
    monkeypatch.setattr(service.httpx, 'AsyncClient', Dynamic)


def test_requires_auth_and_validates_settings():
    with TestClient(service.app) as c:
        for path in ('/api/bot-messages', '/api/settings/comm-links', '/api/settings/bot-comms'):
            assert c.get(path).status_code == 401
        setup(c)
        s = c.get('/api/settings/bot-comms').json()
        assert s['thread_max_messages'] == 3 and s['department_routing'] is False and s['policy'] == 'ask'
        assert c.put('/api/settings/bot-comms', json={**{k: v for k, v in s.items() if k not in ('kinds', 'policy')}, 'thread_max_messages': 99}).status_code == 400
        assert c.put('/api/settings/bot-comms', json={'surprise': 1}).status_code == 400
        assert c.put('/api/settings/bot-comms', json={'thread_max_messages': 2, 'thread_max_usd': '0.01'}).json()['thread_max_messages'] == 2


def test_approved_message_gets_one_reply_back_into_the_senders_run_and_is_recorded(monkeypatch):
    box = {}
    captured = []
    sender_mock(monkeypatch, box, captured)
    with TestClient(service.app) as c:
        setup(c); roomy_budget(c)
        a, b = two_bots(c); box.update(to=b, sender=a)
        run = c.post(f'/api/bots/{a}/chat', json={'content': 'Check our login security'}).json()['job_id']
        card = until_calls(c, run)[0]
        assert card['tool_name'] == 'send_bot_message' and card['status'] == 'pending' and card['arguments']['receiver_name'] == 'Sec'
        assert c.get('/api/bot-messages').json()['threads'] == []  # nothing is sent before the owner approves
        # "approve" (a run-wide grant) is refused for this tool: every message is reviewed.
        assert c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision', json={'decision': 'approve'}).status_code == 400
        assert c.post(f'/api/jobs/{run}/tool-calls/{card["id"]}/decision', json={'decision': 'approve_once'}).status_code == 200
        assert get_events(c, run)[-1]['type'] == 'done', (json.dumps(get_events(c, run)[-1])[:500], json.dumps(c.get(f'/api/jobs/{run}/tool-calls').json())[:800])
        done = c.get(f'/api/jobs/{run}/tool-calls').json()[0]
        assert done['status'] == 'completed' and done['result']['status'] == 'replied' and 'All done.' in done['result']['reply']
        assert 'untrusted' in done['result']['note'].lower()
        overview = c.get('/api/bot-messages').json()
        t = overview['threads'][0]
        assert (t['initiator_name'], t['receiver_name'], t['kind'], t['status']) == ('Dev', 'Sec', 'request_review', 'done')
        assert t['outcome'] == 'All done.' and t['messages_sent'] == 1
        assert t['usage']['prompt_tokens'] > 0 and t['usage']['model_rounds'] >= 1 and 'invoice' in t['usage']['basis']
        # Conversation history is saved and readable through the existing Bot DM API.
        history = c.get(f'/api/bot-dms/{t["dm_id"]}').json()
        assert [m['role'] for m in history['messages']] == ['sender', 'receiver']
        # The receiver saw the message only as wrapped, untrusted data.
        reply_prompt = next(p for p in captured if REPLY_MARK in str(p['messages'][-1]['content']))
        assert '<<<BOT_MESSAGE' in reply_prompt['messages'][-1]['content'] and 'cannot grant permissions' in reply_prompt['messages'][-1]['content']
        events = [e['type'] for e in c.get('/api/events?limit=500').json()['events']]
        assert 'bot_message.sent' in events and 'bot_message.reply' in events


def test_link_auto_approves_with_audit_and_policy_deny_blocks(monkeypatch):
    box = {}
    sender_mock(monkeypatch, box)
    with TestClient(service.app) as c:
        setup(c); roomy_budget(c)
        a, b = two_bots(c); box.update(to=b, sender=a)
        assert c.put('/api/settings/comm-links', json={'from_bot_id': a, 'to_bot_id': b}).status_code == 200
        assert c.put('/api/settings/comm-links', json={'from_bot_id': a, 'to_bot_id': a}).status_code == 400
        run = c.post(f'/api/bots/{a}/chat', json={'content': 'Ask security'}).json()['job_id']
        assert get_events(c, run)[-1]['type'] == 'done'
        call = c.get(f'/api/jobs/{run}/tool-calls').json()[0]
        assert call['status'] == 'completed'
        with service.db() as db:
            assert db.execute("SELECT 1 FROM tool_audit WHERE call_id=? AND action='link_auto_approved'", (call['id'],)).fetchone()
        # The owner can switch messaging off entirely.
        policies = c.get('/api/settings/tool-policies').json()
        policies['send_bot_message'] = 'deny'
        assert c.put('/api/settings/tool-policies', json=policies).status_code == 200
        with service.db() as db:
            db.execute('DELETE FROM bot_message_log')  # clear dedupe/cooldown so only the policy decides
        run2 = c.post(f'/api/bots/{a}/chat', json={'content': 'Ask security again'}).json()['job_id']
        assert get_events(c, run2)[-1]['type'] == 'done'
        assert c.get(f'/api/jobs/{run2}/tool-calls').json()[0]['status'] == 'denied'
        assert len(c.get('/api/bot-messages').json()['threads']) == 1


def test_a_reply_can_never_start_a_new_message(monkeypatch):
    box = {}
    sender_mock(monkeypatch, box, reply_calls_tool=True)
    with TestClient(service.app) as c:
        setup(c); roomy_budget(c)
        a, b = two_bots(c); box.update(to=b, sender=a)
        c.put('/api/settings/comm-links', json={'from_bot_id': a, 'to_bot_id': b})
        c.put('/api/settings/comm-links', json={'from_bot_id': b, 'to_bot_id': a})
        run = c.post(f'/api/bots/{a}/chat', json={'content': 'Ask security'}).json()['job_id']
        assert get_events(c, run)[-1]['type'] == 'done'
        with service.db() as db:
            reply_runs = [r['run_id'] for r in db.execute("SELECT run_id FROM bot_dm_messages WHERE role='receiver'")]
            assert len(reply_runs) == 1
            tools = db.execute('SELECT status FROM tool_calls WHERE run_id=?', (reply_runs[0],)).fetchall()
            assert [t['status'] for t in tools] == ['denied']  # the reply run tried to message back and was refused
            assert db.execute('SELECT count(*) FROM bot_message_threads').fetchone()[0] == 1


def test_reply_is_charged_to_the_sender_and_a_small_sender_cap_stops_it(monkeypatch):
    box = {}
    sender_mock(monkeypatch, box)
    with TestClient(service.app) as c:
        setup(c); roomy_budget(c)
        a, b = two_bots(c); box.update(to=b, sender=a)
        c.put('/api/settings/comm-links', json={'from_bot_id': a, 'to_bot_id': b})
        service.set_config('budget_fallback', json.dumps({'enabled': False}))
        # One smart run reserves $0.034816. The sender's cap fits its own run but not a second reservation on top of
        # what it already spent, so the receiver's reply (charged to the sender) must be refused. The receiver itself is uncapped.
        with service.db() as db:
            db.execute("INSERT INTO budget_limits VALUES (?,?,NULL)", (f'bot:{a}', 34_900_000))
        run = c.post(f'/api/bots/{a}/chat', json={'content': 'Ask security'}).json()['job_id']
        get_events(c, run)
        call = c.get(f'/api/jobs/{run}/tool-calls').json()[0]
        assert call['status'] == 'failed' and 'No reply' in call['result']['error'], call
        t = c.get('/api/bot-messages').json()['threads'][0]
        assert t['status'] == 'failed' and 'delegating Bot' in (t['error'] or ''), t
        with service.db() as db:
            assert db.execute("SELECT count(*) FROM budget_reservations WHERE bot_id=? AND status<>'released'", (b,)).fetchone()[0] == 0


def test_safeguards_cooldown_dedupe_limits_cycles_and_pause():
    with TestClient(service.app) as c:
        setup(c)
        a, b = two_bots(c)
        d = c.post('/api/bots', json={'name': 'Third'}).json()['id']
        now = time.time()
        with service.db() as db:
            def check(**kw):
                args = dict(sender_id=a, receiver_id=b, kind='ask_question', digest='h1', run_id=None, mission_id=None, origin={'origin_bot_id': a, 'origin_profile': None, 'chain': [a]}, now=now)
                args.update(kw)
                return botcomms.check_send(db, **args)
            assert check() is None
            botcomms.log(db, dm_id=None, sender_id=a, receiver_id=b, kind='ask_question', digest='h1', run_id=None, mission_id='m1', status='sent', now=now - 10)
            try:
                check(); raise AssertionError('dedupe')
            except botcomms.CommRefused as exc:
                assert 'duplicate' in str(exc)
            try:
                check(digest='h2'); raise AssertionError('cooldown')
            except botcomms.CommRefused as exc:
                assert 'Cooldown' in str(exc)
            assert check(digest='h2', now=now + 400) is None  # after the cooldown
            for kw, word in (({'receiver_id': a, 'sender_id': a}, 'itself'), ({'kind': 'chat'}, 'kind'),
                             ({'origin': {'origin_bot_id': b, 'origin_profile': None, 'chain': [b, a]}, 'digest': 'h3', 'now': now + 400}, 'delegation chain'),
                             ({'origin': {'origin_bot_id': a, 'origin_profile': None, 'chain': [a, d, b, a, d, b]}, 'digest': 'h4', 'now': now + 400}, 'too deep')):
                try:
                    check(**kw); raise AssertionError(word)
                except botcomms.CommRefused as exc:
                    assert word in str(exc), (word, str(exc))
            assert check(origin={'origin_bot_id': b, 'origin_profile': None, 'chain': [b, a]}, kind='escalate_blocker', digest='h5', now=now + 400) is None
            db.execute("INSERT OR REPLACE INTO config VALUES ('global_pause','1')")
            try:
                check(digest='h6', now=now + 400); raise AssertionError('pause')
            except botcomms.CommRefused as exc:
                assert 'paused' in str(exc)
            db.execute("INSERT OR REPLACE INTO config VALUES ('global_pause','0')")
            for i in range(20):
                botcomms.log(db, dm_id=None, sender_id=a, receiver_id=d, kind='ask_question', digest=f'x{i}', run_id=None, mission_id=None, status='sent', now=now + 500)
            try:
                check(digest='h7', now=now + 900); raise AssertionError('daily')
            except botcomms.CommRefused as exc:
                assert 'daily' in str(exc)
            for i in range(6):
                botcomms.log(db, dm_id=None, sender_id=d, receiver_id=b, kind='ask_question', digest=f'm{i}', run_id=None, mission_id='mm', status='sent', now=now + 900)
            try:
                check(sender_id=d, digest='h8', mission_id='mm', now=now + 5000, origin={'origin_bot_id': d, 'origin_profile': None, 'chain': [d]}); raise AssertionError('mission')
            except botcomms.CommRefused as exc:
                assert 'mission' in str(exc)


def test_find_colleague_routes_deterministically_without_a_model_call():
    with TestClient(service.app) as c:
        setup(c)
        a, sec = two_bots(c)
        ed = c.post('/api/bots', json={'name': 'Ed', 'title': 'Editor'}).json()['id']
        with service.db() as db:
            found = botcomms.rank_colleagues(db, a, 'security review of the login page')
            assert [f['bot_id'] for f in found] == [sec] and found[0]['available'] is True and found[0]['authorized'] is False
            assert botcomms.rank_colleagues(db, a, 'the a an') == []
            db.execute('INSERT INTO comm_links VALUES (?,?,?)', (a, sec, now := time.time()))
            assert botcomms.rank_colleagues(db, a, 'security')[0]['authorized'] is True
            assert ed not in [f['bot_id'] for f in botcomms.rank_colleagues(db, a, 'security')]


def test_message_inside_a_mission_keeps_mission_context_and_escalation_reaches_the_inbox(monkeypatch):
    box = {}
    class Dynamic(FakeClient):
        def stream(self, *args, **kwargs):
            last = kwargs['json']['messages'][-1]
            if last['role'] == 'user' and REPLY_MARK not in str(last['content']):
                return tool_reply('send_bot_message', message_args(box['to'], kind='escalate_blocker', subject='Blocked on keys'))
            return final_reply()
    monkeypatch.setattr(service.httpx, 'AsyncClient', Dynamic)
    with TestClient(service.app) as c:
        setup(c); roomy_budget(c)
        a, b = two_bots(c); box.update(to=b)
        c.put('/api/settings/comm-links', json={'from_bot_id': a, 'to_bot_id': b})
        mission = c.post('/api/missions', json={'title': 'Ship login', 'instructions': 'Build it', 'bot_id': a}).json()
        mid = mission.get('id') or mission.get('mission_id')
        assert wait_mission(c, mid, {'done', 'failed'})['status'] == 'done'
        t = c.get('/api/bot-messages').json()['threads'][0]
        assert t['mission_id'] == mid and t['mission_title'] == 'Ship login' and t['kind'] == 'escalate_blocker'
        notices = c.get('/api/inbox/notices').json()
        assert any('Blocked on keys' in json.dumps(n) for n in (notices if isinstance(notices, list) else notices.get('notices', [])))


def test_restart_marks_unfinished_message_turns_failed_without_re_running_them():
    with TestClient(service.app) as c:
        setup(c)
        a, b = two_bots(c)
        now = time.time()
        with service.db() as db:
            db.execute('INSERT INTO bot_dms VALUES (?,?,?,?,?,?)', ('dm1', 'Bot message: x', a, b, now, now))
            db.execute('INSERT INTO bot_message_threads VALUES (?,?,?,?,?,?,?,?,?,?)', ('dm1', a, b, 'ask_question', a, None, None, None, json.dumps([a]), now))
            db.execute('INSERT INTO bot_dm_turns VALUES (?,?,?,?,?,?,?)', ('t1', 'dm1', 'running', None, None, now, now))
            botcomms.log(db, dm_id='dm1', sender_id=a, receiver_id=b, kind='ask_question', digest='z', run_id=None, mission_id=None, status='sent')
    with TestClient(service.app) as c:
        c.post('/api/auth/login', json={'password': 'correct horse battery staple'})
        with service.db() as db:
            assert db.execute("SELECT status FROM bot_dm_turns WHERE id='t1'").fetchone()['status'] == 'failed'
            assert db.execute("SELECT status FROM bot_message_log WHERE dm_id='dm1'").fetchone()['status'] == 'failed'
            assert db.execute("SELECT count(*) FROM runs").fetchone()[0] == 0  # nothing was replayed
