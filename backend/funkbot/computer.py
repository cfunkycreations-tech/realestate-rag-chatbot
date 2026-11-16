"""Client for the optional isolated, single-use computer worker.

Commands never run in the backend. Only validated, bounded data snapshots cross
into and out of the worker; a transaction persists one snapshot per Bot.
"""
import asyncio
import base64
import binascii
import json
import os
import time

from . import computer_snapshot as snapshots
from .tools import ToolError

SOCKET='/computer-control/computer.sock'
KILL_SOCKET='/computer-control/computer-kill.sock'
MAX_STORED=50 * 1024 * 1024
_lock=asyncio.Lock()  # single backend worker only
_active=None
_channel=None
_frame=None
_last_input=0.0


def enabled(): return os.environ.get('FUNK_COMPUTER_ENABLED')=='1'

def desktop_enabled(): return enabled() and os.environ.get('FUNK_COMPUTER_DESKTOP_ENABLED')=='1'

def frame(run_id):
    return _frame if _active and _active['run_id']==run_id and desktop_enabled() else None

async def send_input(run_id,event):
    global _last_input
    if not desktop_enabled() or not _active or _active['run_id']!=run_id or _channel is None or _frame is None: raise ToolError('No matching live desktop frame.')
    now=time.monotonic()
    if now-_last_input<.1: raise ToolError('Desktop input is too frequent.')
    _last_input=now
    try:
        if _active.get('mode')=='session':
            if not _active.get('takeover'): raise ToolError('Take over the desktop before sending input.')
            event={'type':'owner_input','event':event}
        _channel.write(json.dumps(event,separators=(',',':')).encode()+b'\n')
        await _channel.drain()
    except (OSError,ConnectionError): raise ToolError('Desktop connection closed.') from None


def active_info():
    return dict(_active) if _active else None


def permission(c,bot_id):
    row=c.execute('SELECT allowed,revision FROM computer_permissions WHERE bot_id=?',(bot_id,)).fetchone()
    return {'allowed':bool(row['allowed']),'revision':row['revision']} if row else {'allowed':False,'revision':0}


def check_live(context,expected_revision):
    with context.db() as c:
        row=c.execute('SELECT status,bot_id FROM runs WHERE id=?',(context.run_id,)).fetchone()
        grant=permission(c,context.bot_id)
        if not enabled() or not grant['allowed'] or grant['revision']!=expected_revision or not row or row['bot_id']!=context.bot_id or row['status'] not in ('running','waiting_approval') or context.policy_for(c,'computer_shell','write')=='deny':
            raise ToolError('Computer command blocked: the run, sandbox or policy changed.')


def read_workspace(c,bot_id):
    row=c.execute('SELECT snapshot FROM computer_workspaces WHERE bot_id=?',(bot_id,)).fetchone()
    if not row: return {'dirs':[],'files':{}}
    try:
        if len(row['snapshot'])>snapshots.MAX_JSON: raise ValueError()
        return snapshots.validate(json.loads(row['snapshot']))
    except (ValueError,RecursionError) as exc: raise ToolError('Saved computer workspace is invalid; it was not changed.') from exc


def persist_workspace(c,bot_id,workspace):
    try:
        encoded=json.dumps(snapshots.validate(workspace),ensure_ascii=True,separators=(',',':'))
        if len(encoded)>snapshots.MAX_JSON: raise ValueError()
    except (ValueError,RecursionError) as exc: raise ToolError('Invalid computer workspace; previous workspace retained.') from exc
    used=c.execute('SELECT COALESCE(SUM(length(snapshot)),0) FROM computer_workspaces WHERE bot_id<>?',(bot_id,)).fetchone()[0]
    if used+len(encoded)>MAX_STORED: raise ToolError('Total computer workspace limit reached; previous workspace retained.')
    c.execute('INSERT INTO computer_workspaces(bot_id,snapshot,updated_at) VALUES (?,?,?) ON CONFLICT(bot_id) DO UPDATE SET snapshot=excluded.snapshot,updated_at=excluded.updated_at',(bot_id,encoded,time.time()))


def load_workspace(context):
    with context.db() as c: return read_workspace(c,context.bot_id)


def save_workspace(context,workspace):
    with context.db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT status,bot_id FROM runs WHERE id=?',(context.run_id,)).fetchone()
        if not row or row['bot_id']!=context.bot_id or row['status'] not in ('running','waiting_approval'):
            raise ToolError('Run stopped; previous computer workspace retained.')
        persist_workspace(c,context.bot_id,workspace)


async def ready_connection():
    # Restart after each command may leave a stale socket. Retrying a handshake
    # is safe only before sending a command; after send, never retry automatically.
    deadline=asyncio.get_running_loop().time()+12
    while True:
        writer=None
        try:
            reader,writer=await asyncio.wait_for(asyncio.open_unix_connection(SOCKET,limit=snapshots.MAX_JSON+100000),2)
            greeting=await asyncio.wait_for(reader.readline(),2)
            if greeting!=b'{"ready":1}\n': raise ValueError('Worker not ready')
            return reader,writer
        except (OSError,TimeoutError,ValueError):
            if writer:
                writer.close()
                try: await writer.wait_closed()
                except OSError: pass
            if asyncio.get_running_loop().time()>=deadline: raise ToolError('Computer sandbox is unavailable; no command was sent.') from None
            await asyncio.sleep(.15)


async def execute(context,command,expected_revision):
    global _active,_channel,_frame,_last_input
    if not enabled(): raise ToolError('Computer sandbox is disabled.')
    # Never queue accepted actions behind another Bot's command: policy and run
    # state remain easy to reason about and snapshots cannot overwrite each other.
    if _lock.locked(): raise ToolError('Computer sandbox is busy; no command was sent.')
    async with _lock:
        _active={'run_id':context.run_id,'bot_id':context.bot_id}
        _frame=None;_last_input=0.0
        writer=None;sent=False
        try:
            workspace=load_workspace(context)
            async with asyncio.timeout(50):
                reader,writer=await ready_connection()
                check_live(context,expected_revision)
                desktop=desktop_enabled()
                payload={'command':command,'workspace':workspace}
                if desktop: payload['desktop']=True
                request=json.dumps(payload,ensure_ascii=True,separators=(',',':')).encode()+b'\n'
                sent=True
                writer.write(request);await writer.drain()
                if desktop: _channel=writer
                while True:
                    data=await reader.readline()
                    if not data or len(data)>snapshots.MAX_JSON+100000: raise ValueError('Invalid response')
                    result=json.loads(data)
                    if desktop and isinstance(result,dict) and set(result)=={'frame'}:
                        try:
                            image=base64.b64decode(result['frame'],validate=True)
                            if len(image)>1024*1024 or not image.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('Invalid frame')
                        except (ValueError,TypeError,binascii.Error): raise ValueError('Invalid frame') from None
                        _frame=image
                        continue
                    break
                if not isinstance(result,dict) or 'error' in result: raise ValueError('Worker failed')
                if set(result)!={'output','truncated','exit_code','timed_out','workspace'} or not isinstance(result['output'],str) or len(result['output'])>16384 or type(result['truncated']) is not bool or type(result['timed_out']) is not bool or type(result['exit_code']) is not int: raise ValueError('Invalid response')
                save_workspace(context,result.pop('workspace'))
                return result
        except ToolError as exc:
            if sent: raise ToolError('Computer workspace could not be saved; the command may have run and the previous workspace was retained. Do not retry without review.') from exc
            raise
        except (OSError,TimeoutError,ValueError,UnicodeError,RecursionError) as exc:
            message='Computer sandbox interrupted or workspace could not be saved; the command may have run and the previous workspace is retained. Do not retry without review.' if sent else 'Computer sandbox unavailable; no command was sent.'
            raise ToolError(message) from exc
        finally:
            if writer: writer.close()
            _active=None;_channel=None;_frame=None
            if writer:
                try: await writer.wait_closed()
                except OSError: pass


# One desktop session per backend process; its connection owns the worker until
# close/timeout. The same lock excludes legacy shell commands and other Bots.
_session=None
_session_start_lock=asyncio.Lock()
_ended_sessions=set()


def _decode_frame(value):
    try:
        image=base64.b64decode(value,validate=True)
        if len(image)>1024*1024 or not image.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError()
        return image
    except (ValueError,TypeError,binascii.Error): raise ToolError('Invalid desktop frame.') from None


class DesktopSession:
    def __init__(self,context,revision,reader,writer):
        self.context=context;self.revision=revision;self.reader=reader;self.writer=writer
        self.domains={}
        self.pending={};self.operation=asyncio.Lock();self.available=asyncio.Event();self.available.set()
        self.closed=asyncio.Event();self.task=None

    async def read(self):
        global _active,_channel,_frame,_session
        try:
            while True:
                line=await self.reader.readline()
                if not line or len(line)>snapshots.MAX_JSON+100000: raise ToolError('Desktop session disconnected.')
                message=json.loads(line)
                if not isinstance(message,dict): raise ToolError('Invalid desktop response.')
                if set(message)=={'frame'}:
                    _frame=_decode_frame(message['frame']);continue
                if message.get('session')=='ended':
                    with self.context.db() as c:
                        c.execute('BEGIN IMMEDIATE')
                        row=c.execute('SELECT status,bot_id FROM runs WHERE id=?',(self.context.run_id,)).fetchone()
                        grant=permission(c,self.context.bot_id)
                        if row and row['bot_id']==self.context.bot_id and row['status'] in ('running','waiting_approval','done') and grant['allowed'] and grant['revision']==self.revision:
                            persist_workspace(c,self.context.bot_id,message['workspace'])
                    break
                if 'id' in message:
                    if 'frame' in message: _frame=_decode_frame(message['frame'])
                    future=self.pending.pop(message['id'],None)
                    if future and not future.done(): future.set_result(message)
                    continue
                raise ToolError('Desktop session failed; an action may have run.')
        except (OSError,ValueError,KeyError,TypeError,ToolError,asyncio.CancelledError):
            pass
        finally:
            for future in self.pending.values():
                if not future.done(): future.set_exception(ToolError('Desktop session ended; an action may have run.'))
            self.pending.clear();self.available.set();self.closed.set()
            from . import browser_network
            browser_network.revoke()
            self.writer.close()
            _ended_sessions.add(self.context.run_id)
            if _session is self:
                _session=None;_active=None;_channel=None;_frame=None
                _lock.release()

    async def request(self,body):
        import uuid
        identifier=uuid.uuid4().hex
        future=asyncio.get_running_loop().create_future();self.pending[identifier]=future
        try:
            self.writer.write(json.dumps({**body,'id':identifier},ensure_ascii=True,separators=(',',':')).encode()+b'\n')
            await self.writer.drain()
            async with asyncio.timeout(25): return await future
        except (OSError,TimeoutError):
            self.writer.close()
            raise ToolError('Desktop request interrupted; the action may have run.') from None
        finally: self.pending.pop(identifier,None)

    async def action(self,action,approved_host="",domain_revision=0):
        while True:
            await self.available.wait()
            async with self.operation:
                if self.closed.is_set(): raise ToolError('Desktop session ended.')
                if not self.available.is_set(): continue
                check_live(self.context,self.revision)
                if approved_host:
                    from . import browser_network
                    with self.context.db() as c:
                        p=browser_network.policy(c)
                        if not browser_network.enabled() or p['revision']!=domain_revision or approved_host not in p['domains'] or browser_network.target(action.get('url'))!=approved_host: raise ToolError('Browser domain permission changed.')
                    self.domains[approved_host]=domain_revision
                response=await self.request({'type':'action','action':action})
                if 'frame' not in response: raise ToolError('Action may have run, but no screenshot was returned.')
                result=response.get('result',{}) if response.get('ok') else {'error':str(response.get('error','Desktop action failed.'))[:1000]}
                return result,_decode_frame(response['frame'])

    async def takeover(self,enabled):
        async with self.operation:
            if self.closed.is_set(): raise ToolError('Desktop session ended.')
            check_live(self.context,self.revision)
            response=await self.request({'type':'takeover','enabled':enabled})
            if not response.get('ok') or response.get('takeover') is not enabled: raise ToolError('Could not change desktop control.')
            if enabled: self.available.clear()
            else: self.available.set()
            if _active and _active['run_id']==self.context.run_id: _active['takeover']=enabled


async def get_session(context,revision):
    global _active,_channel,_frame,_session
    if not desktop_enabled(): raise ToolError('Desktop sessions are disabled.')
    async with _session_start_lock:
        if _session and _session.context.run_id==context.run_id:
            if _session.revision!=revision: raise ToolError('Computer permission changed.')
            return _session
        if context.run_id in _ended_sessions: raise ToolError('This desktop session ended; start a new Bot response.')
        if _lock.locked(): raise ToolError('Computer sandbox is busy.')
        await _lock.acquire();writer=None
        try:
            _active={'run_id':context.run_id,'bot_id':context.bot_id,'mode':'session','takeover':False}
            _frame=None
            workspace=load_workspace(context)
            reader,writer=await ready_connection();check_live(context,revision)
            writer.write(json.dumps({'mode':'session','workspace':workspace},separators=(',',':')).encode()+b'\n');await writer.drain()
            line=await asyncio.wait_for(reader.readline(),30)
            if json.loads(line)!= {'session':'started'}: raise ToolError('Desktop session could not start.')
            session=DesktopSession(context,revision,reader,writer);_session=session;_channel=writer
            session.task=asyncio.create_task(session.read())
            return session
        except BaseException as exc:
            if writer: writer.close()
            _ended_sessions.add(context.run_id)
            _active=None;_channel=None;_frame=None;_lock.release()
            if isinstance(exc,(OSError,TimeoutError,ValueError)): raise ToolError('Desktop session failed to start.') from exc
            raise


async def desktop_action(context,revision,action,approved_host="",domain_revision=0):
    session=await get_session(context,revision)
    return await session.action(action,approved_host,domain_revision)


async def set_takeover(run_id,enabled):
    if not _session or _session.context.run_id!=run_id: raise ToolError('No matching desktop session.')
    await _session.takeover(enabled)


async def end_session(run_id,graceful):
    session=_session
    if session and session.context.run_id==run_id:
        if graceful:
            try:
                session.writer.write(b'{"type":"close"}\n');await session.writer.drain()
                await asyncio.wait_for(session.closed.wait(),10)
            except (OSError,TimeoutError): session.writer.close()
        else: session.writer.close()
        if not session.closed.is_set():
            try: await asyncio.wait_for(session.closed.wait(),3)
            except TimeoutError: session.task.cancel()
    _ended_sessions.discard(run_id)


async def request_container_kill():
    writer=None
    try:
        _,writer=await asyncio.wait_for(asyncio.open_unix_connection(KILL_SOCKET),2)
        writer.write(b'kill\n');await writer.drain()
        return True
    except (OSError,TimeoutError): return False
    finally:
        if writer: writer.close()
