import json
from concurrent.futures import ThreadPoolExecutor
import pytest
import app as service
from funkbot.tool_audit import propose, decide, claim, finish
from funkbot.tools import ToolError


def test_read_tool_is_auto_approved_and_every_transition_is_audited():
    with service.db() as c:
        call=propose(c,'run','bot','web_fetch',{'url':'https://example.com'},lambda value:value,now=1)
        row=claim(c,call,now=2)
        assert row['risk']=='read' and row['status']=='running'
        finish(c,call,{'text':'actual secret result'},True,lambda value:value.replace('secret','[redacted]'),now=3)
        assert [row['action'] for row in c.execute('SELECT action FROM tool_audit WHERE call_id=? ORDER BY id',(call,))] == ['proposed','read_auto_approved','started','completed']
        assert json.loads(c.execute('SELECT result FROM tool_calls WHERE id=?',(call,)).fetchone()['result'])=={'text':'actual [redacted] result'}


def test_write_requires_approval_and_cannot_be_approved_or_executed_twice():
    with service.db() as c:
        call=propose(c,'run','bot','write_note',{'filename':'file.txt','content':'secret is here'},lambda value:value.replace('secret','[redacted]'))
        assert '[redacted]' in c.execute('SELECT arguments FROM tool_calls WHERE id=?',(call,)).fetchone()['arguments']
        with pytest.raises(ToolError,match='not approved'): claim(c,call)
        assert decide(c,call,'approve_once')=='approved'
        with pytest.raises(ToolError,match='no longer pending'): decide(c,call,'approve')
        row=claim(c,call);assert json.loads(row['arguments'])['content']=='[redacted] is here'
        with pytest.raises(ToolError,match='already started'): claim(c,call)
        finish(c,call,{'filename':'file.txt'},True,lambda value:value)
        assert [r['action'] for r in c.execute('SELECT action FROM tool_audit WHERE call_id=? ORDER BY id',(call,))]==['proposed','approve_once','started','completed']


def test_deny_is_terminal_and_unknown_tools_and_arguments_are_rejected():
    with service.db() as c:
        with pytest.raises(ToolError,match='Unknown'): propose(c,'r','b','shell',{'command':'echo hi'},lambda x:x)
        with pytest.raises(ToolError,match='arguments'): propose(c,'r','b','write_note',{'filename':'a.txt','content':'x','other':1},lambda x:x)
        call=propose(c,'r','b','write_note',{'filename':'a.txt','content':'x'},lambda x:x)
        assert decide(c,call,'deny')=='denied'
        with pytest.raises(ToolError): claim(c,call)
        with pytest.raises(ToolError): decide(c,call,'approve')


def test_concurrent_claim_only_one_can_execute():
    with service.db() as c:
        call=propose(c,'r','b','write_note',{'filename':'a.txt','content':'x'},lambda x:x)
        decide(c,call,'approve')
    def attempt(_):
        with service.db() as c:
            c.execute('BEGIN IMMEDIATE')
            try: claim(c,call);return True
            except ToolError: return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt,range(2))) == [False,True]
