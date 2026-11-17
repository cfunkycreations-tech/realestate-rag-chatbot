'use client';
import {useCallback,useEffect,useState} from 'react';
import ReactMarkdown from 'react-markdown';
import {costLabel,isLive,kindLabel,outcomeLabel,statusLabel,tokenLabel,type Refused,type Thread} from './model';

type Message={id:string;bot_id:string|null;role:string;content:string;created_at:number};
type Overview={threads:Thread[];refused:Refused[];settings:{enabled:boolean}};
async function api(path:string,signal?:AbortSignal){const r=await fetch('/api'+path,{signal,cache:'no-store'});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'Could not load Bot conversations.');return d}

// Owner's read-only window onto conversations the Bots started themselves. Nothing here sends or approves anything.
export default function BotConversations({names}:{names:Record<string,string>}){
 const [data,setData]=useState<Overview|null>(null),[error,setError]=useState(''),[open,setOpen]=useState(''),[history,setHistory]=useState<Message[]>([]);
 const load=useCallback(async(signal?:AbortSignal)=>{const d:Overview=await api('/bot-messages',signal);if(!signal?.aborted){setData(d);setError('')}},[]);
 useEffect(()=>{
  const ac=new AbortController();let timer:ReturnType<typeof setTimeout>;
  async function poll(){
   if(document.visibilityState==='visible'){try{await load(ac.signal)}catch(e){if(!ac.signal.aborted)setError((e as Error).message)}}
   if(!ac.signal.aborted)timer=setTimeout(poll,4000);
  }
  void poll();return()=>{ac.abort();clearTimeout(timer)};
 },[load]);
 useEffect(()=>{
  if(!open)return;const ac=new AbortController();
  api('/bot-dms/'+open,ac.signal).then(d=>{if(!ac.signal.aborted)setHistory(d.messages)}).catch(()=>{if(!ac.signal.aborted)setHistory([])});
  return()=>ac.abort();
 },[open,data]);
 const who=(id:string|null,fallback:string|null)=>fallback||(id&&names[id])||'Deleted Bot';
 return <section className="bc-panel" aria-label="Bot-started conversations">
  <p className="field-hint">Conversations your Bots started on their own. You can read them here without joining. Costs use the prices you configured, not a provider invoice.{data&&!data.settings.enabled&&' Bot-started messages are currently turned off (Settings → Web access → Bot-to-Bot messaging).'}</p>
  {error&&<p className="error" role="alert">{error}</p>}
  {!data&&!error&&<p>Loading conversations…</p>}
  {data&&data.threads.length===0&&<div className="mission-empty"><h2>No Bot-started conversations yet</h2><p>When a Bot asks a colleague for help, it appears here with its reason, cost and outcome.</p></div>}
  {data?.threads.map(t=><article key={t.dm_id} className={`bc-card${open===t.dm_id?' open':''}`}>
   <button type="button" className="bc-head" aria-expanded={open===t.dm_id} onClick={()=>setOpen(open===t.dm_id?'':t.dm_id)}>
    <span className="bc-route"><strong>{who(t.initiator_id,t.initiator_name)}</strong> → <strong>{who(t.receiver_id,t.receiver_name)}</strong></span>
    <span className={`mission-status ${t.status}`}>{statusLabel(t.status)}</span>
   </button>
   <p className="bc-why"><strong>{kindLabel(t.kind)}:</strong> {t.subject.replace(/^Bot message: /,'')}</p>
   <dl className="bc-facts">
    <div><dt>Mission</dt><dd>{t.mission_title||'None'}</dd></div>
    <div><dt>Messages</dt><dd>{t.messages_sent}</dd></div>
    <div><dt>Tokens</dt><dd>{tokenLabel(t.usage)}</dd></div>
    <div><dt>Cost</dt><dd>{costLabel(t.usage)}</dd></div>
    <div><dt>Updated</dt><dd>{new Date(t.updated_at*1000).toLocaleString()}</dd></div>
   </dl>
   {outcomeLabel(t)&&<p className={t.status==='failed'?'error':'bc-outcome'}>{isLive(t.status)?<span role="status">{outcomeLabel(t)}</span>:outcomeLabel(t)}</p>}
   {open===t.dm_id&&<div className="bc-history">{history.length?history.map(m=><div key={m.id} className="group-message"><small>{m.role==='sender'?`${who(t.initiator_id,t.initiator_name)} wrote`:`${who(t.receiver_id,t.receiver_name)} replied`}</small><div className="markdown"><ReactMarkdown>{m.content}</ReactMarkdown></div></div>):<p>Loading transcript…</p>}</div>}
  </article>)}
  {data&&data.refused.length>0&&<details className="bc-refused"><summary>Blocked attempts ({data.refused.length})</summary><ul>{data.refused.map((r,i)=><li key={i}><time>{new Date(r.created_at*1000).toLocaleString()}</time> {who(r.sender_id,null)} → {who(r.receiver_id,null)} · {kindLabel(r.kind)} — {r.detail||'blocked'}</li>)}</ul></details>}
 </section>;
}
