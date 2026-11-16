// Pure mapping from the real /api/mission-control summary to gauge display values.
// A missing figure is never replaced by a guess: it becomes "No data" or "Not connected".
export type Summary={
 generated_at:number;paused:boolean;
 bots:{configured:number;active:number;waiting_approval:number};
 missions:{done:number;failed:number;completion:number|null;window_days:number};
 workflow:{health:number|null;done:number;failed:number;routines_scheduled:number;workflows_saved:number;window_days:number};
 spending:{connected:boolean;spent?:string;cap?:string;percent?:number|null;error?:string;economy?:boolean};
 activity:{running:number;queued:number;active_runs:number};
 attention:{approvals:number;failures:number;messages:number;total:number};
};
export type Tone='ok'|'info'|'warn'|'bad'|'idle';
export type Target='roster'|'missions'|'workflows'|'analytics'|'inbox'|'budget';
export type GaugeModel={id:string;label:string;value:number|null;display:string;sub:string;tone:Tone;tip:string;target:Target};

const money=(v?:string)=>v==null||Number.isNaN(Number(v))?'':`$${Number(v)<1?Number(v).toFixed(4):Number(v).toFixed(2)}`;
const plural=(n:number,word:string)=>`${n} ${word}${n===1?'':'s'}`;

export function botGauge(s:Summary|null):GaugeModel{
 const base={id:'bots',label:'BOTS',target:'roster' as Target};
 if(!s)return{...base,value:null,display:'Not connected',sub:'',tone:'idle',tip:'Bot availability could not be loaded.'};
 const {configured,active,waiting_approval}=s.bots;
 if(s.paused)return{...base,value:0,display:'PAUSED',sub:`${plural(configured,'Bot')} configured`,tone:'warn',tip:`All Bots are paused; new work is blocked. ${plural(configured,'Bot')} configured.`};
 if(configured===0)return{...base,value:null,display:'No Bots',sub:'none configured',tone:'idle',tip:'No Bots are configured yet.'};
 return{...base,value:active/configured,display:`${active}/${configured}`,sub:active?`${active} active${waiting_approval?` · ${waiting_approval} awaiting you`:''}`:'all idle',tone:active?'ok':'idle',
  tip:`Configured: ${configured}. Genuinely active now (running or waiting for approval): ${active}${waiting_approval?`, of which ${waiting_approval} waiting for your approval`:''}. Idle Bots are configured but not working.`};
}
export function missionMeter(s:Summary|null):GaugeModel{
 const base={id:'missions',label:'MISSION COMPLETION',target:'missions' as Target};
 if(!s)return{...base,value:null,display:'Not connected',sub:'',tone:'idle',tip:'Mission data could not be loaded.'};
 const m=s.missions,total=m.done+m.failed;
 if(m.completion==null)return{...base,value:null,display:'No data',sub:`no finished missions in ${m.window_days} days`,tone:'idle',tip:`Share of finished missions that succeeded in the last ${m.window_days} days. No mission has finished in that time.`};
 return{...base,value:m.completion/100,display:`${m.completion}%`,sub:`${m.done} of ${total} finished`,tone:m.completion>=80?'ok':m.completion>=50?'warn':'bad',
  tip:`${m.done} missions completed and ${m.failed} failed in the last ${m.window_days} days. Queued and running missions are not counted.`};
}
export function workflowIndicator(s:Summary|null):GaugeModel{
 const base={id:'workflow',label:'WORKFLOW HEALTH',target:'workflows' as Target};
 if(!s)return{...base,value:null,display:'Not connected',sub:'',tone:'idle',tip:'Workflow data could not be loaded.'};
 const w=s.workflow;
 if(w.health==null)return{...base,value:null,display:'No data',sub:w.routines_scheduled?`${plural(w.routines_scheduled,'routine')} scheduled`:'no automations yet',tone:'idle',
  tip:`Success rate of routine and workflow runs in the last ${w.window_days} days. None have finished yet. Routines scheduled: ${w.routines_scheduled}. Workflows saved: ${w.workflows_saved}.`};
 return{...base,value:w.health/100,display:`${w.health}%`,sub:`${w.done} ok · ${w.failed} failed`,tone:w.health>=90?'ok':w.health>=60?'warn':'bad',
  tip:`Of ${w.done+w.failed} routine and workflow runs in the last ${w.window_days} days, ${w.done} succeeded and ${w.failed} failed.`};
}
export function spendGauge(s:Summary|null):GaugeModel{
 const base={id:'spend',label:'AI SPEND TODAY',target:'budget' as Target};
 if(!s)return{...base,value:null,display:'Not connected',sub:'',tone:'idle',tip:'Spending data could not be loaded.'};
 const sp=s.spending;
 if(sp.error||sp.percent==null)return{...base,value:null,display:'Unverified',sub:'open Budget',tone:'warn',tip:sp.error||'No daily cap is set, so spending cannot be shown as a share.'};
 return{...base,value:sp.percent/100,display:money(sp.spent),sub:`of ${money(sp.cap)} daily cap${sp.economy?' · Economy':''}`,tone:sp.percent>=100?'bad':sp.percent>=80?'warn':'ok',
  tip:`Account spending today (UTC) including money reserved for running work, against your configured daily cap of ${money(sp.cap)}. Prices are the ones you configured, not a provider invoice.${sp.economy?' Economy Mode is on.':''}`};
}
export function activityMeter(s:Summary|null):GaugeModel{
 const base={id:'activity',label:'TASK ACTIVITY',target:'missions' as Target};
 if(!s)return{...base,value:null,display:'Not connected',sub:'',tone:'idle',tip:'Task activity could not be loaded.'};
 const {running,queued}=s.activity,total=running+queued;
 if(total===0)return{...base,value:0,display:'Idle',sub:'nothing running or queued',tone:'idle',tip:'No missions are running or queued.'};
 return{...base,value:running/total,display:`${running} running`,sub:`${queued} queued`,tone:'info',tip:`${plural(running,'mission')} running or waiting for approval, ${queued} queued. The bar shows the running share.`};
}
export function attentionIndicator(s:Summary|null):GaugeModel{
 const base={id:'attention',label:'ATTENTION',target:'inbox' as Target};
 if(!s)return{...base,value:null,display:'Not connected',sub:'',tone:'idle',tip:'Attention data could not be loaded.'};
 const a=s.attention;
 if(a.total===0)return{...base,value:0,display:'All clear',sub:'nothing needs you',tone:'ok',tip:'No approvals waiting, no failed runs in the last 24 hours, and no unread messages.'};
 const parts=[a.approvals&&plural(a.approvals,'approval'),a.failures&&plural(a.failures,'failure'),a.messages&&plural(a.messages,'message')].filter(Boolean) as string[];
 return{...base,value:null,display:String(a.total),sub:parts.join(' · '),tone:a.failures||a.approvals?'bad':'warn',tip:`Needs you: ${parts.join(', ')}. Failures are runs that failed in the last 24 hours; messages are unread inbox notices.`};
}
export type HudMode='full'|'compact'|'hidden';
export const MODES:HudMode[]=['full','compact','hidden'];
export function nextMode(m:HudMode):HudMode{return MODES[(MODES.indexOf(m)+1)%MODES.length]}
export function readMode(raw:string|null):HudMode{return raw==='compact'||raw==='hidden'||raw==='full'?raw:'full'}
