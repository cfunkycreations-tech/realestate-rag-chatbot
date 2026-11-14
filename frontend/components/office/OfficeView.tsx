'use client';

import {useEffect,useMemo,useRef,useState} from 'react';
import {ArrowLeft, ExternalLink, Sparkles} from 'lucide-react';
import {demoEvents,desk,HEIGHT,obstacles,OfficeBot,OfficeCharacter,OfficeEvent,positionAt,projectOffice,WIDTH} from './office-state';

const TILE=20;
const colors:Record<string,string>={lavender:'#c6b0ed',peach:'#f3b9a2',mint:'#a8d7bd',blue:'#a9c7e7',yellow:'#e8d59c'};
const demoBots:OfficeBot[]=[
  {id:'demo-1',name:'Scout',title:'Demo researcher',color:'blue',shape:'round'},
  {id:'demo-2',name:'Milo',title:'Demo writer',color:'peach',shape:'round'},
  {id:'demo-3',name:'Nova',title:'Demo planner',color:'mint',shape:'round'},
];
function description(e:OfficeEvent,names:Map<string,string>):string{
  const name=e.bot_id?(names.get(e.bot_id)||'Bot'):'Team';
  if(e.type==='message.sent')return `${name}: ${String(e.payload.summary||'')}`;
  if(e.type==='bot.state_changed')return `${name} is ${String(e.payload.state||'idle')}.`;
  if(e.type==='error.raised')return `${name}: ${String(e.payload.message||'A run failed.')}`;
  if(e.type==='run.started')return `${name} started a run.`;
  if(e.type==='run.finished')return `${name} finished: ${String(e.payload.status||'done')}.`;
  if(e.type==='group.session_started')return 'Demo: the team gathers in the meeting room.';
  if(e.type==='group.session_ended')return 'Demo: the meeting ends.';
  return '';
}
function rounded(ctx:CanvasRenderingContext2D,x:number,y:number,w:number,h:number,r:number,color:string){
  ctx.fillStyle=color;ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fill();
}
function drawScene(ctx:CanvasRenderingContext2D,bots:OfficeBot[],characters:OfficeCharacter[],now:number,reduced:boolean,images:Map<string,HTMLImageElement>){
  ctx.clearRect(0,0,WIDTH*TILE,HEIGHT*TILE);
  ctx.fillStyle='#19181d';ctx.fillRect(0,0,WIDTH*TILE,HEIGHT*TILE);
  for(let y=0;y<HEIGHT;y++)for(let x=0;x<WIDTH;x++){
    ctx.fillStyle=(x+y)%2?'#232228':'#26252b';ctx.fillRect(x*TILE,y*TILE,TILE-1,TILE-1);
  }
  rounded(ctx,31*TILE,2*TILE,8*TILE,13*TILE,8,'#302a39');
  rounded(ctx,33*TILE,5*TILE,4*TILE,4*TILE,10,'#574a63');
  ctx.fillStyle='#c7b6d7';ctx.font='bold 9px sans-serif';ctx.fillText('MEETING ROOM',32*TILE,3*TILE);
  const blocks=obstacles(0);ctx.fillStyle='#72617b';
  for(const point of blocks){const [x,y]=point.split(',').map(Number);ctx.fillRect(x*TILE,y*TILE,5,TILE-1)}
  ctx.fillStyle='#b6a0dc';ctx.font='bold 10px sans-serif';ctx.fillText('FUNK BOT  /  OFFICE',14,24);
  bots.forEach((bot,index)=>{
    const p=desk(index),x=p.x*TILE,y=p.y*TILE;
    rounded(ctx,x-13,y-20,27,12,3,'#716479');rounded(ctx,x-8,y-24,17,8,2,'#b4a0d5');
    ctx.fillStyle='#aaa4b0';ctx.font='9px sans-serif';ctx.fillText(bot.name.slice(0,12),x-14,y+25);
  });
  characters.forEach(character=>{
    const point=positionAt(character.motion,now,reduced),x=point.x*TILE,y=point.y*TILE;
    const image=images.get(character.bot.id);
    if(image?.complete&&image.naturalWidth){ctx.drawImage(image,x-13,y-15,26,26)}
    else{
      rounded(ctx,x-11,y-13,22,22,character.bot.shape==='square'?6:11,colors[character.bot.color]||colors.lavender);
      ctx.fillStyle='#282430';ctx.fillRect(x-5,y-5,2,3);ctx.fillRect(x+3,y-5,2,3);
    }
    if(character.state==='working'){ctx.fillStyle='#d0b7ff';ctx.fillRect(x+11,y-15,5,5)}
    if(character.state==='done'){ctx.fillStyle='#a8d8b8';ctx.font='bold 12px sans-serif';ctx.fillText('✓',x+10,y-11)}
    if(character.state==='error'){ctx.fillStyle='#f0a2a2';ctx.font='bold 12px sans-serif';ctx.fillText('!',x+11,y-11)}
    if(character.bubble&&now-character.bubbleAt<7000&&now>=character.bubbleAt){
      const text=character.bubble.slice(0,34)+(character.bubble.length>34?'…':'');
      ctx.font='9px sans-serif';const width=Math.min(190,Math.max(50,ctx.measureText(text).width+14));
      const bx=Math.max(1,Math.min(WIDTH*TILE-width-1,x-width/2)),by=Math.max(26,y-37);
      rounded(ctx,bx,by,width,17,5,'#ece6f3');ctx.fillStyle='#302936';ctx.fillText(text,bx+6,by+12);
    }
  });
}

type Props={bots:OfficeBot[];onBack:()=>void;onOpenBot:(id:string)=>void};
export default function OfficeView({bots,onBack,onOpenBot}:Props){
  const [events,setEvents]=useState<OfficeEvent[]>([]),[error,setError]=useState(''),[demoStart]=useState<number|null>(null),[clock,setClock]=useState(0),[page,setPage]=useState(0);
  const canvas=useRef<HTMLCanvasElement>(null),scene=useRef<OfficeCharacter[]>([]),nowRef=useRef(0);
  const maxPage=Math.max(0,Math.ceil(bots.length/50)-1),safePage=Math.min(page,maxPage);
  const visibleBots=demoStart===null?bots.slice(safePage*50,(safePage+1)*50):demoBots;
  const displayEvents=useMemo(()=>demoStart===null?events:demoEvents(demoStart),[demoStart,events]);
  const names=useMemo(()=>new Map(visibleBots.map(b=>[b.id,b.name])),[visibleBots]);
  useEffect(()=>{
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined,cursor=0;
    async function poll(){
      try{
        let count=0;
        do{
          const response=await fetch(`/api/events?since=${cursor}&limit=500`,{signal:controller.signal});
          if(!response.ok)throw new Error('Could not load office activity.');
          const page=await response.json() as {events:OfficeEvent[];next_cursor:number};
          if(controller.signal.aborted)return;
          cursor=page.next_cursor;count=page.events.length;
          if(count)setEvents(current=>[...current,...page.events]);
        }while(count===500&&!controller.signal.aborted);
        if(!controller.signal.aborted)setError('');
      }catch(e){if(!controller.signal.aborted)setError((e as Error).message)}
      if(!controller.signal.aborted)timer=setTimeout(poll,2000);
    }
    void poll();return()=>{controller.abort();if(timer)clearTimeout(timer)};
  },[]);
  useEffect(()=>{
    if(demoStart===null)return;
    const timer=setInterval(()=>setClock(Date.now()),500);
    return()=>clearInterval(timer);
  },[demoStart]);
  useEffect(()=>{
    const element=canvas.current,ctx=element?.getContext('2d');if(!element||!ctx)return;
    const media=window.matchMedia('(prefers-reduced-motion: reduce)'),images=new Map<string,HTMLImageElement>();
    for(const bot of visibleBots){if(bot.character){const img=new window.Image();img.src=bot.character.avatar_url;images.set(bot.id,img)}}
    let frame=0,lastEventCount=-1;
    const draw=()=>{
      if(document.hidden)return;
      const now=Date.now();nowRef.current=now;
      const current=displayEvents.filter(e=>e.created_at*1000<=now);
      if(lastEventCount!==current.length){scene.current=projectOffice(visibleBots,current,now);lastEventCount=current.length}
      drawScene(ctx,visibleBots,scene.current,now,media.matches,images);
      frame=requestAnimationFrame(draw);
    };
    const visibility=()=>{cancelAnimationFrame(frame);if(!document.hidden)draw()};
    document.addEventListener('visibilitychange',visibility);draw();
    return()=>{cancelAnimationFrame(frame);document.removeEventListener('visibilitychange',visibility)};
  },[visibleBots,displayEvents]);
  const visibleEvents=displayEvents.filter(e=>demoStart===null||e.created_at*1000<=clock).slice(-12).reverse();
  function clickCanvas(event:React.MouseEvent<HTMLCanvasElement>){
    if(demoStart!==null)return;
    const rect=event.currentTarget.getBoundingClientRect();
    const x=(event.clientX-rect.left)*WIDTH*TILE/rect.width,y=(event.clientY-rect.top)*HEIGHT*TILE/rect.height;
    const found=scene.current.find(c=>{const p=positionAt(c.motion,nowRef.current);return Math.hypot(x-p.x*TILE,y-p.y*TILE)<15});
    if(found)onOpenBot(found.bot.id);
  }
  return <div className="office-view"><header className="office-header"><button className="icon-btn mobile-back" aria-label="Back to roster" onClick={onBack}><ArrowLeft size={19}/></button><div><strong>Office</strong><span>A little window into your team</span></div>{bots.length>50&&<div className="office-paging"><button className="secondary" disabled={safePage===0} onClick={()=>setPage(safePage-1)}>Previous</button><span>{safePage+1} / {maxPage+1}</span><button className="secondary" disabled={safePage>=maxPage} onClick={()=>setPage(safePage+1)}>Next</button></div>}</header><div className="office-content"><div className="office-title"><div><p className="eyebrow">{demoStart===null?'LIVE · REAL EVENTS ONLY':'DEMO · SCRIPTED ACTIVITY'}</p><h1>{demoStart===null?'Your team, at a glance.':'A little office preview.'}</h1><p>{demoStart===null?'This view reflects recorded Bot activity. Group meetings aren’t available yet.':'This is a scripted example. It does not use your Bots or call a model.'}</p></div><div className="office-badge"><Sparkles size={14}/>{demoStart===null?'Live':'Demo'}</div></div>{error&&demoStart===null&&<div className="error">{error} Retrying automatically.</div>}<div className="office-grid"><div className="office-scene"><div className="office-canvas-scroll"><canvas ref={canvas} width={WIDTH*TILE} height={HEIGHT*TILE} onClick={clickCanvas} aria-label={demoStart===null?'Office showing your Bots and their recorded activity':'Scripted demonstration of an office'}>Your browser does not support the office canvas.</canvas></div><div className="office-scene-footer"><span>{demoStart===null?'LIVE ACTIVITY':'SCRIPTED DEMO'}</span><span>{demoStart===null?'Pan to explore · select a Bot':'No model calls'}</span></div></div><aside className="office-activity"><div className="office-activity-head"><div><p className="eyebrow">{demoStart===null?'FROM YOUR TIMELINE':'DEMO TIMELINE'}</p><strong>Activity</strong></div><span className="status-dot"/></div><div className="office-events" aria-live="polite">{visibleEvents.length?visibleEvents.map(e=><div className="office-event" key={e.id}><span/><p>{description(e,names)}<small>{new Date(e.created_at*1000).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})}</small></p></div>):<p className="field-hint">{demoStart===null?'No recorded activity yet. Start a conversation with a Bot.':'The demo is getting started.'}</p>}</div></aside></div>{demoStart===null&&visibleBots.length>0&&<div className="office-accessible"><strong>Open a Bot</strong>{visibleBots.map(bot=><button key={bot.id} onClick={()=>onOpenBot(bot.id)}>{bot.name}<ExternalLink size={12}/></button>)}</div>}{demoStart===null&&visibleBots.length===0&&<p className="field-hint">Create a Bot in your roster to see it here.</p>}</div></div>
}
