"""Audited tool execution for a live run, independent of the model adapter."""
import asyncio
import json
import time
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Callable

from . import tool_audit, tools, computer, browser_network


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
    policy_for: Callable = lambda c,name,risk: 'auto' if risk=='read' else 'ask'
    connector_info: Callable = lambda c,connector_id: None
    connector_call: Callable = None
    handoff_catalog: dict = field(default_factory=dict)
    handoff_call: Callable = None
    mission_id: str | None = None
    artifact_call: Callable = None
    artifact_review: Callable = None
    gateway_entries: list = field(default_factory=list)
    destination_snapshot: Callable = None
    search_info: Callable = lambda c: None
    approved_destinations: list | None = None
    vision: bool = False
    desktop_observation_revision: int | None = None


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
        spec=tools.REGISTRY.get(name)
        if not spec: raise tools.ToolError('Unknown tool.')
        policy=context.policy_for(c,name,spec.risk)
        connector=None
        desktop_stale=False
        if name in ('computer_shell','computer_action'):
            parsed=(tools.ComputerArgs if name=='computer_shell' else tools.ComputerActionArgs).model_validate(args)
            grant=computer.permission(c,context.bot_id)
            args={**parsed.model_dump(exclude_none=True),'permission_revision':grant['revision']}
            if not computer.enabled() or not grant['allowed'] or (name=='computer_action' and (not computer.desktop_enabled() or not context.vision)): policy='deny'
            if context.policy_for(c,'computer_shell','write')=='deny': policy='deny'
            if name=='computer_action':
                domain_policy=browser_network.policy(c);host=''
                if parsed.type=='open_url' and not (parsed.url=='about:blank' or parsed.url.startswith('file:')):
                    try: host=browser_network.target(parsed.url)
                    except tools.ToolError: policy='deny'
                    if not browser_network.enabled() or host not in domain_policy['domains']: policy='deny'
                state=computer.desktop_control_state(context.run_id)
                control_revision=state['revision'] if state else 0
                desktop_stale=bool(state and context.desktop_observation_revision is not None and context.desktop_observation_revision!=control_revision and parsed.type!='screenshot')
                if desktop_stale: policy='deny'
                args.update({'approved_host':host,'domain_revision':domain_policy['revision'],'control_revision':control_revision})
        if name=='mcp_call':
            parsed=tools.McpCallArgs.model_validate(args)
            try: arguments=json.loads(parsed.arguments_json)
            except (ValueError,RecursionError) as exc: raise tools.ToolError('Connector arguments must be a JSON object.') from exc
            if not isinstance(arguments,dict): raise tools.ToolError('Connector arguments must be a JSON object.')
            arguments=tool_audit._redact_result(arguments,context.redact)
            connector=context.connector_info(c,parsed.connector_id)
            args={**parsed.model_dump(),'arguments_json':json.dumps(arguments,ensure_ascii=False),'endpoint':connector['url'] if connector else '', 'connector_revision':connector['revision'] if connector else ''}
            if not connector or not connector.get('enabled') or parsed.tool_name not in connector.get('allowed_tools',[]): policy='deny'
        if name=='web_search':
            parsed=tools.WebSearchArgs.model_validate(args)
            endpoint=context.search_info(c)
            args={'query':parsed.query.strip(),'endpoint':endpoint or ''}
            if not endpoint or not parsed.query.strip(): policy='deny'
        if name=='read_work_file':
            parsed=tools.ReadWorkFileArgs.model_validate(args)
            try:
                if not context.mission_id or not context.artifact_review: raise tools.ToolError('Mission file access is unavailable.')
                review=context.artifact_review(c,context,parsed)
                review=tool_audit._redact_result(review,context.redact)
                reviewed=context.redact(json.dumps(review,ensure_ascii=False))
                if len(reviewed)>32000: raise tools.ToolError('File review is too large.')
                try: json.loads(reviewed)
                except (ValueError,RecursionError): raise tools.ToolError('File review could not be safely encoded.') from None
                args={**parsed.model_dump(),'review_json':reviewed}
            except tools.ToolError:
                args={**parsed.model_dump(),'review_json':''};policy='deny'
        if name=='attach_mission_result':
            parsed=tools.MissionArtifactArgs.model_validate(args)
            args={**parsed.model_dump(),'name':parsed.name.strip()}
            if not context.mission_id or not context.artifact_call: policy='deny'
        if name=='create_handoff':
            parsed=tools.HandoffArgs.model_validate(args)
            receiver=c.execute('SELECT name FROM bots WHERE id=?',(parsed.to_bot_id,)).fetchone()
            expected=context.handoff_catalog.get(parsed.to_bot_id)
            args={'receiver_name':expected or '',**{k:v for k,v in parsed.model_dump().items() if k!='receiver_name'}}
            if not receiver or not expected or context.redact(receiver['name'])!=expected or parsed.to_bot_id==context.bot_id: policy='deny'
        call=tool_audit.propose(c,context.run_id,context.bot_id,name,args,context.redact,policy=policy)
        row=dict(c.execute('SELECT * FROM tool_calls WHERE id=?',(call,)).fetchone())
    try:
        context.notify({'type':'tool.proposed','call_id':call,'tool':name,'risk':row['risk'],'arguments':json.loads(row['arguments']),'status':row['status']})
        if row['status']=='denied':
            context.notify({'type':'tool.decision','call_id':call,'decision':'policy_denied','status':'denied'})
            return {'status':'denied','message':'Owner control changed since the last screenshot. Request a new screenshot after hand back before another action.' if desktop_stale else 'The owner tool policy denied this call.'}
        if row['status']=='pending':
            granted=name not in ('mcp_call','create_handoff','attach_mission_result','read_work_file','web_search','computer_shell','computer_action') and name in context.run_grants
            decision='run_grant' if granted else await wait_decision(call)
            with context.db() as c:
                c.execute('BEGIN IMMEDIATE');live(c,context)
                if context.policy_for(c,name,row['risk'])=='deny':
                    tool_audit.deny_policy_change(c,call);status='denied';decision='policy_denied';granted=True
                elif granted:
                    tool_audit.approve_from_run_grant(c,call);status='approved'
                else:
                    status=tool_audit.decide(c,call,decision)
            if not granted and decision=='approve' and name not in ('mcp_call','create_handoff','attach_mission_result','read_work_file','web_search','computer_shell','computer_action'): context.run_grants.add(name)
            context.notify({'type':'tool.decision','call_id':call,'decision':decision,'status':status})
            if status=='denied': return {'status':'denied','message':'The owner denied this tool call.'}
        with context.db() as c:
            c.execute('BEGIN IMMEDIATE');live(c,context)
            current=context.policy_for(c,name,row['risk'])
            if name in ('computer_shell','computer_action'):
                grant=computer.permission(c,context.bot_id);reviewed=json.loads(row['arguments'])
                if not computer.enabled() or not grant['allowed'] or grant['revision']!=reviewed['permission_revision'] or context.policy_for(c,'computer_shell','write')=='deny' or (name=='computer_action' and (not computer.desktop_enabled() or not context.vision)): current='deny'
                if name=='computer_action':
                    state=computer.desktop_control_state(context.run_id)
                    if state and state['revision']!=reviewed['control_revision']: current='deny'
                if name=='computer_action' and reviewed['approved_host']:
                    domains=browser_network.policy(c)
                    if not browser_network.enabled() or domains['revision']!=reviewed['domain_revision'] or reviewed['approved_host'] not in domains['domains']: current='deny'
            if name=='mcp_call':
                reviewed=json.loads(row['arguments']);latest=context.connector_info(c,reviewed['connector_id'])
                if not latest or not latest.get('enabled') or reviewed['tool_name'] not in latest.get('allowed_tools',[]) or latest.get('revision')!=reviewed['connector_revision'] or latest.get('url')!=reviewed['endpoint']: current='deny'
                connector=latest
            if name=='web_search':
                reviewed=json.loads(row['arguments']);endpoint=context.search_info(c)
                if not endpoint or endpoint!=reviewed['endpoint']: current='deny'
            if name=='read_work_file':
                reviewed=tools.ReadWorkFileArgs.model_validate_json(row['arguments'])
                try:
                    latest=context.artifact_review(c,context,reviewed)
                    latest=tool_audit._redact_result(latest,context.redact)
                    if context.redact(json.dumps(latest,ensure_ascii=False))!=reviewed.review_json: current='deny'
                    destinations=context.destination_snapshot(c,context)
                    if context.approved_destinations is not None and context.approved_destinations!=destinations: current='deny'
                except tools.ToolError: current='deny'
            if name=='create_handoff':
                reviewed=json.loads(row['arguments']);receiver=c.execute('SELECT name FROM bots WHERE id=?',(reviewed['to_bot_id'],)).fetchone()
                if not receiver or context.redact(receiver['name'])!=reviewed['receiver_name'] or context.handoff_catalog.get(reviewed['to_bot_id'])!=reviewed['receiver_name']: current='deny'
            if current=='deny' or (policy=='auto' and current!='auto'):
                tool_audit.deny_policy_change(c,call);blocked=True
            else:
                row=tool_audit.claim(c,call);blocked=False
                if name=='read_work_file': context.approved_destinations=destinations
        if blocked:
            context.notify({'type':'tool.decision','call_id':call,'decision':'policy_denied','status':'denied'})
            return {'status':'denied','message':'Tool policy or desktop owner control changed before execution; request a fresh screenshot and approval.' if name=='computer_action' else 'Tool policy changed before execution.'}
        safe_args=json.loads(row['arguments'])
        screenshot=None
        try:
            if name=='computer_action':
                body=tools.ReviewedComputerActionArgs.model_validate(safe_args)
                action=body.model_dump(exclude_none=True,exclude={'permission_revision','approved_host','domain_revision','control_revision'})
                result,screenshot=await computer.desktop_action(context,body.permission_revision,action,body.approved_host,body.domain_revision,body.control_revision)
                # The screenshot was captured under the operation lock at this
                # revision. Owner takeover may occur immediately afterward.
                context.desktop_observation_revision=body.control_revision
            elif name=='computer_shell':
                body=tools.ReviewedComputerArgs.model_validate(safe_args)
                result=await computer.execute(context,body.command,body.permission_revision)
            elif name=='mcp_call':
                if not context.connector_call: raise tools.ToolError('Connector execution is unavailable.')
                result=await context.connector_call(connector,tools.McpCallArgs.model_validate(safe_args))
            elif name=='read_work_file':
                result=json.loads(tools.ReadWorkFileArgs.model_validate(safe_args).review_json)
            elif name=='attach_mission_result':
                if not context.mission_id or not context.artifact_call: raise tools.ToolError('Mission result attachments are unavailable.')
                result=await context.artifact_call(context,tools.MissionArtifactArgs.model_validate(safe_args))
            elif name=='create_handoff':
                if not context.handoff_call: raise tools.ToolError('Handoffs are unavailable.')
                result=await context.handoff_call(context,tools.HandoffArgs.model_validate(safe_args))
            elif name=='web_search':
                result=await tools.web_search(tools.WebSearchArgs.model_validate(safe_args),context.allow,context.deny)
            elif name=='web_fetch': result=await tools.web_fetch(tools.WebFetchArgs.model_validate(safe_args),context.allow,context.deny)
            elif name=='write_note': result=tools.write_note(context.data_dir,context.bot_id,tools.NotesArgs.model_validate(safe_args))
            elif name=='create_followup':
                body=tools.FollowupArgs.model_validate(safe_args)
                try:
                    due=datetime.fromisoformat(body.due.replace('Z','+00:00'))
                    if due.tzinfo is None or due.utcoffset() is None: raise ValueError()
                    timestamp=due.timestamp()
                except (ValueError,OverflowError,OSError) as exc:
                    raise tools.ToolError('Enter an ISO 8601 datetime with an explicit timezone.') from exc
                now=time.time();summary=body.summary.strip()
                if not summary: raise tools.ToolError('Enter a follow-up summary.')
                if not now<timestamp<=now+366*86400: raise tools.ToolError('The follow-up must be due in the next 366 days.')
                with context.db() as c:
                    c.execute('BEGIN IMMEDIATE');live(c,context)
                    if c.execute("SELECT COUNT(*) FROM followups WHERE status='open'").fetchone()[0]>=500: raise tools.ToolError('Open follow-up limit reached (500).')
                    followup_id=str(uuid.uuid4())
                    c.execute("INSERT INTO followups VALUES (?,?,?,?,?,'open',?,?)",(followup_id,context.bot_id,context.run_id,summary,timestamp,now,now))
                result={'id':followup_id,'due_at':timestamp}
            else: raise tools.ToolError('Unknown tool.')
            success=not (name=='computer_action' and isinstance(result,dict) and 'error' in result)
        except tools.ToolError as exc:
            result={'error':str(exc)};success=False
        with context.db() as c:
            c.execute('BEGIN IMMEDIATE');tool_audit.finish(c,call,result,success,context.redact)
            stored=json.loads(c.execute('SELECT result FROM tool_calls WHERE id=?',(call,)).fetchone()['result'])
        context.notify({'type':'tool.finished','call_id':call,'status':'completed' if success else 'failed','result':stored})
        outcome={'status':'completed' if success else 'failed','result':stored}
        if screenshot is not None: outcome['_desktop_screenshot']=screenshot
        return outcome
    except (asyncio.CancelledError, Exception):
        # A call in progress is never automatically replayed after interruption.
        with context.db() as c:
            c.execute('BEGIN IMMEDIATE')
            tool_audit.abort(c,call,'Interrupted; outcome may be unknown.',context.redact)
        raise
