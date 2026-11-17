'use client';
import {useCallback,useEffect,useState} from 'react';
import {api,send} from './api';
import {LEVEL_ORDER,criterionText,eligibilityText,levelLabel,percent,statusLabel,type Eligibility} from './model';
import type {TeamBot} from '../team/TeamDashboard';

type Row={bot_id:string;name:string;title:string;level:string;label:string;source:string;next:string|null;eligible:boolean;completed:number;verified:number;reliability_percent:number|null;pending:{id:string;to_level:string;source:string;rationale:string}|null};
type Overview={bots:Row[];levels:{key:string;label:string}[];authority_note:string};
type Unverified={id:string;title:string;bots:string|null};
type Metrics={completed:number;failed:number;verified:number;rejected:number;reliability_percent:number|null;quality_percent:number|null;collaborators:number;mentees_graduated:number;training_missions_completed:number;note:string};
type Review={id:string;kind:string;period_key:string;level:string;created_at:number};
type Profile={bot_id:string;name:string;title:string;level:string;label:string;since:number;source:string;next:string|null;eligibility:Eligibility;metrics:Metrics;history:{event:string;detail:string;created_at:number}[];recommendations:{id:string;to_level:string;source:string;rationale:string;status:string;decision_note:string}[];reviews:Review[]};
type ReviewDetail={id:string;kind:string;period:string;level:string;metrics:Metrics;evidence:{mission_id:string;title:string;status:string;verdict:string|null}[];strengths:string[];development:{areas:string[];recommended_training:string[]};feedback:{items:{id:string;from_name:string;role:string;rating:number;comment:string}[];count:number;mean:number|null}};

// The owner's view of every Bot's career. A level is only a label: promoting never changes permissions, spending or secrets.
export default function CareerCenter({bots}:{bots:TeamBot[]}){
 const [data,setData]=useState<Overview|null>(null),[todo,setTodo]=useState<Unverified[]>([]),[open,setOpen]=useState(''),[loaded,setProfile]=useState<Profile|null>(null),[skills,setSkills]=useState<string[]>([]);
 const [review,setReview]=useState<ReviewDetail|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[rating,setRating]=useState(4),[comment,setComment]=useState('');
 const load=useCallback(async()=>{const [d,u]=await Promise.all([api('/career'),api('/career/unverified')]);setData(d);setTodo(u)},[]);
 useEffect(()=>{let live=true;Promise.all([api('/career'),api('/career/unverified')]).then(([d,u])=>{if(live){setData(d);setTodo(u)}}).catch(e=>{if(live)setError((e as Error).message)});return()=>{live=false}},[]);
 useEffect(()=>{
  if(!open)return;
  let live=true;
  Promise.all([api('/career/'+open),api('/bots/'+open+'/career').catch(()=>null)]).then(([p,c])=>{if(!live)return;setProfile(p);const list=c?.career?.skills||c?.career?.competencies||[];setSkills(Array.isArray(list)?list.filter((x:unknown)=>typeof x==='string').slice(0,12):[])}).catch(e=>{if(live)setError((e as Error).message)});
  return()=>{live=false};
 },[open,data]);
 async function act(fn:()=>Promise<unknown>,done:string){setBusy(true);setError('');setNotice('');try{const r=await fn();setNotice(typeof r==='string'?r:done);await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 const byId=Object.fromEntries(bots.map(b=>[b.id,b]));
 const profile=open&&loaded&&loaded.bot_id===open?loaded:null;
 function choose(id:string){setOpen(id);setReview(null);setSkills([])}
 if(!data)return <section className="fam-panel">{error?<p className="error" role="alert">{error}</p>:<p>Loading careers…</p>}</section>;
 return <section className="fam-panel" aria-label="Career Center">
  <p className="field-hint">{data.authority_note} “Completed” is a Bot’s own report that a mission finished; only work you mark verified counts as verified. Reviews and requirements are counted from records and cost nothing.</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}
  <ol className="fam-ladder" aria-label="Career levels">{LEVEL_ORDER.map(k=><li key={k}>{levelLabel(k)}<small>{data.bots.filter(b=>b.level===k).length}</small></li>)}</ol>
  <div className="fam-actions"><button className="secondary" disabled={busy} onClick={()=>void act(async()=>{const r=await api('/career/reviews/run',send('POST'));return `${r.built} new review${r.built===1?'':'s'} built.`},'Reviews are up to date.')}>Run this period’s reviews (free)</button></div>
  {todo.length>0&&<div className="fam-card"><h2>Check finished work ({todo.length})</h2><p className="field-hint">Tell us which completed missions were really good. This is the only way work becomes “verified”.</p>
   <ul className="fam-votes">{todo.slice(0,8).map(m=><li key={m.id}><strong>{m.title}</strong>{m.bots&&<small> by {m.bots}</small>} <button className="secondary" disabled={busy} onClick={()=>void act(()=>api(`/missions/${m.id}/verification`,send('PUT',{verdict:'verified',note:''})),'Marked verified.')}>Verified</button> <button className="secondary" disabled={busy} onClick={()=>void act(()=>api(`/missions/${m.id}/verification`,send('PUT',{verdict:'rejected',note:''})),'Marked not good enough.')}>Not good enough</button></li>)}</ul></div>}
  {data.bots.length===0&&<div className="mission-empty"><h2>No Bots yet</h2><p>Create a Bot and its career record starts here.</p></div>}
  <div className="fam-grid">{data.bots.map(b=><article key={b.bot_id} className={`fam-card${open===b.bot_id?' open':''}`} aria-label={b.name}>
   <button type="button" className="bc-head" aria-expanded={open===b.bot_id} onClick={()=>choose(open===b.bot_id?'':b.bot_id)}><span className="bc-route"><strong>{b.name}</strong> <small>{byId[b.bot_id]?.title||b.title}</small></span><span className="mission-status done">{b.label}</span></button>
   <dl className="bc-facts"><div><dt>Completed</dt><dd>{b.completed}</dd></div><div><dt>Verified by you</dt><dd>{b.verified}</dd></div><div><dt>Reliability</dt><dd>{percent(b.reliability_percent)}</dd></div></dl>
   {b.pending?<p role="status">Recommended for {levelLabel(b.pending.to_level)} ({b.pending.source}). Waiting for you.</p>:b.eligible&&b.next?<p>Meets the requirements for {levelLabel(b.next)}.</p>:null}
  </article>)}</div>
  {profile&&<aside className="fam-card fam-profile" aria-label={`${profile.name} profile`}>
   <header className="fam-head"><h2>{profile.name} · {profile.label}</h2><button type="button" className="secondary" onClick={()=>choose('')}>Close</button></header>
   <p className="fam-meta">{profile.title||'No job title'} · level source: {profile.source} · {eligibilityText(profile.eligibility)}</p>
   {skills.length>0&&<><h3>Skills (from Employee DNA)</h3><p>{skills.join(' · ')}</p></>}
   <h3>Requirements for {profile.next?levelLabel(profile.next):'—'}</h3>
   <ul className="fam-votes">{profile.eligibility.criteria.map(c=><li key={c.key}>{c.met?'✓':'○'} {criterionText(c)}</li>)}</ul>
   <h3>Development plan</h3>
   <ul className="fam-votes">{profile.eligibility.criteria.filter(c=>!c.met).map(c=><li key={c.key}>{criterionText(c)}</li>)}{profile.eligibility.criteria.every(c=>c.met)&&<li>All requirements for the next level are met.</li>}</ul>
   <div className="fam-actions">
    {profile.next&&!profile.recommendations.some(r=>r.status==='pending')&&<button disabled={busy||!profile.eligibility.eligible} title={profile.eligibility.eligible?'':'Not yet eligible'} onClick={()=>void act(()=>api(`/career/${profile.bot_id}/recommendations`,send('POST',{to_level:profile.next,source:'system',rationale:''})),'Recommendation recorded. Nothing changes until you approve it.')}>Recommend for {levelLabel(profile.next)}</button>}
    <button className="secondary" disabled={busy} onClick={()=>void act(async()=>{const r=await api(`/career/${profile.bot_id}/reviews`,send('POST',{kind:'periodic'}));setReview(await api('/career/reviews/'+r.id))},'Review ready.')}>Build this period’s review</button>
   </div>
   {profile.recommendations.filter(r=>r.status==='pending').map(r=><div key={r.id} className="fam-plan" role="group" aria-label="Promotion recommendation"><p><strong>Recommended for {levelLabel(r.to_level)}</strong> ({r.source}). {r.rationale}</p><p className="field-hint">Approving only changes this label. Tool permissions, spending limits and access to secrets stay exactly as they are.</p>
    <button disabled={busy} onClick={()=>void act(()=>api(`/career/recommendations/${r.id}/decision`,send('POST',{approve:true,note:''})),'Promoted. No permissions changed.')}>Approve promotion</button> <button className="secondary" disabled={busy} onClick={()=>void act(()=>api(`/career/recommendations/${r.id}/decision`,send('POST',{approve:false,note:''})),'Declined.')}>Decline</button> <button className="secondary" disabled={busy} onClick={()=>void act(()=>api(`/career/recommendations/${r.id}`,send('DELETE')),'Withdrawn.')}>Withdraw</button></div>)}
   {profile.reviews.length>0&&<><h3>Review history</h3><ul className="fam-votes">{profile.reviews.map(r=><li key={r.id}><button className="secondary" onClick={()=>void api('/career/reviews/'+r.id).then(setReview).catch(e=>setError((e as Error).message))}>{r.kind==='periodic'?`Period ${r.period_key}`:'Mission review'} · {levelLabel(r.level)}</button></li>)}</ul></>}
   {review&&<div className="fam-plan" role="region" aria-label="Review"><h3>Review: {review.period} ({levelLabel(review.level)})</h3>
    <p>Completed {review.metrics.completed}, failed {review.metrics.failed}, verified {review.metrics.verified}, not good enough {review.metrics.rejected}. Reliability {percent(review.metrics.reliability_percent)}; quality {percent(review.metrics.quality_percent)}.</p>
    {review.strengths.length>0&&<><strong>Strengths</strong><ul>{review.strengths.map(x=><li key={x}>{x}</li>)}</ul></>}
    {review.development.areas.length>0&&<><strong>Development areas</strong><ul>{review.development.areas.map(x=><li key={x}>{x}</li>)}</ul></>}
    {review.development.recommended_training.length>0&&<><strong>Recommended training</strong><ul>{review.development.recommended_training.map(x=><li key={x}>{x}</li>)}</ul></>}
    {review.evidence.length>0&&<><strong>Evidence</strong><ul>{review.evidence.map(e=><li key={e.mission_id}>{e.title} — {e.status}{e.verdict?`, ${statusLabel(e.verdict)}`:''}</li>)}</ul></>}
    <strong>Feedback ({review.feedback.count}{review.feedback.mean?`, average ${review.feedback.mean}`:''}) — shown for context; never counted toward promotion</strong>
    <ul>{review.feedback.items.map(f=><li key={f.id}>{f.from_name} ({f.role}): {f.rating}/5. {f.comment}</li>)}</ul>
    <label htmlFor="fb-rating">Your rating (1–5)</label><select id="fb-rating" value={rating} onChange={e=>setRating(Number(e.target.value))}>{[1,2,3,4,5].map(n=><option key={n} value={n}>{n}</option>)}</select>
    <label htmlFor="fb-comment">Your comment</label><input id="fb-comment" maxLength={500} value={comment} onChange={e=>setComment(e.target.value)}/>
    <button className="secondary" disabled={busy||!comment.trim()} onClick={()=>void act(async()=>{await api(`/career/reviews/${review.id}/feedback`,send('POST',{rating,comment}));setComment('');setReview(await api('/career/reviews/'+review.id))},'Feedback added.')}>Add your feedback</button></div>}
   <h3>Career history</h3>
   {profile.history.length===0?<p className="field-hint">Nothing recorded yet.</p>:<ul className="fam-votes">{profile.history.map((h,i)=><li key={i}><time>{new Date(h.created_at*1000).toLocaleDateString()}</time> {h.detail}</li>)}</ul>}
  </aside>}
 </section>;
}
