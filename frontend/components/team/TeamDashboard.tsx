'use client';
import {useEffect,useMemo,useRef,useState} from 'react';
import Image from 'next/image';
import {useVirtualizer} from '@tanstack/react-virtual';
import Avatar from './BotAvatar';
import {identityLabel,jobTitle} from './identity';
import {Grid2X2, List, Network, MoreHorizontal, ArrowUp, Sparkles} from 'lucide-react';

export type TeamBot={id:string;name:string;title:string;color:string;shape:string;character?:{name:string;role:string;tags:string[];avatar_url:string}|null};
export type TeamEvent={id:number;bot_id:string|null;type:string;payload:Record<string,unknown>;created_at:number};
export type Overview={bots:number;runs_today:number;last_activity:number|null;events:TeamEvent[];states:Record<string,string>};
export const PAGE_SIZE=60;
export function collections<T extends TeamBot>(bots:T[]){
  const groups=new Map<string,T[]>();
  for(const bot of bots){const tags=bot.character?.tags.length?bot.character.tags:['Uncategorized'];const seen=new Set<string>();for(const tag of tags){const key=tag.trim();if(!key||seen.has(key.toLowerCase()))continue;seen.add(key.toLowerCase());const existing=[...groups.keys()].find(k=>k.toLowerCase()===key.toLowerCase())||key;groups.set(existing,[...(groups.get(existing)||[]),bot])}}
  return [...groups.entries()].sort(([a],[b])=>a.localeCompare(b));
}
export function sidebarCollections<T extends TeamBot>(bots:T[]){
  const groups=collections(bots);
  return groups.length===1&&groups[0][0]==='Uncategorized'?[]:groups;
}
export function describeEvent(e:TeamEvent,names:Map<string,string>){
 const name=e.bot_id?(names.get(e.bot_id)||'Bot'):'Team';
 switch(e.type){case 'message.sent':return `${name}: ${String(e.payload.summary||'')}`;case 'run.started':return `${name} started a run.`;case 'run.finished':return `${name} finished: ${String(e.payload.status||'unknown')}.`;case 'bot.state_changed':return `${name}: ${String(e.payload.state||'unknown')}.`;case 'error.raised':return `${name}: ${String(e.payload.message||'A run failed.')}`;default:return `${name}: ${e.type}`}
}
export function timeLabel(value:number|null){return value?new Date(value*1000).toLocaleString():'No recorded activity'}
export function useOverview(enabled:boolean,botId=''){
 const [data,setData]=useState<Overview|null>(null),[error,setError]=useState('');
 useEffect(()=>{if(!enabled)return;const abort=new AbortController();let timer:ReturnType<typeof setTimeout>;
  async function poll(){try{const date=new Date();date.setHours(0,0,0,0);const q=new URLSearchParams({day_start:String(date.getTime()/1000)});if(botId)q.set('bot_id',botId);const r=await fetch('/api/team/overview?'+q,{signal:abort.signal});if(!r.ok)throw Error('Could not load recorded activity.');const result=await r.json();if(!abort.signal.aborted){setData(result);setError('')}}catch(e){if(!abort.signal.aborted)setError((e as Error).message)}if(!abort.signal.aborted)timer=setTimeout(poll,3000)}
  void poll();return()=>{abort.abort();clearTimeout(timer)};
 },[enabled,botId]);return {data,error};
}
export function Activity({events,bots}:{events:TeamEvent[];bots:TeamBot[]}){const names=useMemo(()=>new Map(bots.map(b=>[b.id,identityLabel(b)])),[bots]);return <div className="team-activity">{events.length?events.map(e=><div className="team-event" key={e.id}><span className="event-spark">✧</span><div>{describeEvent(e,names)}<small>{timeLabel(e.created_at)}</small></div></div>):<p className="team-empty">No recorded activity yet.</p>}</div>}
export function SpotlightActivity({bot,bots}:{bot:TeamBot;bots:TeamBot[]}){const {data,error}=useOverview(true,bot.id);return <section className="spotlight-activity"><strong>Recent activity</strong>{error?<p className="error">{error}</p>:data?<Activity events={data.events} bots={bots}/>:<p className="team-empty">Loading activity…</p>}</section>}

type Props={bots:TeamBot[];query:string;collection:string;selected:string;working:boolean;quickError:string;onOpen:(id:string)=>void;onEdit:(id:string)=>void;onDuplicate:(id:string)=>void;onSend:(text:string)=>void;onCreate:()=>void};
export default function TeamDashboard({bots,query,collection,selected,working,quickError,onOpen,onEdit,onDuplicate,onSend,onCreate}:Props){
 const [view,setView]=useState<'grid'|'list'|'cluster'>('grid'),[page,setPage]=useState(0),[mission,setMission]=useState(''),[width,setWidth]=useState(700),[menu,setMenu]=useState('');
 const viewport=useRef<HTMLDivElement>(null);const {data,error}=useOverview(true);
 const groups=useMemo(()=>collections(bots),[bots]);
 const filtered=useMemo(()=>{let items=bots.filter(b=>`${b.name} ${b.title} ${b.character?.name||''} ${(b.character?.tags||[]).join(' ')}`.toLowerCase().includes(query.trim().toLowerCase()));if(collection)items=items.filter(b=>(b.character?.tags.length?b.character.tags:['Uncategorized']).some(t=>t.toLowerCase()===collection.toLowerCase()));if(view==='cluster')items=[...items].sort((a,b)=>(a.character?.tags[0]||'Uncategorized').localeCompare(b.character?.tags[0]||'Uncategorized')||a.name.localeCompare(b.name));return items},[bots,query,collection,view]);
 useEffect(()=>{setPage(0);if(viewport.current)viewport.current.scrollTop=0},[query,collection,view]);
 useEffect(()=>{const el=viewport.current;if(!el)return;const observer=new ResizeObserver(()=>setWidth(el.clientWidth));observer.observe(el);setWidth(el.clientWidth);return()=>observer.disconnect()},[]);
 const pages=Math.max(1,Math.ceil(filtered.length/PAGE_SIZE)),safePage=Math.min(page,pages-1),items=filtered.slice(safePage*PAGE_SIZE,(safePage+1)*PAGE_SIZE);
 const columns=view==='list'?1:Math.max(1,Math.floor((width+12)/190));const rowHeight=view==='list'?145:view==='cluster'?275:250;
 const rows:{label:string;bots:TeamBot[]}[]=[];
 for(const item of items){const label=view==='cluster'?(item.character?.tags[0]||'Uncategorized'):'';const last=rows[rows.length-1];if(!last||last.bots.length>=columns||last.label!==label)rows.push({label,bots:[item]});else last.bots.push(item)}
 // TanStack Virtual is intentionally not memoized; its scroll state changes independently.
 // eslint-disable-next-line react-hooks/incompatible-library
 const virtual=useVirtualizer({count:rows.length,getScrollElement:()=>viewport.current,estimateSize:()=>rowHeight,overscan:2});
 const chosen=bots.find(b=>b.id===selected);
 return <div className="command-center"><div className="command-head"><div><p className="eyebrow">YOUR TEAM COMMAND CENTER</p><h1>{collection||'Your team, at a glance.'}</h1><p>{filtered.length} {filtered.length===1?'Bot':'Bots'} {collection?'in this collection':'shown'} · Real activity only</p></div><div className="view-switch" aria-label="Gallery layout">{([['grid','Grid',Grid2X2],['list','List',List],['cluster','Cluster',Network]] as const).map(([key,label,Icon])=><button key={key} aria-label={`${label} view`} aria-pressed={view===key} className={view===key?'active':''} onClick={()=>setView(key)}><Icon size={16}/><span>{label}</span></button>)}</div></div>
 <div className="command-layout"><section className="gallery-panel" aria-label="Bot gallery"><div className="gallery-scroll" ref={viewport}>{items.length?<div style={{height:virtual.getTotalSize(),position:'relative'}}>{virtual.getVirtualItems().map(row=><div key={row.key} className={`gallery-row ${view}`} style={{position:'absolute',top:0,left:0,width:'100%',height:rowHeight,transform:`translateY(${row.start}px)`,gridTemplateColumns:`repeat(${columns}, minmax(0, 1fr))`}}>{view==='cluster'&&<div className="cluster-heading">{rows[row.index].label}</div>}{rows[row.index].bots.map(bot=>{const state=data?.states[bot.id]||'No recorded status';return <article className={`bot-card ${bot.id===selected?'selected':''}`} key={bot.id}><button className="bot-card-open" onClick={()=>onOpen(bot.id)} aria-label={`Open ${bot.name} spotlight`} aria-pressed={bot.id===selected}><div className={`bot-card-art ${bot.color}`}>{bot.character?<Image src={bot.character.avatar_url} alt="" width={230} height={180} unoptimized/>:<Avatar bot={{...bot,character:null}} size="large"/>}</div><div className="bot-card-details"><strong><i className={`real-state ${state==='working'?'busy':state==='error'?'failed':state==='No recorded status'?'unknown':'recorded'}`} title={state}/>{bot.name}</strong><span>{jobTitle(bot)}</span>{view==='cluster'&&<small>{bot.character?.tags[0]||'Uncategorized'}</small>}</div></button><div className="card-menu"><button aria-label={`${bot.name} options`} onClick={()=>setMenu(menu===bot.id?'':bot.id)}><MoreHorizontal size={19}/></button>{menu===bot.id&&<div className="card-dropdown"><button onClick={()=>{setMenu('');onOpen(bot.id)}}>Open chat</button><button onClick={()=>{setMenu('');onEdit(bot.id)}}>Edit Bot</button><button disabled={working} onClick={()=>{setMenu('');onDuplicate(bot.id)}}>Duplicate Bot</button></div>}</div></article>})}</div>)}</div>:<div className="gallery-empty"><Sparkles/><h2>{bots.length?'No matching Bots':'Your gallery is empty'}</h2><p>{bots.length?'Try another search or collection.':'Create a Bot to see it here. Imported characters are revealed when assigned.'}</p>{!bots.length&&<button className="primary" onClick={onCreate}>Create your first Bot</button>}</div>}</div><div className="gallery-pagination"><span>{filtered.length?`${safePage*PAGE_SIZE+1}–${Math.min((safePage+1)*PAGE_SIZE,filtered.length)} of ${filtered.length}`:'No Bots to show'}</span><div><button disabled={safePage===0} onClick={()=>{setPage(safePage-1);viewport.current?.scrollTo(0,0)}}>Previous</button><span>Page {safePage+1} of {pages}</span><button disabled={safePage>=pages-1} onClick={()=>{setPage(safePage+1);viewport.current?.scrollTo(0,0)}}>Next</button></div></div></section>
 <aside className="command-aside"><section className="team-panel"><h2>Activity</h2>{error?<p className="error">{error}</p>:data?<Activity events={data.events} bots={bots}/>:<p className="team-empty">Loading activity…</p>}</section><section className="team-panel"><h2>Team stats</h2>{data?<dl className="team-stats"><div><dt>Bots</dt><dd>{data.bots}</dd></div><div><dt>Runs today</dt><dd>{data.runs_today}</dd></div><div className="last"><dt>Last activity</dt><dd>{timeLabel(data.last_activity)}</dd></div></dl>:<p className="team-empty">{error?'Stats unavailable.':'Loading stats…'}</p>}</section></aside></div>
 <form className="quick-mission" onSubmit={e=>{e.preventDefault();if(!mission.trim()||!chosen||working)return;onSend(mission);setMission('')}}><label htmlFor="quick-mission">✦ QUICK MISSION{chosen?` · ${identityLabel(chosen)}`:' · Select a Bot'}</label><input id="quick-mission" value={mission} onChange={e=>setMission(e.target.value)} placeholder={chosen?`Message ${chosen.name}…`:'Select a Bot first'} disabled={!chosen||working}/><button aria-label="Send quick mission" disabled={!chosen||working||!mission.trim()}><ArrowUp size={19}/></button></form>{quickError&&<div className="error" role="alert">{quickError}</div>}<span className="sr-only">{groups.length} collections</span></div>
}
