"""Suggest routines when a Bot completes the same owner-assigned work repeatedly."""
import hashlib
import unicodedata
import uuid


def fingerprint(text):
    normalized=' '.join(unicodedata.normalize('NFKC',text).casefold().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def discover(c, now):
    # Only single-Bot, owner-created completed missions; scheduled executions and
    # workflow replays are not evidence that the owner repeatedly requested work.
    rows=c.execute('''SELECT m.id,m.title,m.instructions,a.bot_id FROM missions m
        JOIN mission_assignees a ON a.mission_id=m.id
        WHERE m.status='done' AND a.bot_id IS NOT NULL
        AND (SELECT count(*) FROM mission_assignees x WHERE x.mission_id=m.id)=1
        AND NOT EXISTS (SELECT 1 FROM routine_runs r WHERE r.mission_id=m.id)
        AND NOT EXISTS (SELECT 1 FROM workflow_replays w WHERE w.mission_id=m.id)
        ORDER BY m.updated_at DESC LIMIT 1000''').fetchall()
    grouped={}
    for row in rows:
        if not row['instructions'].strip(): continue
        key=(row['bot_id'],fingerprint(row['instructions']))
        if key not in grouped: grouped[key]=[row,0]
        grouped[key][1]+=1
    for (bot_id,fp),(row,count) in grouped.items():
        if count>=2:
            c.execute('''INSERT OR IGNORE INTO routine_suggestions
                (id,bot_id,fingerprint,title,instructions,examples,status,created_at)
                VALUES (?,?,?,?,?,?,'pending',?)''',
                (str(uuid.uuid4()),bot_id,fp,row['title'],row['instructions'],count,now))
            c.execute('UPDATE routine_suggestions SET examples=? WHERE bot_id=? AND fingerprint=? AND status=?',(count,bot_id,fp,'pending'))
