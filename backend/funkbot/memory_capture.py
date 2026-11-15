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
