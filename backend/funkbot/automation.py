"""Optional, owner-enabled Family automation. EVERYTHING here is off by default.

Free triggers (reviews, recommendations) make no model call. A scheduled council meeting is the only
paid trigger: it is planned through the same gate as a manual one (cap, worst-case estimate, pause),
is rate-limited by a persisted cooldown, and a meeting can never cause another meeting.
Nothing here can raise a permission, spending limit or secret access: the only writes are reviews,
recommendations/requests that wait for the owner, and planned meetings.
"""
import json
import time
import uuid

from funkbot import council, progression, mentorship

DEFAULTS = {'auto_mission_reviews': False, 'auto_system_recommendations': False, 'auto_periodic_reviews': False,
            'scheduled_meetings': False, 'meeting_cooldown_hours': 24, 'min_open_proposals': 1,
            'bots_may_propose': False, 'bots_may_give_feedback': False, 'bots_may_request': False, 'bot_daily_limit': 3}
BOOLS = ('auto_mission_reviews', 'auto_system_recommendations', 'auto_periodic_reviews', 'scheduled_meetings', 'bots_may_propose', 'bots_may_give_feedback', 'bots_may_request')
INTS = (('meeting_cooldown_hours', 6, 168), ('min_open_proposals', 1, 20), ('bot_daily_limit', 1, 10))
LOOKBACK = 14 * 86400      # automation never back-fills older history
RETRY = 7 * 86400          # an owner-rejected promotion is not re-suggested for a week
BATCH = 20


class AutomationError(ValueError):
    pass


def settings(c):
    row = c.execute("SELECT value FROM config WHERE key='family_automation'").fetchone()
    try:
        saved = json.loads(row['value']) if row else {}
    except ValueError:
        saved = {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def validate_settings(body):
    out = {}
    for k in BOOLS:
        v = body.get(k, DEFAULTS[k])
        if not isinstance(v, bool):
            raise AutomationError(f'{k.replace("_", " ").capitalize()} must be true or false.')
        out[k] = v
    for k, lo, hi in INTS:
        v = body.get(k, DEFAULTS[k])
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            raise AutomationError(f'{k.replace("_", " ").capitalize()} must be a whole number from {lo} to {hi}.')
        out[k] = v
    return out


def save_settings(c, normalized):
    c.execute("INSERT OR REPLACE INTO config VALUES ('family_automation',?)", (json.dumps(normalized),))


def state(c):
    row = c.execute("SELECT value FROM config WHERE key='family_automation_state'").fetchone()
    try:
        return json.loads(row['value']) if row else {}
    except ValueError:
        return {}


def _save_state(c, s):
    c.execute("INSERT OR REPLACE INTO config VALUES ('family_automation_state',?)", (json.dumps(s),))


def paused(c):
    row = c.execute("SELECT value FROM config WHERE key='global_pause'").fetchone()
    return bool(row and row['value'] == '1')


def tick(c, now=None):
    """One bounded pass. Returns counts and a planned meeting id. Idempotent and restart-safe:
    unique indexes stop duplicate reviews/recommendations, and the meeting cooldown is stored in the database."""
    now = time.time() if now is None else now
    cfg, out = settings(c), {'reviews': 0, 'recommendations': 0, 'periodic': 0, 'meeting_id': None}
    if paused(c) or not any(cfg[k] for k in ('auto_mission_reviews', 'auto_system_recommendations', 'auto_periodic_reviews', 'scheduled_meetings')):
        return out
    st = state(c)
    since = now - LOOKBACK
    if cfg['auto_mission_reviews']:
        rows = c.execute("""SELECT DISTINCT r.mission_id,r.bot_id FROM mission_runs r WHERE r.bot_id IS NOT NULL AND r.status IN ('done','failed') AND r.updated_at>=?
            AND NOT EXISTS (SELECT 1 FROM reviews v WHERE v.bot_id=r.bot_id AND v.kind='mission' AND v.period_key=r.mission_id) LIMIT ?""", (since, BATCH)).fetchall()
        for row in rows:
            try:
                progression.build_review(c, row['bot_id'], 'mission', row['mission_id'], now)
                out['reviews'] += 1
            except progression.ProgressionError:
                pass
    if cfg['auto_system_recommendations']:
        for row in c.execute("SELECT DISTINCT bot_id FROM mission_runs WHERE bot_id IS NOT NULL AND status='done' AND updated_at>=? LIMIT ?", (since, BATCH)).fetchall():
            bid = row['bot_id']
            nxt = progression.next_level(progression.current(c, bid, now)['level'])
            if not nxt or c.execute("SELECT 1 FROM promotion_recommendations WHERE bot_id=? AND (status='pending' OR (status='rejected' AND decided_at>=?))", (bid, now - RETRY)).fetchone():
                continue
            if not progression.eligibility(c, bid, now)['eligible']:
                continue
            try:
                progression.recommend(c, bid, nxt, 'system', 'Meets the written evidence requirements for the next level. The owner decides; a level changes no permissions.', now=now)
                out['recommendations'] += 1
            except progression.ProgressionError:
                pass
    if cfg['auto_periodic_reviews'] and now - st.get('periodic_at', 0) >= 3600:
        out['periodic'] = progression.run_due_reviews(c, now)
        st['periodic_at'] = now
    if cfg['scheduled_meetings'] and council.settings(c)['enabled'] and now - st.get('meeting_attempt_at', 0) >= cfg['meeting_cooldown_hours'] * 3600:
        limit = council.settings(c)['max_proposals_per_meeting']
        open_ids = [r['id'] for r in c.execute("SELECT id FROM council_proposals WHERE status='open' ORDER BY created_at LIMIT ?", (limit,)).fetchall()]
        total_open = c.execute("SELECT COUNT(*) FROM council_proposals WHERE status='open'").fetchone()[0]
        if open_ids and total_open >= cfg['min_open_proposals'] and not c.execute("SELECT 1 FROM council_meetings WHERE status IN ('planned','running')").fetchone():
            st['meeting_attempt_at'] = now   # recorded BEFORE planning: a refusal also waits out the cooldown
            try:
                out['meeting_id'] = council.plan_meeting(c, open_ids, 'scheduled', now)
                st['last_meeting_result'] = 'Planned a scheduled meeting.'
            except council.CouncilError as exc:
                st['last_meeting_result'] = 'Skipped: ' + str(exc)
    st['last_tick_at'] = now
    if out['reviews'] or out['recommendations'] or out['periodic'] or out['meeting_id']:
        st['last_activity'] = {'at': now, 'reviews': out['reviews'], 'recommendations': out['recommendations'], 'periodic': out['periodic'], 'meeting': bool(out['meeting_id'])}
    _save_state(c, st)
    return out


# ---- Bot-originated, owner-approved requests ----
def create_request(c, kind, bot_id, other_bot_id, payload, now=None):
    now = time.time() if now is None else now
    if kind not in ('mentorship', 'training_mission'):
        raise AutomationError('Unknown request type.')
    if c.execute("SELECT COUNT(*) FROM family_requests WHERE status='pending'").fetchone()[0] >= 50:
        raise AutomationError('Too many requests are waiting for the owner.')
    if c.execute("SELECT 1 FROM family_requests WHERE kind=? AND bot_id=? AND COALESCE(other_bot_id,'')=? AND status='pending'", (kind, bot_id, other_bot_id or '')).fetchone():
        raise AutomationError('This request is already waiting for the owner.')
    rid = uuid.uuid4().hex
    c.execute('INSERT INTO family_requests(id,kind,bot_id,other_bot_id,payload_json,status,created_at) VALUES (?,?,?,?,?,?,?)', (rid, kind, bot_id, other_bot_id, json.dumps(payload), 'pending', now))
    return rid


def request_mentorship(c, trainee_id, mentor_id, why, now=None):
    """A Bot asks to be mentored by a colleague. Validity is re-checked, with the real rules, when the owner approves."""
    why = (why or '').strip()[:500]
    if trainee_id == mentor_id:
        raise AutomationError('A Bot cannot mentor itself.')
    if not c.execute('SELECT 1 FROM bots WHERE id=?', (mentor_id,)).fetchone():
        raise AutomationError('Bot not found.')
    return create_request(c, 'mentorship', trainee_id, mentor_id, {'why': why}, now)


def propose_training(c, mentor_id, mentorship_id, objective_index, title, instructions, now=None):
    """A mentor suggests one training mission. The owner supplies the accepted cost; nothing starts by itself."""
    m = c.execute("SELECT trainee_id,objectives_json FROM mentorships WHERE id=? AND mentor_id=? AND status='active'", (mentorship_id, mentor_id)).fetchone()
    if not m:
        raise AutomationError('Only the mentor of an active mentorship can suggest training.')
    if not isinstance(objective_index, int) or isinstance(objective_index, bool) or not 0 <= objective_index < len(json.loads(m['objectives_json'])):
        raise AutomationError('Unknown objective.')
    title, instructions = (title or '').strip(), (instructions or '').strip()
    if not title or len(title) > 160 or not instructions or len(instructions) > 6000:
        raise AutomationError('A title (up to 160 characters) and instructions (up to 6000) are required.')
    return create_request(c, 'training_mission', mentor_id, m['trainee_id'], {'mentorship_id': mentorship_id, 'objective_index': objective_index, 'title': title, 'instructions': instructions}, now)


def list_requests(c, status='pending'):
    out = []
    for r in c.execute('SELECT * FROM family_requests WHERE status=? ORDER BY created_at DESC LIMIT 100', (status,)).fetchall():
        names = {b['id']: b['name'] for b in c.execute('SELECT id,name FROM bots WHERE id IN (?,?)', (r['bot_id'], r['other_bot_id'] or '')).fetchall()}
        out.append({'id': r['id'], 'kind': r['kind'], 'bot_id': r['bot_id'], 'bot_name': names.get(r['bot_id']), 'other_bot_id': r['other_bot_id'], 'other_name': names.get(r['other_bot_id']),
                    'payload': json.loads(r['payload_json']), 'status': r['status'], 'created_at': r['created_at'],
                    'note': 'Waiting for you. Approving never changes permissions, budgets or secrets.'})
    return out


def decide_request(c, request_id, approve, note='', now=None, objectives=None):
    """Owner decision. Approving a mentorship request starts it through the normal rules (higher-level mentor, caps).
    Training requests are approved through the training-mission endpoint, which makes the owner accept the worst-case cost."""
    now = time.time() if now is None else now
    r = c.execute("SELECT * FROM family_requests WHERE id=? AND status='pending'", (request_id,)).fetchone()
    if not r:
        raise AutomationError('This request is not waiting for a decision.')
    result = None
    if approve and r['kind'] == 'mentorship':
        try:
            objectives = [{'skill': str(s), 'target_missions': 2} for s in objectives] if objectives else mentorship.suggest_objectives(c, r['bot_id'])
            result = mentorship.start(c, r['other_bot_id'], r['bot_id'], objectives, note=json.loads(r['payload_json']).get('why', ''), now=now)
        except mentorship.MentorshipError as exc:
            raise AutomationError(str(exc))
    c.execute('UPDATE family_requests SET status=?,decision_note=?,decided_at=? WHERE id=?', ('approved' if approve else 'rejected', (note or '')[:500], now, request_id))
    return result


def bot_actions_today(c, bot_id, now=None):
    """What one Bot authored in the last 24 hours, for the per-Bot daily limit."""
    now = time.time() if now is None else now
    since = now - 86400
    return (c.execute('SELECT COUNT(*) FROM council_proposals WHERE proposer_bot_id=? AND created_at>=?', (bot_id, since)).fetchone()[0]
            + c.execute('SELECT COUNT(*) FROM review_feedback WHERE from_bot_id=? AND created_at>=?', (bot_id, since)).fetchone()[0]
            + c.execute('SELECT COUNT(*) FROM family_requests WHERE bot_id=? AND created_at>=?', (bot_id, since)).fetchone()[0])


def check_bot_allowed(c, bot_id, flag, now=None):
    cfg = settings(c)
    if not cfg[flag]:
        raise AutomationError('The owner has not allowed Bots to do this.')
    if paused(c):
        raise AutomationError('Global Pause is on.')
    if bot_actions_today(c, bot_id, now) >= cfg['bot_daily_limit']:
        raise AutomationError('This Bot reached its daily limit for Family actions.')


def bot_propose(c, bot_id, title, body, kind, now=None):
    check_bot_allowed(c, bot_id, 'bots_may_propose', now)
    return council.propose(c, title, body, kind, 'bot', bot_id, now)


def bot_feedback(c, bot_id, about_bot_id, rating, comment, now=None):
    check_bot_allowed(c, bot_id, 'bots_may_give_feedback', now)
    if about_bot_id == bot_id:
        raise AutomationError('A Bot cannot review itself.')
    if not c.execute('SELECT 1 FROM bots WHERE id=?', (about_bot_id,)).fetchone():
        raise AutomationError('Bot not found.')
    row = c.execute('SELECT id FROM reviews WHERE bot_id=? ORDER BY created_at DESC LIMIT 1', (about_bot_id,)).fetchone()
    review_id = row['id'] if row else progression.build_review(c, about_bot_id, 'periodic', None, now)['id']
    role = 'mentor' if c.execute("SELECT 1 FROM mentorships WHERE mentor_id=? AND trainee_id=? AND status IN ('active','graduated')", (bot_id, about_bot_id)).fetchone() else 'peer'
    return progression.add_feedback(c, review_id, bot_id, role, rating, comment, now)


def overview(c):
    return {'settings': settings(c), 'state': state(c), 'requests': list_requests(c),
            'note': 'Everything here is off until you turn it on. Automation makes no model calls except a scheduled council meeting, which uses the same cost cap and Global Pause as a manual one. It can never change a permission, budget or secret.'}
