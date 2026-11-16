"""Store notifications for the owner; never sends to an external destination."""
import time
import uuid


def add(c,bot_id,kind,title,body,run_id=None,mission_id=None):
    identifier=str(uuid.uuid4())
    c.execute('INSERT INTO inbox_notices VALUES (?,?,?,?,?,?,?,?,NULL)',
              (identifier,bot_id,kind,title[:160],body[:2000],run_id,mission_id,time.time()))
    return identifier
