'use client';
import {useEffect,useRef,useState} from 'react';
import ComputerDesktop from './ComputerDesktop';

type ComputerStatus={enabled:boolean;desktop_enabled:boolean;active:{bot_id:string;run_id:string}|null};
export default function ComputerControl(){
 const [status,setStatus]=useState<ComputerStatus|null>(null),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[error,setError]=useState(''),[desktopRun,setDesktopRun]=useState('');
 const changing=useRef(false),generation=useRef(0);
 useEffect(()=>{const ac=new AbortController();let timer:ReturnType<typeof setTimeout>;async function poll(){const started=generation.current;try{if(!changing.current){const response=await fetch('/api/control/computer',{signal:ac.signal,cache:'no-store'});if(!response.ok)throw Error('Computer status unavailable.');const data=await response.json();if(!ac.signal.aborted&&!changing.current&&started===generation.current){setStatus(data);setError('')}}}catch(e){if(!ac.signal.aborted&&!changing.current&&started===generation.current)setError((e as Error).message)}if(!ac.signal.aborted)timer=setTimeout(poll,1500)}void poll();return()=>{ac.abort();clearTimeout(timer)}},[]);
 async function stop(){if(!status?.active||busy)return;changing.current=true;generation.current++;setBusy(true);setError('');try{const response=await fetch('/api/control/computer/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:status.active.run_id})}),data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Could not request computer stop.');setNotice(data.requested?'Stop requested. The command may already have run; verify the result.':'No active computer request was found.');setStatus({...status,active:null})}catch(e){setError((e as Error).message)}finally{changing.current=false;setBusy(false)}}
 if(!status?.enabled&&!error)return null;
 return <><div className="global-pause computer-control"><span role="status">{error||(status?.active?'Computer request active':notice||'Computer idle · offline sandbox')}</span><div>{status?.desktop_enabled&&<button type="button" disabled={!status.active} onClick={()=>setDesktopRun(status.active?.run_id||'')}>View desktop</button>} <button type="button" disabled={busy||!status?.active} onClick={()=>void stop()}>{busy?'Stopping…':'Stop computer'}</button></div></div>{desktopRun&&<ComputerDesktop key={desktopRun} runId={desktopRun} onClose={()=>setDesktopRun('')}/>}</>
}
