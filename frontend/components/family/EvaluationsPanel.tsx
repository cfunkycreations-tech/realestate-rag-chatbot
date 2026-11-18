'use client';
import {useCallback,useEffect,useState} from 'react';
import {api,send} from './api';

type Overview={bots:{bot_id:string;name:string;title:string;certification:string;label:string;results:number}[];suites:{suite:string;name:string;version:number;pass_mark:number;what:string}[];labels:{key:string;label:string}[];note:string};
type Report={bot_id:string;label:string;suites:{suite:string;name:string;version:number;pass_mark:number;what:string;latest:{status:string;score:number;at:number}|null}[];history:{id:string;suite:string;status:string;score:number;cause:string;created_at:number}[]};
type Version={id:string;source:string;reason:string;created_at:number;chars:number};
type Run={bot_id:string;label:string;changed:boolean;results:{suite:string;name:string;status:string;score?:number;previous_score?:number|null;delta?:number|null;cause?:string;evidence:Record<string,unknown>}[]};

const when=(t:number)=>new Date(t*1000).toLocaleString();

// Zero-cost evaluations scored from recorded work. A certification is a label: it never changes a permission, budget or secret.
export default function EvaluationsPanel(){
 const [data,setData]=useState<Overview|null>(null),[open,setOpen]=useState(''),[report,setReport]=useState<Report|null>(null),[versions,setVersions]=useState<Version[]>([]),[last,setLast]=useState<Run|null>(null);
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const load=useCallback(async()=>setData(await api('/evaluations')),[]);
 useEffect(()=>{let live=true;api('/evaluations').then(d=>{if(live)setData(d)}).catch(e=>{if(live)setError((e as Error).message)});return()=>{live=false}},[]);
 useEffect(()=>{
  if(!open)return;let live=true;
  Promise.all([api('/evaluations/'+open),api(`/bots/${open}/instructions`)]).then(([r,v])=>{if(live){setReport(r);setVersions(v.versions)}}).catch(e=>{if(live)setError((e as Error).message)});
  return()=>{live=false};
 },[open,notice]);
 async function act(fn:()=>Promise<string>){setBusy(true);setError('');setNotice('');try{setNotice(await fn());await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 const runFor=(ids:string[]|null)=>act(async()=>{const r=await api('/evaluations/run',send('POST',ids?{bot_ids:ids}:{}));const runs:Run[]=r.runs;setLast(ids&&runs[0]?runs[0]:null);const recorded=runs.reduce((n,x)=>n+x.results.filter(y=>y.status!=='not_evaluated').length,0);return `${runs.length} Bot${runs.length===1?'':'s'} evaluated, ${recorded} result${recorded===1?'':'s'} recorded. Cost: $0.00 (no model was called).`});
 if(!data)return <section className="fam-panel">{error?<p className="error" role="alert">{error}</p>:<p>Loading evaluations…</p>}</section>;
 return <section className="fam-panel" aria-label="Evaluations">
  <p className="field-hint">{data.note} Not enough work yet means “Not evaluated”, never a fail. Results from practice or mocked runs would be stored as simulated and never count toward a certification.</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}
  <ol className="fam-ladder" aria-label="Certification levels">{data.labels.map(l=><li key={l.key}>{l.label}<small>{data.bots.filter(b=>b.certification===l.key).length}</small></li>)}</ol>
  <div className="fam-actions"><button disabled={busy||data.bots.length===0} onClick={()=>void runFor(null)}>Evaluate every Bot (free)</button></div>
  <details className="fam-card"><summary>What each test checks</summary><ul>{data.suites.map(s=><li key={s.suite}><strong>{s.name}</strong> v{s.version}: {s.what} Pass at {s.pass_mark}%.</li>)}</ul></details>
  {data.bots.length===0&&<div className="mission-empty"><h2>No Bots yet</h2><p>Create a Bot and its evaluations start here.</p></div>}
  <div className="fam-grid">{data.bots.map(b=><article key={b.bot_id} className={`fam-card${open===b.bot_id?' open':''}`} aria-label={b.name}>
   <h2>{b.name}</h2><p className="field-hint">{b.title||'No job title'}</p>
   <p><strong>{b.label}</strong> <small>{b.results} recorded result{b.results===1?'':'s'}</small></p>
   <div className="fam-actions"><button className="secondary" aria-expanded={open===b.bot_id} onClick={()=>{setOpen(open===b.bot_id?'':b.bot_id);setLast(null)}}>{open===b.bot_id?'Hide':'Details'}</button><button className="secondary" disabled={busy} onClick={()=>void runFor([b.bot_id])}>Evaluate</button></div>
   {open===b.bot_id&&report&&report.bot_id===b.bot_id&&<div>
    {last&&last.bot_id===b.bot_id&&<ul aria-label="Latest run">{last.results.map(r=><li key={r.suite}><strong>{r.name}</strong>: {r.status==='not_evaluated'?'Not evaluated (not enough work yet)':`${r.status==='passed'?'Passed':'Failed'} at ${r.score}%${r.delta!=null?` (${r.delta>=0?'+':''}${r.delta} since last time)`:''}`}{r.cause&&<small> · {r.cause}</small>}</li>)}</ul>}
    <table className="fam-table"><thead><tr><th>Test</th><th>Latest</th><th>Pass mark</th></tr></thead><tbody>{report.suites.map(s=><tr key={s.suite}><td>{s.name} <small>v{s.version}</small></td><td>{s.latest?`${s.latest.status==='passed'?'Passed':'Failed'} · ${s.latest.score}%`:'Not evaluated'}</td><td>{s.pass_mark}%</td></tr>)}</tbody></table>
    <h3>Instruction history</h3>
    {versions.length===0?<p className="field-hint">No earlier versions yet. Every edit to this Bot’s instructions saves the old text first.</p>:<ul>{versions.map(v=><li key={v.id}>{when(v.created_at)} · {v.source} <small>{v.reason}</small> <button className="secondary" disabled={busy} onClick={()=>void act(async()=>{await api(`/bots/${b.bot_id}/instructions/rollback`,send('POST',{version_id:v.id}));return 'Restored. The text it replaced was saved too, so this can be undone.'})}>Restore</button></li>)}</ul>}
   </div>}
  </article>)}</div>
 </section>;
}
