'use client';
import {useCallback,useEffect,useState} from 'react';
import {api,send} from './api';
import {usd} from './model';

type Settings={auto_mission_reviews:boolean;auto_system_recommendations:boolean;auto_periodic_reviews:boolean;scheduled_meetings:boolean;meeting_cooldown_hours:number;min_open_proposals:number;bots_may_propose:boolean;bots_may_give_feedback:boolean;bots_may_request:boolean;bot_daily_limit:number};
type Req={id:string;kind:'mentorship'|'training_mission';bot_name:string|null;other_name:string|null;payload:{why?:string;title?:string;instructions?:string;mentorship_id?:string};note:string};
type Overview={settings:Settings;state:{last_tick_at?:number;last_meeting_result?:string;last_activity?:{at:number;reviews:number;recommendations:number;periodic:number;meeting:boolean}};requests:Req[];note:string};

const SWITCHES:[keyof Settings,string,string][]=[
 ['auto_mission_reviews','Review finished missions automatically','Free. Writes one review per finished mission (last 14 days only).'],
 ['auto_system_recommendations','Suggest promotions when the written requirements are met','Free. Only creates a suggestion you approve or decline. Levels are labels.'],
 ['auto_periodic_reviews','Build this period’s reviews on their own','Free. At most once an hour.'],
 ['scheduled_meetings','Hold council meetings on a schedule','Paid: uses the council’s per-meeting cap, shows nothing until it fits, and stops on Global Pause.'],
 ['bots_may_propose','Let Bots propose ideas to the council','Each proposal still needs your approval before it exists.'],
 ['bots_may_give_feedback','Let Bots give peer feedback','Each note needs your approval. Never counts toward promotions.'],
 ['bots_may_request','Let Bots ask for a mentor, nominate colleagues or suggest training','These only create requests that wait for you.']];

// Everything automatic is listed here with its own switch. All are off by default and none can change a permission, budget or secret.
export default function AutomationPanel(){
 const [data,setData]=useState<Overview|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [skills,setSkills]=useState<Record<string,string>>({}),[cost,setCost]=useState<Record<string,{max:string|null;basis:string}>>({});
 const load=useCallback(async()=>{setData(await api('/family/automation'))},[]);
 useEffect(()=>{let live=true;api('/family/automation').then(d=>{if(live)setData(d)}).catch(e=>{if(live)setError((e as Error).message)});return()=>{live=false}},[]);
 async function act(fn:()=>Promise<unknown>,done:string){setBusy(true);setError('');setNotice('');try{await fn();setNotice(done);await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function showCost(r:Req){setError('');try{const e=await api(`/mentorships/${r.payload.mentorship_id}/estimate`);setCost(c=>({...c,[r.id]:{max:e.max_usd,basis:e.basis}}))}catch(e){setError((e as Error).message)}}
 if(!data)return <section className="fam-panel">{error?<p className="error" role="alert">{error}</p>:<p>Loading automation…</p>}</section>;
 const s=data.settings,st=data.state;
 const put=(patch:Partial<Settings>)=>act(()=>api('/family/automation',send('PUT',{...s,...patch})),'Saved.');
 return <section className="fam-panel" aria-label="Automation">
  <p className="field-hint">{data.note}</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}
  <div className="fam-card"><h2>Automatic actions</h2>
   {SWITCHES.map(([key,label,hint])=><div key={key}><label className="checkline"><input type="checkbox" checked={s[key] as boolean} disabled={busy} onChange={e=>void put({[key]:e.target.checked} as Partial<Settings>)}/> {label}</label><p className="field-hint">{hint}</p></div>)}
   <p className="field-hint">Scheduled meetings also need the council turned on in Family Council, and run at most once every {s.meeting_cooldown_hours} hours. Each Bot may author at most {s.bot_daily_limit} Family actions a day.</p>
   <p className="field-hint">{st.last_activity?`Last automatic activity: ${st.last_activity.reviews} mission reviews, ${st.last_activity.recommendations} suggestions${st.last_activity.meeting?', 1 meeting planned':''}.`:'Nothing automatic has run yet.'} {st.last_meeting_result||''}</p>
  </div>
  <div className="fam-card"><h2>Waiting for you ({data.requests.length})</h2>
   {data.requests.length===0&&<p>No requests. Bots can only ask; nothing happens until you decide.</p>}
   {data.requests.map(r=><article key={r.id} className="fam-plan" aria-label={`Request from ${r.bot_name}`}>
    {r.kind==='mentorship'?<>
     <p><strong>{r.bot_name}</strong> asks for <strong>{r.other_name}</strong> as a mentor.{r.payload.why?` “${r.payload.why}”`:''}</p>
     <label htmlFor={`rq-sk-${r.id}`}>Skill objectives (one per line)</label><textarea id={`rq-sk-${r.id}`} rows={2} maxLength={600} value={skills[r.id]||''} onChange={e=>setSkills({...skills,[r.id]:e.target.value})}/>
     <div className="fam-actions"><button disabled={busy} onClick={()=>void act(()=>api(`/family/requests/${r.id}/decision`,send('POST',{approve:true,objectives:(skills[r.id]||'').split('\n').map(x=>x.trim()).filter(Boolean)})),'Mentorship started. No permissions changed.')}>Approve mentorship</button><button className="secondary" disabled={busy} onClick={()=>void act(()=>api(`/family/requests/${r.id}/decision`,send('POST',{approve:false})),'Declined.')}>Decline</button></div></>:<>
     <p>Mentor <strong>{r.bot_name}</strong> suggests a training mission for <strong>{r.other_name}</strong>: “{r.payload.title}”.</p><p className="field-hint">{r.payload.instructions}</p>
     {cost[r.id]?<p><strong>Worst-case cost: {usd(cost[r.id].max)}.</strong> {cost[r.id].basis}</p>:<button className="secondary" disabled={busy} onClick={()=>void showCost(r)}>Show worst-case cost</button>}
     <div className="fam-actions"><button disabled={busy||!cost[r.id]?.max} onClick={()=>void act(()=>api(`/family/requests/${r.id}/decision`,send('POST',{approve:true,accept_max_usd:cost[r.id].max})),'Training mission started.')}>Start and accept up to {usd(cost[r.id]?.max)}</button><button className="secondary" disabled={busy} onClick={()=>void act(()=>api(`/family/requests/${r.id}/decision`,send('POST',{approve:false})),'Declined.')}>Decline</button></div></>}
    <p className="field-hint">{r.note}</p>
   </article>)}
  </div>
 </section>;
}
