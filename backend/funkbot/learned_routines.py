"""Detect repeated similar work and queue model drafts from real transcripts."""
import hashlib
import json
import re
import unicodedata
import uuid
from difflib import SequenceMatcher


def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC',text).casefold().split())


def fingerprint(text): return hashlib.sha256(normalized(text).encode()).hexdigest()


def similar(a,b):
    a,b=normalized(a),normalized(b)
    if a==b: return True
    words=lambda s:set(re.findall(r'[\w]+',s))
    x,y=words(a),words(b)
    overlap=len(x & y)/max(1,len(x | y))
    return overlap>=.55 or (min(len(a),len(b))>=20 and SequenceMatcher(None,a,b).ratio()>=.75)


def discover(c, now):
    rows=c.execute('''SELECT m.id,m.title,m.instructions,m.result,a.bot_id FROM missions m
        JOIN mission_assignees a ON a.mission_id=m.id
        WHERE m.status='done' AND a.bot_id IS NOT NULL
        AND (SELECT count(*) FROM mission_assignees x WHERE x.mission_id=m.id)=1
        AND NOT EXISTS (SELECT 1 FROM routine_runs r WHERE r.mission_id=m.id)
        AND NOT EXISTS (SELECT 1 FROM workflow_replays w WHERE w.mission_id=m.id)
        AND NOT EXISTS (SELECT 1 FROM routine_learning_examples e WHERE e.mission_id=m.id)
        ORDER BY m.updated_at DESC LIMIT 1000''').fetchall()
    # The model judges meaning, not word overlap. Test recent consecutive
    # triples per Bot, one new candidate per tick; negative triples are kept
    # so the scheduler does not repeatedly spend on the same comparison.
    groups={}
    for row in rows:
        if row['instructions'].strip(): groups.setdefault(row['bot_id'],[]).append(row)
    for bot_id,work in groups.items():
        for offset in range(len(work)-2):
            matches=work[offset:offset+3]
            fp=hashlib.sha256('|'.join(sorted(r['id'] for r in matches)).encode()).hexdigest()
            if c.execute('SELECT 1 FROM routine_learning WHERE bot_id=? AND fingerprint=?',(bot_id,fp)).fetchone(): continue
            transcripts=[]
            for row in matches:
                calls=c.execute('''SELECT tc.tool_name,tc.arguments,tc.status,tc.result FROM tool_calls tc
                    JOIN mission_runs mr ON mr.run_id=tc.run_id WHERE mr.mission_id=? ORDER BY tc.created_at LIMIT 4''',(row['id'],)).fetchall()
                transcripts.append({'mission_id':row['id'],'title':row['title'][:160],'request':row['instructions'][:700],'result':(row['result'] or '')[:600],
                    'tools':[{'name':call['tool_name'],'arguments':call['arguments'][:100],'status':call['status'],'result':(call['result'] or '')[:100]} for call in calls]})
            c.execute("INSERT OR IGNORE INTO routine_learning VALUES (?,?,?,?, 'queued',?)",(str(uuid.uuid4()),bot_id,fp,json.dumps(transcripts,ensure_ascii=False),now))
            break
