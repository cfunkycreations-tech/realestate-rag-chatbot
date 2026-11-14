"""Funk Bot: local-first, single-user chat service."""
import asyncio
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
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
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def init_db():
    with db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bots (id TEXT PRIMARY KEY, name TEXT NOT NULL, title TEXT NOT NULL, personality TEXT NOT NULL, color TEXT NOT NULL, shape TEXT NOT NULL, profile TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS usage (id INTEGER PRIMARY KEY, bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL, gateway TEXT, model TEXT, prompt_tokens INTEGER, completion_tokens INTEGER, cost REAL, created_at REAL NOT NULL);
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

def redact(text):
    for gateway in json.loads(config('gateways','{}')).values():
        try:
            if gateway.get('key'):
                key = cipher.decrypt(gateway['key'].encode()).decode()
                if key: text = text.replace(key, '[redacted]')
        except Exception: pass
    return re.sub(r'(?i)\b(sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._-]{12,})', '[redacted]', text)

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
app = FastAPI(title='Funk Bot')
jobs = {}

class Password(BaseModel):
    password: str = Field(min_length=8, max_length=256)

@app.get('/api/auth/status')
def auth_status(request: Request):
    authenticated = True
    try: require_auth(request)
    except HTTPException: authenticated = False
    return {'setup': config('password_hash') is not None, 'authenticated': authenticated}

@app.post('/api/auth/setup')
def setup(body: Password, response: Response):
    # Atomic first-run initialization prevents a concurrent setup from replacing the password.
    with db() as c:
        try: c.execute('INSERT INTO config VALUES (?,?)', ('password_hash', ph.hash(body.password)))
        except sqlite3.IntegrityError: raise HTTPException(409, 'Setup is already complete.')
    response.set_cookie('funk_session', signer.dumps('owner'), httponly=True, samesite='strict', max_age=2592000, secure=os.getenv('FUNK_SECURE_COOKIE') == '1')
    return {'ok': True}

@app.post('/api/auth/login')
def login(body: Password, response: Response):
    stored = config('password_hash')
    try:
        if not stored or not ph.verify(stored, body.password): raise HTTPException(401, 'Incorrect password.')
    except (VerifyMismatchError, VerificationError): raise HTTPException(401, 'Incorrect password.')
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
    if any(j['bot_id']==bot_id and not j['done'] for j in jobs.values()): raise HTTPException(409, 'Wait for the current response before deleting this Bot.')
    with db() as c:
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

def event(job, kind, **values):
    job['events'].append({'type':kind, **values})

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
                            # Don't stream stored gateway keys even if a model echoes them.
                            content+=delta; emitted=True
                    if not content: raise ValueError('Gateway returned an empty response')
                    content=redact(content)
                    # Buffer before emitting to avoid leaking secrets split across stream chunks.
                    event(job,'delta',content=content)
                    with db() as c:
                        c.execute('INSERT INTO messages VALUES (?,?,?,?,?)',(str(uuid.uuid4()),bot['id'],'assistant',content,time.time()))
                        c.execute('INSERT INTO usage (bot_id,gateway,model,prompt_tokens,completion_tokens,cost,created_at) VALUES (?,?,?,?,?,?,?)',(bot['id'],entry['gateway'],entry['model'],usage.get('prompt_tokens',0),usage.get('completion_tokens',0),usage.get('cost'),time.time()))
                    event(job,'done'); job['done']=True; return
        except asyncio.CancelledError:
            event(job,'error',message='Response stopped.'); job['done']=True; return
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            # Only fail over on transient gateway errors or invalid/empty responses.
            status = exc.response.status_code if isinstance(exc,httpx.HTTPStatusError) else None
            if emitted or (status is not None and status not in (429,500,502,503,504)):
                break
    event(job,'error',message='Could not get a response from the configured models. Check gateway settings and try again.')
    job['done']=True

@app.post('/api/bots/{bot_id}/chat')
async def chat(bot_id: str, body: ChatIn, request: Request):
    require_auth(request)
    if any(j['bot_id']==bot_id and not j['done'] for j in jobs.values()): raise HTTPException(409,'This Bot is already responding.')
    with db() as c:
        row=c.execute('SELECT * FROM bots WHERE id=?',(bot_id,)).fetchone()
        if not row: raise HTTPException(404,'Bot not found.')
        bot=dict(row)
        c.execute('INSERT INTO messages VALUES (?,?,?,?,?)',(str(uuid.uuid4()),bot_id,'user',redact(body.content),time.time()))
        history=[{'role':r['role'],'content':r['content']} for r in c.execute('SELECT role,content FROM messages WHERE bot_id=? ORDER BY created_at DESC LIMIT 40',(bot_id,)).fetchall()][::-1]
    job_id=str(uuid.uuid4()); job={'bot_id':bot_id,'events':[],'done':False,'created':time.time()}; jobs[job_id]=job
    job['task']=asyncio.create_task(run_chat(job,bot,history,body.profile or bot['profile']))
    def finish_unexpected(task):
        # Cancellation before the coroutine starts, or any unexpected error,
        # must not leave the roster permanently busy. Do not expose exceptions.
        if not job['done']:
            event(job, 'error', message='Response stopped.' if task.cancelled() else 'The response failed unexpectedly. Please try again.')
            job['done'] = True
    job['task'].add_done_callback(finish_unexpected)
    # Limit retained completed jobs without disturbing active work.
    for k in list(jobs):
        if jobs[k]['done'] and jobs[k]['created'] < time.time()-3600: del jobs[k]
    return {'job_id':job_id}

@app.get('/api/jobs/{job_id}/events')
async def job_events(job_id: str, request: Request):
    require_auth(request)
    job=jobs.get(job_id)
    if not job: raise HTTPException(404,'Run not found.')
    async def stream():
        index=0
        while True:
            while index < len(job['events']):
                yield 'data: '+json.dumps(job['events'][index])+'\n\n'; index+=1
            if job['done']: break
            if await request.is_disconnected(): break
            await asyncio.sleep(.2)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.post('/api/jobs/{job_id}/stop')
def stop_job(job_id: str, request: Request):
    require_auth(request)
    job=jobs.get(job_id)
    if not job: raise HTTPException(404,'Run not found.')
    if not job['done']: job['task'].cancel()
    return {'ok':True}

@app.get('/api/health')
def health(): return {'status':'ok'}
