'use client';
import {useCallback,useEffect,useState} from 'react';
import {api,send} from './api';
import {statusLabel,tallyText,usd,voteWord,type Proposal} from './model';
import type {TeamBot} from '../team/TeamDashboard';

type Meeting={id:string;status:string;members:{id:string;name:string}[];proposal_ids:string[];estimate_usd:string;cap_usd:string;spent_usd:string;error:string|null;created_at:number;basis:string};
type Overview={settings:{enabled:boolean;max_members:number;max_proposals_per_meeting:number;meeting_max_usd:string;reply_timeout_seconds:number;max_open_proposals:number};members:{id:string;name:string}[];kinds:string[];owner_only_kinds:string[];proposals:Proposal[];meetings:Meeting[];authority_note:string};
const KIND_LABEL=(k:string)=>k.charAt(0).toUpperCase()+k.slice(1);

// Owner's Council desk. Every action here is the owner's click; the council itself can only recommend.
export default function CouncilPanel({bots}:{bots:TeamBot[]}){
 const [data,setData]=useState<Overview|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [form,setForm]=useState({title:'',body:'',kind:'workflow'}),[picked,setPicked]=useState<string[]>([]),[plan,setPlan]=useState<Meeting|null>(null),[cap,setCap]=useState('');
 const load=useCallback(async(signal?:AbortSignal)=>{const d:Overview=await api('/council',{signal});if(!signal?.aborted){setData(d);setCap(c=>c||d.settings.meeting_max_usd)}},[]);
 useEffect(()=>{
  const ac=new AbortController();let timer:ReturnType<typeof setTimeout>;
  async function poll(){
   if(document.visibilityState==='visible'){try{await load(ac.signal)}catch(e){if(!ac.signal.aborted)setError((e as Error).message)}}
   if(!ac.signal.aborted)timer=setTimeout(poll,4000);
  }
  void poll();return()=>{ac.abort();clearTimeout(timer)};
 },[load]);
 async function act(fn:()=>Promise<unknown>,done='Saved.'){setBusy(true);setError('');setNotice('');try{await fn();setNotice(done);await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 const names=Object.fromEntries(bots.map(b=>[b.id,b.name]));
 if(!data)return <section className="fam-panel">{error?<p className="error" role="alert">{error}</p>:<p>Loading the council…</p>}</section>;
 const s=data.settings,memberIds=data.members.map(m=>m.id),open=data.proposals.filter(p=>p.status==='open'),live=data.meetings.find(m=>m.status==='running');
 const enrolled=picked.length?picked:memberIds;
 return <section className="fam-panel" aria-label="Family Council">
  <p className="field-hint">{data.authority_note} A meeting is the only thing here that can spend money: one short reply per member, started by you, with a worst-case cost shown first.</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}
  <div className="fam-card"><h2>Council settings</h2>
   <label className="checkline"><input type="checkbox" checked={s.enabled} disabled={busy} onChange={e=>void act(()=>api('/council/settings',send('PUT',{...s,enabled:e.target.checked})))}/> Allow council meetings</label>
   <p className="field-hint">Off by default and costs nothing while off. Meetings never start on their own.</p>
   <label>Spending cap per meeting (USD)<input inputMode="decimal" value={cap} onChange={e=>setCap(e.target.value)}/></label>
   <button className="secondary" disabled={busy} onClick={()=>void act(()=>api('/council/settings',send('PUT',{...s,meeting_max_usd:cap})))}>Save cap</button>
   <fieldset className="fam-members"><legend>Council members (the order they vote in; up to {s.max_members})</legend>
    {bots.map(b=><label key={b.id} className="checkline"><input type="checkbox" checked={enrolled.includes(b.id)} onChange={e=>setPicked(e.target.checked?[...enrolled,b.id]:enrolled.filter(x=>x!==b.id))}/> {b.name}</label>)}
    {bots.length===0&&<p>Create some Bots first.</p>}
   </fieldset>
   <button className="secondary" disabled={busy||bots.length===0} onClick={()=>void act(async()=>{await api('/council/members',send('PUT',{bot_ids:enrolled}));setPicked([])},'Members saved.')}>Save members</button>
  </div>
  <form className="fam-card" onSubmit={e=>{e.preventDefault();void act(async()=>{await api('/council/proposals',send('POST',form));setForm({...form,title:'',body:''})},'Proposal added.')}}>
   <h2>New proposal</h2>
   <label htmlFor="fam-title">Title</label><input id="fam-title" required maxLength={160} value={form.title} onChange={e=>setForm({...form,title:e.target.value})}/>
   <label htmlFor="fam-kind">Type</label><select id="fam-kind" value={form.kind} onChange={e=>setForm({...form,kind:e.target.value})}>{data.kinds.map(k=><option key={k} value={k}>{KIND_LABEL(k)}{data.owner_only_kinds.includes(k)?' (you decide)':''}</option>)}</select>
   <label htmlFor="fam-body">What should change, and why?</label><textarea id="fam-body" required maxLength={2000} rows={3} value={form.body} onChange={e=>setForm({...form,body:e.target.value})}/>
   <button disabled={busy||!form.title.trim()||!form.body.trim()}>Add proposal</button>
  </form>
  <div className="fam-card"><h2>Meeting</h2>
   {live&&<p role="status">A meeting is in session. {live.members.length} members, spending so far {usd(live.spent_usd)} of a {usd(live.cap_usd)} cap.</p>}
   {!plan&&<button disabled={busy||!s.enabled||open.length===0||Boolean(live)} onClick={()=>void act(async()=>{setPlan(await api('/council/meetings',send('POST',{proposal_ids:open.slice(0,s.max_proposals_per_meeting).map(p=>p.id)})))},'Meeting planned. Review the cost, then start it.')}>Plan a meeting on {Math.min(open.length,s.max_proposals_per_meeting)} open proposal{open.length===1?'':'s'}</button>}
   {!s.enabled&&<p className="field-hint">Turn the council on to plan a meeting.</p>}
   {plan&&<div className="fam-plan" role="group" aria-label="Meeting cost">
    <p><strong>Worst-case cost: {usd(plan.estimate_usd)}</strong> (cap {usd(plan.cap_usd)}). {plan.members.map(m=>m.name).join(', ')} each give one short reply. {plan.basis}</p>
    <button disabled={busy} onClick={()=>void act(async()=>{await api(`/council/meetings/${plan.id}/start`,send('POST'));setPlan(null)},'Meeting started.')}>Start meeting</button>
    <button className="secondary" disabled={busy} onClick={()=>void act(async()=>{await api(`/council/meetings/${plan.id}/cancel`,send('POST'));setPlan(null)},'Meeting cancelled.')}>Cancel</button>
   </div>}
   {live&&<button className="secondary" disabled={busy} onClick={()=>void act(()=>api(`/council/meetings/${live.id}/cancel`,send('POST')),'Meeting stopped.')}>Stop the meeting</button>}
  </div>
  <h2>Proposals and decisions</h2>
  {data.proposals.length===0&&<div className="mission-empty"><h2>No proposals yet</h2><p>Add one above. Nothing is decided, and nothing is spent, until you hold a meeting.</p></div>}
  {data.proposals.map(p=><article key={p.id} className="fam-card" aria-label={p.title}>
   <header className="fam-head"><strong>{p.title}</strong><span className={`mission-status ${p.status}`}>{statusLabel(p.status)}</span></header>
   <p className="fam-meta">{p.kind}{p.requires_owner?' · you decide':''} · proposed by {p.proposer==='owner'?'you':'a Bot'}</p>
   <p>{p.body}</p>
   {p.tally&&<p><strong>{tallyText(p.tally)}.</strong> {p.rationale}</p>}
   {p.votes.length>0&&<details><summary>Votes ({p.votes.length})</summary><ul className="fam-votes">{p.votes.map(v=><li key={v.id}><strong>{v.voter_name}</strong>: {voteWord(v.vote)}. {v.rationale}{v.evidence.cited_missions_discarded>0&&<small> ({v.evidence.cited_missions_discarded} cited mission(s) did not check out and were ignored)</small>}</li>)}</ul></details>}
   {(p.status==='escalated'||p.status==='passed'||p.status==='open')&&<div className="fam-actions">
    {p.status==='open'&&<button className="secondary" disabled={busy} onClick={()=>void act(()=>api(`/council/proposals/${p.id}`,send('DELETE')),'Withdrawn.')}>Withdraw</button>}
    <button className="secondary" disabled={busy} onClick={()=>void act(()=>api(`/council/proposals/${p.id}/decision`,send('POST',{approve:true,note:''})),'Recorded: you approved.')}>I approve</button>
    <button className="secondary" disabled={busy} onClick={()=>void act(()=>api(`/council/proposals/${p.id}/decision`,send('POST',{approve:false,note:''})),'Recorded: you declined.')}>I decline</button>
   </div>}
  </article>)}
  <h2>Meeting records</h2>
  {data.meetings.length===0&&<p className="field-hint">No meetings yet.</p>}
  <ul className="fam-records">{data.meetings.map(m=><li key={m.id}><strong>{new Date(m.created_at*1000).toLocaleString()}</strong> · {statusLabel(m.status)} · {m.members.map(x=>names[x.id]||x.name).join(', ')} · spent {usd(m.spent_usd)} (worst case {usd(m.estimate_usd)}){m.error&&<span className="error"> · {m.error}</span>}</li>)}</ul>
 </section>;
}
