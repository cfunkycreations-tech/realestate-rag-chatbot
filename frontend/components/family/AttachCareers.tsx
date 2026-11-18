'use client';
import {useCallback,useEffect,useState} from 'react';
import {api,send} from './api';

type Item={id:string;name:string;title:string};
type Preset={id:string;title:string;department:string;level:string};
type Preview={bot_id:string;name:string;preset_title:string;adds:{level:string;department:string;model_tier:string};keeps:string[];note:string};

// Bots made before Employee DNA get a career recorded BESIDE them: preview first, then apply. Nothing about the Bot itself changes.
export default function AttachCareers({onDone}:{onDone:()=>void}){
 const [bots,setBots]=useState<Item[]>([]),[presets,setPresets]=useState<Preset[]>([]),[pick,setPick]=useState<Record<string,string>>({}),[bulk,setBulk]=useState('');
 const [preview,setPreview]=useState<Preview[]|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const load=useCallback(async()=>{const d=await api('/career/unassigned');setBots(d.bots);setPresets(d.presets)},[]);
 useEffect(()=>{let live=true;api('/career/unassigned').then(d=>{if(live){setBots(d.bots);setPresets(d.presets)}}).catch(e=>{if(live)setError((e as Error).message)});return()=>{live=false}},[]);
 const chosen=bots.filter(b=>pick[b.id]);
 const body=(confirm:boolean)=>({assignments:chosen.map(b=>({bot_id:b.id,preset_id:pick[b.id]})),confirm});
 async function run(confirm:boolean){
  if(chosen.length===0)return;setBusy(true);setError('');setNotice('');
  try{
   const r=await api('/career/attach',send('POST',body(confirm)));
   if(confirm){setPreview(null);setPick({});setBulk('');setNotice(`Added a career to ${r.count} Bot${r.count===1?'':'s'}. Names, personalities, memory and sprites were not changed.`);await load();onDone()}
   else setPreview(r.previews);
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 if(bots.length===0)return notice||error?<section className="fam-card">{notice&&<p className="notice" role="status">{notice}</p>}{error&&<p className="error" role="alert">{error}</p>}</section>:null;
 return <section className="fam-card" aria-label="Bots without a career">
  <h2>Bots without a career ({bots.length})</h2>
  <p className="field-hint">These Bots were created before careers existed. Choose a role for each, preview, then add. The career is recorded beside the Bot: its name, job title, personality, memory, skills and sprite stay exactly as they are, and no permission or spending limit changes.</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}
  <div className="fam-actions"><label htmlFor="att-bulk">Same role for every Bot</label><select id="att-bulk" value={bulk} onChange={e=>{const v=e.target.value;setBulk(v);setPreview(null);setPick(v?Object.fromEntries(bots.map(b=>[b.id,v])):{})}}><option value="">Choose a role…</option>{presets.map(p=><option key={p.id} value={p.id}>{p.title} · {p.department}</option>)}</select></div>
  <ul className="fam-votes">{bots.map(b=><li key={b.id}><strong>{b.name}</strong><small> {b.title||'No job title'}</small> <select aria-label={`Role for ${b.name}`} value={pick[b.id]||''} onChange={e=>{setPreview(null);setPick({...pick,[b.id]:e.target.value})}}><option value="">No career yet</option>{presets.map(p=><option key={p.id} value={p.id}>{p.title} · {p.department}</option>)}</select></li>)}</ul>
  {presets.length===0&&<p className="field-hint">No active role presets. Import a role pack first.</p>}
  <div className="fam-actions"><button className="secondary" disabled={busy||chosen.length===0} onClick={()=>void run(false)}>Preview {chosen.length||''}</button>{preview&&<button disabled={busy} onClick={()=>void run(true)}>Add career to {preview.length} Bot{preview.length===1?'':'s'}</button>}</div>
  {preview&&<div role="region" aria-label="Preview"><p className="field-hint">{preview[0].note}</p><ul>{preview.map(p=><li key={p.bot_id}><strong>{p.name}</strong> gets <em>{p.preset_title}</em> · {p.adds.level} · {p.adds.department} · {p.adds.model_tier} tier</li>)}</ul><p className="field-hint">Unchanged: {preview[0].keeps.join(', ')}.</p></div>}
 </section>;
}
