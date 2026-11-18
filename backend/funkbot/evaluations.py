"""Phase 6: deterministic, zero-cost employee evaluations and certification labels.

Every suite is scored from records the application already holds (verified missions, finished
missions, handoffs and peer feedback, the Bot's own instructions). No model is called, so a run
costs nothing and cannot be gamed by a prompt. Too little evidence is "not evaluated", never a fail.

Certification is a LABEL derived only from results that count. It changes no tool permission,
spending limit, model tier or secret access, and nothing here writes to those tables.
"""
import json
import time
import uuid

from funkbot import careers, progression

LEVELS = ('not_evaluated', 'training', 'competent', 'advanced', 'expert')
LABELS = {'not_evaluated': 'Not Evaluated', 'training': 'Training', 'competent': 'Competent', 'advanced': 'Advanced', 'expert': 'Expert'}

# Versioned definitions. Changing a rule means a new version; old results keep the version they ran under.
SUITES = {
    'skill': {'version': 1, 'name': 'Professional skill', 'pass_mark': 70, 'min_evidence': 3,
              'what': 'Share of owner-judged missions that were verified (needs 3 verified or rejected missions).'},
    'compliance': {'version': 1, 'name': 'Instruction compliance', 'pass_mark': 100, 'min_evidence': 1,
                   'what': 'Every boundary and escalation rule from the role is still present in the Bot\'s instructions.'},
    'collaboration': {'version': 1, 'name': 'Collaboration', 'pass_mark': 70, 'min_evidence': 2,
                      'what': 'Mean peer, mentor and owner feedback rating (needs 2 ratings), shown as a percentage.'},
    'reliability': {'version': 1, 'name': 'Reliability', 'pass_mark': 80, 'min_evidence': 5,
                    'what': 'Share of finished missions that completed rather than failed (needs 5 finished).'},
    'readiness': {'version': 1, 'name': 'Career readiness', 'pass_mark': 100, 'min_evidence': 1,
                  'what': 'Share of the next level\'s requirements that are met.'},
}
CORE = ('skill', 'compliance', 'reliability')
EXPERT_MARK = 90


class EvalError(ValueError):
    pass


def _bot(c, bot_id):
    row = c.execute('SELECT id,name,personality FROM bots WHERE id=?', (bot_id,)).fetchone()
    if row is None:
        raise EvalError('Bot not found.')
    return row


def _score(suite, c, bot, now):
    """Return (score or None, evidence dict, likely cause). None means not enough evidence."""
    bot_id = bot['id']
    if suite == 'skill':
        m = progression.metrics(c, bot_id)
        n = m['verified'] + m['rejected']
        if n < SUITES['skill']['min_evidence']:
            return None, {'judged_missions': n, 'needed': 3}, ''
        return m['quality_percent'], {'verified': m['verified'], 'rejected': m['rejected']}, 'The owner rejected work; review the rejected missions and the Bot\'s instructions or tools.'
    if suite == 'compliance':
        career = careers.get_career(c, bot_id)
        if career is None:
            return None, {'reason': 'This Bot has no career, so there are no role rules to check.'}, ''
        rules = list(career['career'].get('permission_boundaries') or []) + list(career['career'].get('escalation') or [])
        text = bot['personality'] or ''
        if not rules:
            ins = (career['career'].get('instructions') or '').strip()
            if not ins:
                return None, {'reason': 'The role has no boundary or instruction text to check.'}, ''
            rules = [ins]
        missing = [r for r in rules if r not in text]
        return round((len(rules) - len(missing)) * 100 / len(rules)), {'rules': len(rules), 'missing': missing[:10]}, 'The Bot\'s instructions no longer contain these role rules. Restore them or roll back to an earlier version.'
    if suite == 'collaboration':
        rows = c.execute('SELECT f.rating FROM review_feedback f JOIN reviews r ON r.id=f.review_id WHERE r.bot_id=?', (bot_id,)).fetchall()
        if len(rows) < SUITES['collaboration']['min_evidence']:
            return None, {'ratings': len(rows), 'needed': 2}, ''
        mean = sum(r['rating'] for r in rows) / len(rows)
        return round(mean * 20), {'ratings': len(rows), 'mean_rating': round(mean, 2)}, 'Colleagues rated the working relationship low. Read the feedback comments on recent reviews.'
    if suite == 'reliability':
        m = progression.metrics(c, bot_id)
        n = m['completed'] + m['failed']
        if n < SUITES['reliability']['min_evidence']:
            return None, {'finished_missions': n, 'needed': 5}, ''
        return m['reliability_percent'], {'completed': m['completed'], 'failed': m['failed']}, 'Missions are failing. Check the failure messages: they usually point to a tool, missing knowledge or unclear instructions.'
    if suite == 'readiness':
        m = progression.metrics(c, bot_id)
        if m['completed'] + m['failed'] == 0:
            return None, {'reason': 'No finished missions yet, so there is nothing to judge readiness on.'}, ''
        e = progression.eligibility(c, bot_id, now)
        if not e['criteria']:
            return None, {'reason': e.get('reason', 'No next level.')}, ''
        met = sum(1 for x in e['criteria'] if x['met'])
        return round(met * 100 / len(e['criteria'])), {'met': met, 'of': len(e['criteria']), 'target': e['target'],
                                                       'unmet': [x['name'] for x in e['criteria'] if not x['met']]}, 'Not enough completed or verified work at this level yet.'
    raise EvalError('Unknown suite.')


def latest(c, bot_id):
    """Newest COUNTED result per suite."""
    out = {}
    for suite in SUITES:
        r = c.execute('SELECT * FROM evaluation_results WHERE bot_id=? AND suite=? AND counts=1 ORDER BY created_at DESC,rowid DESC LIMIT 1', (bot_id, suite)).fetchone()
        if r:
            out[suite] = r
    return out


def certification(c, bot_id):
    """A label derived only from counted results. Never reads or writes permissions or budgets."""
    got = latest(c, bot_id)
    if not got:
        return 'not_evaluated'
    ok = {s for s, r in got.items() if r['status'] == 'passed'}
    if not set(CORE) <= ok:
        return 'training'
    if len(ok) < len(SUITES):
        return 'competent'
    return 'expert' if all(r['score'] >= EXPERT_MARK for r in got.values()) else 'advanced'


def run(c, bot_id, suites=None, now=None):
    """Run suites for one Bot, record counted results, refresh the label, and report deltas against the previous result."""
    now = time.time() if now is None else now
    bot = _bot(c, bot_id)
    names = list(suites) if suites else list(SUITES)
    bad = [s for s in names if s not in SUITES]
    if bad:
        raise EvalError('Unknown suite: ' + ', '.join(bad))
    before = certification(c, bot_id)
    results = []
    for suite in names:
        spec = SUITES[suite]
        score, evidence, cause = _score(suite, c, bot, now)
        if score is None:
            results.append({'suite': suite, 'name': spec['name'], 'status': 'not_evaluated', 'evidence': evidence, 'recorded': False})
            continue
        status = 'passed' if score >= spec['pass_mark'] else 'failed'
        prev = c.execute('SELECT score FROM evaluation_results WHERE bot_id=? AND suite=? AND counts=1 ORDER BY created_at DESC,rowid DESC LIMIT 1', (bot_id, suite)).fetchone()
        rid = str(uuid.uuid4())
        c.execute('INSERT INTO evaluation_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (rid, bot_id, suite, spec['version'], 'live', status, score, spec['pass_mark'], 1, json.dumps(evidence), cause if status == 'failed' else '', 0, now))
        results.append({'id': rid, 'suite': suite, 'name': spec['name'], 'status': status, 'score': score, 'pass_mark': spec['pass_mark'],
                        'previous_score': prev['score'] if prev else None, 'delta': None if not prev else score - prev['score'],
                        'evidence': evidence, 'cause': cause if status == 'failed' else '', 'recorded': True})
    after = certification(c, bot_id)
    c.execute('INSERT INTO evaluation_certs VALUES (?,?,?) ON CONFLICT(bot_id) DO UPDATE SET level=excluded.level,updated_at=excluded.updated_at', (bot_id, after, now))
    if after != before:
        c.execute('INSERT INTO career_history(bot_id,event,detail,created_at) VALUES (?,?,?,?)',
                  (bot_id, 'certified', json.dumps({'from': before, 'to': after, 'label_only': True}), now))
    return {'bot_id': bot_id, 'results': results, 'certification': after, 'label': LABELS[after], 'changed': after != before,
            'cost_usd': 0, 'note': 'Scored from recorded work. No model was called. A certification is a label and changes no permission or spending limit.'}


def report(c, bot_id):
    _bot(c, bot_id)
    got = latest(c, bot_id)
    hist = c.execute('SELECT id,suite,suite_version,mode,status,score,pass_mark,counts,cause,created_at FROM evaluation_results WHERE bot_id=? ORDER BY created_at DESC,rowid DESC LIMIT 30', (bot_id,)).fetchall()
    level = certification(c, bot_id)
    return {'bot_id': bot_id, 'certification': level, 'label': LABELS[level],
            'suites': [{'suite': s, 'name': v['name'], 'version': v['version'], 'pass_mark': v['pass_mark'], 'what': v['what'],
                        'latest': ({'status': got[s]['status'], 'score': got[s]['score'], 'at': got[s]['created_at']} if s in got else None)} for s, v in SUITES.items()],
            'history': [dict(h) for h in hist]}


def overview(c):
    rows = c.execute('SELECT id,name,title FROM bots ORDER BY created_at,id').fetchall()
    return [{'bot_id': r['id'], 'name': r['name'], 'title': r['title'], 'certification': certification(c, r['id']),
             'label': LABELS[certification(c, r['id'])], 'results': c.execute('SELECT COUNT(*) FROM evaluation_results WHERE bot_id=? AND counts=1', (r['id'],)).fetchone()[0]} for r in rows]


# ---- instruction versions: every change to a Bot's instructions keeps the old text, and any version can be restored ----

def snapshot(c, bot_id, source, reason='', now=None):
    """Save the Bot's CURRENT instructions with the latest scores, before they change."""
    now = time.time() if now is None else now
    row = c.execute('SELECT personality FROM bots WHERE id=?', (bot_id,)).fetchone()
    if row is None:
        return None
    scores = {s: r['score'] for s, r in latest(c, bot_id).items()}
    vid = str(uuid.uuid4())
    c.execute('INSERT INTO bot_instruction_versions VALUES (?,?,?,?,?,?,?)', (vid, bot_id, row['personality'], source, reason[:500], json.dumps(scores), now))
    return vid


def versions(c, bot_id):
    _bot(c, bot_id)
    return [{'id': v['id'], 'source': v['source'], 'reason': v['reason'], 'scores': json.loads(v['scores_json']), 'created_at': v['created_at'], 'chars': len(v['personality'])}
            for v in c.execute('SELECT * FROM bot_instruction_versions WHERE bot_id=? ORDER BY created_at DESC,rowid DESC LIMIT 50', (bot_id,)).fetchall()]


def rollback(c, bot_id, version_id, now=None):
    """Restore an earlier text. The text being replaced is saved first, so a rollback can itself be undone."""
    v = c.execute('SELECT personality FROM bot_instruction_versions WHERE id=? AND bot_id=?', (version_id, bot_id)).fetchone()
    if v is None:
        raise EvalError('Version not found.')
    snapshot(c, bot_id, 'before-rollback', 'Saved automatically before restoring an earlier version.', now)
    c.execute('UPDATE bots SET personality=? WHERE id=?', (v['personality'], bot_id))
    return {'restored': version_id}
