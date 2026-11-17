'use client';
import {useCallback,useEffect,useState} from 'react';
import {api,send} from './api';
import {statusLabel,usd} from './model';
import type {TeamBot} from '../team/TeamDashboard';

type Objective={skill:string;target_missions:number;index:number;completed:number;failed:number;verified:number;met:boolean};
type Mentorship={id:string;status:string;mentor_id:string;mentor_name:string|null;trainee_id:string;trainee_name:string|null;objectives:Objective[];checks:{name:string;met:boolean}[];ready_to_graduate:boolean;note:string;authority_note:string};
type Estimate={max_usd:string|null;basis:string};

// Mentor and trainee relationships. A mentorship grants no permissions; training missions are normal missions you approve with the cost shown.
export default function MentorshipPanel({bots}:{bots:TeamBot[]}){
 const [items,setItems]=useState<Mentorship[]|null>(null),[note,setNote]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [form,setForm]=useState({mentor:'',trainee:'',skills:''}),[mission,setMission]=useState<{id:string;idx:number;title:string;text:string;estimate:Estimate|null}|null>(null);
 const load=useCallback(async()=>{const d=await api('/mentorships');setItems(d.mentorships);setNote(d.authority_note)},[]);
 useEffect(()=>{let live=true;api('/mentorships').then(d=>{if(live){setItems(d.mentorships);setNote(d.authority_note)}}).catch(e=>{if(live)setError((e as Error).message)});return()=>{live=false}},[]);
 async function act(fn:()=>Promise<unknown>,done:string){setBusy(true);setError('');setNotice('');try{await fn();setNotice(done);await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function suggest(){if(!form.trainee)return;try{const d=await api('/mentorships/suggest?trainee_id='+encodeURIComponent(form.trainee));setForm(f=>({...f,skills:d.objectives.map((o:{skill:string})=>o.skill).join('\n')}))}catch(e){setError((e as Error).message)}}
 async function openMission(m:Mentorship,idx:number){setError('');try{const estimate:Estimate=await api(`/mentorships/${m.id}/estimate`);setMission({id:m.id,idx,title:'',text:'',estimate})}catch(e){setError((e as Error).message)}}
 if(!items)return <section className="fam-panel">{error?<p className="error" role="alert">{error}</p>:<p>Loading mentorships…</p>}</section>;
 const skills=form.skills.split('\n').map(s=>s.trim()).filter(Boolean);
 return <section className="fam-panel" aria-label="Mentorship">
  <p className="field-hint">{note} A mentor must be at a higher career level than the trainee. Progress counts only training missions the trainee actually completed, and “verified” only counts work you marked verified.</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}
  <form className="fam-card" onSubmit={e=>{e.preventDefault();void act(async()=>{await api('/mentorships',send('POST',{mentor_id:form.mentor,trainee_id:form.trainee,objectives:skills.length?skills.map(s=>({skill:s,target_missions:2})):undefined}));setForm({mentor:'',trainee:'',skills:''})},'Mentorship started.')}}>
   <h2>Start a mentorship</h2>
   <label htmlFor="ms-mentor">Mentor</label><select id="ms-mentor" value={form.mentor} onChange={e=>setForm({...form,mentor:e.target.value})}><option value="">Choose a mentor</option>{bots.map(b=><option key={b.id} value={b.id}>{b.name}</option>)}</select>
   <label htmlFor="ms-trainee">Trainee</label><select id="ms-trainee" value={form.trainee} onChange={e=>setForm({...form,trainee:e.target.value})}><option value="">Choose a trainee</option>{bots.filter(b=>b.id!==form.mentor).map(b=><option key={b.id} value={b.id}>{b.name}</option>)}</select>
   <label htmlFor="ms-skills">Skill objectives (one per line; each needs two completed training missions)</label><textarea id="ms-skills" rows={3} maxLength={600} value={form.skills} onChange={e=>setForm({...form,skills:e.target.value})}/>
   <div className="fam-actions"><button type="button" className="secondary" disabled={!form.trainee} onClick={()=>void suggest()}>Suggest from Employee DNA</button><button disabled={busy||!form.mentor||!form.trainee}>Start mentorship</button></div>
  </form>
  {items.length===0&&<div className="mission-empty"><h2>No mentorships yet</h2><p>Pair a more experienced Bot with a newer one. Nothing runs and nothing is spent until you start a training mission.</p></div>}
  {items.map(m=><article key={m.id} className="fam-card" aria-label={`${m.mentor_name} mentors ${m.trainee_name}`}>
   <header className="fam-head"><strong>{m.mentor_name||'Deleted Bot'} → {m.trainee_name||'Deleted Bot'}</strong><span className={`mission-status ${m.status==='active'?'running':'done'}`}>{statusLabel(m.status)}</span></header>
   <ul className="fam-votes">{m.objectives.map(o=><li key={o.index}>{o.met?'✓':'○'} <strong>{o.skill}</strong>: {o.completed} of {o.target_missions} training missions completed, {o.verified} verified{o.failed>0?`, ${o.failed} failed`:''}
    {m.status==='active'&&<> <button type="button" className="secondary" disabled={busy} onClick={()=>void openMission(m,o.index)}>Start a training mission</button></>}</li>)}</ul>
   <p><strong>Graduation:</strong> {m.checks.map(c=>`${c.met?'✓':'○'} ${c.name}`).join(' · ')}</p>
   {m.status==='active'&&<div className="fam-actions"><button disabled={busy||!m.ready_to_graduate} onClick={()=>void act(()=>api(`/mentorships/${m.id}/graduate`,send('POST')),'Graduated. No permissions changed.')}>Graduate</button><button className="secondary" disabled={busy} onClick={()=>void act(()=>api(`/mentorships/${m.id}/end`,send('POST')),'Mentorship ended.')}>End</button></div>}
   {mission?.id===m.id&&<form className="fam-plan" onSubmit={e=>{e.preventDefault();void act(async()=>{await api(`/mentorships/${m.id}/training-missions`,send('POST',{objective_index:mission.idx,title:mission.title,instructions:mission.text,accept_max_usd:mission.estimate?.max_usd||'0'}));setMission(null)},'Training mission started.')}}>
    <h3>Training mission for “{m.objectives[mission.idx]?.skill}”</h3>
    <p><strong>Worst-case cost: {usd(mission.estimate?.max_usd)}.</strong> {mission.estimate?.basis}</p>
    <label htmlFor="tm-title">Title</label><input id="tm-title" required maxLength={160} value={mission.title} onChange={e=>setMission({...mission,title:e.target.value})}/>
    <label htmlFor="tm-text">Instructions</label><textarea id="tm-text" required rows={3} maxLength={6000} value={mission.text} onChange={e=>setMission({...mission,text:e.target.value})}/>
    <button disabled={busy||!mission.estimate?.max_usd||!mission.title.trim()||!mission.text.trim()}>Start and accept up to {usd(mission.estimate?.max_usd)}</button> <button type="button" className="secondary" onClick={()=>setMission(null)}>Cancel</button>
   </form>}
  </article>)}
 </section>;
}
