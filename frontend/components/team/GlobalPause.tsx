'use client';
import {useEffect,useRef,useState} from 'react';

export default function GlobalPause(){
 const [paused,setPaused]=useState<boolean|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const changing=useRef(false),generation=useRef(0);
 useEffect(()=>{const controller=new AbortController();let timer:ReturnType<typeof setTimeout>;async function poll(){const started=generation.current;try{if(!changing.current){const response=await fetch('/api/control/pause',{signal:controller.signal,cache:'no-store'});if(!response.ok)throw Error('Could not load global pause state.');const data=await response.json();if(!controller.signal.aborted&&!changing.current&&started===generation.current){setPaused(data.paused);setError('')}}}catch(e){if(!controller.signal.aborted&&!changing.current&&started===generation.current)setError((e as Error).message)}if(!controller.signal.aborted)timer=setTimeout(poll,3000)}void poll();return()=>{controller.abort();clearTimeout(timer)}},[]);
 async function change(){
  if(paused===null||busy)return;
  if(!paused&&!window.confirm('Pause all Bots? Active responses and approvals will stop, and queued missions and Lab work will be cancelled. Completed actions cannot be undone.'))return;
  changing.current=true;generation.current++;setBusy(true);setError('');try{const response=await fetch('/api/control/pause',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({paused:!paused})});const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Could not change global pause.');setPaused(data.paused);window.dispatchEvent(new Event('funkbot:refresh'))}catch(e){setError((e as Error).message)}finally{changing.current=false;setBusy(false)}
 }
 return <div className="global-pause"><span role="status">{error|| (paused===null?'Checking Bot control…':paused?'All Bots paused · new work blocked':'Bots available · owner control')}</span><button type="button" disabled={busy||paused===null} onClick={()=>void change()}>{busy?'Updating…':paused?'Resume Bots':'Pause all Bots'}</button></div>
}
