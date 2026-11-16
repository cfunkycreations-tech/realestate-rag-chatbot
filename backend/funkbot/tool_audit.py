"""Transactional audit/state primitives; never execute a tool from this module."""
import json
import time
import uuid
from pydantic import ValidationError
from .tools import REGISTRY, ReviewedComputerArgs, ReviewedComputerActionArgs, ToolError


def audit(c, call_id, action, now):
    c.execute('INSERT INTO tool_audit (call_id,action,created_at) VALUES (?,?,?)', (call_id,action,now))


def propose(c, run_id, bot_id, name, arguments, redact, now=None, policy=None):
    """Validate and redact before persistence; caller owns a write transaction."""
    spec=REGISTRY.get(name)
    if not spec: raise ToolError('Unknown tool.')
    args_type=ReviewedComputerArgs if name=='computer_shell' else ReviewedComputerActionArgs if name=='computer_action' else spec.args
    try:
        parsed=args_type.model_validate(arguments).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise ToolError('Invalid tool arguments.') from exc
    # The exact redacted arguments are both approved and later executed; never
    # show a sanitized card while executing different hidden arguments.
    cleaned={key:redact(value) if isinstance(value,str) else value for key,value in parsed.items()}
    try:
        cleaned=args_type.model_validate(cleaned).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise ToolError('Redacted tool arguments are invalid.') from exc
    call_id=str(uuid.uuid4());now=time.time() if now is None else now
    policy=policy or ('auto' if spec.risk=='read' else 'ask')
    if policy not in ('auto','ask','deny') or (policy=='auto' and spec.risk!='read' and name not in ('remember_fact','notify_owner','create_handoff')): raise ToolError('Invalid tool policy.')
    status='denied' if policy=='deny' else 'approved' if policy=='auto' else 'pending'
    c.execute('''INSERT INTO tool_calls (id,run_id,bot_id,tool_name,risk,arguments,status,created_at,updated_at)
                 VALUES (?,?,?,?,?,?,?,?,?)''', (call_id,run_id,bot_id,name,spec.risk,json.dumps(cleaned),status,now,now))
    audit(c,call_id,'proposed',now)
    if status=='approved': audit(c,call_id,'pair_auto_approved' if name=='create_handoff' else 'internal_auto_approved' if name in ('remember_fact','notify_owner') else 'read_auto_approved',now)
    if status=='denied': audit(c,call_id,'policy_denied',now)
    return call_id


def decide(c, call_id, decision, now=None):
    if decision not in ('approve','approve_once','deny'): raise ToolError('Invalid approval decision.')
    row=c.execute('SELECT risk,status FROM tool_calls WHERE id=?', (call_id,)).fetchone()
    if not row or row['risk'] not in ('read','write','send','spend') or row['status']!='pending': raise ToolError('This approval is no longer pending.')
    now=time.time() if now is None else now
    status='denied' if decision=='deny' else 'approved'
    c.execute('UPDATE tool_calls SET status=?,updated_at=? WHERE id=?', (status,now,call_id))
    audit(c,call_id,decision,now)
    return status


def claim(c, call_id, now=None):
    now=time.time() if now is None else now
    result=c.execute("UPDATE tool_calls SET status='running',updated_at=? WHERE id=? AND status='approved'", (now,call_id))
    if not result.rowcount: raise ToolError('Tool call is not approved or has already started.')
    audit(c,call_id,'started',now)
    return dict(c.execute('SELECT * FROM tool_calls WHERE id=?', (call_id,)).fetchone())


def _redact_result(value, redact):
    if isinstance(value, str): return redact(value)
    if isinstance(value, list): return [_redact_result(item, redact) for item in value]
    if isinstance(value, dict): return {redact(str(key)): _redact_result(item, redact) for key,item in value.items()}
    return value


def finish(c, call_id, result, success, redact, now=None):
    now=time.time() if now is None else now
    status='completed' if success else 'failed'
    changed=c.execute("UPDATE tool_calls SET status=?,result=?,updated_at=? WHERE id=? AND status='running'", (status,json.dumps(_redact_result(result,redact)),now,call_id))
    if not changed.rowcount: raise ToolError('Tool call is not running.')
    audit(c,call_id,status,now)


def approve_from_run_grant(c, call_id, now=None):
    """Use a grant that exists only for the current, live run."""
    now=time.time() if now is None else now
    changed=c.execute("UPDATE tool_calls SET status='approved',updated_at=? WHERE id=? AND risk IN ('read','write','send','spend') AND status='pending'", (now,call_id))
    if not changed.rowcount: raise ToolError('This approval is no longer pending.')
    audit(c,call_id,'run_grant',now)


def abort(c, call_id, reason, redact, now=None):
    """Mark interruption without misrepresenting it as an owner denial."""
    now=time.time() if now is None else now
    changed=c.execute("UPDATE tool_calls SET status='failed',result=?,updated_at=? WHERE id=? AND status IN ('pending','approved','running')", (json.dumps({'error':redact(reason)}),now,call_id))
    if changed.rowcount: audit(c,call_id,'interrupted',now)


def deny_policy_change(c,call_id,now=None):
    now=time.time() if now is None else now
    changed=c.execute("UPDATE tool_calls SET status='denied',updated_at=? WHERE id=? AND status IN ('pending','approved')",(now,call_id))
    if not changed.rowcount: raise ToolError('This tool call is no longer awaiting execution.')
    audit(c,call_id,'policy_denied',now)
