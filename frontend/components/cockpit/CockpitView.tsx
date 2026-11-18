'use client';
import {useEffect,useState} from 'react';

type Workforce={paused:boolean;bots:{configured:number;busy:number;waiting_approval:number;idle:number;needing_attention:number};
 missions:{pending:number;active:number;blocked:number;completed:number;failed:number;window_days:number};
 workflow:{health:number|null;done:number;failed:number;routines_scheduled:number;workflows_saved:number;window_days:number};
 spending:{error?:string;today?:string;daily_cap?:string;remaining_today?:string;percent_today?:number|null;month?:string;monthly_cap?:string;remaining_month?:string;percent_month?:number;by_bot?:{bot_id:string;name:string;spent:string}[];alerts?:{scope:string;period:string;threshold:number}[]};
 council:{open_proposals:number;escalated:number;meetings_7d:number;members:number};approvals:number;
 training:{active_mentorships:number;training_missions_done:number;results_recorded:number;certified:Record<string,number>};
 activity:{running:number;queued:number;active_runs:number}};
type Source={title:string;wants:string[];connectors:{id:string;name:string;enabled:boolean}[];connected:boolean;figures:null;note:string};
type Sources=Record<'lyricist'|'business',Source>;
export type CockpitTarget='roster'|'missions'|'workflows'|'budget'|'inbox'|'family';

const MODES=[['workforce','AI Workforce'],['lyricist','Lyricist Pro'],['business','Business Operations']] as const;
type Mode=typeof MODES[number][0];
const usd=(v?:string)=>v==null||Number.isNaN(Number(v))?'No data':`$${Number(v)<1?Number(v).toFixed(4):Number(v).toFixed(2)}`;

function Tile({label,value,sub,tip,onOpen,tone='idle'}:{label:string;value:string;sub?:string;tip:string;onOpen?:()=>void;tone?:'ok'|'warn'|'bad'|'idle'}){
 const body=<><small>{label}</small><strong>{value}</strong>{sub&&<span>{sub}</span>}</>;
 return onOpen?<button type="button" className={`ck-tile tone-${tone}`} title={tip} aria-label={`${label}: ${value}. ${tip}`} onClick={onOpen}>{body}</button>:<div className={`ck-tile tone-${tone}`} title={tip}>{body}</div>;
}

// Read-only command cockpit. Every number is counted from the app's own records; a source that is not connected says so and shows nothing.
export default function CockpitView({onNavigate}:{onNavigate:(t:CockpitTarget)=>void}){
 const [mode,setMode]=useState<Mode>('workforce'),[w,setW]=useState<Workforce|null>(null),[src,setSrc]=useState<Sources|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  let live=true;
  const load=async()=>{
   if(document.hidden)return;
   try{const [a,b]=await Promise.all([fetch('/api/cockpit/workforce',{cache:'no-store'}),fetch('/api/cockpit/sources',{cache:'no-store'})]);if(!a.ok||!b.ok)throw Error('The cockpit could not be loaded.');const [x,y]=await Promise.all([a.json(),b.json()]);if(live){setW(x);setSrc(y);setError('')}}
   catch(e){if(live)setError((e as Error).message)}
  };
  void load();const t=window.setInterval(()=>void load(),15000);
  return()=>{live=false;window.clearInterval(t)};
 },[]);
 const s=w?.spending;
 return <div className="missions-view cockpit-view"><header className="missions-heading"><div><p className="eyebrow">COMMAND COCKPIT</p><h1>Cockpit</h1><p>Real figures from your own records, refreshed every 15 seconds. Nothing here spends money or changes a setting.</p></div></header>
  <div className="bc-tabs" role="tablist" aria-label="Cockpit modes">{MODES.map(([k,l])=><button key={k} type="button" role="tab" aria-selected={mode===k} className={mode===k?'active':''} onClick={()=>setMode(k)}>{l}</button>)}</div>
  {error&&<p className="error" role="alert">{error}</p>}
  {mode==='workforce'&&(!w?<p>Loading…</p>:<div className="ck-grid" role="tabpanel" aria-label="AI Workforce">
   {w.paused&&<p className="notice" role="status">All Bots are paused. New work is blocked until you resume.</p>}
   <Tile label="BOTS CONFIGURED" value={String(w.bots.configured)} sub={`${w.bots.busy} busy · ${w.bots.idle} idle`} tip="Configured Bots are not the same as Bots working right now. Busy means a run is active or waiting for you." onOpen={()=>onNavigate('roster')} tone={w.bots.busy?'ok':'idle'}/>
   <Tile label="NEED ATTENTION" value={String(w.bots.needing_attention)} sub="waiting on you or failed in 24h" tip="Bots with a run waiting for approval, or a run that failed in the last 24 hours." onOpen={()=>onNavigate('inbox')} tone={w.bots.needing_attention?'bad':'ok'}/>
   <Tile label="MISSIONS" value={`${w.missions.active} active`} sub={`${w.missions.pending} pending · ${w.missions.blocked} blocked · ${w.missions.completed} done · ${w.missions.failed} failed (${w.missions.window_days}d)`} tip="Pending is queued; blocked is waiting for your approval. Done and failed are counted over the last 7 days." onOpen={()=>onNavigate('missions')} tone={w.missions.failed?'warn':'idle'}/>
   <Tile label="WORKFLOW HEALTH" value={w.workflow.health==null?'No data':`${w.workflow.health}%`} sub={`${w.workflow.done} ok · ${w.workflow.failed} failed · ${w.workflow.routines_scheduled} routines scheduled`} tip="Success rate of routine and workflow runs in the last 7 days." onOpen={()=>onNavigate('workflows')} tone={w.workflow.health==null?'idle':w.workflow.health>=90?'ok':'warn'}/>
   {s?.error?<Tile label="TOKEN SPENDING" value="Unverified" sub="open Budget" tip={s.error} onOpen={()=>onNavigate('budget')} tone="warn"/>:<>
    <Tile label="SPENT TODAY" value={usd(s?.today)} sub={`of ${usd(s?.daily_cap)} · ${usd(s?.remaining_today)} left`} tip="Includes money reserved for running work. Prices are the ones you configured, not a provider invoice." onOpen={()=>onNavigate('budget')} tone={(s?.percent_today??0)>=80?'warn':'ok'}/>
    <Tile label="SPENT THIS MONTH" value={usd(s?.month)} sub={s?.monthly_cap?`of ${usd(s.monthly_cap)} · ${usd(s.remaining_month)} left`:'no monthly cap set'} tip="Month to date (UTC)." onOpen={()=>onNavigate('budget')} tone={(s?.percent_month??0)>=80?'warn':'ok'}/></>}
   <Tile label="BUDGET WARNINGS" value={String(s?.alerts?.length??0)} sub={s?.alerts?.length?s.alerts.map(a=>`${a.threshold}% ${a.period}`).join(' · '):'no threshold crossed'} tip="Alert thresholds that have fired this day or month." onOpen={()=>onNavigate('budget')} tone={s?.alerts?.length?'warn':'ok'}/>
   <Tile label="PENDING APPROVALS" value={String(w.approvals)} sub="tools and routines" tip="Tool calls and routine runs waiting for your decision." onOpen={()=>onNavigate('inbox')} tone={w.approvals?'bad':'ok'}/>
   <Tile label="COUNCIL" value={`${w.council.open_proposals} open`} sub={`${w.council.escalated} escalated · ${w.council.meetings_7d} meetings (7d) · ${w.council.members} members`} tip="Family Council proposals. Votes are recommendations; they change no permission or limit." onOpen={()=>onNavigate('family')}/>
   <Tile label="TRAINING" value={`${w.training.active_mentorships} mentorships`} sub={`${w.training.training_missions_done} training missions done · ${w.training.results_recorded} results recorded`} tip="Mentorships in progress and evaluation results recorded. Certifications are labels only." onOpen={()=>onNavigate('family')}/>
   <Tile label="CERTIFIED" value={String(Object.values(w.training.certified).reduce((a,b)=>a+b,0))} sub={Object.entries(w.training.certified).filter(([,n])=>n).map(([k,n])=>`${n} ${k}`).join(' · ')||'none yet'} tip="Bots holding a certification label from recorded evaluation results." onOpen={()=>onNavigate('family')}/>
   <section className="fam-card ck-wide" aria-label="Spending by Bot"><h2>Spending by Bot today</h2>{s?.by_bot?.length?<ul>{s.by_bot.map(b=><li key={b.bot_id}><strong>{b.name}</strong> {usd(b.spent)}</li>)}</ul>:<p className="field-hint">No Bot has spent anything today.</p>}</section>
  </div>)}
  {mode!=='workforce'&&(!src?<p>Loading…</p>:(()=>{const x=src[mode];return <div role="tabpanel" aria-label={x.title}>
   <section className="fam-card"><h2>{x.title}</h2><p className={x.connected?'notice':'field-hint'}>{x.note}</p>
    <p className="field-hint">What this view is for: {x.wants.join(', ')}.</p>
    {x.connectors.length>0&&<ul>{x.connectors.map(k=><li key={k.id}>{k.name} · {k.enabled?'enabled':'disabled'}</li>)}</ul>}
    <p className="field-hint">Credentials stay on the server in Settings, then Connectors; they are never sent to this page.</p></section></div>})())}
 </div>;
}
