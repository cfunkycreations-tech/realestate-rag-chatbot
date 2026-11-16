"""Employee DNA: versioned role presets (Career DNA) and career installation at birth.

Career DNA is stored separately from Character DNA (the Vault). The `bots` table is
never altered; a bot's career lives in `bot_careers` as an immutable snapshot of the
preset version it was born with, so later preset edits never silently rewrite an
existing employee.
"""
import hashlib
import json
import re
import secrets
import time

TIERS = ('LIGHT', 'STANDARD', 'ADVANCED', 'RESEARCH')
LEVELS = ('junior', 'mid', 'senior', 'lead', 'principal')
SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{1,63}$')
LIST_FIELDS = ('responsibilities', 'specializations', 'competencies', 'expected_outputs',
               'collaboration', 'promotion_requirements', 'tools', 'skills',
               'permission_boundaries', 'escalation', 'career_path')
TEXT_LIMITS = {'title': 100, 'department': 80, 'personality': 4000, 'job_description': 4000,
               'instructions': 12000, 'reports_to': 100}
MAX_PRESETS_PER_IMPORT = 500
PERSONALITY_CAP = 6000  # BotIn.personality limit used everywhere else in the app


class PresetError(ValueError):
    pass


def _clean_list(name, value):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 50 or not all(isinstance(v, str) and 0 < len(v) <= 500 for v in value):
        raise PresetError(f'{name} must be a list of up to 50 non-empty strings (max 500 chars each).')
    return [v.strip() for v in value]


def validate_preset(raw):
    """Return a normalized preset dict or raise PresetError. Pure, no database access."""
    if not isinstance(raw, dict):
        raise PresetError('Each preset must be an object.')
    pid = raw.get('id')
    if not isinstance(pid, str) or not SLUG.match(pid):
        raise PresetError('id must be a stable lowercase slug (a-z, 0-9, hyphens, 2-64 chars).')
    out = {'id': pid}
    for field, limit in TEXT_LIMITS.items():
        value = raw.get(field, '')
        if not isinstance(value, str):
            raise PresetError(f'{pid}: {field} must be text.')
        value = value.strip()
        if len(value) > limit:
            raise PresetError(f'{pid}: {field} exceeds {limit} characters.')
        out[field] = value
    for field in ('title', 'department', 'instructions'):
        if not out[field]:
            raise PresetError(f'{pid}: {field} is required.')
    level = str(raw.get('level', 'mid')).lower()
    if level not in LEVELS:
        raise PresetError(f'{pid}: level must be one of {", ".join(LEVELS)}.')
    tier = str(raw.get('model_tier', 'STANDARD')).upper()
    if tier not in TIERS:
        raise PresetError(f'{pid}: model_tier must be one of {", ".join(TIERS)}.')
    out['level'], out['model_tier'] = level, tier
    for field in LIST_FIELDS:
        out[field] = _clean_list(f'{pid}: {field}', raw.get(field))
    out['mentorship_eligible'] = bool(raw.get('mentorship_eligible', False))
    policy = raw.get('resource_policy', {})
    if not isinstance(policy, dict) or len(json.dumps(policy)) > 2000:
        raise PresetError(f'{pid}: resource_policy must be a small object.')
    out['resource_policy'] = policy
    return out


def content_hash(preset):
    body = {k: v for k, v in preset.items() if k != 'id'}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def import_presets(c, raw_presets, *, overwrite_customized=False, source='import', now=None):
    """Bulk import. Never silently replaces an owner-customized preset.

    Returns per-preset outcomes: created / new_version / unchanged / skipped_customized / invalid.
    """
    now = now or time.time()
    if not isinstance(raw_presets, list) or not raw_presets:
        raise PresetError('Provide a non-empty list of presets.')
    if len(raw_presets) > MAX_PRESETS_PER_IMPORT:
        raise PresetError(f'At most {MAX_PRESETS_PER_IMPORT} presets per import.')
    results, seen = [], set()
    for raw in raw_presets:
        pid = raw.get('id') if isinstance(raw, dict) else None
        try:
            preset = validate_preset(raw)
        except PresetError as exc:
            results.append({'id': pid, 'outcome': 'invalid', 'detail': str(exc)})
            continue
        if preset['id'] in seen:
            results.append({'id': pid, 'outcome': 'invalid', 'detail': 'Duplicate id inside this import.'})
            continue
        seen.add(preset['id'])
        digest = content_hash(preset)
        row = c.execute('SELECT current_version,customized FROM role_presets WHERE id=?', (pid,)).fetchone()
        if row is None:
            twin = c.execute('SELECT preset_id FROM role_preset_versions WHERE content_hash=? LIMIT 1', (digest,)).fetchone()
            c.execute('INSERT INTO role_presets VALUES (?,?,?,?,?,?,?)', (pid, preset['department'], 'active', 1, 0, now, now))
            c.execute('INSERT INTO role_preset_versions VALUES (?,?,?,?,?,?)', (pid, 1, json.dumps(preset), digest, source, now))
            results.append({'id': pid, 'outcome': 'created', 'version': 1,
                            **({'warning': f'Identical content already exists as {twin["preset_id"]}.'} if twin else {})})
            continue
        latest = c.execute('SELECT content_hash FROM role_preset_versions WHERE preset_id=? AND version=?', (pid, row['current_version'])).fetchone()
        if latest['content_hash'] == digest:
            results.append({'id': pid, 'outcome': 'unchanged', 'version': row['current_version']})
            continue
        if row['customized'] and not overwrite_customized:
            results.append({'id': pid, 'outcome': 'skipped_customized', 'version': row['current_version']})
            continue
        version = row['current_version'] + 1
        c.execute('INSERT INTO role_preset_versions VALUES (?,?,?,?,?,?)', (pid, version, json.dumps(preset), digest, source, now))
        c.execute('UPDATE role_presets SET current_version=?, department=?, updated_at=? WHERE id=?', (version, preset['department'], now, pid))
        results.append({'id': pid, 'outcome': 'new_version', 'version': version})
    return results


def update_preset(c, pid, raw, now=None):
    """Owner edit of one preset: new version, marks it customized so imports will not clobber it."""
    now = now or time.time()
    row = c.execute('SELECT current_version FROM role_presets WHERE id=?', (pid,)).fetchone()
    if row is None:
        raise KeyError(pid)
    preset = validate_preset({**raw, 'id': pid})
    digest = content_hash(preset)
    current = c.execute('SELECT content_hash FROM role_preset_versions WHERE preset_id=? AND version=?', (pid, row['current_version'])).fetchone()
    if current['content_hash'] == digest:
        return row['current_version']
    version = row['current_version'] + 1
    c.execute('INSERT INTO role_preset_versions VALUES (?,?,?,?,?,?)', (pid, version, json.dumps(preset), digest, 'owner-edit', now))
    c.execute('UPDATE role_presets SET current_version=?, department=?, customized=1, updated_at=? WHERE id=?', (version, preset['department'], now, pid))
    return version


def get_preset(c, pid, version=None):
    row = c.execute('SELECT current_version,status,customized FROM role_presets WHERE id=?', (pid,)).fetchone()
    if row is None:
        return None
    version = version or row['current_version']
    data = c.execute('SELECT data FROM role_preset_versions WHERE preset_id=? AND version=?', (pid, version)).fetchone()
    if data is None:
        return None
    return {**json.loads(data['data']), 'version': version, 'status': row['status'], 'customized': bool(row['customized'])}


def list_presets(c):
    rows = c.execute('SELECT id FROM role_presets ORDER BY department,id').fetchall()
    return [get_preset(c, r['id']) for r in rows]


def export_presets(c):
    return {'format': 'funkbot-role-pack', 'format_version': 1,
            'presets': [{k: v for k, v in p.items() if k not in ('version', 'status', 'customized')} for p in list_presets(c)]}


def compose_personality(preset):
    """Professional instructions first; decorative character flavor never overrides them."""
    parts = [f'You are working as {preset["title"]} ({preset["department"]}).']
    if preset['personality']:
        parts.append(preset['personality'])
    parts.append('PROFESSIONAL INSTRUCTIONS (these take precedence over any character persona):\n' + preset['instructions'])
    if preset['permission_boundaries']:
        parts.append('Boundaries: ' + '; '.join(preset['permission_boundaries']))
    if preset['escalation']:
        parts.append('Escalate when: ' + '; '.join(preset['escalation']))
    text = '\n\n'.join(parts)
    return text[:PERSONALITY_CAP]


def eligible_presets(c):
    return [r['id'] for r in c.execute("SELECT id FROM role_presets WHERE status='active' ORDER BY id").fetchall()]


def pick_surprise_preset(c):
    ids = eligible_presets(c)
    return ids[secrets.randbelow(len(ids))] if ids else None


def install_career(c, bot_id, preset, *, birth_mode, now=None):
    """Snapshot the preset version onto the bot, apply title/personality, record the event."""
    now = now or time.time()
    c.execute('UPDATE bots SET title=?, personality=? WHERE id=?', (preset['title'], compose_personality(preset), bot_id))
    c.execute('INSERT INTO bot_careers VALUES (?,?,?,?,?,?,?,?,?)',
              (bot_id, preset['id'], preset['version'], json.dumps({k: v for k, v in preset.items() if k not in ('status', 'customized')}),
               preset['level'], preset['department'], preset['model_tier'], None, now))
    c.execute('INSERT INTO career_history(bot_id,event,detail,created_at) VALUES (?,?,?,?)',
              (bot_id, 'born', json.dumps({'preset_id': preset['id'], 'preset_version': preset['version'], 'birth_mode': birth_mode, 'level': preset['level']}), now))


def get_career(c, bot_id):
    row = c.execute('SELECT * FROM bot_careers WHERE bot_id=?', (bot_id,)).fetchone()
    if row is None:
        return None
    history = [{'event': h['event'], 'detail': json.loads(h['detail']), 'created_at': h['created_at']}
               for h in c.execute('SELECT event,detail,created_at FROM career_history WHERE bot_id=? ORDER BY id', (bot_id,)).fetchall()]
    return {'bot_id': bot_id, 'preset_id': row['preset_id'], 'preset_version': row['preset_version'],
            'level': row['level'], 'department': row['department'], 'model_tier': row['model_tier'],
            'mentor_bot_id': row['mentor_bot_id'], 'career': json.loads(row['career_json']), 'history': history}
