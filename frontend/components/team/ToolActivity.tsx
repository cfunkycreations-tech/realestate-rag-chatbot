'use client';
import {useState} from 'react';

export type ToolCall={id:string;tool_name:string;risk:string;arguments:Record<string,unknown>;status:string;result:unknown;created_at:number;audit:{action:string;created_at:number}[]};
type Decision='approve'|'approve_once'|'deny';

export default function ToolActivity({calls,jobId,pendingId,onDecision}:{calls:ToolCall[];jobId:string;pendingId:string;onDecision:(call:string,decision:Decision)=>Promise<void>}){
 const [busy,setBusy]=useState(''),[error,setError]=useState('');
 if(!calls.length)return null;
 async function decide(call:string,decision:Decision){setError('');setBusy(call);try{await onDecision(call,decision)}catch(e){setError((e as Error).message)}finally{setBusy('')}}
 return <section className="tool-activity" aria-label="Tool activity"><div className="tool-activity-heading"><strong>Tool activity</strong><span>Recorded for this response</span></div>{error&&<p role="alert" className="error">{error}</p>}{calls.map(call=>{
  const pending=!!jobId&&call.id===pendingId&&call.status==='pending';
  return <article className={`tool-card ${pending?'tool-card-pending':''}`} key={call.id}><div className="tool-card-head"><div><strong>{call.tool_name==='write_note'?'Create workspace note':call.tool_name==='web_fetch'?'Fetch a web page':call.tool_name}</strong><span>{call.risk==='read'?'Read-only · automatic':`${call.risk[0].toUpperCase()+call.risk.slice(1)} · approval required`}</span></div><span className="tool-status">{pending?'Needs your approval':call.status}</span></div><dl>{Object.entries(call.arguments).map(([key,value])=><div key={key}><dt>{key}</dt><dd><pre>{typeof value==='string'?value:JSON.stringify(value,null,2)}</pre></dd></div>)}</dl>{pending&&<><p className="tool-help">Review the exact content above. Approve once permits only this call; Approve permits this tool for the rest of this response. Deny prevents this call.</p><div className="tool-actions"><button type="button" className="primary" disabled={!!busy} onClick={()=>void decide(call.id,'approve_once')}>Approve once</button><button type="button" className="secondary" disabled={!!busy} onClick={()=>void decide(call.id,'approve')}>Approve for this response</button><button type="button" className="secondary" disabled={!!busy} onClick={()=>void decide(call.id,'deny')}>Deny</button></div></>}{call.result!=null&&<details><summary>Result</summary><pre>{JSON.stringify(call.result,null,2)}</pre></details>}<details><summary>Audit trail</summary><table><thead><tr><th>Action</th><th>Time</th></tr></thead><tbody>{call.audit.map((entry,index)=><tr key={index}><td>{entry.action.replaceAll('_',' ')}</td><td>{new Date(entry.created_at*1000).toLocaleString()}</td></tr>)}</tbody></table></details></article>
 })}</section>
}
