"""Funk Bot: local-first, single-user chat service."""
import asyncio
import io
import warnings
import json
import logging
import os
import secrets
import time
import uuid
from decimal import Decimal
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from cryptography.fernet import Fernet
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from funkbot.database import migrate, session
from funkbot.events import EventPage, append_event, row_to_event
from funkbot.auth_security import ensure_setup_token, lockout_seconds
from funkbot.redaction import SlidingRedactor, redact_text
from funkbot.vault import MAX_ARCHIVE, VaultError, character_for_bot, draw_character, import_zip
from funkbot.budget import BudgetError, NANOS_PER_DOLLAR, dollars_to_nanos, limit_to_nanos, limits_for, reconcile_run, reconcile_usage, reserve, settle, token_cost_nanos

DATA = Path(os.environ.get('FUNK_DATA_DIR', Path(__file__).parent.parent / 'data'))
DATA.mkdir(parents=True, exist_ok=True)

def get_or_create_key(name, factory):
    path = DATA / name
    try:
        with path.open('x') as f:
            os.chmod(path, 0o600)
            f.write(factory())
    except FileExistsError:
        pass
    return path.read_text().strip()

cipher = Fernet(get_or_create_key('vault.key', lambda: Fernet.generate_key().decode()).encode())
session_secret = os.environ.get('FUNK_SESSION_SECRET') or get_or_create_key('session.key', lambda: secrets.token_urlsafe(48))
signer = URLSafeTimedSerializer(session_secret, salt='funk-session')
ph = PasswordHasher()
DB = DATA / 'funk.db'

def db():
    return session(DB)

def init_db():
    migrate(DB)
    with db() as c:
        defaults = {
            'gateways': json.dumps({'omniroute': {'url': os.getenv('OMNIROUTE_URL', 'http://localhost:20128/v1'), 'key': ''}, 'openrouter': {'url':'https://openrouter.ai/api/v1', 'key':''}, 'custom': {'url':'', 'key':''}}),
            'profiles': json.dumps({'fast': [{'gateway':'omniroute','model':'auto'}], 'smart': [{'gateway':'openrouter','model':'openai/gpt-4o-mini'}, {'gateway':'omniroute','model':'auto'}], 'thinker': [{'gateway':'openrouter','model':'openai/o3-mini'}], 'vision': [{'gateway':'openrouter','model':'openai/gpt-4o-mini'}], 'cheap-bulk': [{'gateway':'omniroute','model':'auto'}]})
        }
        for k,v in defaults.items(): c.execute('INSERT OR IGNORE INTO config VALUES (?,?)',(k,v))

def config(key, fallback=None):
    with db() as c:
        row = c.execute('SELECT value FROM config WHERE key=?',(key,)).fetchone()
    return row['value'] if row else fallback

def set_config(key, value):
    with db() as c: c.execute('INSERT OR REPLACE INTO config VALUES (?,?)',(key,value))

def configured_secrets():
    found = []
    for gateway in json.loads(config('gateways','{}')).values():
        try:
            if gateway.get('key'):
                found.append(cipher.decrypt(gateway['key'].encode()).decode())
        except Exception:
            pass
    return found

def redact(text):
    return redact_text(text, configured_secrets())

def require_auth(request: Request):
    try:
        if signer.loads(request.cookies.get('funk_session',''), max_age=60*60*24*30) != 'owner': raise BadSignature('invalid')
    except BadSignature: raise HTTPException(401, 'Please sign in.')

def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(400, 'Enter a valid HTTP(S) gateway URL without credentials.')
    return url.rstrip('/')

init_db()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Only new installations need the one-time code. Existing volumes keep working.
    mark_interrupted_runs()
    if config('password_hash') is None:
        token = ensure_setup_token(DATA)
        logging.getLogger('uvicorn.error').warning(
            'Funk Bot first-run setup code (enter this in the setup screen): %s', token
        )
    yield

app = FastAPI(title='Funk Bot', lifespan=lifespan)
jobs = {}

class Password(BaseModel):
    password: str = Field(min_length=8, max_length=256)

class SetupPassword(Password):
    setup_token: str = Field(default='', max_length=256)

@app.get('/api/auth/status')
def auth_status(request: Request):
    authenticated = True
    try: require_auth(request)
    except HTTPException: authenticated = False
    return {'setup': config('password_hash') is not None, 'authenticated': authenticated}

@app.post('/api/auth/setup')
def setup(body: SetupPassword, response: Response):
    # Do not reveal the setup code via the API. The file is readable only to
    # the installation owner; the code is printed to the backend startup log.
    if config('password_hash') is not None:
        raise HTTPException(409, 'Setup is already complete.')
    token_file = DATA / 'setup.token'
    try:
        expected = token_file.read_text(encoding='utf-8').strip()
    except FileNotFoundError:
        raise HTTPException(503, 'Setup code unavailable. Restart the backend.')
    if not body.setup_token or not secrets.compare_digest(expected, body.setup_token):
        raise HTTPException(403, 'Incorrect setup code. Check the backend logs.')
    with db() as c:
        try: c.execute('INSERT INTO config VALUES (?,?)', ('password_hash', ph.hash(body.password)))
        except IntegrityError: raise HTTPException(409, 'Setup is already complete.')
    token_file.unlink(missing_ok=True)
    response.set_cookie('funk_session', signer.dumps('owner'), httponly=True, samesite='strict', max_age=2592000, secure=os.getenv('FUNK_SECURE_COOKIE') == '1')
    return {'ok': True}

@app.post('/api/auth/login')
def login(body: Password, response: Response):
    # The account-wide guard is stored in SQLite, not keyed by a proxy-provided
    # IP. BEGIN IMMEDIATE serializes attempts across threads and processes.
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        guard = c.execute('SELECT failures, locked_until FROM login_guard WHERE id=1').fetchone()
        remaining = guard['locked_until'] - time.time()
        if remaining > 0:
            c.commit()
            raise HTTPException(429, 'Too many attempts. Please wait and try again.', headers={'Retry-After': str(max(1, int(remaining) + 1))})
        row = c.execute('SELECT value FROM config WHERE key=?', ('password_hash',)).fetchone()
        valid = False
        try:
            valid = bool(row and ph.verify(row['value'], body.password))
        except (VerifyMismatchError, VerificationError):
            pass
        if not valid:
            failures = guard['failures'] + 1
            c.execute('UPDATE login_guard SET failures=?, locked_until=? WHERE id=1', (failures, time.time() + lockout_seconds(failures)))
            c.commit()
            raise HTTPException(401, 'Incorrect password.')
        c.execute('UPDATE login_guard SET failures=0, locked_until=0 WHERE id=1')
        c.commit()
    response.set_cookie('funk_session', signer.dumps('owner'), httponly=True, samesite='strict', max_age=2592000, secure=os.getenv('FUNK_SECURE_COOKIE') == '1')
    return {'ok': True}

@app.post('/api/auth/logout')
def logout(response: Response):
    response.delete_cookie('funk_session')
    return {'ok':True}

class BotIn(BaseModel):
    name: str = Field(default='New Bot', min_length=1,max_length=120)
    title: str = Field(default='Personal assistant', max_length=100)
    personality: str = Field(default='You are a helpful, thoughtful personal assistant.', max_length=6000)
    color: str = Field(default='lavender', pattern='^(lavender|peach|mint|blue|yellow)$')
    shape: str = Field(default='round', pattern='^(round|square|cloud)$')
    profile: str = Field(default='smart', pattern='^(fast|smart|thinker|vision|cheap-bulk)$')

def redact_character(character, keys):
    # Gateway keys saved after an import must not leak through old metadata.
    for field in ('name', 'role', 'notes'):
        character[field] = redact_text(character[field], keys)
    character['tags'] = [redact_text(tag, keys) for tag in character['tags']]
    return character

@app.get('/api/bots')
def bots(request: Request):
    require_auth(request)
    with db() as c:
        rows = c.execute("""SELECT b.*, (SELECT content FROM messages m WHERE m.bot_id=b.id ORDER BY created_at DESC LIMIT 1) as latest,
                            ch.name as character_name, ch.role as character_role, ch.tags as character_tags,
                            ch.notes as character_notes, ch.rarity as character_rarity
                            FROM bots b LEFT JOIN bot_characters bc ON bc.bot_id=b.id
                            LEFT JOIN characters ch ON ch.id=bc.character_id ORDER BY b.created_at""").fetchall()
    result=[]
    keys=configured_secrets()
    for row in rows:
        item=dict(row)
        for field in ('name','title','personality','latest'):
            if item[field] is not None:
                item[field] = redact_text(item[field], keys)
        character = None
        if item['character_name'] is not None:
            character=character_for_bot({'name':item['character_name'], 'role':item['character_role'], 'tags':item['character_tags'],
                                         'notes':item['character_notes'], 'rarity':item['character_rarity']}, item['id'])
            character = redact_character(character, keys)
        for field in ('character_name','character_role','character_tags','character_notes','character_rarity'):
            item.pop(field)
        item['character']=character
        result.append(item)
    return result

@app.post('/api/bots')
def create_bot(body: BotIn, request: Request):
    require_auth(request)
    name,title,personality=redact(body.name.strip()),redact(body.title.strip()),redact(body.personality)
    keys=configured_secrets()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        id = str(uuid.uuid4())
        c.execute('INSERT INTO bots VALUES (?,?,?,?,?,?,?,?)',(id,name,title,personality,body.color,body.shape,body.profile,time.time()))
        character=draw_character(c,id)
        if character:
            c.execute('UPDATE bots SET name=? WHERE id=?', (redact_text(character['name'], keys),id))
    return {'id':id,'character':redact_character(character, configured_secrets()) if character else None}

class SpriteChoice(BaseModel):
    adopt_character_name: bool


@app.post('/api/bots/{bot_id}/sprite')
def give_sprite(bot_id: str, body: SpriteChoice, request: Request):
    require_auth(request)
    keys = configured_secrets()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM bots WHERE id=?', (bot_id,)).fetchone():
            raise HTTPException(404, 'Bot not found.')
        if c.execute('SELECT 1 FROM bot_characters WHERE bot_id=?', (bot_id,)).fetchone():
            raise HTTPException(409, 'This Bot already has a sprite. Its existing sprite was not changed.')
        character = draw_character(c, bot_id)
        if not character:
            raise HTTPException(409, 'The Character Vault is empty. Import characters first.')
        character = redact_character(character, keys)
        if body.adopt_character_name:
            c.execute('UPDATE bots SET name=? WHERE id=?', (character['name'], bot_id))
    return {'character':character}


@app.put('/api/bots/{bot_id}')
def update_bot(bot_id: str, body: BotIn, request: Request):
    require_auth(request)
    with db() as c:
        cur=c.execute('UPDATE bots SET name=?, title=?, personality=?, color=?, shape=?, profile=? WHERE id=?',(redact(body.name.strip()),redact(body.title.strip()),redact(body.personality),body.color,body.shape,body.profile,bot_id))
        if not cur.rowcount: raise HTTPException(404,'Bot not found.')
    return {'ok':True}

@app.delete('/api/bots/{bot_id}')
def delete_bot(bot_id: str, request: Request):
    require_auth(request)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM runs WHERE bot_id=? AND status IN ('queued','running','waiting_approval')", (bot_id,)).fetchone(): raise HTTPException(409, 'Wait for the current response before deleting this Bot.')
        assignment=c.execute('SELECT character_id FROM bot_characters WHERE bot_id=?',(bot_id,)).fetchone()
        if not c.execute('DELETE FROM bots WHERE id=?',(bot_id,)).rowcount: raise HTTPException(404,'Bot not found.')
        if assignment and not c.execute('SELECT 1 FROM bot_characters WHERE character_id=?',(assignment['character_id'],)).fetchone():
            c.execute('UPDATE characters SET drawn=0 WHERE id=?',(assignment['character_id'],))
    return {'ok':True}

@app.get('/api/bots/{bot_id}/avatar')
def bot_avatar(bot_id: str, request: Request):
    require_auth(request)
    with db() as c:
        row=c.execute('SELECT character_id FROM bot_characters WHERE bot_id=?',(bot_id,)).fetchone()
    if not row: raise HTTPException(404, 'Character not found.')
    path=DATA / 'vault' / (row['character_id'] + '.png')
    if not path.is_file(): raise HTTPException(404, 'Character artwork is missing.')
    return FileResponse(path, media_type='image/png', headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

@app.get('/api/vault/status')
def vault_status(request: Request):
    require_auth(request)
    with db() as c:
        row=c.execute('SELECT COUNT(*) as total, COALESCE(SUM(CASE WHEN drawn=0 THEN 1 ELSE 0 END),0) as available FROM characters').fetchone()
    return dict(row)

@app.post('/api/vault/import')
async def vault_import(request: Request, file: UploadFile = File(...), collection: str = Form(default="", max_length=60)):
    require_auth(request)
    try:
        data=await file.read(MAX_ARCHIVE+1)
        if len(data)>MAX_ARCHIVE: raise VaultError('ZIP is too large (maximum 20 MB).')
        keys=configured_secrets()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            result=import_zip(data,c,DATA / 'vault',keys,collection.strip())
        return result
    except VaultError as exc:
        raise HTTPException(400,str(exc)) from exc
    finally:
        await file.close()

@app.get('/api/bots/{bot_id}/messages')
def messages(bot_id: str, request: Request):
    require_auth(request)
    with db() as c:
        return [dict(r) for r in c.execute('SELECT * FROM messages WHERE bot_id=? ORDER BY created_at',(bot_id,))]

class GatewayIn(BaseModel):
    url: str
    key: str | None = None
    clear_key: bool = False

@app.get('/api/settings')
def settings(request: Request):
    require_auth(request)
    gateways=json.loads(config('gateways'))
    for g in gateways.values():
        g['has_key']=bool(g.pop('key', ''))
    with db() as c:
        usage=dict(c.execute('SELECT COALESCE(SUM(prompt_tokens),0) as prompt_tokens, COALESCE(SUM(completion_tokens),0) as completion_tokens, COALESCE(SUM(cost),0) as cost FROM usage').fetchone())
        usage['cost'] += c.execute('SELECT COALESCE(SUM(cost_nanos),0) FROM budget_reconciliations WHERE run_id IS NOT NULL').fetchone()[0] / NANOS_PER_DOLLAR
        usage['unknown'] = c.execute("SELECT COUNT(*) FROM budget_reservations WHERE status='uncertain'").fetchone()[0] + c.execute("SELECT COUNT(*) FROM usage WHERE cost IS NULL AND NOT EXISTS (SELECT 1 FROM budget_reservations WHERE budget_reservations.usage_id=usage.id)").fetchone()[0]
    return {'gateways':gateways, 'profiles':json.loads(config('profiles')), 'usage':usage}

@app.put('/api/settings/gateways/{name}')
def save_gateway(name: str, body: GatewayIn, request: Request):
    require_auth(request)
    gateways=json.loads(config('gateways'))
    if name not in gateways: raise HTTPException(404,'Gateway not found.')
    gateways[name]['url']=validate_url(body.url) if body.url else ''
    if body.clear_key: gateways[name]['key']=''
    elif body.key: gateways[name]['key']=cipher.encrypt(body.key.encode()).decode()
    set_config('gateways',json.dumps(gateways))
    return {'ok':True}

class ProfileEntry(BaseModel):
    gateway: str = Field(pattern='^(omniroute|openrouter|custom)$')
    model: str = Field(min_length=1,max_length=200)

@app.put('/api/settings/profiles')
def save_profiles(body: dict[str,list[ProfileEntry]], request: Request):
    require_auth(request)
    if set(body) != {'fast','smart','thinker','vision','cheap-bulk'} or any(not v or len(v)>10 for v in body.values()): raise HTTPException(400,'Each profile needs one to ten models.')
    set_config('profiles',json.dumps({k:[x.model_dump() for x in v] for k,v in body.items()}))
    return {'ok':True}

def gateway_config(name):
    g=json.loads(config('gateways'))[name]
    if not g['url']: raise ValueError('Gateway URL is not configured')
    key=cipher.decrypt(g['key'].encode()).decode() if g['key'] else ''
    return g['url'], {'Authorization':f'Bearer {key}'} if key else {}

@app.get('/api/settings/gateways/{name}/models')
async def models(name: str, request: Request):
    require_auth(request)
    if name not in ('omniroute','openrouter','custom'): raise HTTPException(404, 'Gateway not found.')
    try:
        url, headers=gateway_config(name)
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            result=await client.get(url+'/models',headers=headers)
            result.raise_for_status()
        return {'models': [x['id'] for x in result.json().get('data',[]) if isinstance(x,dict) and isinstance(x.get('id'),str)][:1000]}
    except Exception as e: raise HTTPException(502, 'Could not reach gateway. Check its URL and credentials.') from e

PROFILES = {'fast', 'smart', 'thinker', 'vision', 'cheap-bulk'}


class BudgetLimitsIn(BaseModel):
    daily: str = Field(max_length=32)
    monthly: str | None = Field(default=None, max_length=32)


class BudgetPriceIn(BaseModel):
    prompt: str = Field(max_length=32)
    completion: str = Field(max_length=32)
    max_prompt_tokens: int = Field(ge=1, le=1_000_000, strict=True)
    max_completion_tokens: int = Field(ge=1, le=100_000, strict=True)


class BudgetCorrectionIn(BaseModel):
    amount: str = Field(max_length=32)
    source: str = Field(min_length=1, max_length=500)


def nano_string(value):
    return str(Decimal(value) / Decimal(NANOS_PER_DOLLAR))


@app.get('/api/budget')
def get_budget(request: Request):
    require_auth(request)
    with db() as c:
        account = limits_for(c, 'account')
        bots = {row['scope'][4:]: {'daily': nano_string(row['daily_nanos']), 'monthly': None if row['monthly_nanos'] is None else nano_string(row['monthly_nanos'])} for row in c.execute("SELECT * FROM budget_limits WHERE scope LIKE 'bot:%'")}
        prices = {row['profile']: {'prompt': row['prompt_usd_per_million'], 'completion': row['completion_usd_per_million'], 'max_prompt_tokens': row['max_prompt_tokens'], 'max_completion_tokens': row['max_completion_tokens']} for row in c.execute('SELECT * FROM budget_prices')}
        uncertain = [dict(row) for row in c.execute("SELECT run_id,bot_id,profile,created_at FROM budget_reservations WHERE status='uncertain' ORDER BY created_at DESC")]
        unknown = [dict(row) for row in c.execute("SELECT id,bot_id,gateway,model,created_at FROM usage WHERE cost IS NULL AND NOT EXISTS (SELECT 1 FROM budget_reservations WHERE budget_reservations.usage_id=usage.id) ORDER BY created_at DESC")]
    keys=configured_secrets()
    for row in unknown:
        for field in ('gateway','model'):
            if row[field] is not None: row[field]=redact_text(row[field],keys)
    return {'account': {'daily': nano_string(account[0]), 'monthly': None if account[1] is None else nano_string(account[1])}, 'bots': bots, 'prices': prices, 'unreconciled': uncertain, 'unknown_usage': unknown}


@app.put('/api/budget/limits/{scope}')
def put_budget_limits(scope: str, body: BudgetLimitsIn, request: Request):
    require_auth(request)
    if scope != 'account' and not scope.startswith('bot:'): raise HTTPException(400, 'Invalid budget scope.')
    try:
        daily = limit_to_nanos(body.daily)
        monthly = None if body.monthly is None else limit_to_nanos(body.monthly)
    except BudgetError as exc: raise HTTPException(400, str(exc)) from exc
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if scope.startswith('bot:') and not c.execute('SELECT 1 FROM bots WHERE id=?', (scope[4:],)).fetchone(): raise HTTPException(404, 'Bot not found.')
        c.execute('INSERT OR REPLACE INTO budget_limits VALUES (?,?,?)', (scope,daily,monthly))
    return {'ok': True}


@app.put('/api/budget/prices/{profile}')
def put_budget_price(profile: str, body: BudgetPriceIn, request: Request):
    require_auth(request)
    if profile not in PROFILES: raise HTTPException(404, 'Profile not found.')
    try:
        token_cost_nanos(body.max_prompt_tokens,body.max_completion_tokens,body.prompt,body.completion)
    except BudgetError as exc: raise HTTPException(400,str(exc)) from exc
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('INSERT OR REPLACE INTO budget_prices VALUES (?,?,?,?,?)', (profile,body.prompt,body.completion,body.max_prompt_tokens,body.max_completion_tokens))
    return {'ok': True}


@app.post('/api/budget/reconcile/{kind}/{identifier}')
def reconcile_budget(kind: str, identifier: str, body: BudgetCorrectionIn, request: Request):
    require_auth(request)
    source = redact(body.source)
    try:
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if kind == 'run': reconcile_run(c,identifier,body.amount,source)
            elif kind == 'usage' and identifier.isdigit(): reconcile_usage(c,int(identifier),body.amount,source)
            else: raise HTTPException(400, 'Invalid correction target.')
    except BudgetError as exc: raise HTTPException(400, str(exc)) from exc
    return {'ok': True}


class ChatIn(BaseModel):
    content: str = Field(min_length=1,max_length=20000)
    profile: str | None = Field(default=None, pattern='^(fast|smart|thinker|vision|cheap-bulk)$')

ACTIVE_STATUSES = ('queued', 'running', 'waiting_approval')

def record_event(c, run_id, kind, values):
    c.execute('INSERT INTO run_events (run_id,event_type,payload,created_at) VALUES (?,?,?,?)',
              (run_id, kind, json.dumps(values), time.time()))
    if kind in ('bot.state_changed', 'error'):
        bot_id = c.execute('SELECT bot_id FROM runs WHERE id=?', (run_id,)).fetchone()['bot_id']
        append_event(c, bot_id, run_id, 'error.raised' if kind == 'error' else kind, values)

def mark_interrupted_runs():
    # This server runs one worker. A restart cannot resume an HTTP model stream;
    # mark incomplete runs failed rather than silently losing them.
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        rows = c.execute("SELECT id,bot_id FROM runs WHERE status IN ('queued','running','waiting_approval')").fetchall()
        for row in rows:
            record_event(c, row['id'], 'bot.state_changed', {'state':'error'})
            record_event(c, row['id'], 'error', {'message':'The backend restarted before this response finished. Please try again.'})
            c.execute("UPDATE budget_reservations SET status='uncertain' WHERE run_id=? AND status='reserved'", (row['id'],))
            c.execute("UPDATE runs SET status='failed', updated_at=? WHERE id=?", (time.time(), row['id']))
            append_event(c, row['bot_id'], row['id'], 'run.finished', {'status':'failed'})

def event(job, kind, **values):
    payload = {'type':kind, **values}
    if 'id' in job:
        with db() as c:
            record_event(c, job['id'], kind, values)
        job['notify'].set()
    else:
        # Lightweight direct-runtime tests do not create a persistent run.
        job['events'].append(payload)

def finish_run(job, status, kind, values=None, completion=None):
    values = values or {}
    if 'id' not in job:
        event(job, kind, **values)
        job['done'] = True
        return
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        current = c.execute('SELECT status FROM runs WHERE id=?', (job['id'],)).fetchone()
        if not current or current['status'] not in ACTIVE_STATUSES:
            job['done'] = True
            job['notify'].set()
            return
        if completion:
            bot_id, content, gateway, model, usage = completion
            message_id = str(uuid.uuid4())
            c.execute('INSERT INTO messages VALUES (?,?,?,?,?)', (message_id, bot_id, 'assistant', content, time.time()))
            append_event(c, bot_id, job['id'], 'message.sent', {'message_id':message_id, 'role':'assistant', 'summary':content[:240]})
            reservation = c.execute('SELECT * FROM budget_reservations WHERE run_id=?', (job['id'],)).fetchone()
            if reservation:
                prompt_tokens, completion_tokens = usage.get('prompt_tokens'), usage.get('completion_tokens')
                if type(prompt_tokens) is int and type(completion_tokens) is int and prompt_tokens >= 0 and completion_tokens >= 0:
                    c.execute('INSERT INTO usage (bot_id,gateway,model,prompt_tokens,completion_tokens,cost,created_at) VALUES (?,?,?,?,?,?,?)', (bot_id,gateway,model,prompt_tokens,completion_tokens,None,time.time()))
                    usage_id = c.execute('SELECT last_insert_rowid()').fetchone()[0]
                    cost = None if job.get('uncertain') else settle(c,job['id'],usage_id,prompt_tokens,completion_tokens)
                    if cost is None:
                        c.execute("UPDATE budget_reservations SET status='uncertain', usage_id=? WHERE run_id=? AND status IN ('reserved','uncertain')", (usage_id,job['id']))
                        values['warning'] = 'Gateway charges could not be verified. Further spending is blocked pending reconciliation.'
                else:
                    c.execute("UPDATE budget_reservations SET status='uncertain' WHERE run_id=? AND status='reserved'", (job['id'],))
                    values['warning'] = 'Gateway did not report token usage. Further spending is blocked pending reconciliation.'
            else:
                c.execute('INSERT INTO usage (bot_id,gateway,model,prompt_tokens,completion_tokens,cost,created_at) VALUES (?,?,?,?,?,?,?)', (bot_id, gateway, model, usage.get('prompt_tokens',0), usage.get('completion_tokens',0), usage.get('cost'), time.time()))
        else:
            c.execute("UPDATE budget_reservations SET status=? WHERE run_id=? AND status='reserved'", ('uncertain' if job.get('dispatched') else 'released',job['id']))
            if job.get('dispatched'):
                values['message'] = values.get('message','Run stopped.') + ' Gateway charges are unknown; reconcile them before further spending.'
        record_event(c, job['id'], 'bot.state_changed', {'state':'done' if status == 'done' else 'error' if status == 'failed' else 'idle'})
        record_event(c, job['id'], kind, values)
        c.execute('UPDATE runs SET status=?,updated_at=? WHERE id=?', (status, time.time(), job['id']))
        append_event(c, job['bot_id'], job['id'], 'run.finished', {'status':status})
    job['done'] = True
    job['notify'].set()

def bot_system_prompt(bot):
    return bot['personality'] + '\nYou are ' + bot['name'] + '. Your job title is ' + (bot.get('title') or 'Personal assistant') + '. Perform that job for the user.'

async def run_chat(job, bot, history, profile):
    entries=job.get('entries') or json.loads(config('profiles')).get(profile,[])
    for entry in entries:
        emitted=False
        try:
            url, headers=gateway_config(entry['gateway'])
            payload={'model':entry['model'], 'messages':[{'role':'system','content':bot_system_prompt(bot)}, *history], 'stream':True, 'stream_options':{'include_usage':True}}
            if job.get('max_completion_tokens') is not None: payload['max_tokens']=job['max_completion_tokens']
            async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=10), follow_redirects=False) as client:
                job['dispatched']=True
                async with client.stream('POST', url+'/chat/completions', headers=headers, json=payload) as response:
                    response.raise_for_status()
                    content=''; usage={}
                    redactor=SlidingRedactor(configured_secrets() + [headers.get('Authorization', '').removeprefix('Bearer ')])
                    async for line in response.aiter_lines():
                        if job.get('cancel'): raise asyncio.CancelledError()
                        if not line.startswith('data:'): continue
                        data=line[5:].strip()
                        if data=='[DONE]': break
                        try: chunk=json.loads(data)
                        except json.JSONDecodeError: continue
                        if chunk.get('error'): raise ValueError('Gateway returned an error')
                        usage=chunk.get('usage') or usage
                        choices=chunk.get('choices') or []
                        delta=choices[0].get('delta',{}).get('content') if choices else None
                        if isinstance(delta,str) and delta:
                            emitted=True
                            safe=redactor.feed(delta)
                            if safe:
                                content+=safe
                                event(job,'delta',content=safe)
                    if not emitted: raise ValueError('Gateway returned an empty response')
                    safe=redactor.finish()
                    if safe:
                        content+=safe
                        event(job,'delta',content=safe)
                    if 'id' in job:
                        finish_run(job, 'done', 'done', completion=(bot['id'],content,entry['gateway'],entry['model'],usage))
                    else:
                        # Direct runtime tests use the same storage behavior.
                        with db() as c:
                            c.execute('INSERT INTO messages VALUES (?,?,?,?,?)',(str(uuid.uuid4()),bot['id'],'assistant',content,time.time()))
                            c.execute('INSERT INTO usage (bot_id,gateway,model,prompt_tokens,completion_tokens,cost,created_at) VALUES (?,?,?,?,?,?,?)',(bot['id'],entry['gateway'],entry['model'],usage.get('prompt_tokens',0),usage.get('completion_tokens',0),usage.get('cost'),time.time()))
                        finish_run(job, 'done', 'done')
                    return
        except asyncio.CancelledError:
            user_stopped = job.get('user_cancelled', False)
            finish_run(job, 'cancelled' if user_stopped else 'failed', 'error', {'message':'Response stopped.' if user_stopped else 'The backend stopped before this response finished. Please try again.'}); return
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            if job.get('dispatched'): job['uncertain']=True
            # Only fail over on transient gateway errors or invalid/empty responses.
            status = exc.response.status_code if isinstance(exc,httpx.HTTPStatusError) else None
            if emitted or (status is not None and status not in (429,500,502,503,504)):
                break
    finish_run(job, 'failed', 'error', {'message':'Could not get a response from the configured models. Check gateway settings and try again.'})

@app.post('/api/bots/{bot_id}/chat')
async def chat(bot_id: str, body: ChatIn, request: Request):
    require_auth(request)
    # Compute redaction before acquiring the write lock: redact reads config.
    keys = configured_secrets()
    content = redact_text(body.content, keys)
    job_id = str(uuid.uuid4())
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM bots WHERE id=?',(bot_id,)).fetchone()
        if not row: raise HTTPException(404,'Bot not found.')
        if c.execute("SELECT 1 FROM runs WHERE bot_id=? AND status IN ('queued','running','waiting_approval')", (bot_id,)).fetchone():
            raise HTTPException(409,'This Bot is already responding.')
        bot=dict(row)
        for field in ('name','title','personality'):
            bot[field] = redact_text(bot[field], keys)
        now=time.time()
        chosen_profile=body.profile or bot['profile']
        entries=json.loads(c.execute('SELECT value FROM config WHERE key=?', ('profiles',)).fetchone()['value']).get(chosen_profile,[])
        previous=[{'role':r['role'],'content':r['content']} for r in c.execute('SELECT role,content FROM messages WHERE bot_id=? ORDER BY created_at DESC LIMIT 39',(bot_id,)).fetchall()][::-1]
        history=[*previous,{'role':'user','content':content}]
        price=c.execute('SELECT * FROM budget_prices WHERE profile=?', (chosen_profile,)).fetchone()
        if price:
            # Conservative byte estimate with protocol overhead, not a guarantee
            # for unknown tokenizers or gateways that add unreported tokens.
            prompt_bound = len(bot_system_prompt(bot).encode('utf-8')) + sum(len(item['content'].encode('utf-8')) for item in history) + 1024 + 128*(len(history)+1)
            if prompt_bound > price['max_prompt_tokens']:
                raise HTTPException(400, 'Message and conversation exceed the configured prompt token safety bound for this profile.')
        try:
            reserve(c, job_id, bot_id, chosen_profile, now, attempts=len(entries))
        except BudgetError as exc: raise HTTPException(402, str(exc)) from exc
        c.execute('INSERT INTO runs VALUES (?,?,?,?,?)', (job_id,bot_id,'running',now,now))
        append_event(c, bot_id, job_id, 'run.started', {'status':'running'})
        record_event(c, job_id, 'bot.state_changed', {'state':'working'})
        message_id = str(uuid.uuid4())
        c.execute('INSERT INTO messages VALUES (?,?,?,?,?)',(message_id,bot_id,'user',content,now))
        append_event(c, bot_id, job_id, 'message.sent', {'message_id':message_id, 'role':'user', 'summary':content[:240]})
    job={'id':job_id,'bot_id':bot_id,'done':False,'created':time.time(),'notify':asyncio.Event(),'entries':entries,'max_completion_tokens':price['max_completion_tokens']}; jobs[job_id]=job
    job['task']=asyncio.create_task(run_chat(job,bot,history,body.profile or bot['profile']))
    def finish_unexpected(task):
        if not job['done']:
            user_stopped = task.cancelled() and job.get('user_cancelled', False)
            finish_run(job, 'cancelled' if user_stopped else 'failed', 'error', {'message':'Response stopped.' if user_stopped else 'The response ended unexpectedly. Please try again.'})
        # Retrieve the exception to avoid leaking arbitrary provider data in logs.
        if not task.cancelled(): task.exception()
    job['task'].add_done_callback(finish_unexpected)
    for k in list(jobs):
        if jobs[k]['done'] and jobs[k]['created'] < time.time()-3600: del jobs[k]
    return {'job_id':job_id}

@app.get('/api/bots/{bot_id}/latest-run')
def latest_run(bot_id: str, request: Request):
    require_auth(request)
    with db() as c:
        if not c.execute('SELECT 1 FROM bots WHERE id=?', (bot_id,)).fetchone():
            raise HTTPException(404, 'Bot not found.')
        row = c.execute('SELECT id,status FROM runs WHERE bot_id=? ORDER BY created_at DESC LIMIT 1', (bot_id,)).fetchone()
        if not row: return None
        result = dict(row)
        if result['status'] == 'failed':
            last_error = c.execute("SELECT payload FROM run_events WHERE run_id=? AND event_type='error' ORDER BY id DESC LIMIT 1", (row['id'],)).fetchone()
            result['message'] = json.loads(last_error['payload']).get('message','The last response failed.') if last_error else 'The last response failed.'
    return result

@app.get('/api/jobs/{job_id}/events')
async def job_events(job_id: str, request: Request, after: int = 0):
    require_auth(request)
    with db() as c:
        if not c.execute('SELECT 1 FROM runs WHERE id=?',(job_id,)).fetchone(): raise HTTPException(404,'Run not found.')
    async def stream():
        cursor=max(0,after)
        while True:
            current_job=jobs.get(job_id)
            if current_job: current_job['notify'].clear()
            with db() as c:
                c.execute('BEGIN')  # Events and status must share a read snapshot.
                rows=c.execute('SELECT id,event_type,payload FROM run_events WHERE run_id=? AND id>? ORDER BY id', (job_id,cursor)).fetchall()
                run=c.execute('SELECT status FROM runs WHERE id=?',(job_id,)).fetchone()
            for row in rows:
                cursor=row['id']
                yield 'data: '+json.dumps({'id':cursor,'type':row['event_type'], **json.loads(row['payload'])})+'\n\n'
            if not run or run['status'] not in ACTIVE_STATUSES: break
            if await request.is_disconnected(): break
            # Notification avoids polling. Heartbeats keep proxies alive.
            if not current_job:
                yield ': run unavailable on this worker\n\n'
                break
            try:
                await asyncio.wait_for(current_job['notify'].wait(), timeout=15)
            except asyncio.TimeoutError:
                yield ': keep-alive\n\n'
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.post('/api/jobs/{job_id}/stop')
async def stop_job(job_id: str, request: Request):
    require_auth(request)
    job=jobs.get(job_id)
    with db() as c:
        row=c.execute('SELECT status FROM runs WHERE id=?', (job_id,)).fetchone()
    if not row: raise HTTPException(404,'Run not found.')
    if row['status'] in ACTIVE_STATUSES and job and not job['done']:
        job['user_cancelled'] = True
        job['task'].cancel()
    return {'ok':True}

@app.get('/api/events', response_model=EventPage)
def account_events(request: Request, since: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500)):
    require_auth(request)
    with db() as c:
        rows = c.execute('SELECT id,bot_id,run_id,event_type,payload,created_at FROM events WHERE id>? ORDER BY id LIMIT ?', (since, limit)).fetchall()
    events = [row_to_event(row) for row in rows]
    return EventPage(events=events, next_cursor=events[-1].id if events else since)

@app.get('/api/team/overview')
def team_overview(request: Request, day_start: float = Query(ge=0), bot_id: str | None = None):
    """Counts and recent activity from the event log; day_start is local midnight in UTC seconds."""
    require_auth(request)
    if day_start > time.time() + 86400:
        raise HTTPException(400, 'Invalid day start.')
    with db() as c:
        count = c.execute('SELECT COUNT(*) FROM bots').fetchone()[0]
        runs = c.execute("SELECT COUNT(*) FROM events WHERE event_type='run.started' AND created_at>=?", (day_start,)).fetchone()[0]
        last = c.execute('SELECT MAX(created_at) FROM events').fetchone()[0]
        where = 'WHERE bot_id=?' if bot_id else ''
        rows = c.execute(f'SELECT id,bot_id,run_id,event_type,payload,created_at FROM events {where} ORDER BY id DESC LIMIT 12', (bot_id,) if bot_id else ()).fetchall()
        states = c.execute("""SELECT e.bot_id,e.payload FROM events e JOIN
                    (SELECT bot_id,MAX(id) id FROM events WHERE event_type='bot.state_changed' GROUP BY bot_id) latest
                    ON latest.id=e.id""").fetchall()
    keys = configured_secrets()
    events = []
    for row in rows:
        event = row_to_event(row).model_dump()
        for field in ('summary', 'message'):
            if field in event['payload']:
                event['payload'][field] = redact_text(event['payload'][field], keys)
        events.append(event)
    return {'bots':count,'runs_today':runs,'last_activity':last,'events':events,
            'states':{r['bot_id']:json.loads(r['payload'])['state'] for r in states if r['bot_id']}}


class BannerPlacement(BaseModel):
    x: float = Field(default=50, ge=0, le=100, allow_inf_nan=False)
    y: float = Field(default=50, ge=0, le=100, allow_inf_nan=False)
    zoom: float = Field(default=1, ge=1, le=3, allow_inf_nan=False)


@app.get('/api/settings/banner-placement')
def get_banner_placement(request: Request):
    require_auth(request)
    return BannerPlacement.model_validate_json(config('banner_placement', '{}')).model_dump()


@app.put('/api/settings/banner-placement')
def save_banner_placement(body: BannerPlacement, request: Request):
    require_auth(request)
    set_config('banner_placement', body.model_dump_json())
    return body.model_dump()


@app.get('/api/settings/banner')
def banner(request: Request):
    require_auth(request)
    path = DATA / 'banner.png'
    if not path.is_file(): raise HTTPException(404, 'No banner uploaded.')
    return FileResponse(path, media_type='image/png', headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


@app.put('/api/settings/banner')
async def upload_banner(request: Request, file: UploadFile = File(...)):
    require_auth(request)
    try:
        data = await file.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024: raise HTTPException(400, 'Banner must be 8 MB or smaller.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('PNG', 'JPEG', 'WEBP') or image.width * image.height > 16_000_000:
                    raise HTTPException(400, 'Choose a PNG, JPEG or WebP under 16 megapixels.')
                image.load()
                out = io.BytesIO()
                image.convert('RGB').save(out, format='PNG', optimize=True)
        tmp = DATA / ('banner-' + uuid.uuid4().hex + '.tmp')
        try:
            tmp.write_bytes(out.getvalue())
            os.replace(tmp, DATA / 'banner.png')
        finally:
            tmp.unlink(missing_ok=True)
        return {'ok':True}
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(400, 'Choose a valid image.') from exc
    finally:
        await file.close()


@app.delete('/api/settings/banner')
def remove_banner(request: Request):
    require_auth(request)
    (DATA / 'banner.png').unlink(missing_ok=True)
    return {'ok':True}


@app.get('/api/health')
def health(): return {'status':'ok'}
