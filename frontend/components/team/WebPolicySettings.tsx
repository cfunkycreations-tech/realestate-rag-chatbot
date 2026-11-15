'use client';
import {useEffect,useState} from 'react';

type Policy={allow:string[];deny:string[]};
async function request(init?:RequestInit):Promise<Policy>{
 const res=await fetch('/api/settings/web-policy',init),body=await res.json();
 if(!res.ok)throw Error(typeof body.detail==='string'?body.detail:'Enter valid hostnames without paths or ports.');
 return body;
}
export default function WebPolicySettings(){
 const [allow,setAllow]=useState(''),[deny,setDeny]=useState(''),[loaded,setLoaded]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 useEffect(()=>{let active=true;request().then(p=>{if(active){setAllow(p.allow.join('\n'));setDeny(p.deny.join('\n'));setLoaded(true)}}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[]);
 async function save(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');setNotice('');try{const lines=(value:string)=>value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean);const p=await request({method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({allow:lines(allow),deny:lines(deny)})});setAllow(p.allow.join('\n'));setDeny(p.deny.join('\n'));setNotice('Web policy saved.')}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <div className="settings-body web-policy"><h3>Web access policy</h3><p className="field-hint">Web fetch is read-only and blocked by default. Add one exact hostname per line, or use a leading dot to include a domain and its subdomains (for example, .example.com). Denied hosts always take precedence.</p><p className="field-hint">Private and loopback addresses are blocked even if a domain resolves to them. Redirects are not followed; responses have size and time limits.</p>{error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}{loaded?<form onSubmit={save}><label htmlFor="web-allow">Allowed hosts</label><textarea id="web-allow" rows={5} value={allow} onChange={e=>setAllow(e.target.value)} placeholder="example.com"/><label htmlFor="web-deny">Denied hosts</label><textarea id="web-deny" rows={5} value={deny} onChange={e=>setDeny(e.target.value)} placeholder="private.example.com"/><button className="primary" disabled={busy}>{busy?'Saving…':'Save web policy'}</button></form>:!error&&<p>Loading web policy…</p>}</div>
}
