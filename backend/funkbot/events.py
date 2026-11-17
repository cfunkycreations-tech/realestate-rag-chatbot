"""Validated account-level events, separate from per-run streaming deltas."""
import json
import time
from typing import Literal
from pydantic import BaseModel, Field


class ComputerDomainsChanged(BaseModel):
    domains: list[str] = Field(max_length=100)
    revision: int = Field(ge=1)


class ComputerTakeover(BaseModel):
    enabled: bool


class ComputerOwnerInput(BaseModel):
    input_type: Literal['click','key','text']


class ComputerPermissionChanged(BaseModel):
    allowed: bool
    revision: int = Field(ge=1)


class RunStarted(BaseModel):
    status: Literal['running']


class RunFinished(BaseModel):
    status: Literal['done', 'failed', 'cancelled']


class StateChanged(BaseModel):
    state: Literal['idle', 'working', 'done', 'error']


class MessageSent(BaseModel):
    message_id: str
    role: Literal['user', 'assistant']
    summary: str = Field(max_length=240)


class ErrorRaised(BaseModel):
    message: str = Field(max_length=500)


class GroupSession(BaseModel):
    mission_id: str
    session_kind: Literal['mission','group_chat'] = 'mission'
    participants: list[str] = Field(min_length=2, max_length=6)


class GroupExchange(BaseModel):
    mission_id: str
    session_kind: Literal['mission','group_chat'] = 'mission'
    from_bot_id: str
    to_bot_id: str
    summary: str = Field(max_length=240)


class DelegationPair(BaseModel):
    to_bot_id: str


class HandoffEvent(GroupExchange):
    approval: Literal['pair','individual','owner'] = 'owner'


class BotDMMessage(BaseModel):
    dm_id: str
    turn_id: str
    from_bot_id: str
    to_bot_id: str
    summary: str = Field(max_length=240)


class BotMessageEvent(BaseModel):
    to_bot_id: str
    kind: str
    summary: str
    dm_id: str | None = None
    approval: Literal['individual','link'] | None = None


class BotMessageReplyEvent(BaseModel):
    dm_id: str
    turn_id: str
    summary: str


class OrgEvent(BaseModel):
    summary: str = Field(max_length=300)
    ref_id: str | None = None

PAYLOAD_TYPES = {
    'career.review': OrgEvent,
    'career.promotion_recommended': OrgEvent,
    'career.promotion_decided': OrgEvent,
    'mentorship.started': OrgEvent,
    'mentorship.ended': OrgEvent,
    'council.proposal': OrgEvent,
    'council.vote': OrgEvent,
    'council.meeting': OrgEvent,
    'council.decision': OrgEvent,

    'bot_message.sent': BotMessageEvent,
    'bot_message.refused': BotMessageEvent,
    'bot_message.reply': BotMessageReplyEvent,
    'comm.link_approved': DelegationPair,
    'comm.link_revoked': DelegationPair,
    'computer.permission_changed': ComputerPermissionChanged,
    'computer.owner_input': ComputerOwnerInput,
    'computer.takeover': ComputerTakeover,
    'computer.domains_changed': ComputerDomainsChanged,
    'bot_dm.message': BotDMMessage,
    'handoff.created': HandoffEvent,
    'delegation.pair_approved': DelegationPair,
    'delegation.pair_revoked': DelegationPair,
    'group.session_started': GroupSession,
    'group.session_ended': GroupSession,
    'group.delegated': GroupExchange,
    'group.replied': GroupExchange,
    'run.started': RunStarted,
    'run.finished': RunFinished,
    'bot.state_changed': StateChanged,
    'message.sent': MessageSent,
    'error.raised': ErrorRaised,
}


class EventOut(BaseModel):
    id: int
    bot_id: str | None
    run_id: str | None
    type: Literal['bot_message.sent', 'bot_message.refused', 'bot_message.reply', 'comm.link_approved', 'comm.link_revoked', 'career.review', 'career.promotion_recommended', 'career.promotion_decided', 'mentorship.started', 'mentorship.ended', 'council.proposal', 'council.vote', 'council.meeting', 'council.decision', 'delegation.pair_approved', 'delegation.pair_revoked', 'computer.domains_changed', 'computer.takeover', 'computer.owner_input', 'computer.permission_changed', 'bot_dm.message', 'handoff.created', 'run.started', 'run.finished', 'bot.state_changed', 'message.sent', 'error.raised', 'group.session_started', 'group.session_ended', 'group.delegated', 'group.replied']
    payload: dict
    created_at: float


class EventPage(BaseModel):
    events: list[EventOut]
    next_cursor: int


def append_event(connection, bot_id, run_id, kind, payload):
    model = PAYLOAD_TYPES[kind].model_validate(payload)
    connection.execute('INSERT INTO events (bot_id,run_id,event_type,payload,created_at) VALUES (?,?,?,?,?)',
                       (bot_id, run_id, kind, model.model_dump_json(), time.time()))


def row_to_event(row):
    return EventOut(id=row['id'], bot_id=row['bot_id'], run_id=row['run_id'], type=row['event_type'],
                    payload=json.loads(row['payload']), created_at=row['created_at'])
