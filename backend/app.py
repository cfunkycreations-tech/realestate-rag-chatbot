"""Funk Bot: local-first, single-user chat service."""
import asyncio
import json
import logging
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from funkbot.auth_security import ensure_setup_token, lockout_seconds
from funkbot.redaction import SlidingRedactor, redact_text

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

@contextmanager
def db():
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def init_db():
    with db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bots (id TEXT PRIMARY KEY, name TEXT NOT NULL, title TEXT NOT NULL, personality TEXT NOT NULL, color TEXT NOT NULL, shape TEXT NOT NULL, profile TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS usage (id INTEGER PRIMARY KEY, bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL, gateway TEXT, model TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, cost REAL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS login_guard (id INTEGER PRIMARY KEY CHECK (id=1), failures INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0);
        INSERT OR IGNORE INTO login_guard (id) VALUES (1);
        CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE, status TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_run_per_bot ON runs(bot_id) WHERE status IN ('queued', 'running', 'waiting_approval');
        CREATE TABLE IF NOT EXISTS run_events (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE, event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS run_events_order ON run_events(run_id, id);
        ''')
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
        except sqlite3.IntegrityError: raise HTTPException(409, 'Setup is already complete.')
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
    name: str = Field(min_length=1,max_length=60)
    title: str = Field(default='Personal assistant', max_length=100)
    personality: str = Field(default='You are a helpful, thoughtful personal assistant.', max_length=6000)
    color: str = Field(default='lavender', pattern='^(lavender|peach|mint|blue|yellow)$')
    shape: str = Field(default='round', pattern='^(round|square|cloud)$')
    profile: str = Field(default='smart', pattern='^(fast|smart|thinker|vision|cheap-bulk)$')

@app.get('/api/bots')
def bots(request: Request):
    require_auth(request)
    with db() as c:
        rows = c.execute('''SELECT b.*, (SELECT content FROM messages m WHERE m.bot_id=b.id ORDER BY created_at DESC LIMIT 1) as latest FROM bots b ORDER BY b.created_at''').fetchall()
    return [dict(r) for r in rows]

@app.post('/api/bots')
def create_bot(body: BotIn, request: Request):
    require_auth(request)
    with db() as c:
        if c.execute('SELECT COUNT(*) FROM bots').fetchone()[0] >= 50: raise HTTPException(400, 'You can have up to 50 Bots.')
        id = str(uuid.uuid4())
        c.execute('INSERT INTO bots VALUES (?,?,?,?,?,?,?,?)',(id,redact(body.name.strip()),redact(body.title.strip()),redact(body.personality),body.color,body.shape,body.profile,time.time()))
    return {'id':id}

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
        if not c.execute('DELETE FROM bots WHERE id=?',(bot_id,)).rowcount: raise HTTPException(404,'Bot not found.')
    return {'ok':True}

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

class ChatIn(BaseModel):
    content: str = Field(min_length=1,max_length=20000)
    profile: str | None = Field(default=None, pattern='^(fast|smart|thinker|vision|cheap-bulk)$')

ACTIVE_STATUSES = ('queued', 'running', 'waiting_approval')

def record_event(c, run_id, kind, values):
    c.execute('INSERT INTO run_events (run_id,event_type,payload,created_at) VALUES (?,?,?,?)',
              (run_id, kind, json.dumps(values), time.time()))

def mark_interrupted_runs():
    # This server runs one worker. A restart cannot resume an HTTP model stream;
    # mark incomplete runs failed rather than silently losing them.
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        rows = c.execute("SELECT id FROM runs WHERE status IN ('queued','running','waiting_approval')").fetchall()
        for row in rows:
            record_event(c, row['id'], 'bot.state_changed', {'state':'error'})
            record_event(c, row['id'], 'error', {'message':'The backend restarted before this response finished. Please try again.'})
            c.execute("UPDATE runs SET status='failed', updated_at=? WHERE id=?", (time.time(), row['id']))

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
            c.execute('INSERT INTO messages VALUES (?,?,?,?,?)', (str(uuid.uuid4()), bot_id, 'assistant', content, time.time()))
            c.execute('INSERT INTO usage (bot_id,gateway,model,prompt_tokens,completion_tokens,cost,created_at) VALUES (?,?,?,?,?,?,?)',
                      (bot_id, gateway, model, usage.get('prompt_tokens',0), usage.get('completion_tokens',0), usage.get('cost'), time.time()))
        record_event(c, job['id'], 'bot.state_changed', {'state':'done' if status == 'done' else 'error' if status == 'failed' else 'idle'})
        record_event(c, job['id'], kind, values)
        c.execute('UPDATE runs SET status=?,updated_at=? WHERE id=?', (status, time.time(), job['id']))
    job['done'] = True
    job['notify'].set()

async def run_chat(job, bot, history, profile):
    entries=json.loads(config('profiles')).get(profile,[])
    for entry in entries:
        emitted=False
        try:
            url, headers=gateway_config(entry['gateway'])
            payload={'model':entry['model'], 'messages':[{'role':'system','content':bot['personality']+'\nYou are '+bot['name']+'.'}, *history], 'stream':True, 'stream_options':{'include_usage':True}}
            async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=10), follow_redirects=False) as client:
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
            # Only fail over on transient gateway errors or invalid/empty responses.
            status = exc.response.status_code if isinstance(exc,httpx.HTTPStatusError) else None
            if emitted or (status is not None and status not in (429,500,502,503,504)):
                break
    finish_run(job, 'failed', 'error', {'message':'Could not get a response from the configured models. Check gateway settings and try again.'})

@app.post('/api/bots/{bot_id}/chat')
async def chat(bot_id: str, body: ChatIn, request: Request):
    require_auth(request)
    # Compute redaction before acquiring the write lock: redact reads config.
    content = redact(body.content)
    job_id = str(uuid.uuid4())
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM bots WHERE id=?',(bot_id,)).fetchone()
        if not row: raise HTTPException(404,'Bot not found.')
        if c.execute("SELECT 1 FROM runs WHERE bot_id=? AND status IN ('queued','running','waiting_approval')", (bot_id,)).fetchone():
            raise HTTPException(409,'This Bot is already responding.')
        bot=dict(row); now=time.time()
        c.execute('INSERT INTO runs VALUES (?,?,?,?,?)', (job_id,bot_id,'running',now,now))
        record_event(c, job_id, 'bot.state_changed', {'state':'working'})
        c.execute('INSERT INTO messages VALUES (?,?,?,?,?)',(str(uuid.uuid4()),bot_id,'user',content,now))
        history=[{'role':r['role'],'content':r['content']} for r in c.execute('SELECT role,content FROM messages WHERE bot_id=? ORDER BY created_at DESC LIMIT 40',(bot_id,)).fetchall()][::-1]
    job={'id':job_id,'bot_id':bot_id,'done':False,'created':time.time(),'notify':asyncio.Event()}; jobs[job_id]=job
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

@app.get('/api/health')
def health(): return {'status':'ok'}
