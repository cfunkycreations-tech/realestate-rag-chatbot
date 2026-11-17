"""Career levels, deterministic performance reviews and promotion recommendations.

Everything here is plain SQL and arithmetic over records that already exist. No model is
called, so reviews and eligibility cost nothing and can be re-run at will.

Safety contract: a level is a descriptive label. Nothing in this module (or in the tables
it writes: career_levels, reviews, review_feedback, promotion_recommendations and the
career_history audit rows) is read by tool policies, budgets, model tiers or the Vault, so
a promotion cannot raise anyone's authority. Only the owner approves a promotion.
"""
import json
import time
import uuid
from datetime import datetime, timezone

LEVELS = ('trainee', 'junior', 'specialist', 'senior', 'lead', 'principal')
LABELS = {'trainee': 'Trainee', 'junior': 'Junior', 'specialist': 'Specialist', 'senior': 'Senior', 'lead': 'Lead', 'principal': 'Principal'}
# The Phase 2 preset scale (careers.LEVELS) is kept as-is; this maps it onto the six-step ladder.
PRESET_MAP = {'junior': 'junior', 'mid': 'specialist', 'senior': 'senior', 'lead': 'lead', 'principal': 'principal'}
DAY = 86400
MAX_TEXT = 500

# Requirements for moving UP from the key level. Counted only from work done since the Bot reached its current level.
RULES = {
    'trainee': {'done': 3, 'verified': 1, 'reliability': 60, 'days': 0, 'partners': 0, 'graduates': 0},
    'junior': {'done': 8, 'verified': 3, 'reliability': 70, 'days': 7, 'partners': 0, 'graduates': 0},
    'specialist': {'done': 20, 'verified': 8, 'reliability': 80, 'days': 14, 'partners': 2, 'graduates': 0},
    'senior': {'done': 40, 'verified': 15, 'reliability': 85, 'days': 30, 'partners': 3, 'graduates': 1},
    'lead': {'done': 80, 'verified': 30, 'reliability': 90, 'days': 60, 'partners': 4, 'graduates': 2},
}


class ProgressionError(ValueError):
    pass


def _text(value, name, limit=MAX_TEXT, required=True):
    if not isinstance(value, str):
        raise ProgressionError(f'{name} must be text.')
    value = value.strip()
    if required and not value:
        raise ProgressionError(f'{name} is required.')
    if len(value) > limit:
        raise ProgressionError(f'{name} must be at most {limit} characters.')
    return value


def next_level(level):
    i = LEVELS.index(level)
    return LEVELS[i + 1] if i + 1 < len(LEVELS) else None


def current(c, bot_id, now=None):
    """The Bot's level, where it came from, and when it reached it. Works for Bots with no career record."""
    row = c.execute('SELECT level,since FROM career_levels WHERE bot_id=?', (bot_id,)).fetchone()
    if row:
        return {'level': row['level'], 'since': row['since'], 'source': 'recorded'}
    bot = c.execute('SELECT created_at FROM bots WHERE id=?', (bot_id,)).fetchone()
    if not bot:
        raise ProgressionError('Bot not found.')
    pre = c.execute('SELECT level,installed_at FROM bot_careers WHERE bot_id=?', (bot_id,)).fetchone()
    if pre and pre['level'] in PRESET_MAP:
        return {'level': PRESET_MAP[pre['level']], 'since': pre['installed_at'], 'source': 'role preset'}
    return {'level': 'trainee', 'since': bot['created_at'], 'source': 'default'}


def collaborated(c, a, b):
    """True when two Bots have really worked together: a shared mission, a handoff, a Bot message or a mentorship."""
    if a == b or not a or not b:
        return False
    queries = (
        'SELECT 1 FROM mission_assignees x JOIN mission_assignees y ON x.mission_id=y.mission_id WHERE x.bot_id=? AND y.bot_id=? LIMIT 1',
        'SELECT 1 FROM handoffs WHERE (from_bot_id=? AND to_bot_id=?) OR (from_bot_id=? AND to_bot_id=?) LIMIT 1',
        'SELECT 1 FROM bot_message_threads WHERE (initiator_id=? AND receiver_id=?) OR (initiator_id=? AND receiver_id=?) LIMIT 1',
        'SELECT 1 FROM mentorships WHERE (mentor_id=? AND trainee_id=?) OR (mentor_id=? AND trainee_id=?) LIMIT 1',
    )
    for i, q in enumerate(queries):
        args = (a, b) if i == 0 else (a, b, b, a)
        if c.execute(q, args).fetchone():
            return True
    return False


def metrics(c, bot_id, since=0, until=None):
    """Counted facts only. Anything with no underlying data is None, never a guess."""
    until = time.time() + 1 if until is None else until
    base = "FROM mission_runs r WHERE r.bot_id=? AND r.updated_at>=? AND r.updated_at<=?"
    args = (bot_id, since, until)
    count = lambda status: c.execute(f"SELECT COUNT(DISTINCT r.mission_id) {base} AND r.status=?", args + (status,)).fetchone()[0]
    done, failed, cancelled = count('done'), count('failed'), count('cancelled')
    verdict = lambda v: c.execute(f"""SELECT COUNT(DISTINCT r.mission_id) {base} AND r.status='done'
        AND EXISTS (SELECT 1 FROM mission_verifications v WHERE v.mission_id=r.mission_id AND v.verdict=?)""", args + (v,)).fetchone()[0]
    verified, rejected = verdict('verified'), verdict('rejected')
    partners = set()
    for row in c.execute('SELECT from_bot_id a,to_bot_id b FROM handoffs WHERE (from_bot_id=? OR to_bot_id=?) AND created_at>=?', (bot_id, bot_id, since)):
        partners.update({row['a'], row['b']})
    for row in c.execute('SELECT initiator_id a,receiver_id b FROM bot_message_threads WHERE (initiator_id=? OR receiver_id=?) AND created_at>=?', (bot_id, bot_id, since)):
        partners.update({row['a'], row['b']})
    for row in c.execute('SELECT y.bot_id b FROM mission_assignees x JOIN mission_assignees y ON x.mission_id=y.mission_id AND y.bot_id<>x.bot_id WHERE x.bot_id=?', (bot_id,)):
        partners.add(row['b'])
    partners.discard(bot_id)
    partners.discard(None)
    graduates = c.execute("SELECT COUNT(*) FROM mentorships WHERE mentor_id=? AND status='graduated' AND ended_at>=?", (bot_id, since)).fetchone()[0]
    training = c.execute(f"""SELECT COUNT(DISTINCT t.mission_id) FROM training_missions t JOIN mission_runs r ON r.mission_id=t.mission_id
        WHERE r.bot_id=? AND r.status='done' AND r.updated_at>=? AND r.updated_at<=?""", args).fetchone()[0]
    return {'completed': done, 'failed': failed, 'cancelled': cancelled, 'verified': verified, 'rejected': rejected,
            'reliability_percent': None if done + failed == 0 else round(done * 100 / (done + failed)),
            'quality_percent': None if verified + rejected == 0 else round(verified * 100 / (verified + rejected)),
            'collaborators': len(partners), 'mentees_graduated': graduates, 'training_missions_completed': training,
            'note': '"Completed" is the Bot\'s own report that a mission finished. Only the owner marks work verified.'}


def eligibility(c, bot_id, now=None):
    now = time.time() if now is None else now
    cur = current(c, bot_id, now)
    target = next_level(cur['level'])
    if not target:
        return {'level': cur['level'], 'target': None, 'eligible': False, 'criteria': [], 'reason': 'Already at the highest level.'}
    rule = RULES[cur['level']]
    m = metrics(c, bot_id, cur['since'], now)
    days = int((now - cur['since']) // DAY)
    have = {'done': m['completed'], 'verified': m['verified'], 'reliability': m['reliability_percent'], 'days': days,
            'partners': m['collaborators'], 'graduates': m['mentees_graduated']}
    names = {'done': 'Completed missions at this level', 'verified': 'Owner-verified missions', 'reliability': 'Reliability (% of finished missions that completed)',
             'days': 'Days at this level', 'partners': 'Different colleagues worked with', 'graduates': 'Mentees graduated'}
    criteria = []
    for key, need in rule.items():
        if need == 0:
            continue
        got = have[key]
        criteria.append({'key': key, 'name': names[key], 'need': need, 'have': got, 'met': got is not None and got >= need})
    return {'level': cur['level'], 'target': target, 'eligible': all(x['met'] for x in criteria), 'criteria': criteria,
            'authority_note': 'A level is a label. Promotion never changes tool permissions, spending limits or access to secrets.'}


def _evidence(c, bot_id, since, limit=20):
    rows = c.execute("""SELECT r.mission_id,m.title,r.status,r.updated_at,v.verdict FROM mission_runs r JOIN missions m ON m.id=r.mission_id
        LEFT JOIN mission_verifications v ON v.mission_id=r.mission_id WHERE r.bot_id=? AND r.updated_at>=? AND r.status IN ('done','failed')
        ORDER BY r.updated_at DESC LIMIT ?""", (bot_id, since, limit)).fetchall()
    return [{'mission_id': r['mission_id'], 'title': r['title'], 'status': r['status'], 'verdict': r['verdict'], 'at': r['updated_at']} for r in rows]


def _assess(m, elig):
    strengths, growth, training = [], [], []
    if m['reliability_percent'] is not None and m['reliability_percent'] >= 85 and m['completed'] >= 3:
        strengths.append(f"Reliable: {m['completed']} completed against {m['failed']} failed.")
    if m['quality_percent'] is not None and m['quality_percent'] >= 80:
        strengths.append(f"The owner verified {m['verified']} of {m['verified'] + m['rejected']} reviewed missions.")
    if m['collaborators'] >= 3:
        strengths.append(f"Worked with {m['collaborators']} different colleagues.")
    if m['mentees_graduated']:
        strengths.append(f"Mentored {m['mentees_graduated']} colleague(s) to graduation.")
    for crit in elig['criteria']:
        if not crit['met']:
            have = 'no data yet' if crit['have'] is None else crit['have']
            growth.append(f"{crit['name']}: {have} of {crit['need']} needed.")
    if m['failed'] > m['completed'] and m['failed'] > 0:
        growth.append('More missions failed than completed.')
        training.append('Consider a mentor and smaller training missions.')
    if m['completed'] and not m['verified'] and not m['rejected']:
        growth.append('No finished work has been verified by the owner yet.')
    return strengths, growth, training


def period_key(now):
    y, w, _ = datetime.fromtimestamp(now, timezone.utc).isocalendar()
    return f'{y}-W{w:02d}'


def build_review(c, bot_id, kind='periodic', key=None, now=None):
    """Create (or return the cached) review. One row per Bot, kind and period, so re-running is free and idempotent."""
    now = time.time() if now is None else now
    if kind not in ('periodic', 'mission'):
        raise ProgressionError('Unknown review kind.')
    if kind == 'periodic':
        key = key or period_key(now)
    elif not key or not c.execute("SELECT 1 FROM mission_runs WHERE mission_id=? AND bot_id=? AND status IN ('done','failed')", (key, bot_id)).fetchone():
        raise ProgressionError('A mission review needs a finished mission this Bot worked on.')
    old = c.execute('SELECT id FROM reviews WHERE bot_id=? AND kind=? AND period_key=?', (bot_id, kind, key)).fetchone()
    if old:
        return get_review(c, old['id'])
    cur = current(c, bot_id, now)
    since = cur['since'] if kind == 'periodic' else 0
    m = metrics(c, bot_id, since, now) if kind == 'periodic' else metrics_for_mission(c, bot_id, key)
    elig = eligibility(c, bot_id, now)
    strengths, growth, training = _assess(m, elig)
    evidence = _evidence(c, bot_id, since) if kind == 'periodic' else [e for e in _evidence(c, bot_id, 0, 200) if e['mission_id'] == key]
    rid = uuid.uuid4().hex
    c.execute('INSERT INTO reviews(id,bot_id,kind,period_key,level,metrics_json,evidence_json,strengths_json,development_json,eligibility_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
              (rid, bot_id, kind, key, cur['level'], json.dumps(m), json.dumps(evidence), json.dumps(strengths), json.dumps({'areas': growth, 'recommended_training': training}), json.dumps(elig), now))
    return get_review(c, rid)


def metrics_for_mission(c, bot_id, mission_id):
    row = c.execute('SELECT status FROM mission_runs WHERE mission_id=? AND bot_id=? ORDER BY updated_at DESC LIMIT 1', (mission_id, bot_id)).fetchone()
    v = c.execute('SELECT verdict,note FROM mission_verifications WHERE mission_id=?', (mission_id,)).fetchone()
    return {'completed': int(row['status'] == 'done'), 'failed': int(row['status'] == 'failed'), 'cancelled': 0,
            'verified': int(bool(v and v['verdict'] == 'verified')), 'rejected': int(bool(v and v['verdict'] == 'rejected')),
            'reliability_percent': None, 'quality_percent': None, 'collaborators': 0, 'mentees_graduated': 0, 'training_missions_completed': 0,
            'note': 'Single-mission review. "Completed" is the Bot\'s own report; only the owner marks work verified.'}


def feedback_for(c, review_id):
    rows = c.execute('SELECT id,from_bot_id,from_name,role,rating,comment,created_at FROM review_feedback WHERE review_id=? ORDER BY created_at,id', (review_id,)).fetchall()
    items = [dict(r) for r in rows]
    mean = round(sum(r['rating'] for r in items) / len(items), 2) if items else None
    return {'items': items, 'count': len(items), 'mean': mean, 'counted_in_eligibility': False}


def get_review(c, review_id):
    r = c.execute('SELECT * FROM reviews WHERE id=?', (review_id,)).fetchone()
    if not r:
        return None
    bot = c.execute('SELECT name FROM bots WHERE id=?', (r['bot_id'],)).fetchone()
    return {'id': r['id'], 'bot_id': r['bot_id'], 'bot_name': bot['name'] if bot else None, 'kind': r['kind'], 'period': r['period_key'], 'level': r['level'],
            'metrics': json.loads(r['metrics_json']), 'evidence': json.loads(r['evidence_json']), 'strengths': json.loads(r['strengths_json']),
            'development': json.loads(r['development_json']), 'eligibility': json.loads(r['eligibility_json']),
            'feedback': feedback_for(c, r['id']), 'created_at': r['created_at']}


def add_feedback(c, review_id, from_bot_id, role, rating, comment, now=None):
    """Peer or mentor feedback. Only from a Bot that has genuinely worked with the subject, never from itself, once per review.
    It is displayed beside the review and is never used in eligibility, so it cannot be used to inflate a promotion."""
    now = time.time() if now is None else now
    r = c.execute('SELECT bot_id FROM reviews WHERE id=?', (review_id,)).fetchone()
    if not r:
        raise ProgressionError('Review not found.')
    if role not in ('mentor', 'peer'):
        raise ProgressionError('Feedback role must be mentor or peer.')
    if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
        raise ProgressionError('Rating must be a whole number from 1 to 5.')
    comment = _text(comment, 'Comment')
    subject = r['bot_id']
    if from_bot_id == subject:
        raise ProgressionError('A Bot cannot review itself.')
    giver = c.execute('SELECT name FROM bots WHERE id=?', (from_bot_id,)).fetchone()
    if not giver:
        raise ProgressionError('Bot not found.')
    if role == 'mentor':
        if not c.execute("SELECT 1 FROM mentorships WHERE mentor_id=? AND trainee_id=? AND status IN ('active','graduated')", (from_bot_id, subject)).fetchone():
            raise ProgressionError('Only the Bot\'s mentor can give mentor feedback.')
    elif not collaborated(c, from_bot_id, subject):
        raise ProgressionError('Peer feedback needs recorded work together (a shared mission, handoff, Bot message or mentorship).')
    if c.execute('SELECT 1 FROM review_feedback WHERE review_id=? AND from_bot_id=?', (review_id, from_bot_id)).fetchone():
        raise ProgressionError('This Bot already gave feedback on this review.')
    fid = uuid.uuid4().hex
    c.execute('INSERT INTO review_feedback(id,review_id,from_bot_id,from_name,role,rating,comment,created_at) VALUES (?,?,?,?,?,?,?,?)',
              (fid, review_id, from_bot_id, giver['name'], role, rating, comment, now))
    return fid


def add_owner_feedback(c, review_id, rating, comment, now=None):
    now = time.time() if now is None else now
    if not c.execute('SELECT 1 FROM reviews WHERE id=?', (review_id,)).fetchone():
        raise ProgressionError('Review not found.')
    if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
        raise ProgressionError('Rating must be a whole number from 1 to 5.')
    fid = uuid.uuid4().hex
    c.execute("INSERT INTO review_feedback(id,review_id,from_bot_id,from_name,role,rating,comment,created_at) VALUES (?,?,NULL,'Owner','owner',?,?,?)",
              (fid, review_id, rating, _text(comment, 'Comment'), now))
    return fid


def set_verification(c, mission_id, verdict, note='', now=None):
    now = time.time() if now is None else now
    if verdict not in ('verified', 'rejected'):
        raise ProgressionError('Verdict must be verified or rejected.')
    m = c.execute('SELECT status FROM missions WHERE id=?', (mission_id,)).fetchone()
    if not m:
        raise ProgressionError('Mission not found.')
    if m['status'] != 'done':
        raise ProgressionError('Only a completed mission can be verified or rejected.')
    note = _text(note, 'Note', required=False)
    c.execute('INSERT INTO mission_verifications(mission_id,verdict,note,created_at) VALUES (?,?,?,?) ON CONFLICT(mission_id) DO UPDATE SET verdict=excluded.verdict,note=excluded.note,created_at=excluded.created_at',
              (mission_id, verdict, note, now))


def _history(c, bot_id, event, detail, now):
    c.execute('INSERT INTO career_history(bot_id,event,detail,created_at) VALUES (?,?,?,?)', (bot_id, event, detail, now))


def recommend(c, bot_id, to_level, source, rationale, proposer_bot_id=None, review_id=None, now=None):
    """Record a promotion recommendation. It changes nothing by itself; the owner decides.
    System and Bot recommendations require the deterministic eligibility check to pass."""
    now = time.time() if now is None else now
    if source not in ('system', 'bot', 'owner'):
        raise ProgressionError('Unknown source.')
    cur = current(c, bot_id, now)
    if next_level(cur['level']) != to_level:
        raise ProgressionError('A promotion moves up exactly one level.')
    rationale = _text(rationale, 'Rationale')
    elig = eligibility(c, bot_id, now)
    if source in ('system', 'bot') and not elig['eligible']:
        raise ProgressionError('This Bot does not yet meet the evidence requirements for the next level.')
    if source == 'bot':
        if not proposer_bot_id or proposer_bot_id == bot_id:
            raise ProgressionError('A Bot cannot recommend itself.')
        if not collaborated(c, proposer_bot_id, bot_id):
            raise ProgressionError('Only a Bot that has worked with this colleague can recommend them.')
    if c.execute("SELECT 1 FROM promotion_recommendations WHERE bot_id=? AND status='pending'", (bot_id,)).fetchone():
        raise ProgressionError('A promotion recommendation is already waiting for the owner.')
    rid = uuid.uuid4().hex
    c.execute('INSERT INTO promotion_recommendations(id,bot_id,from_level,to_level,source,proposer_bot_id,review_id,rationale,evidence_json,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
              (rid, bot_id, cur['level'], to_level, source, proposer_bot_id if source == 'bot' else None, review_id, rationale, json.dumps(elig['criteria']), 'pending', now))
    _history(c, bot_id, 'promotion_recommended', f'{LABELS[cur["level"]]} to {LABELS[to_level]} ({source}). Waiting for the owner.', now)
    return rid


def decide(c, rec_id, approve, note='', now=None):
    """Owner decision. Approval writes ONLY career_levels and the history row; no authority is touched."""
    now = time.time() if now is None else now
    rec = c.execute('SELECT * FROM promotion_recommendations WHERE id=?', (rec_id,)).fetchone()
    if not rec:
        raise ProgressionError('Recommendation not found.')
    if rec['status'] != 'pending':
        raise ProgressionError('This recommendation was already decided.')
    note = _text(note, 'Note', required=False)
    if approve:
        cur = current(c, rec['bot_id'], now)
        if cur['level'] != rec['from_level']:
            raise ProgressionError('The Bot\'s level changed after this was recommended. Withdraw it and recommend again.')
        c.execute('INSERT INTO career_levels(bot_id,level,since) VALUES (?,?,?) ON CONFLICT(bot_id) DO UPDATE SET level=excluded.level,since=excluded.since', (rec['bot_id'], rec['to_level'], now))
        _history(c, rec['bot_id'], 'promotion', f'Promoted from {LABELS[rec["from_level"]]} to {LABELS[rec["to_level"]]} by the owner. No permissions, spending limits or secrets changed.', now)
    else:
        _history(c, rec['bot_id'], 'promotion_declined', f'Recommendation for {LABELS[rec["to_level"]]} was declined by the owner.', now)
    c.execute('UPDATE promotion_recommendations SET status=?,decision_note=?,decided_at=? WHERE id=?', ('approved' if approve else 'rejected', note, now, rec_id))


def withdraw(c, rec_id, now=None):
    now = time.time() if now is None else now
    n = c.execute("UPDATE promotion_recommendations SET status='withdrawn',decided_at=? WHERE id=? AND status='pending'", (now, rec_id)).rowcount
    if not n:
        raise ProgressionError('No pending recommendation to withdraw.')


def run_due_reviews(c, now=None):
    """Build this period's review for every Bot that has finished any mission. Free, cached and safe to repeat."""
    now = time.time() if now is None else now
    built = 0
    for row in c.execute("SELECT DISTINCT bot_id FROM mission_runs WHERE bot_id IS NOT NULL AND status IN ('done','failed')").fetchall():
        key = period_key(now)
        if not c.execute('SELECT 1 FROM reviews WHERE bot_id=? AND kind=? AND period_key=?', (row['bot_id'], 'periodic', key)).fetchone():
            build_review(c, row['bot_id'], 'periodic', key, now)
            built += 1
    return built


def summary(c, bot_id, now=None):
    """Everything the Career Center shows for one Bot."""
    now = time.time() if now is None else now
    cur = current(c, bot_id, now)
    bot = c.execute('SELECT id,name,title FROM bots WHERE id=?', (bot_id,)).fetchone()
    history = [dict(h) for h in c.execute('SELECT event,detail,created_at FROM career_history WHERE bot_id=? ORDER BY id DESC LIMIT 100', (bot_id,))]
    recs = [dict(r) for r in c.execute('SELECT id,from_level,to_level,source,proposer_bot_id,rationale,status,decision_note,created_at,decided_at FROM promotion_recommendations WHERE bot_id=? ORDER BY created_at DESC LIMIT 20', (bot_id,))]
    reviews = [dict(r) for r in c.execute('SELECT id,kind,period_key,level,created_at FROM reviews WHERE bot_id=? ORDER BY created_at DESC LIMIT 20', (bot_id,))]
    return {'bot_id': bot_id, 'name': bot['name'] if bot else None, 'title': bot['title'] if bot else None,
            'level': cur['level'], 'label': LABELS[cur['level']], 'since': cur['since'], 'source': cur['source'],
            'next': next_level(cur['level']), 'eligibility': eligibility(c, bot_id, now),
            'metrics': metrics(c, bot_id, cur['since'], now), 'history': history, 'recommendations': recs, 'reviews': reviews}
