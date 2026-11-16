'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
import {Gauge as GaugeIcon} from 'lucide-react';
import {ArcGauge,BarMeter,StatusLight} from './Gauges';
import {activityMeter,attentionIndicator,botGauge,missionMeter,nextMode,readMode,spendGauge,workflowIndicator,type GaugeModel,type HudMode,type Summary,type Target} from './model';

const KEY='funkbot.missionControl.mode',POLL_MS=15000;
export const REFRESH_EVENT='funkbot:refresh';

export default function MissionControl({onNavigate,collapsed}:{onNavigate:(target:Target)=>void;collapsed:boolean}){
 const [summary,setSummary]=useState<Summary|null>(null),[failed,setFailed]=useState(false),[mode,setMode]=useState<HudMode>(()=>{try{return readMode(localStorage.getItem(KEY))}catch{return 'full'}});
 const inflight=useRef<AbortController|null>(null);
 const load=useCallback(async()=>{
  inflight.current?.abort();const ac=new AbortController();inflight.current=ac;
  try{const r=await fetch('/api/mission-control',{signal:ac.signal,cache:'no-store'});if(!r.ok)throw Error('unavailable');const d=await r.json();if(!ac.signal.aborted){setSummary(d);setFailed(false)}}
  catch{if(!ac.signal.aborted)setFailed(true)}
 },[]);
 useEffect(()=>{
  let timer:ReturnType<typeof setTimeout>|undefined,stopped=false;
  const wake=()=>{if(document.visibilityState==='visible'&&mode!=='hidden')void load()};
  const tick=()=>{if(stopped)return;wake();timer=setTimeout(tick,POLL_MS)};
  tick();document.addEventListener('visibilitychange',wake);window.addEventListener(REFRESH_EVENT,wake);
  return()=>{stopped=true;clearTimeout(timer);inflight.current?.abort();document.removeEventListener('visibilitychange',wake);window.removeEventListener(REFRESH_EVENT,wake)};
 },[load,mode]);
 function cycle(){const m=nextMode(mode);setMode(m);try{localStorage.setItem(KEY,m)}catch{/* per-viewer convenience only */}}
 const data=failed?null:summary,compact=mode==='compact';
 const open=(m:GaugeModel)=>onNavigate(m.target);
 const toggle=<button type="button" className="icon-btn hud-toggle" aria-label={`Mission Control gauges: ${mode}. Click to change.`} title={`Mission Control gauges: ${mode} (click to change)`} onClick={cycle}><GaugeIcon size={17}/><span className="hud-toggle-mode">{mode}</span></button>;
 // Nothing is drawn until real data (or a real failure) arrives, so a first paint never claims "Not connected".
 if(mode==='hidden'||collapsed||(!summary&&!failed))return toggle;
 return <>
  <section className={`hud hud-left${compact?' compact':''}`} aria-label="Workforce operations">
   <ArcGauge m={botGauge(data)} compact={compact} onOpen={open}/><BarMeter m={missionMeter(data)} compact={compact} onOpen={open}/><StatusLight m={workflowIndicator(data)} compact={compact} onOpen={open}/>
  </section>
  <section className={`hud hud-right${compact?' compact':''}`} aria-label="System and resources">
   <ArcGauge m={spendGauge(data)} compact={compact} onOpen={open}/><BarMeter m={activityMeter(data)} compact={compact} onOpen={open}/><StatusLight m={attentionIndicator(data)} compact={compact} onOpen={open}/>
  </section>
  {toggle}
 </>;
}
