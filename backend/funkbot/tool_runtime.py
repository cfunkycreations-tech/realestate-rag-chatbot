"""Audited tool execution for a live run, independent of the model adapter."""
import asyncio
import json
from dataclasses import dataclass, field
from typing import Callable

from . import tool_audit, tools


@dataclass
class ToolContext:
    db: Callable
    data_dir: object
    run_id: str
    bot_id: str
    redact: Callable[[str], str]
    allow: list[str]
    deny: list[str]
    notify: Callable[[dict], None]
    # The broader approval is deliberately run-scoped, not permanent.
    run_grants: set[str] = field(default_factory=set)


def live(c, context):
    row=c.execute('SELECT status,bot_id FROM runs WHERE id=?',(context.run_id,)).fetchone()
    if not row or row['bot_id'] != context.bot_id or row['status'] not in ('running','waiting_approval'):
        raise tools.ToolError('The Bot run is no longer active.')


async def execute(context: ToolContext, name: str, args: dict, wait_decision):
    """Propose, obtain permission, then execute the exact displayed arguments.

    wait_decision is an async callback returning approve, approve_once, or deny.
    Each write is surfaced in notify even when an earlier run-scoped grant is
    used. The caller is responsible for forwarding notifications to the UI.
    """
    with context.db() as c:
        c.execute('BEGIN IMMEDIATE');live(c,context)
        call=tool_audit.propose(c,context.run_id,context.bot_id,name,args,context.redact)
        row=dict(c.execute('SELECT * FROM tool_calls WHERE id=?',(call,)).fetchone())
    try:
        context.notify({'type':'tool.proposed','call_id':call,'tool':name,'risk':row['risk'],'arguments':json.loads(row['arguments']),'status':row['status']})
        if row['status']=='pending':
            granted=name in context.run_grants
            decision='run_grant' if granted else await wait_decision(call)
            with context.db() as c:
                c.execute('BEGIN IMMEDIATE');live(c,context)
                if granted:
                    tool_audit.approve_from_run_grant(c,call);status='approved'
                else:
                    status=tool_audit.decide(c,call,decision)
            if not granted and decision=='approve': context.run_grants.add(name)
            context.notify({'type':'tool.decision','call_id':call,'decision':decision,'status':status})
            if status=='denied': return {'status':'denied','message':'The owner denied this tool call.'}
        with context.db() as c:
            c.execute('BEGIN IMMEDIATE');live(c,context);row=tool_audit.claim(c,call)
        safe_args=json.loads(row['arguments'])
        try:
            if name=='web_fetch': result=await tools.web_fetch(tools.WebFetchArgs.model_validate(safe_args),context.allow,context.deny)
            elif name=='write_note': result=tools.write_note(context.data_dir,context.bot_id,tools.NotesArgs.model_validate(safe_args))
            else: raise tools.ToolError('Unknown tool.')
            success=True
        except tools.ToolError as exc:
            result={'error':str(exc)};success=False
        with context.db() as c:
            c.execute('BEGIN IMMEDIATE');tool_audit.finish(c,call,result,success,context.redact)
            stored=json.loads(c.execute('SELECT result FROM tool_calls WHERE id=?',(call,)).fetchone()['result'])
        context.notify({'type':'tool.finished','call_id':call,'status':'completed' if success else 'failed','result':stored})
        return {'status':'completed' if success else 'failed','result':stored}
    except (asyncio.CancelledError, Exception):
        # A call in progress is never automatically replayed after interruption.
        with context.db() as c:
            c.execute('BEGIN IMMEDIATE')
            tool_audit.abort(c,call,'Interrupted; outcome may be unknown.',context.redact)
        raise
