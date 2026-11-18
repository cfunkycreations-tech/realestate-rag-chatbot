'use client';
import {useEffect,useState} from 'react';

async function call(path:string,init?:RequestInit){const r=await fetch('/api'+path,{...init,headers:{'Content-Type':'application/json'}});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||'Request failed.');return d}

// Owner picks one exact model for this Bot. Spending limits and the Economy ceiling still apply to it.
export default function ModelPin({botId}:{botId:string}){
 const [gateway,setGateway]=useState('openrouter'),[model,setModel]=useState(''),[saved,setSaved]=useState(false),[list,setList]=useState<string[]>([]),[msg,setMsg]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{let live=true;call(`/bots/${botId}/model-pin`).then(d=>{if(live&&d.pin){setGateway(d.pin.gateway);setModel(d.pin.model);setSaved(true)}}).catch(()=>{});return()=>{live=false}},[botId]);
 async function run(fn:()=>Promise<void>){setBusy(true);setMsg('');try{await fn()}catch(e){setMsg((e as Error).message)}finally{setBusy(false)}}
 return <div className="model-pin"><label htmlFor="pin-model">Pin an exact model (optional)</label>
  <div className="profile-row"><select aria-label="Gateway" value={gateway} onChange={e=>{setGateway(e.target.value);setList([])}}>{['openrouter','omniroute','custom'].map(g=><option key={g}>{g}</option>)}</select>
   <input id="pin-model" list="pin-models" value={model} onChange={e=>setModel(e.target.value)} placeholder="e.g. anthropic/claude-sonnet-4.5" maxLength={200}/><datalist id="pin-models">{list.map(m=><option key={m} value={m}/>)}</datalist></div>
  <div className="gateway-actions"><button type="button" className="secondary" disabled={busy} onClick={()=>run(async()=>{const d=await call(`/settings/gateways/${gateway}/models`);setList(d.models);setMsg(`${d.models.length} models found. Start typing to pick one.`)})}>Browse models</button>
   <button type="button" className="primary" disabled={busy||!model.trim()} onClick={()=>run(async()=>{await call(`/bots/${botId}/model-pin`,{method:'PUT',body:JSON.stringify({gateway,model:model.trim()})});setSaved(true);setMsg('Pinned. This Bot now uses that model.')})}>Pin model</button>
   {saved&&<button type="button" className="text-button" disabled={busy} onClick={()=>run(async()=>{await call(`/bots/${botId}/model-pin`,{method:'DELETE'});setSaved(false);setModel('');setMsg('Unpinned. This Bot uses its profile again.')})}>Unpin</button>}</div>
  <p className="field-hint" role="status">{msg||(saved?`Pinned: ${model}. Your spending caps and Economy ceiling still apply.`:'Without a pin, the Bot uses its model profile above. Your spending caps and Economy ceiling still apply either way.')}</p></div>
}
