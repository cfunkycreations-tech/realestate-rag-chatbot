'use client';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import BotAvatar from '../team/BotAvatar';
import type {TeamBot} from '../team/TeamDashboard';
import {PLAYBOOKS} from './playbooks';
import {STAGES} from './Stages';

async function call(path:string,init?:RequestInit){
 const res=await fetch('/api'+path,{cache:'no-store',...init,headers:{'Content-Type':'application/json',...init?.headers}});
 const data=await res.json().catch(()=>({}));
 if(!res.ok)throw Error(typeof data.detail==='string'?data.detail:'That did not work. Try again.');
 return data;
}

// "What you get" pages. The stage is SAMPLE OUTPUT. The Bot shown is yours; "Set up" only creates a PAUSED routine you review first.
export default function PlaybooksView({bots,onHire,onRoutines}:{bots:TeamBot[];onHire:()=>void;onRoutines:()=>void}){
 const [index,setIndex]=useState(0),[tick,setTick]=useState(0),[playing,setPlaying]=useState(false),[assign,setAssign]=useState<Record<string,string>>({}),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [reduced,setReduced]=useState(false),lock=useRef(false);
 const p=PLAYBOOKS[index],Stage=STAGES[p.id];
 useEffect(()=>{const q=window.matchMedia('(prefers-reduced-motion: reduce)');const sync=()=>setReduced(q.matches);sync();if(q.matches===false)setPlaying(true);q.addEventListener('change',sync);return()=>q.removeEventListener('change',sync)},[]);
 useEffect(()=>{if(!playing)return;const t=window.setInterval(()=>setTick(n=>n+1),reduced?3600:2400);return()=>window.clearInterval(t)},[playing,reduced]);
 useEffect(()=>{let live=true;call('/playbooks/assignments').then(d=>{if(live)setAssign(d.assignments)}).catch(e=>{if(live)setError((e as Error).message)});return()=>{live=false}},[]);
 const bot=useMemo(()=>bots.find(b=>b.id===assign[p.id])||null,[bots,assign,p.id]);
 const step=tick%8;
 const choose=useCallback(async(id:string)=>{setError('');setNotice('');try{const d=await call(`/playbooks/assignments/${p.id}`,{method:'PUT',body:JSON.stringify({bot_id:id||null})});setAssign(d.assignments)}catch(e){setError((e as Error).message)}},[p.id]);
 async function setup(){
  if(!bot||lock.current)return;lock.current=true;setBusy(true);setError('');setNotice('');
  try{
   const tz=Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC';
   const made=await call('/routines',{method:'POST',body:JSON.stringify({title:`${p.name} playbook`,instructions:p.brief,bot_id:bot.id,cron:p.cron,timezone:tz,paused:true})});
   if(!made.id)throw Error('That did not work. Try again.');
   setNotice(`Created a PAUSED routine for ${bot.name}. Nothing runs or spends until you review it in Routines and resume it.`);
  }catch(e){setError((e as Error).message)}finally{lock.current=false;setBusy(false)}
 }
 const [a,b,c]=p.head,[s1,s2,s3]=p.sub;
 return <div className="missions-view pb-view" style={{['--pb' as string]:p.accent}}>
  <nav className="pb-tabs" aria-label="Playbooks" role="tablist">{PLAYBOOKS.map((x,i)=><button key={x.id} type="button" role="tab" aria-selected={i===index} aria-label={`Bot ${x.n}: ${x.name}`} className={i===index?'active':''} style={{['--pb' as string]:x.accent}} onClick={()=>{setIndex(i);setTick(0);setNotice('');setError('')}}><b>{x.n}</b><span>{x.name}</span></button>)}</nav>
  <article className="pb-page-card" aria-label={`${p.name} playbook`}>
   <header className="pb-top"><div className="pb-bot">{bot?<BotAvatar bot={bot} size="xl" working={playing&&!reduced}/>:<span className="pb-empty" role="img" aria-label="No Bot chosen yet">+</span>}<span className="pb-eyebrow">BOT {p.n} — {p.name.toUpperCase()} — WHAT YOU GET</span></div><span className="pb-sample" title="Everything in the panel below is an illustration, not your data">SAMPLE OUTPUT</span></header>
   <h1 className="pb-title">{a}<em>{b}</em>{c}</h1>
   <p className="pb-sub">{s1}<strong>{s2}</strong>{s3}</p>
   <div className="pb-stage" aria-label="Sample output (illustration)"><Stage f={tick} pill={p.pill}/></div>
   <div className="pb-steps" role="list" aria-label="How it works, 8 steps"><div className="pb-steps-head"><small>HOW IT WORKS</small><b>8 steps</b><button type="button" className="pb-play" aria-pressed={!playing} onClick={()=>setPlaying(v=>!v)}>{playing?'Pause':'Play'}</button></div>{p.steps.map((s,i)=><button key={s.name} type="button" role="listitem" className={`pb-step${i===step?' on':''}`} aria-current={i===step?'step':undefined} onClick={()=>{setPlaying(false);setTick(i)}}><small>{String(i+1).padStart(2,'0')}</small><b>{s.name}</b><span>{s.hint}</span></button>)}</div>
   <dl className="pb-facts"><div><dt>RUNS</dt><dd>{p.runs}</dd></div><div><dt>REPLACES</dt><dd>{p.replaces}</dd></div><div><dt>NEVER</dt><dd>{p.never}</dd></div><div className="pb-accent-cell"><dt>{p.ruleLabel}</dt><dd>{p.rule}</dd></div></dl>
   <section className="pb-use" aria-label="Use this playbook">
    <p className={`pb-reality ${p.reality.ready?'ready':'needs'}`}><strong>{p.reality.ready?'Works today.':'Needs a source.'}</strong> {p.reality.text}</p>
    {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice} <button type="button" className="linkish" onClick={onRoutines}>Open Routines</button></p>}
    {bots.length===0?<div className="pb-actions-row"><p>You have no Bots yet.</p><button type="button" onClick={onHire}>Hire a Bot</button></div>:
    <div className="pb-actions-row"><label htmlFor={`pb-bot-${p.id}`}>Bot for this playbook</label><select id={`pb-bot-${p.id}`} value={assign[p.id]||''} onChange={e=>void choose(e.target.value)}><option value="">Choose a Bot</option>{bots.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select>
     <button type="button" disabled={!bot||busy} onClick={()=>void setup()}>Set up as a paused routine</button></div>}
    <p className="field-hint">Choosing a Bot only changes the picture. “Set up” saves this playbook’s instructions as a routine that starts paused; every tool still follows your approval settings.</p>
   </section>
  </article>
 </div>;
}
