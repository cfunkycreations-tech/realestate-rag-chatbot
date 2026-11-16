from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
import app as service
from funkbot.schedule import next_occurrence
from test_app import setup, configure_budget, FakeClient
from test_live_tools import final_reply
from test_missions_api import wait_mission


def stamp(s): return datetime.fromisoformat(s).timestamp()

def test_cron_timezone_dst_and_validation():
    # Nonexistent spring-forward minute is skipped; repeated fall-back minute fires once.
    assert next_occurrence('30 2 * * *','America/New_York',stamp('2026-03-07T08:00:00+00:00'))==stamp('2026-03-09T06:30:00+00:00')
    first=next_occurrence('30 1 * * *','America/New_York',stamp('2026-11-01T04:00:00+00:00'))
    assert first==stamp('2026-11-01T05:30:00+00:00')
    assert next_occurrence('30 1 * * *','America/New_York',first)==stamp('2026-11-02T06:30:00+00:00')
    assert next_occurrence('0 9 * * 1-5','UTC',stamp('2026-11-13T10:00:00+00:00'))==stamp('2026-11-16T09:00:00+00:00')
    for expression,zone in [('60 * * * *','UTC'),('* * *','UTC'),('* * * * *','Not/AZone'),('0 0 31 2 *','UTC')]:
        with pytest.raises(ValueError): next_occurrence(expression,zone,stamp('2026-01-01T00:00:00+00:00'))


def test_routine_creation_run_now_history_pause_and_budget(monkeypatch):
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient);FakeClient.responses=[final_reply()]
    with TestClient(service.app) as c:
        assert c.get('/api/routines').status_code==401
        setup(c);configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Planner'}).json()['id']
        body={'title':'Daily planning','instructions':'Plan the day','bot_id':bot,'cron':'0 9 * * *','timezone':'America/Chicago'}
        assert c.post('/api/routines',json={**body,'cron':'nonsense'}).status_code==400
        rid=c.post('/api/routines',json=body).json()['id']
        assert c.put(f'/api/routines/{rid}/pause',json={'paused':True}).status_code==200
        result=c.post(f'/api/routines/{rid}/run').json();pending=c.get('/api/routine-approvals').json();assert len(pending)==1 and pending[0]['mission_id']==result['mission_id']
        assert c.post(f"/api/routines/{rid}/runs/{pending[0]['id']}/decision",json={'decision':'approve'}).status_code==200
        assert c.post(f"/api/routines/{rid}/runs/{pending[0]['id']}/decision",json={'decision':'approve'}).status_code==409
        assert wait_mission(c,result['mission_id'],{'done'})['status']=='done'
        assert c.get(f'/api/routines/{rid}/runs').json()[0]['status']=='done'
        assert c.put('/api/control/pause',json={'paused':True}).status_code==200
        assert c.post(f'/api/routines/{rid}/run').status_code==423
        assert c.delete(f'/api/routines/{rid}').status_code==200
        assert c.get('/api/missions/'+result['mission_id']).status_code==200


@pytest.mark.asyncio
async def test_catchup_unique_slots_and_restart_preserves_unsent(monkeypatch):
    # A committed queued slot survives a restart; slots are created once only.
    dispatched=[];monkeypatch.setattr(service,'schedule_mission',lambda mid,*args:dispatched.append(mid))
    now=stamp('2026-11-01T05:35:00+00:00')
    with TestClient(service.app) as c:
        setup(c);bot=c.post('/api/bots',json={'name':'Planner'}).json()['id']
        body={'title':'Hourly','instructions':'Check','bot_id':bot,'cron':'0 * * * *','timezone':'UTC'}
        rid=c.post('/api/routines',json=body).json()['id']
        with service.db() as db: db.execute('UPDATE routines SET next_at=? WHERE id=?',(now-3600,rid))
        await service.routine_tick(now);service.mark_interrupted_runs();await service.routine_tick(now)
        history=c.get(f'/api/routines/{rid}/runs').json();assert len(history)==2
        assert len({h['scheduled_at'] for h in history})==2
        assert all(h['status']=='queued' for h in history)
        await service.routine_tick(now);assert len(c.get(f'/api/routines/{rid}/runs').json())==2


def test_restart_replays_committed_queued_routine_once_and_budget_refuses(monkeypatch):
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient);FakeClient.responses=[final_reply()]
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Planner'}).json()['id']
        body={'title':'Recovery','instructions':'Check','bot_id':bot,'cron':'0 9 * * *','timezone':'UTC'}
        rid=c.post('/api/routines',json=body).json()['id']
        # Model work has not started. Simulate a crash just after atomic creation.
        with service.db() as db:
            row=db.execute('SELECT * FROM routines WHERE id=?',(rid,)).fetchone()
            mid=service.routine_mission(db,row,1000,1000)
            db.execute("UPDATE routine_runs SET approval='approved' WHERE mission_id=?",(mid,))
    with TestClient(service.app) as c:
        assert c.post('/api/auth/login',json={'password':'correct horse battery staple'}).status_code==200
        assert wait_mission(c,mid,{'done'})['status']=='done'
        history=c.get(f'/api/routines/{rid}/runs').json()
        assert len(history)==1 and history[0]['mission_id']==mid
        assert c.put('/api/budget/limits/account',json={'daily':'0','monthly':None}).status_code==200
        rejected=c.post(f'/api/routines/{rid}/run').json()['mission_id']
        pending=c.get('/api/routine-approvals').json()[0]
        assert c.post(f"/api/routines/{rid}/runs/{pending['id']}/decision",json={'decision':'approve'}).status_code==200
        failed=wait_mission(c,rejected,{'failed'})
        assert 'budget cap' in failed['error']
        assert len(FakeClient.responses)==0


def test_duplicate_copies_routines_paused_without_history():
    with TestClient(service.app) as c:
        setup(c);bot=c.post('/api/bots',json={'name':'Planner'}).json()['id']
        body={'title':'Daily','instructions':'Check','bot_id':bot,'cron':'0 9 * * *','timezone':'UTC'}
        rid=c.post('/api/routines',json=body).json()['id']
        clone=c.post(f'/api/bots/{bot}/duplicate').json()['id']
        routines=c.get('/api/routines').json();copied=next(r for r in routines if r['bot_id']==clone)
        assert copied['paused']==1 and copied['title']=='Daily' and copied['cron']==body['cron']
        assert copied['id']!=rid and c.get(f"/api/routines/{copied['id']}/runs").json()==[]


def test_routine_approval_denial_and_global_pause(monkeypatch):
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient);FakeClient.responses=[final_reply()]
    with TestClient(service.app) as c:
        assert c.get('/api/routine-approvals').status_code==401
        setup(c);configure_budget(c);bot=c.post('/api/bots',json={'name':'Planner'}).json()['id']
        rid=c.post('/api/routines',json={'title':'Review','instructions':'Think','bot_id':bot,'cron':'0 9 * * *','timezone':'UTC'}).json()['id']
        mid=c.post(f'/api/routines/{rid}/run').json()['mission_id'];item=c.get('/api/routine-approvals').json()[0]
        assert c.get('/api/missions/'+mid).json()['status']=='queued' and len(FakeClient.responses)==1
        assert c.post(f"/api/routines/{rid}/runs/{item['id']}/decision",json={'decision':'deny'}).json()['approval']=='denied'
        assert c.get('/api/missions/'+mid).json()['status']=='cancelled' and c.get('/api/routine-approvals').json()==[]
        assert len(FakeClient.responses)==1
        mid=c.post(f'/api/routines/{rid}/run').json()['mission_id'];item=c.get('/api/routine-approvals').json()[0]
        c.put('/api/control/pause',json={'paused':True})
        assert c.post(f"/api/routines/{rid}/runs/{item['id']}/decision",json={'decision':'approve'}).status_code==409
        assert c.get('/api/missions/'+mid).json()['status']=='cancelled'
        assert len(FakeClient.responses)==1


def test_repeated_work_suggests_owner_approved_routine():
    with TestClient(service.app) as c:
        setup(c);bot=c.post('/api/bots',json={'name':'Observer'}).json()['id']
        with service.db() as db:
            from funkbot.learned_routines import discover
            for i,text in enumerate(['Summarize the weekly report','  summarize  the weekly report  ']):
                mid='learned-'+str(i)
                db.execute('INSERT INTO missions VALUES (?,?,?,?,?,?,?,?,?)',(mid,'Weekly report',text,None,'done','Done',None,1+i,1+i))
                db.execute('INSERT INTO mission_assignees VALUES (?,?,?)',(mid,0,bot))
            discover(db,10);discover(db,11)
        suggestions=c.get('/api/routine-suggestions').json()
        assert len(suggestions)==1 and suggestions[0]['examples']==2
        assert c.get('/api/routines').json()==[]
        body={'title':'Weekly report','instructions':'Summarize the weekly report','bot_id':bot,'cron':'0 9 * * 1','timezone':'UTC'}
        approved=c.post('/api/routine-suggestions/'+suggestions[0]['id']+'/approve',json=body)
        assert approved.status_code==200 and len(c.get('/api/routines').json())==1
        assert c.get('/api/routine-suggestions').json()==[]


def test_inbox_contains_routine_results_mentions_and_bot_notices(monkeypatch):
    from test_live_tools import tool_reply
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Notifier'}).json()['id']
        other=c.post('/api/bots',json={'name':'Mentioned'}).json()['id']
        FakeClient.responses=[tool_reply('notify_owner',{'title':'Update','message':'Work is ready.'}),final_reply()]
        run=c.post(f'/api/bots/{bot}/chat',json={'content':f'Please update @{{bot:{other}|Mentioned}}'}).json()['job_id']
        assert '"type": "done"' in c.get(f'/api/jobs/{run}/events').text
        notices=c.get('/api/inbox/notices').json()
        assert {n['kind'] for n in notices}=={'bot','mention'}
        notice=next(n for n in notices if n['kind']=='bot')
        assert notice['title']=='Update' and notice['body']=='Work is ready.'
        assert c.post('/api/inbox/notices/'+notice['id']+'/read').status_code==200
        assert next(n for n in c.get('/api/inbox/notices').json() if n['id']==notice['id'])['read_at']
        FakeClient.responses=[final_reply()]
        rid=c.post('/api/routines',json={'title':'Daily','instructions':'Report','bot_id':bot,'cron':'0 9 * * *','timezone':'UTC'}).json()['id']
        mid=c.post(f'/api/routines/{rid}/run').json()['mission_id']
        approval=c.get('/api/routine-approvals').json()[0]
        assert c.post(f"/api/routines/{rid}/runs/{approval['id']}/decision",json={'decision':'approve'}).status_code==200
        assert wait_mission(c,mid,{'done'})['status']=='done'
        assert any(n['kind']=='routine' and n['mission_id']==mid for n in c.get('/api/inbox/notices').json())
        assert c.delete('/api/inbox/notices/'+notice['id']).status_code==200


def test_scheduled_routine_runs_unattended_and_retries_once(monkeypatch):
    import time
    from fastapi import HTTPException
    monkeypatch.setattr(service.httpx,'AsyncClient',FakeClient)
    # A pre-dispatch failure is retried, with no uncertain provider charge.
    FakeClient.responses=[final_reply()]
    original=service.start_chat;attempts=[]
    async def flaky(*args,**kwargs):
        attempts.append(True)
        if len(attempts)==1: raise HTTPException(503,'Temporary startup failure')
        return await original(*args,**kwargs)
    monkeypatch.setattr(service,'start_chat',flaky)
    with TestClient(service.app) as c:
        setup(c);configure_budget(c)
        bot=c.post('/api/bots',json={'name':'Scheduler'}).json()['id']
        settings=c.get('/api/settings').json();settings['profiles']['smart']=[{'gateway':'openrouter','model':'fixture'}]
        c.put('/api/settings/profiles',json=settings['profiles'])
        rid=c.post('/api/routines',json={'title':'Scheduled','instructions':'Report','bot_id':bot,'cron':'0 9 * * *','timezone':'UTC'}).json()['id']
        with service.db() as db: db.execute('UPDATE routines SET next_at=? WHERE id=?',(time.time()-1,rid))
        for _ in range(200):
            history=c.get(f'/api/routines/{rid}/runs').json()
            if history and history[0]['status']=='done': break
            time.sleep(.1)
        assert history and history[0]['status']=='done' and history[0]['retry_count']==1,history
        assert history[0]['approval']=='approved' and c.get('/api/routine-approvals').json()==[]
        mission=c.get('/api/missions/'+history[0]['mission_id']).json()
        assert len(attempts)==2 and len(mission['runs'])==1
        assert any(n['kind']=='routine' and n['mission_id']==mission['id'] for n in c.get('/api/inbox/notices').json())
