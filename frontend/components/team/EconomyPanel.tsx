'use client';
import {useEffect,useState} from 'react';

type Tier='LIGHT'|'STANDARD'|'ADVANCED'|'RESEARCH';
type Flag={gateway:string;model:string;kind:string;note:string};
type Spend={spent?:string;cap:string;percent?:number|null;error?:string};
type Economy={
 tier_policy:Record<Tier,string>;economy:{enabled:boolean;ceiling_tier:Tier;prefer_free:boolean};
 alerts:{enabled:boolean;thresholds:number[]};fallback:{enabled:boolean};model_flags:Flag[];
 profile_reserve_usd:Record<string,string|null>;spend:Record<string,Spend>;recent_alerts:{scope:string;period:string;threshold:number;fired_at:number}[];
};
type Row={key:string|null;rounds:number;prompt_tokens:number;completion_tokens:number;usd:string;unverified_rounds:number;owner_free_rounds:number;source:string};
export const TIERS:Tier[]=['LIGHT','STANDARD','ADVANCED','RESEARCH'];
export const PROFILE_NAMES=['cheap-bulk','fast','smart','thinker','vision'];
export const GROUPS=['bot','mission','project','model','provider','profile','tier'];

export function parseThresholds(text:string):number[]{
 const values=text.split(/[\s,]+/).filter(Boolean).map(Number);
 if(!values.length||values.length>6||values.some(v=>!Number.isInteger(v)||v<1||v>100))throw new Error('Enter one to six whole percentages from 1 to 100, such as 50, 80, 100.');
 return [...new Set(values)].sort((a,b)=>a-b);
}
export function describeSpend(s?:Spend):string{
 if(!s)return 'No cap set';
 if(s.error)return s.error;
 return `$${Number(s.spent).toFixed(4)} of $${Number(s.cap).toFixed(2)}${s.percent==null?'':` (${s.percent}%)`}`;
}
async function request(path:string,init?:RequestInit){const r=await fetch('/api'+path,init);const b=await r.json();if(!r.ok)throw Error(typeof b.detail==='string'?b.detail:'Could not save.');return b}
const put=(body:unknown):RequestInit=>({method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});

export default function EconomyPanel(){
 const [data,setData]=useState<Economy|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [group,setGroup]=useState('bot'),[days,setDays]=useState(30),[rows,setRows]=useState<Row[]|null>(null),[thresholds,setThresholds]=useState('');
 const [flag,setFlag]=useState({gateway:'custom',model:'',kind:'local',note:''});
 useEffect(()=>{let live=true;request('/economy').then(d=>{if(live){setData(d);setThresholds(d.alerts.thresholds.join(', '))}}).catch(e=>{if(live)setError(e.message)});return()=>{live=false}},[]);
 useEffect(()=>{let live=true;request(`/budget/usage?group=${group}&days=${days}`).then(d=>{if(live)setRows(d.rows)}).catch(e=>{if(live)setError(e.message)});return()=>{live=false}},[group,days,data]);
 async function save(body:unknown,message='Saved.'){setError('');setNotice('');try{await request('/economy',put(body));setData(await request('/economy'));setNotice(message)}catch(e){setError((e as Error).message)}}
 async function addFlag(e:React.FormEvent){e.preventDefault();setError('');setNotice('');try{await request('/economy/model-flags',put(flag));setData(await request('/economy'));setFlag({...flag,model:'',note:''});setNotice('Saved.')}catch(err){setError((err as Error).message)}}
 async function removeFlag(f:Flag){setError('');try{await request(`/economy/model-flags?gateway=${encodeURIComponent(f.gateway)}&model=${encodeURIComponent(f.model)}`,{method:'DELETE'});setData(await request('/economy'))}catch(err){setError((err as Error).message)}}
 if(!data)return <section className="gateway">{error?<p className="error" role="alert">{error}</p>:<p>Loading Economy settings…</p>}</section>;
 const e=data.economy;
 return <section className="gateway economy-panel" aria-label="Economy and usage">
  <h3>Economy Mode</h3>
  <p className="field-hint">Owner-controlled. When on, no Bot runs on a profile whose reserved maximum is higher than the ceiling tier&apos;s profile. It can lower spending, never raise it. Profiles without a price are never treated as cheaper.</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}
  <div className="economy-status"><span className={`career-chip ${e.enabled?'strong':'dim'}`}>{e.enabled?'Economy Mode ON':'Economy Mode off'}</span><span className="career-chip">Today: {describeSpend(data.spend.daily)}</span>{data.spend.monthly&&<span className="career-chip">Month: {describeSpend(data.spend.monthly)}</span>}</div>
  <div className="budget-fields">
   <label className="check-row"><input type="checkbox" checked={e.enabled} onChange={ev=>save({economy:{...e,enabled:ev.target.checked}},ev.target.checked?'Economy Mode is on.':'Economy Mode is off.')}/> Economy Mode</label>
   <label className="check-row"><input type="checkbox" checked={e.prefer_free} onChange={ev=>save({economy:{...e,prefer_free:ev.target.checked}})}/> Try models I marked free or local first</label>
   <label>Ceiling tier<select aria-label="Ceiling tier" value={e.ceiling_tier} onChange={ev=>save({economy:{...e,ceiling_tier:ev.target.value}})}>{TIERS.map(t=><option key={t}>{t}</option>)}</select></label>
   <label className="check-row"><input type="checkbox" checked={data.fallback.enabled} onChange={ev=>save({fallback:{enabled:ev.target.checked}})}/> Fall back to a cheaper priced profile instead of refusing when a cap is near</label>
  </div>
  <h3>Resource policy by tier</h3>
  <p className="field-hint">Career Bots use the profile for their role&apos;s tier unless you choose a profile for a chat. Delegated work never uses a costlier profile than the Bot that delegated it.</p>
  <div className="budget-fields">{TIERS.map(t=><label key={t}>{t[0]+t.slice(1).toLowerCase()}<select aria-label={`${t} profile`} value={data.tier_policy[t]} onChange={ev=>save({tier_policy:{...data.tier_policy,[t]:ev.target.value}})}>{PROFILE_NAMES.map(p=><option key={p} value={p}>{p}{data.profile_reserve_usd[p]?` · reserves $${Number(data.profile_reserve_usd[p]).toFixed(4)}`:' · no price set'}</option>)}</select></label>)}</div>
  <h3>Budget alerts</h3>
  <form onSubmit={ev=>{ev.preventDefault();try{save({alerts:{enabled:data.alerts.enabled,thresholds:parseThresholds(thresholds)}})}catch(err){setError((err as Error).message)}}}>
   <div className="budget-fields"><label className="check-row"><input type="checkbox" checked={data.alerts.enabled} onChange={ev=>save({alerts:{...data.alerts,enabled:ev.target.checked}})}/> Alert me in the inbox</label><label>Percent of cap<input aria-label="Alert thresholds" value={thresholds} onChange={ev=>setThresholds(ev.target.value)}/></label></div>
   <button className="secondary">Save alert thresholds</button>
  </form>
  {data.recent_alerts.length>0&&<ul className="economy-alerts">{data.recent_alerts.slice(0,5).map(a=><li key={`${a.scope}${a.period}${a.threshold}${a.fired_at}`}>{a.scope==='account'?'Account':'Bot'} {a.period} reached {a.threshold}% · {new Date(a.fired_at*1000).toLocaleString()}</li>)}</ul>}
  <h3>Free or local models</h3>
  <p className="field-hint">Only models you have verified yourself. They settle at $0 and are tried first in Economy Mode. OmniRoute itself is never assumed free; flag the specific model.</p>
  {data.model_flags.map(f=><div className="economy-flag" key={f.gateway+f.model}><span><strong>{f.model}</strong> · {f.gateway} · {f.kind}{f.note?` · ${f.note}`:''}</span><button type="button" className="text-button" onClick={()=>removeFlag(f)}>Remove</button></div>)}
  <form onSubmit={addFlag}><div className="budget-fields">
   <label>Gateway<select aria-label="Flag gateway" value={flag.gateway} onChange={ev=>setFlag({...flag,gateway:ev.target.value})}><option>custom</option><option>openrouter</option><option>omniroute</option></select></label>
   <label>Exact model id<input aria-label="Flag model" required value={flag.model} onChange={ev=>setFlag({...flag,model:ev.target.value})}/></label>
   <label>Kind<select aria-label="Flag kind" value={flag.kind} onChange={ev=>setFlag({...flag,kind:ev.target.value})}><option>local</option><option>free</option></select></label>
   <label>Note<input aria-label="Flag note" maxLength={300} value={flag.note} onChange={ev=>setFlag({...flag,note:ev.target.value})}/></label>
  </div><button className="secondary">Mark as free or local</button></form>
  <h3>Usage</h3>
  <div className="budget-fields"><label>Group by<select aria-label="Group usage by" value={group} onChange={ev=>setGroup(ev.target.value)}>{GROUPS.map(g=><option key={g}>{g}</option>)}</select></label><label>Period<select aria-label="Usage period" value={days} onChange={ev=>setDays(Number(ev.target.value))}>{[1,7,30,90].map(d=><option key={d} value={d}>{d===1?'Last 24 hours':`Last ${d} days`}</option>)}</select></label></div>
  <div className="economy-table" role="region" aria-label="Usage table" tabIndex={0}>
   {rows===null?<p>Loading usage…</p>:rows.length===0?<p className="field-hint">No usage in this period.</p>:<table><thead><tr><th>{group}</th><th>Rounds</th><th>In</th><th>Out</th><th>USD</th></tr></thead><tbody>{rows.map((r,i)=><tr key={`${r.key}${i}`}><td>{r.key??'(none)'}{r.source==='legacy'?' · before budgets':''}</td><td>{r.rounds}{r.unverified_rounds?` (${r.unverified_rounds} unverified)`:''}</td><td>{r.prompt_tokens.toLocaleString()}</td><td>{r.completion_tokens.toLocaleString()}</td><td>${Number(r.usd).toFixed(4)}{r.owner_free_rounds?` · ${r.owner_free_rounds} free`:''}</td></tr>)}</tbody></table>}
  </div>
  <p className="field-hint">USD is each round&apos;s configured profile price, or $0 for models you marked free. It is not a provider invoice.</p>
 </section>;
}
