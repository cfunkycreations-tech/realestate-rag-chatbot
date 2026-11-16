import {describe,expect,it} from 'vitest';
import {activityMeter,attentionIndicator,botGauge,missionMeter,nextMode,readMode,spendGauge,workflowIndicator,type Summary} from './model';

const base:Summary={generated_at:1,paused:false,
 bots:{configured:3,active:2,waiting_approval:1},
 missions:{done:2,failed:1,completion:67,window_days:7},
 workflow:{health:50,done:1,failed:1,routines_scheduled:1,workflows_saved:0,window_days:7},
 spending:{connected:true,spent:'0.0123',cap:'5.0',percent:0,economy:false},
 activity:{running:1,queued:1,active_runs:2},
 attention:{approvals:1,failures:1,messages:2,total:4}};
const empty:Summary={...base,bots:{configured:0,active:0,waiting_approval:0},missions:{done:0,failed:0,completion:null,window_days:7},
 workflow:{health:null,done:0,failed:0,routines_scheduled:0,workflows_saved:0,window_days:7},activity:{running:0,queued:0,active_runs:0},attention:{approvals:0,failures:0,messages:0,total:0}};

describe('mission control gauge models',()=>{
 it('says Not connected for every gauge when no data source answered',()=>{
  for(const f of [botGauge,missionMeter,workflowIndicator,spendGauge,activityMeter,attentionIndicator])expect(f(null).display).toBe('Not connected');
 });
 it('separates configured from genuinely active Bots',()=>{
  const g=botGauge(base);expect(g.display).toBe('2/3');expect(g.value).toBeCloseTo(2/3);expect(g.sub).toContain('1 awaiting you');
  expect(botGauge({...base,bots:{configured:3,active:0,waiting_approval:0}}).sub).toBe('all idle');
 });
 it('shows PAUSED and No Bots without inventing numbers',()=>{
  expect(botGauge({...base,paused:true}).display).toBe('PAUSED');
  expect(botGauge(empty).display).toBe('No Bots');
 });
 it('shows No data when nothing has finished',()=>{
  expect(missionMeter(empty)).toMatchObject({display:'No data',value:null});
  expect(workflowIndicator(empty)).toMatchObject({display:'No data',value:null});
  expect(workflowIndicator({...empty,workflow:{...empty.workflow,routines_scheduled:2}}).sub).toBe('2 routines scheduled');
 });
 it('reports real completion and health with honest tones',()=>{
  expect(missionMeter(base)).toMatchObject({display:'67%',tone:'warn'});
  expect(workflowIndicator(base)).toMatchObject({display:'50%',tone:'bad'});
 });
 it('spend gauge uses the real cap, warns at 80% and flags unverified spend',()=>{
  expect(spendGauge(base)).toMatchObject({display:'$0.0123',tone:'ok'});
  expect(spendGauge({...base,spending:{...base.spending,percent:85}}).tone).toBe('warn');
  expect(spendGauge({...base,spending:{...base.spending,percent:100}}).tone).toBe('bad');
  expect(spendGauge({...base,spending:{connected:true,error:'x cannot be verified'}})).toMatchObject({display:'Unverified',tone:'warn'});
 });
 it('activity and attention reflect zero and non-zero states',()=>{
  expect(activityMeter(empty)).toMatchObject({display:'Idle',value:0});
  expect(activityMeter(base)).toMatchObject({display:'1 running',sub:'1 queued',value:0.5});
  expect(attentionIndicator(empty)).toMatchObject({display:'All clear',tone:'ok'});
  expect(attentionIndicator(base)).toMatchObject({display:'4',tone:'bad'});
  expect(attentionIndicator({...base,attention:{approvals:0,failures:0,messages:2,total:2}}).tone).toBe('warn');
 });
 it('cycles display modes and ignores bad stored values',()=>{
  expect(nextMode('full')).toBe('compact');expect(nextMode('compact')).toBe('hidden');expect(nextMode('hidden')).toBe('full');
  expect(readMode('hidden')).toBe('hidden');expect(readMode('weird')).toBe('full');expect(readMode(null)).toBe('full');
 });
});
