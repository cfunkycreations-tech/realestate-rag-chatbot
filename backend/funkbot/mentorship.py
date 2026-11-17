"""Mentor and trainee relationships, skill objectives, training-mission tracking and graduation.

Deterministic bookkeeping only: no model call happens here. A mentorship grants nobody any
permission, tool, budget or access; it only records who is helping whom and what the trainee
has demonstrated. Graduating does not promote anyone (promotions are the owner's decision).
Training missions are ordinary missions started by the owner, so they use the normal budgets
and approvals; this module only links them to an objective and counts the results.
"""
import json
import time
import uuid

from funkbot import progression
from funkbot.budget import NANOS_PER_DOLLAR
from funkbot import economy

MAX_TRAINEES = 3
MAX_OBJECTIVES = 5
MAX_TARGET = 10
MISSION_ROUNDS = 25  # the mission runner's tool-round limit; used for the worst-case estimate


class MentorshipError(ValueError):
    pass


def _rank(level):
    return progression.LEVELS.index(level)


def suggest_objectives(c, trainee_id):
    """Objectives drawn from the trainee's Employee DNA skills; empty when it has no career preset."""
    row = c.execute('SELECT career_json FROM bot_careers WHERE bot_id=?', (trainee_id,)).fetchone()
    if not row:
        return []
    try:
        career = json.loads(row['career_json'])
    except ValueError:
        return []
    skills = [s for s in (career.get('skills') or career.get('competencies') or []) if isinstance(s, str) and s.strip()]
    return [{'skill': s.strip()[:120], 'target_missions': 2, 'source': 'employee_dna'} for s in skills[:3]]


def validate_objectives(raw):
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_OBJECTIVES:
        raise MentorshipError(f'Give between 1 and {MAX_OBJECTIVES} skill objectives.')
    out = []
    for item in raw:
        if not isinstance(item, dict):
            raise MentorshipError('Each objective needs a skill and a target.')
        skill = item.get('skill')
        target = item.get('target_missions', 1)
        if not isinstance(skill, str) or not skill.strip() or len(skill.strip()) > 120:
            raise MentorshipError('Each objective needs a skill name (up to 120 characters).')
        if isinstance(target, bool) or not isinstance(target, int) or not 1 <= target <= MAX_TARGET:
            raise MentorshipError(f'Target missions must be a whole number from 1 to {MAX_TARGET}.')
        out.append({'skill': skill.strip(), 'target_missions': target, 'source': 'employee_dna' if item.get('source') == 'employee_dna' else 'custom'})
    return out


def validate_criteria(min_verified, min_reliability, objectives):
    if isinstance(min_verified, bool) or not isinstance(min_verified, int) or not 0 <= min_verified <= len(objectives) * MAX_TARGET:
        raise MentorshipError('Minimum verified training missions is out of range.')
    if isinstance(min_reliability, bool) or not isinstance(min_reliability, int) or not 0 <= min_reliability <= 100:
        raise MentorshipError('Minimum reliability must be 0 to 100.')
    return {'min_verified': min_verified, 'min_reliability': min_reliability}


def _sync_pointer(c, trainee_id, mentor_id):
    # bot_careers.mentor_bot_id is descriptive; nothing reads it for authority.
    c.execute('UPDATE bot_careers SET mentor_bot_id=? WHERE bot_id=?', (mentor_id, trainee_id))


def start(c, mentor_id, trainee_id, objectives, min_verified=1, min_reliability=70, note='', now=None):
    now = time.time() if now is None else now
    if mentor_id == trainee_id:
        raise MentorshipError('A Bot cannot mentor itself.')
    for bid in (mentor_id, trainee_id):
        if not c.execute('SELECT 1 FROM bots WHERE id=?', (bid,)).fetchone():
            raise MentorshipError('Bot not found.')
    ml, tl = progression.current(c, mentor_id, now)['level'], progression.current(c, trainee_id, now)['level']
    if _rank(ml) <= _rank(tl) or _rank(ml) < _rank('junior'):
        raise MentorshipError('A mentor must be at a higher career level than the trainee.')
    if c.execute("SELECT 1 FROM mentorships WHERE trainee_id=? AND status='active'", (trainee_id,)).fetchone():
        raise MentorshipError('This Bot already has an active mentor.')
    if c.execute("SELECT COUNT(*) FROM mentorships WHERE mentor_id=? AND status='active'", (mentor_id,)).fetchone()[0] >= MAX_TRAINEES:
        raise MentorshipError(f'A mentor can have at most {MAX_TRAINEES} trainees at once.')
    objectives = validate_objectives(objectives)
    criteria = validate_criteria(min_verified, min_reliability, objectives)
    if not isinstance(note, str) or len(note) > 500:
        raise MentorshipError('Note must be at most 500 characters.')
    mid = uuid.uuid4().hex
    c.execute('INSERT INTO mentorships(id,mentor_id,trainee_id,status,objectives_json,criteria_json,note,created_at) VALUES (?,?,?,?,?,?,?,?)',
              (mid, mentor_id, trainee_id, 'active', json.dumps(objectives), json.dumps(criteria), note.strip(), now))
    _sync_pointer(c, trainee_id, mentor_id)
    c.execute('INSERT INTO career_history(bot_id,event,detail,created_at) VALUES (?,?,?,?)', (trainee_id, 'mentorship_started', 'Mentorship started. It grants no permissions.', now))
    return mid


def mission_estimate(c, bot_id):
    """Worst-case spend for one training mission: the reserved ceiling of one model call times the round limit."""
    bot = c.execute('SELECT profile FROM bots WHERE id=?', (bot_id,)).fetchone()
    if not bot:
        raise MentorshipError('Bot not found.')
    per_call = economy.profile_cost(c, bot['profile'])
    if per_call is None:
        return {'max_usd': None, 'basis': 'This Bot\'s model profile has no configured price, so no estimate is possible.'}
    return {'max_usd': str(per_call * MISSION_ROUNDS / NANOS_PER_DOLLAR),
            'basis': f'Worst case: {MISSION_ROUNDS} model rounds at the profile\'s reserved ceiling. Real cost is usually far lower and is capped by your budgets.'}


def link_training_mission(c, mentorship_id, mission_id, objective_idx, cap_usd, now=None):
    now = time.time() if now is None else now
    m = c.execute("SELECT objectives_json FROM mentorships WHERE id=? AND status='active'", (mentorship_id,)).fetchone()
    if not m:
        raise MentorshipError('Mentorship not found or no longer active.')
    if not 0 <= objective_idx < len(json.loads(m['objectives_json'])):
        raise MentorshipError('Unknown objective.')
    c.execute('INSERT INTO training_missions(mission_id,mentorship_id,objective_idx,cap_usd,created_at) VALUES (?,?,?,?,?)', (mission_id, mentorship_id, objective_idx, str(cap_usd), now))


def progress(c, mentorship_id):
    row = c.execute('SELECT * FROM mentorships WHERE id=?', (mentorship_id,)).fetchone()
    if not row:
        return None
    objectives, criteria = json.loads(row['objectives_json']), json.loads(row['criteria_json'])
    trainee = row['trainee_id']
    items, done_total, failed_total, verified_total = [], 0, 0, 0
    for idx, obj in enumerate(objectives):
        q = lambda cond: c.execute(f"""SELECT COUNT(DISTINCT t.mission_id) FROM training_missions t JOIN mission_runs r ON r.mission_id=t.mission_id
            WHERE t.mentorship_id=? AND t.objective_idx=? AND r.bot_id=? AND {cond}""", (mentorship_id, idx, trainee)).fetchone()[0]
        done = q("r.status='done'")
        failed = q("r.status='failed'")
        verified = q("r.status='done' AND EXISTS (SELECT 1 FROM mission_verifications v WHERE v.mission_id=t.mission_id AND v.verdict='verified')")
        done_total, failed_total, verified_total = done_total + done, failed_total + failed, verified_total + verified
        items.append({**obj, 'index': idx, 'completed': done, 'failed': failed, 'verified': verified, 'met': done >= obj['target_missions']})
    reliability = None if done_total + failed_total == 0 else round(done_total * 100 / (done_total + failed_total))
    checks = [{'name': 'Every objective reached its target', 'met': all(i['met'] for i in items)},
              {'name': f"Owner-verified training missions: {verified_total} of {criteria['min_verified']} needed", 'met': verified_total >= criteria['min_verified']},
              {'name': f"Reliability on training missions: {'no data' if reliability is None else str(reliability) + '%'} (needs {criteria['min_reliability']}%)",
               'met': criteria['min_reliability'] == 0 or (reliability is not None and reliability >= criteria['min_reliability'])}]
    names = {r['id']: r['name'] for r in c.execute('SELECT id,name FROM bots WHERE id IN (?,?)', (row['mentor_id'], row['trainee_id']))}
    return {'id': row['id'], 'status': row['status'], 'mentor_id': row['mentor_id'], 'mentor_name': names.get(row['mentor_id']),
            'trainee_id': trainee, 'trainee_name': names.get(trainee), 'objectives': items, 'criteria': criteria, 'checks': checks,
            'ready_to_graduate': row['status'] == 'active' and all(x['met'] for x in checks), 'reliability_percent': reliability,
            'note': row['note'], 'created_at': row['created_at'], 'ended_at': row['ended_at'],
            'authority_note': 'A mentorship grants no permissions, tools, spending or access. Graduating does not promote anyone.'}


def list_all(c):
    return [progress(c, r['id']) for r in c.execute('SELECT id FROM mentorships ORDER BY (status=\'active\') DESC, created_at DESC LIMIT 100')]


def finish(c, mentorship_id, graduate, now=None):
    now = time.time() if now is None else now
    p = progress(c, mentorship_id)
    if not p:
        raise MentorshipError('Mentorship not found.')
    if p['status'] != 'active':
        raise MentorshipError('This mentorship has already ended.')
    if graduate and not p['ready_to_graduate']:
        raise MentorshipError('The graduation criteria are not met yet.')
    c.execute('UPDATE mentorships SET status=?,ended_at=? WHERE id=?', ('graduated' if graduate else 'ended', now, mentorship_id))
    _sync_pointer(c, p['trainee_id'], None)
    verb = 'Graduated from mentorship. No permissions changed.' if graduate else 'Mentorship ended.'
    c.execute('INSERT INTO career_history(bot_id,event,detail,created_at) VALUES (?,?,?,?)', (p['trainee_id'], 'mentorship_graduated' if graduate else 'mentorship_ended', verb, now))
    if graduate:
        c.execute('INSERT INTO career_history(bot_id,event,detail,created_at) VALUES (?,?,?,?)', (p['mentor_id'], 'mentee_graduated', f"Mentee {p['trainee_name']} graduated.", now))
