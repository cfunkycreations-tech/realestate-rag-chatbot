'use client';
import {useEffect, useMemo, useRef, useState} from 'react';
import {ArrowRight, Dices, Download, Search, Upload} from 'lucide-react';

export type RolePreset = {
  id:string; title:string; department:string; level:string; model_tier:string; personality:string;
  job_description:string; instructions:string; responsibilities:string[]; specializations:string[];
  competencies:string[]; career_path:string[]; mentorship_eligible:boolean; version:number; customized:boolean;
};
export type Career = {
  preset_id:string; preset_version:number; level:string; department:string; model_tier:string;
  career:RolePreset; history:{event:string;detail:Record<string,unknown>;created_at:number}[];
};
type Born = {id:string; character:unknown; career:Career};
type Outcome = {id:string|null; outcome:string; detail?:string};

async function call(path:string, init?:RequestInit){
  const res=await fetch('/api'+path,{...init,headers:{'Content-Type':'application/json',...init?.headers}});
  if(!res.ok){const data=await res.json().catch(()=>({}));throw new Error(typeof data.detail==='string'?data.detail:'Something went wrong. Please try again.')}
  return res.json();
}
export function slug(title:string){return title.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'')}
export function summarize(results:Outcome[]){
  const count=(o:string)=>results.filter(r=>r.outcome===o).length;
  const parts=[[count('created'),'added'],[count('new_version'),'updated'],[count('unchanged'),'unchanged'],[count('skipped_customized'),'kept (your edits)'],[count('invalid'),'invalid']] as const;
  return parts.filter(([n])=>n>0).map(([n,label])=>`${n} ${label}`).join(' · ')||'Nothing to import.';
}
/** Accepts a bare list of presets or an exported pack ({presets:[...]}). */
export function readPack(text:string):unknown[]{
  const data=JSON.parse(text);
  const list=Array.isArray(data)?data:data&&Array.isArray(data.presets)?data.presets:null;
  if(!list||!list.length)throw new Error('This file has no role presets. Expected a list, or an object with a "presets" list.');
  return list;
}
const label=(value:string)=>value.charAt(0).toUpperCase()+value.slice(1).toLowerCase();

export function CareerSummary({botId}:{botId:string}){
  const [career,setCareer]=useState<Career|null>(null);
  useEffect(()=>{let live=true;call(`/bots/${botId}/career`).then(d=>{if(live)setCareer(d.career)}).catch(()=>{});return()=>{live=false}},[botId]);
  if(!career)return null;
  return <div className="career-summary" aria-label="Career DNA"><span className="career-chip strong">{career.career.title}</span><span className="career-chip">{career.department}</span><span className="career-chip">{label(career.level)}</span><span className="career-chip">{label(career.model_tier)} tier</span><span className="career-chip dim">Role v{career.preset_version}</span></div>;
}

export default function CareerBirth({starter,onBorn,onCancel}:{starter:{title:string;personality:string}[];onBorn:(born:Born)=>void;onCancel:()=>void}){
  const [presets,setPresets]=useState<RolePreset[]|null>(null),[query,setQuery]=useState(''),[picked,setPicked]=useState(''),[busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const file=useRef<HTMLInputElement>(null);
  useEffect(()=>{let live=true;call('/role-presets').then((list:RolePreset[])=>{if(live)setPresets(list)}).catch((e:Error)=>{if(live){setError(e.message);setPresets([])}});return()=>{live=false}},[]);
  async function load(){setPresets(await call('/role-presets'))}
  const groups=useMemo(()=>{
    const q=query.trim().toLowerCase(),out=new Map<string,RolePreset[]>();
    for(const p of presets||[]){if(q&&!(p.title+' '+p.department).toLowerCase().includes(q))continue;out.set(p.department,[...(out.get(p.department)||[]),p])}
    return [...out.entries()];
  },[presets,query]);
  const selected=(presets||[]).find(p=>p.id===picked);
  async function importList(list:unknown[]){
    setBusy('import');setError('');setNotice('');
    try{const result=await call('/role-presets/import',{method:'POST',body:JSON.stringify({presets:list})});setNotice(summarize(result.results));const bad=(result.results as Outcome[]).find(r=>r.outcome==='invalid');if(bad)setError(`${bad.id||'A preset'}: ${bad.detail}`);await load()}
    catch(e){setError((e as Error).message)}finally{setBusy('')}
  }
  async function upload(e:React.ChangeEvent<HTMLInputElement>){
    const chosen=e.target.files?.[0];e.target.value='';if(!chosen)return;
    try{await importList(readPack(await chosen.text()))}catch(err){setError(err instanceof SyntaxError?'That file is not valid JSON.':(err as Error).message)}
  }
  function installStarter(){importList(starter.map(t=>({id:slug(t.title),title:t.title,department:'General',level:'mid',model_tier:'STANDARD',instructions:t.personality})))}
  async function birth(mode:'choose'|'surprise'){
    setBusy(mode);setError('');
    try{onBorn(await call('/bots/birth',{method:'POST',body:JSON.stringify(mode==='choose'?{mode,preset_id:picked}:{mode})}))}catch(e){setError((e as Error).message)}finally{setBusy('')}
  }
  const tools=<div className="career-tools"><input ref={file} type="file" accept="application/json,.json" hidden onChange={upload}/><button type="button" className="text-button" disabled={!!busy} onClick={()=>file.current?.click()}><Upload size={14}/> {busy==='import'?'Importing…':'Import role pack'}</button>{!!presets?.length&&<a className="text-button" href="/api/role-presets/export" download="funkbot-role-pack.json"><Download size={14}/> Export</a>}</div>;
  if(presets===null)return <p className="field-hint" role="status">Loading the role library…</p>;
  if(!presets.length)return <div className="career-empty"><strong>No role library yet</strong><p className="field-hint">Careers give a new Bot its full job: instructions, department, level and resource tier. Import your role pack (JSON), or start with the nine built-in jobs and replace them later.</p>{notice&&<p className="career-notice" role="status">{notice}</p>}{error&&<div className="error">{error}</div>}<div className="modal-actions career-actions"><button type="button" className="secondary" onClick={onCancel}>Cancel</button>{tools}<button type="button" className="primary" disabled={!!busy} onClick={installStarter}>Install 9 starter roles</button></div></div>;
  return <div className="career-birth">
    <div className="career-bar"><div className="career-search"><Search size={15}/><input aria-label="Search roles" placeholder={`Search ${presets.length} roles`} value={query} onChange={e=>setQuery(e.target.value)}/></div>{tools}</div>
    {notice&&<p className="career-notice" role="status">{notice}</p>}
    <div className="career-columns">
      <div className="career-list" role="listbox" aria-label="Roles">{groups.length?groups.map(([department,list])=><div key={department} className="career-group"><small>{department}</small>{list.map(p=><button type="button" role="option" aria-selected={p.id===picked} key={p.id} className={p.id===picked?'selected':''} onClick={()=>setPicked(p.id)}>{p.title}</button>)}</div>):<p className="field-hint">No roles match “{query}”.</p>}</div>
      <div className="career-preview" aria-live="polite">{selected?<><p className="eyebrow">{selected.department}</p><h3>{selected.title}</h3><div className="career-summary"><span className="career-chip">{label(selected.level)}</span><span className="career-chip">{label(selected.model_tier)} tier</span><span className="career-chip dim">v{selected.version}{selected.customized?' · edited':''}</span></div><p>{selected.job_description||selected.instructions}</p>{!!selected.responsibilities.length&&<ul>{selected.responsibilities.slice(0,5).map(r=><li key={r}>{r}</li>)}</ul>}</>:<><p className="eyebrow">Two ways to hire</p><h3>Pick a role, or roll the dice</h3><p>Choose a career and Funk Bot draws a surprise character from your Vault. Or let it choose both.</p></>}</div>
    </div>
    {error&&<div className="error">{error}</div>}
    <div className="modal-actions career-actions"><button type="button" className="secondary" onClick={onCancel}>Cancel</button><button type="button" className="secondary" disabled={!!busy} onClick={()=>birth('surprise')}><Dices size={15}/> {busy==='surprise'?'Rolling…':'Surprise me'}</button><button type="button" className="primary" disabled={!selected||!!busy} onClick={()=>birth('choose')}>{busy==='choose'?'Hiring…':selected?`Hire ${selected.title}`:'Choose a role'} <ArrowRight size={15}/></button></div>
  </div>;
}
