'use client';
import {useCallback,useEffect,useState} from 'react';

type Entry={id:string;content:string;created_at:number};
type Project={id:string;name:string};
async function request(path:string,init?:RequestInit){
 const response=await fetch('/api'+path,{...init,headers:{'Content-Type':'application/json',...init?.headers}});
 const result=await response.json();
 if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'Request failed.');
 return result;
}
export default function MemoryLayers({projects}:{projects:Project[]}){
 const [scope,setScope]=useState('shared'),[entries,setEntries]=useState<Entry[]>([]),[content,setContent]=useState(''),[editing,setEditing]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const path=scope==='shared'?'/memory/shared':`/projects/${encodeURIComponent(scope)}/memory`;
 const refresh=useCallback(async(signal?:AbortSignal)=>{const data=await request(path,{signal});if(!signal?.aborted)setEntries(data)},[path]);
 useEffect(()=>{const ac=new AbortController();async function load(){try{await refresh(ac.signal)}catch(e){if(!ac.signal.aborted)setError((e as Error).message)}}void load();return()=>ac.abort()},[refresh]);
 async function action(fn:()=>Promise<void>){setBusy(true);setError('');try{await fn();await refresh()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <section className="mission-detail memory-section"><h2>Shared and project memory</h2><p className="field-hint">Only you can write these entries. Shared facts are available to all Bots; project facts are included only for missions linked to that project. Each layer has a 50-entry, 32,000-character limit and shares the normal 8,000-character recall budget. Memory is untrusted data and secret filtering is not guaranteed.</p>
 <label htmlFor="memory-layer">Memory layer</label><select id="memory-layer" disabled={busy} value={scope} onChange={e=>{setScope(e.target.value);setEntries([]);setContent('');setEditing('');setError('')}}><option value="shared">Shared across Bots</option>{projects.map(p=><option value={p.id} key={p.id}>Project · {p.name}</option>)}</select>
 {error&&<div className="error" role="alert">{error}</div>}{entries.length?entries.map(item=><div className="project-row" key={item.id}><div><strong>Owner · {new Date(item.created_at*1000).toLocaleDateString()}</strong><p className="project-text">{item.content}</p></div><div><button className="secondary" disabled={busy} aria-label={`Edit memory: ${item.content}`} onClick={()=>{setEditing(item.id);setContent(item.content)}}>Edit</button> <button className="secondary" disabled={busy} aria-label={`Delete memory: ${item.content}`} onClick={()=>void action(async()=>{await request(`${path}/${item.id}`,{method:'DELETE'});if(editing===item.id){setEditing('');setContent('')}})}>Delete</button></div></div>):<p>No entries in this layer.</p>}
 <form onSubmit={e=>{e.preventDefault();void action(async()=>{await request(path+(editing?'/'+editing:''),{method:editing?'PUT':'POST',body:JSON.stringify({content})});setContent('');setEditing('')})}}><label htmlFor="layer-memory-text">{editing?'Edit layer memory':'New layer memory'}</label><textarea id="layer-memory-text" maxLength={4000} rows={3} value={content} onChange={e=>setContent(e.target.value)} required/><button className="secondary" disabled={busy}>{editing?'Save layer memory':'Add layer memory'}</button>{editing&&<button type="button" className="secondary" onClick={()=>{setEditing('');setContent('')}}>Cancel</button>}</form></section>
}
