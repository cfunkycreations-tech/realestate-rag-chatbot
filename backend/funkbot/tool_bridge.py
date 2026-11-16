"""Connect an audited tool runtime to a live run's approval events.

The host application supplies the event sink and owns the run lifecycle.
"""
from .approval_broker import ApprovalBroker
from .tool_runtime import execute


class ToolBridge:
    def __init__(self, context, emit):
        self.context=context
        self.emit=emit
        self.broker=ApprovalBroker()
        self.context.notify=self.notify

    def notify(self, event):
        # Register before sending the card, so an immediate response cannot race
        # the server's approval waiter. A run grant needs no second decision.
        if event['type']=='tool.proposed' and event['status']=='pending' and (event['tool'] in ('mcp_call','create_handoff','attach_mission_result','read_work_file','web_search','computer_shell','computer_action') or event['tool'] not in self.context.run_grants):
            self.broker.prepare(event['call_id'])
        try: self.emit(event)
        except Exception:
            if event['type']=='tool.proposed': self.broker.discard(event['call_id'])
            raise

    async def execute(self, name, arguments):
        return await execute(self.context,name,arguments,self.broker.wait)

    def submit(self, call_id, decision):
        self.broker.submit(call_id,decision)

    def cancel(self):
        self.broker.cancel_all()
