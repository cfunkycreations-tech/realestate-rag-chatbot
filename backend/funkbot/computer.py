"""Client for the optional isolated, single-use computer worker.

Commands never run in the backend. Only validated, bounded data snapshots cross
into and out of the worker; a transaction persists one snapshot per Bot.
"""
import asyncio
import json
import os
import time

from . import computer_snapshot as snapshots
from .tools import ToolError

SOCKET='/computer-control/computer.sock'
MAX_STORED=50 * 1024 * 1024
_lock=asyncio.Lock()  # single backend worker only
_active=None


def enabled(): return os.environ.get('FUNK_COMPUTER_ENABLED')=='1'


def active_info():
    return dict(_active) if _active else None


def check_live(context):
    with context.db() as c:
        row=c.execute('SELECT status,bot_id FROM runs WHERE id=?',(context.run_id,)).fetchone()
        if not enabled() or not row or row['bot_id']!=context.bot_id or row['status'] not in ('running','waiting_approval') or context.policy_for(c,'computer_shell','write')=='deny':
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


async def execute(context,command):
    global _active
    if not enabled(): raise ToolError('Computer sandbox is disabled.')
    # Never queue accepted actions behind another Bot's command: policy and run
    # state remain easy to reason about and snapshots cannot overwrite each other.
    if _lock.locked(): raise ToolError('Computer sandbox is busy; no command was sent.')
    async with _lock:
        _active={'run_id':context.run_id,'bot_id':context.bot_id}
        writer=None;sent=False
        try:
            workspace=load_workspace(context)
            async with asyncio.timeout(50):
                reader,writer=await ready_connection()
                check_live(context)
                request=json.dumps({'command':command,'workspace':workspace},ensure_ascii=True,separators=(',',':')).encode()+b'\n'
                sent=True
                writer.write(request);await writer.drain()
                data=await reader.readline()
                if not data or len(data)>snapshots.MAX_JSON+100000: raise ValueError('Invalid response')
                result=json.loads(data)
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
            _active=None
            if writer:
                try: await writer.wait_closed()
                except OSError: pass
