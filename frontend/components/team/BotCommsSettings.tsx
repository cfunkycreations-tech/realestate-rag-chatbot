'use client';
import {useEffect,useState} from 'react';
type Bot={id:string;name:string};
type Link={from_bot_id:string;to_bot_id:string};
type Cfg={enabled:boolean;thread_max_messages:number;pair_cooldown_seconds:number;daily_per_bot:number;mission_max_messages:number;dedupe_window_seconds:number;reply_timeout_seconds:number;max_chain:number;active_threads_max:number;department_routing:boolean;thread_max_usd:string;thread_max_model_calls:number;policy?:string;kinds?:string[]};
const NUM:[keyof Cfg,string,string][]=[
 ['thread_max_messages','Messages per conversation','1–10'],['thread_max_model_calls','Model calls per conversation','1–50'],['mission_max_messages','Messages per mission','0–50'],
 ['daily_per_bot','Messages per Bot per day','0–200'],['pair_cooldown_seconds','Cooldown between the same two Bots (seconds)','0–86400'],['reply_timeout_seconds','Reply timeout (seconds)','30–1800'],
 ['active_threads_max','Conversations at once','1–20'],['max_chain','Longest delegation chain','2–5']];
async function call(path:string,init?:RequestInit){const r=await fetch(path,{...init,headers:{'Content-Type':'application/json'}});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'Could not save.');return d}

export default function BotCommsSettings(){
 const [cfg,setCfg]=useState<Cfg|null>(null),[bots,setBots]=useState<Bot[]>([]),[links,setLinks]=useState<Link[]>([]),[from,setFrom]=useState(''),[to,setTo]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function refresh(){const [c,b,l]=await Promise.all([call('/api/settings/bot-comms'),call('/api/bots'),call('/api/settings/comm-links')]);setCfg(c);setBots(b);setLinks(l)}
 useEffect(()=>{let live=true;Promise.all([call('/api/settings/bot-comms'),call('/api/bots'),call('/api/settings/comm-links')]).then(([c,b,l])=>{if(live){setCfg(c);setBots(b);setLinks(l)}}).catch(e=>{if(live)setError(e.message)});return()=>{live=false}},[]);
 async function save(next:Cfg){setError('');setNotice('');try{const {policy:_p,kinds:_k,...body}=next;void _p;void _k;setCfg({...await call('/api/settings/bot-comms',{method:'PUT',body:JSON.stringify(body)}),policy:cfg?.policy,kinds:cfg?.kinds});setNotice('Saved.')}catch(e){setError((e as Error).message)}}
 async function change(method:string,link:Link){setError('');try{await call('/api/settings/comm-links',{method,body:JSON.stringify(link)});await refresh()}catch(e){setError((e as Error).message)}}
 const name=(id:string)=>bots.find(b=>b.id===id)?.name||'Deleted Bot';
 return <section className="settings-body bc-settings"><h3>Bot-to-Bot messaging</h3>
  <p className="field-hint">Lets a Bot ask a colleague for help, a review, a finding or a blocker. It is off by default and costs nothing while off. Every message is a short, recorded work request; the colleague answers once, using the normal budgets. A message never gives anyone a permission, and you can watch every conversation under Bot DMs → Bot-started.</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}
  {!cfg?<p>Loading…</p>:<>
   <label className="checkline"><input type="checkbox" checked={cfg.enabled} onChange={e=>void save({...cfg,enabled:e.target.checked})}/> Allow Bots to start conversations</label>
   <p className="field-hint">While allowed, you approve each message unless a pair below is pre-approved. {cfg.policy==='deny'?'Messages are currently denied in Tool review policies.':'You can deny all messages under Tool review policies.'}</p>
   <label className="checkline"><input type="checkbox" checked={cfg.department_routing} onChange={e=>void save({...cfg,department_routing:e.target.checked})}/> Treat Bots with the same department as pre-approved</label>
   <h4>Safety limits</h4>
   <form onSubmit={e=>{e.preventDefault();void save(cfg)}} className="bc-limits">
    {NUM.map(([key,label,range])=><label key={key}>{label} <small>({range})</small><input type="number" value={cfg[key] as number} onChange={e=>setCfg({...cfg,[key]:Number(e.target.value)})}/></label>)}
    <label>Spending limit per conversation (USD) <small>(0–100)</small><input inputMode="decimal" value={cfg.thread_max_usd} onChange={e=>setCfg({...cfg,thread_max_usd:e.target.value})}/></label>
    <button className="secondary">Save limits</button>
   </form>
   <h4>Pre-approved pairs</h4>
   <p className="field-hint">The first Bot may message the second without your click each time. Replies still follow the budgets of the Bot that started it.</p>
   <label>Sending Bot<select value={from} onChange={e=>setFrom(e.target.value)}><option value="">Choose sender</option>{bots.map(b=><option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
   <label>Receiving Bot<select value={to} onChange={e=>setTo(e.target.value)}><option value="">Choose receiver</option>{bots.map(b=><option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
   <button className="secondary" disabled={!from||!to||from===to} onClick={()=>void change('PUT',{from_bot_id:from,to_bot_id:to})}>Approve pair</button>
   {links.map(l=><div className="tool-policy-row" key={l.from_bot_id+':'+l.to_bot_id}><span>{name(l.from_bot_id)} → {name(l.to_bot_id)}</span><button className="secondary" onClick={()=>void change('DELETE',l)}>Revoke</button></div>)}
  </>}
 </section>;
}
