"""Conservative, local capture of explicit first-person preferences.

Only the owner's direct chat message is considered. Model, webpage, tool and
mission text are never candidates. This intentionally is not semantic memory.
"""
import re
import unicodedata
import uuid

# Require a standalone sentence, not a quotation or text embedded in a document.
_PREFERENCE = re.compile(r"(?i)^i prefer\s+([^\n\r.!?]{3,300})[.!]?$", re.ASCII)
_EXPLICIT = re.compile(r"(?i)^remember that\s+([^\n\r.!?]{3,300})[.!]?$", re.ASCII)


def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split()).rstrip('.!')


def candidate(message):
    text = message.strip()
    if '[redacted]' in text.casefold():
        return None
    match = _PREFERENCE.fullmatch(text) or _EXPLICIT.fullmatch(text)
    if not match:
        return None
    value = ' '.join(match.group(1).split())
    if not value or '[redacted]' in value.casefold():
        return None
    return ('I prefer ' if _PREFERENCE.fullmatch(text) else '') + value


def capture(c, bot_id, message_id, message, now):
    text = candidate(message)
    if text is None:
        return False
    rows = c.execute('SELECT content FROM bot_memories WHERE bot_id=?', (bot_id,)).fetchall()
    if len(rows) >= 50 or sum(len(row['content']) for row in rows) + len(text) > 32000:
        return False
    if any(normalized(row['content']) == normalized(text) for row in rows):
        return False
    c.execute('''INSERT INTO bot_memories
        (id,bot_id,content,pinned,created_at,updated_at,source,source_ref)
        VALUES (?,?,?,0,?,?,?,?)''',
        (str(uuid.uuid4()),bot_id,text,now,now,'direct_chat',message_id))
    return True


def is_command(text):
    """Only the explicit, owner-typed prefix invokes local memory control."""
    return bool(re.match(r'^!memory(?:\s|$)', text.strip(), re.IGNORECASE))


def parse_command(text):
    """Return a bounded operation. No fuzzy deletions or model interpretation."""
    command = text.strip()
    parts = command.split(None, 2)
    if len(parts) == 1 or (len(parts) == 2 and parts[1].lower() == 'help'):
        return ('help', None, None)
    if len(parts) == 2 and parts[1].lower() == 'show':
        return ('show', None, None)
    if len(parts) < 3:
        raise ValueError('Use !memory show, remember TEXT, forget TEXT, or replace OLD => NEW.')
    action = parts[1].lower()
    arg = parts[2].strip()
    if action == 'replace':
        pieces = arg.split(' => ')
        if len(pieces) != 2:
            raise ValueError('Use !memory replace OLD => NEW with one separator.')
        old, new = (piece.strip() for piece in pieces)
    elif action in ('remember', 'forget'):
        old, new = arg, None
    else:
        raise ValueError('Use !memory show, remember TEXT, forget TEXT, or replace OLD => NEW.')
    if not old or not normalized(old) or len(old) > 4000 or (new is not None and (not new or not normalized(new) or len(new) > 4000)):
        raise ValueError('Memory text must be between 1 and 4,000 characters.')
    return (action, old, new)


def save_learned(c, bot_id, message_id, facts, now):
    rows=c.execute('SELECT content FROM bot_memories WHERE bot_id=?',(bot_id,)).fetchall()
    existing={normalized(row['content']) for row in rows}
    count=len(rows);size=sum(len(row['content']) for row in rows)
    for fact in facts:
        text=fact.strip();key=normalized(text)
        if not key or key in existing or '[redacted]' in text.casefold() or count>=50 or size+len(text)>32000: continue
        c.execute("INSERT INTO bot_memories (id,bot_id,content,pinned,created_at,updated_at,source,source_ref) VALUES (?,?,?,0,?,?,?,?)",(str(uuid.uuid4()),bot_id,text,now,now,'learned_chat',message_id))
        existing.add(key);count+=1;size+=len(text)
