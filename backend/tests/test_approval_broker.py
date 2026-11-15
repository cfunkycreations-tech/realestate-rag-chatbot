import asyncio
import pytest
from funkbot.approval_broker import ApprovalBroker
from funkbot.tools import ToolError


@pytest.mark.asyncio
async def test_decision_cannot_be_submitted_twice_or_after_completion():
    broker=ApprovalBroker();broker.prepare('one');broker.submit('one','approve_once')
    with pytest.raises(ToolError): broker.submit('one','deny')
    assert await broker.wait('one')=='approve_once'
    with pytest.raises(ToolError): broker.submit('one','approve')


@pytest.mark.asyncio
async def test_cancel_and_invalid_decisions_fail_closed():
    broker=ApprovalBroker();broker.prepare('one')
    with pytest.raises(ToolError): broker.submit('one','always')
    task=asyncio.create_task(broker.wait('one'));await asyncio.sleep(0);broker.cancel_all()
    with pytest.raises(asyncio.CancelledError): await task
    with pytest.raises(ToolError): broker.submit('one','approve')
