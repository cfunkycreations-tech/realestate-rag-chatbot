"""Validated account-level events, separate from per-run streaming deltas."""
import json
import time
from typing import Literal
from pydantic import BaseModel, Field


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


PAYLOAD_TYPES = {
    'handoff.created': GroupExchange,
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
    type: Literal['handoff.created', 'run.started', 'run.finished', 'bot.state_changed', 'message.sent', 'error.raised', 'group.session_started', 'group.session_ended', 'group.delegated', 'group.replied']
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
