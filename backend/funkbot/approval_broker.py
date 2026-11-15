"""In-memory decision rendezvous for live tool calls.

Durable decision auditing is handled separately by tool_audit. A process
restart cancels the run; it must never re-execute an unresolved write.
"""
import asyncio
from .tools import ToolError


class ApprovalBroker:
    def __init__(self): self.pending={}

    def prepare(self, call_id):
        if call_id in self.pending: raise ToolError('Approval is already pending.')
        self.pending[call_id]=asyncio.get_running_loop().create_future()

    def submit(self, call_id, decision):
        if decision not in ('approve','approve_once','deny'): raise ToolError('Invalid approval decision.')
        future=self.pending.get(call_id)
        if not future or future.done(): raise ToolError('This approval is no longer pending.')
        future.set_result(decision)

    async def wait(self, call_id):
        future=self.pending.get(call_id)
        if not future: raise ToolError('This approval is no longer pending.')
        try: return await future
        finally: self.pending.pop(call_id,None)

    def cancel_all(self):
        for future in self.pending.values():
            if not future.done(): future.cancel()
        self.pending.clear()
