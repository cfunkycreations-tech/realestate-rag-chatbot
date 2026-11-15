'use client';

import {useEffect,useMemo,useRef,useState} from 'react';
import {identityLabel,jobTitle} from '../team/identity';
import {ArrowLeft, ExternalLink, Sparkles} from 'lucide-react';
import {demoEvents,desk,HEIGHT,obstacles,OfficeBot,OfficeCharacter,OfficeEvent,positionAt,projectOffice,WIDTH} from './office-state';

const TILE=32;
type Palette={floor:string;grid:string;room:string;gold:string;bright:string;panel:string;ink:string;muted:string;purple:string};
function readPalette(element:HTMLElement):Palette{const css=getComputedStyle(element);const v=(name:string)=>css.getPropertyValue(name).trim();return {floor:v("--command-bg"),grid:v("--command-grid"),room:v("--command-room"),gold:v("--command-frame"),bright:v("--command-frame-bright"),panel:v("--command-panel-raised"),ink:v("--command-ink"),muted:v("--command-muted"),purple:v("--command-purple")}}
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
  if(e.type==='group.session_started')return `${e.payload.mission_id?'Mission':'Demo'}: the team gathers in the meeting room.`;
  if(e.type==='group.session_ended')return `${e.payload.mission_id?'Mission':'Demo'}: the meeting ends.`;
  if(e.type==='group.delegated')return `${name} delegated: ${String(e.payload.summary||'')}`;
  if(e.type==='group.replied')return `${name} replied: ${String(e.payload.summary||'')}`;
  return '';
}
function rounded(ctx:CanvasRenderingContext2D,x:number,y:number,w:number,h:number,r:number,color:string){
  ctx.fillStyle=color;ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fill();
}
function drawScene(ctx:CanvasRenderingContext2D,bots:OfficeBot[],characters:OfficeCharacter[],now:number,reduced:boolean,images:Map<string,HTMLImageElement>,palette:Palette){
  ctx.clearRect(0,0,WIDTH*TILE,HEIGHT*TILE);
  const floor=ctx.createLinearGradient(0,0,WIDTH*TILE,HEIGHT*TILE);floor.addColorStop(0,palette.room);floor.addColorStop(1,palette.floor);ctx.fillStyle=floor;ctx.fillRect(0,0,WIDTH*TILE,HEIGHT*TILE);
  ctx.strokeStyle=palette.grid;ctx.lineWidth=1;ctx.globalAlpha=.45;ctx.beginPath();
  for(let x=0;x<=WIDTH;x++){ctx.moveTo(x*TILE,0);ctx.lineTo(x*TILE,HEIGHT*TILE)}
  for(let y=0;y<=HEIGHT;y++){ctx.moveTo(0,y*TILE);ctx.lineTo(WIDTH*TILE,y*TILE)}ctx.stroke();ctx.globalAlpha=1;
  ctx.save();ctx.shadowColor=palette.purple;ctx.shadowBlur=14;rounded(ctx,31*TILE,2*TILE,8*TILE,13*TILE,12,palette.room);ctx.restore();
  ctx.strokeStyle=palette.gold;ctx.lineWidth=3;ctx.beginPath();ctx.roundRect(31*TILE,2*TILE,8*TILE,13*TILE,12);ctx.stroke();
  rounded(ctx,33*TILE,5*TILE,4*TILE,4*TILE,12,palette.panel);ctx.strokeStyle=palette.gold;ctx.lineWidth=2;ctx.strokeRect(33*TILE+2,5*TILE+2,4*TILE-4,4*TILE-4);
  ctx.fillStyle=palette.bright;ctx.font='bold 12px sans-serif';ctx.fillText('MEETING ROOM',31.5*TILE,3*TILE);
  const blocks=obstacles(0);ctx.fillStyle=palette.gold;for(const point of blocks){const [x,y]=point.split(',').map(Number);ctx.fillRect(x*TILE,y*TILE,4,TILE-1)}
  ctx.fillStyle=palette.bright;ctx.font='bold 14px sans-serif';ctx.fillText('FUNK BOT  /  OFFICE',18,25);
  bots.forEach((bot,index)=>{
    const p=desk(index),x=p.x*TILE,y=p.y*TILE;
    const glow=ctx.createRadialGradient(x,y,2,x,y,50);glow.addColorStop(0,palette.purple);glow.addColorStop(1,'transparent');ctx.save();ctx.globalAlpha=.23;ctx.fillStyle=glow;ctx.fillRect(x-50,y-50,100,100);ctx.restore();
    rounded(ctx,x-29,y+12,58,13,4,palette.panel);ctx.strokeStyle=palette.gold;ctx.lineWidth=1;ctx.strokeRect(x-29,y+12,58,13);
    ctx.textAlign='center';ctx.fillStyle=palette.ink;ctx.font='bold 15px sans-serif';ctx.fillText(bot.name,x,y+41,92);ctx.fillStyle=palette.muted;ctx.font='13px sans-serif';ctx.fillText(jobTitle(bot),x,y+56,92);ctx.textAlign='start';
  });
  characters.forEach((character,index)=>{
    const point=positionAt(character.motion,now,reduced),x=point.x*TILE,y=point.y*TILE;
    const bob=!reduced&&['idle','done'].includes(character.state)?Math.sin(now/1000+index)*2:0;
    const image=images.get(character.bot.id);
    if(image?.complete&&image.naturalWidth){ctx.drawImage(image,x-40,y-64+bob,80,80)}
    else{rounded(ctx,x-30,y-54+bob,60,60,character.bot.shape==='square'?10:30,colors[character.bot.color]||colors.lavender);ctx.fillStyle=palette.floor;ctx.fillRect(x-10,y-34+bob,5,7);ctx.fillRect(x+5,y-34+bob,5,7)}
    if(character.state==='working'){ctx.fillStyle=palette.bright;ctx.beginPath();ctx.arc(x+29,y-43+bob,5,0,Math.PI*2);ctx.fill()}
    if(character.state==='done'){ctx.fillStyle=palette.bright;ctx.font='bold 16px sans-serif';ctx.fillText('✓',x+27,y-38+bob)}
    if(character.state==='error'){ctx.fillStyle='#f09cae';ctx.font='bold 16px sans-serif';ctx.fillText('!',x+27,y-38+bob)}
    if(character.bubble&&now-character.bubbleAt<7000&&now>=character.bubbleAt){
      const text=character.bubble.slice(0,34)+(character.bubble.length>34?'…':'');ctx.font='11px sans-serif';const width=Math.min(240,Math.max(60,ctx.measureText(text).width+18));
      const bx=Math.max(1,Math.min(WIDTH*TILE-width-1,x-width/2)),by=Math.max(28,y-78);rounded(ctx,bx,by,width,22,6,palette.ink);ctx.fillStyle=palette.floor;ctx.fillText(text,bx+8,by+15);
    }
  });
}

type Props={bots:OfficeBot[];onBack:()=>void;onOpenBot:(id:string)=>void};
export default function OfficeView({bots,onBack,onOpenBot}:Props){
  const [events,setEvents]=useState<OfficeEvent[]>([]),[error,setError]=useState(''),[demoStart]=useState<number|null>(null),[clock,setClock]=useState(0),[page,setPage]=useState(0);
  const canvas=useRef<HTMLCanvasElement>(null),scene=useRef<OfficeCharacter[]>([]),nowRef=useRef(0);
  const maxPage=Math.max(0,Math.ceil(bots.length/50)-1),safePage=Math.min(page,maxPage);
  const visibleBots=useMemo(()=>demoStart===null?bots.slice(safePage*50,(safePage+1)*50):demoBots,[bots,safePage,demoStart]);
  const displayEvents=useMemo(()=>demoStart===null?events:demoEvents(demoStart),[demoStart,events]);
  const names=useMemo(()=>new Map(bots.map(b=>[b.id,identityLabel(b)])),[bots]);
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
    const media=window.matchMedia('(prefers-reduced-motion: reduce)'),images=new Map<string,HTMLImageElement>(),palette=readPalette(element);
    for(const bot of visibleBots){if(bot.character){const img=new window.Image();img.src=bot.character.avatar_url;images.set(bot.id,img)}}
    let frame=0,lastEventCount=-1;
    const draw=()=>{
      if(document.hidden)return;
      const now=Date.now();nowRef.current=now;
      const current=displayEvents.filter(e=>e.created_at*1000<=now);
      if(lastEventCount!==current.length){scene.current=projectOffice(visibleBots,current,now);lastEventCount=current.length}
      drawScene(ctx,visibleBots,scene.current,now,media.matches,images,palette);
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
    const found=scene.current.find(c=>{const p=positionAt(c.motion,nowRef.current);return Math.hypot(x-p.x*TILE,y-(p.y*TILE-20))<36});
    if(found)onOpenBot(found.bot.id);
  }
  return <div className="office-view"><header className="office-header"><button className="icon-btn mobile-back" aria-label="Back to roster" onClick={onBack}><ArrowLeft size={19}/></button><div><strong>Office</strong><span>A little window into your team</span></div>{bots.length>50&&<div className="office-paging"><button className="secondary" disabled={safePage===0} onClick={()=>setPage(safePage-1)}>Previous</button><span>{safePage+1} / {maxPage+1}</span><button className="secondary" disabled={safePage>=maxPage} onClick={()=>setPage(safePage+1)}>Next</button></div>}</header><div className="office-content"><div className="office-title"><div><p className="eyebrow">{demoStart===null?'LIVE · REAL EVENTS ONLY':'DEMO · SCRIPTED ACTIVITY'}</p><h1>{demoStart===null?'Your team, at a glance.':'A little office preview.'}</h1><p>{demoStart===null?'This view reflects recorded Bot activity and real group mission meetings.':'This is a scripted example. It does not use your Bots or call a model.'}</p></div><div className="office-badge"><Sparkles size={14}/>{demoStart===null?'Live':'Demo'}</div></div>{error&&demoStart===null&&<div className="error">{error} Retrying automatically.</div>}<div className="office-grid"><div className="office-scene"><div className="office-canvas-scroll"><canvas ref={canvas} width={WIDTH*TILE} height={HEIGHT*TILE} onClick={clickCanvas} aria-label={demoStart===null?'Office showing your Bots and their recorded activity':'Scripted demonstration of an office'}>Your browser does not support the office canvas.</canvas></div><div className="office-scene-footer"><span>{demoStart===null?'LIVE ACTIVITY':'SCRIPTED DEMO'}</span><span>{demoStart===null?'Pan to explore · select a Bot':'No model calls'}</span></div></div><aside className="office-activity"><div className="office-activity-head"><div><p className="eyebrow">{demoStart===null?'FROM YOUR TIMELINE':'DEMO TIMELINE'}</p><strong>Activity</strong></div><span className="status-dot"/></div><div className="office-events" aria-live="polite">{visibleEvents.length?visibleEvents.map(e=><div className="office-event" key={e.id}><span/><p>{description(e,names)}<small>{new Date(e.created_at*1000).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})}</small></p></div>):<p className="field-hint">{demoStart===null?'No recorded activity yet. Start a conversation with a Bot.':'The demo is getting started.'}</p>}</div></aside></div>{demoStart===null&&visibleBots.length>0&&<div className="office-accessible"><strong>Open a Bot</strong>{visibleBots.map(bot=><button key={bot.id} onClick={()=>onOpenBot(bot.id)}>{identityLabel(bot)}<ExternalLink size={12}/></button>)}</div>}{demoStart===null&&visibleBots.length===0&&<p className="field-hint">Create a Bot in your roster to see it here.</p>}</div></div>
}
