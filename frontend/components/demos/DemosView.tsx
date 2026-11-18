'use client';
import {useEffect,useMemo,useState} from 'react';
import {DEMOS,type Row} from './demos';

const GROUPS=['Team','Work','Automation','Control'] as const;
const mark:Record<Row['k'],string>={you:'You',bot:'',do:'▶',ok:'✓',hold:'⏸',stat:'●',note:'ℹ'};

// Guided demos. Everything shown is SAMPLE content: no model call, no spending, none of the owner's data.
export default function DemosView({onOpen}:{onOpen:(t:{view?:string;settings?:string})=>void}){
 const [id,setId]=useState(DEMOS[0].id),[step,setStep]=useState(0),[playing,setPlaying]=useState(false),[group,setGroup]=useState<string>('All'),[reduced,setReduced]=useState(false);
 const d=useMemo(()=>DEMOS.find(x=>x.id===id)||DEMOS[0],[id]);
 const last=d.steps.length-1;
 useEffect(()=>{const q=window.matchMedia('(prefers-reduced-motion: reduce)');const s=()=>setReduced(q.matches);s();q.addEventListener('change',s);return()=>q.removeEventListener('change',s)},[]);
 useEffect(()=>{
  if(!playing)return;
  const t=window.setTimeout(()=>{if(step>=last)setPlaying(false);else setStep(step+1)},reduced?3200:2200);
  return()=>window.clearTimeout(t);
 },[playing,step,last,reduced]);
 function pick(next:string){setId(next);setStep(0);setPlaying(true)}
 function toggle(){if(playing){setPlaying(false);return}if(step>=last)setStep(0);setPlaying(true)}
 const shown=d.steps.slice(0,step+1);
 const list=DEMOS.filter(x=>group==='All'||x.group===group);
 return <div className="dm-view" style={{['--dm' as string]:d.accent}}>
  <header className="missions-heading"><div><p className="eyebrow">SEE IT WORK</p><h1>Demos</h1><p>One short demo for each part of Funk Bot. Press Play and watch. Everything here is sample content: nothing is sent, spent or changed.</p></div></header>
  <div className="dm-groups" role="group" aria-label="Filter demos">{['All',...GROUPS].map(g=><button key={g} type="button" aria-pressed={group===g} className={group===g?'on':''} onClick={()=>setGroup(g)}>{g}</button>)}</div>
  <nav className="dm-tabs" aria-label="Demos" role="tablist">{list.map(x=><button key={x.id} type="button" role="tab" aria-selected={x.id===id} className={x.id===id?'on':''} onClick={()=>pick(x.id)}>{x.name}</button>)}</nav>
  <article className="dm-card" aria-label={`${d.name} demo`}>
   <header className="dm-head"><div><span className="dm-badge">SAMPLE · NOTHING REAL RUNS</span><h2>{d.name}</h2><p>{d.line}</p></div>
    <button type="button" className="primary dm-play" onClick={toggle} aria-pressed={playing}>{playing?'Pause':step>=last?'Replay':'Play'}</button></header>
   <ol className="dm-steps" aria-label="Steps">{d.steps.map((s,i)=><li key={s.name}><button type="button" className={i===step?'on':i<step?'done':''} aria-current={i===step?'step':undefined} onClick={()=>{setPlaying(false);setStep(i)}}><small>{String(i+1).padStart(2,'0')}</small><b>{s.name}</b></button></li>)}</ol>
   <p className="dm-say" role="status" aria-live="polite"><b>Step {step+1}.</b> {d.steps[step].say}</p>
   <div className="dm-stage" aria-label="Sample screen">{shown.flatMap((s,si)=>s.rows.map((r,ri)=><div key={`${si}-${ri}`} className={`dm-row k-${r.k}${si===step?' new':''}`}>{r.k==='bot'?<><b>{r.who}</b><span>{r.t}</span></>:<><i aria-hidden>{mark[r.k]}</i><span>{r.t}</span></>}</div>))}</div>
   <div className="dm-foot"><button type="button" className="secondary" onClick={()=>onOpen(d.open)}>{d.open.label} →</button><span className="field-hint">That opens the real screen with your real data.</span></div>
  </article>
 </div>;
}
