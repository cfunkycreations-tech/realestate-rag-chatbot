/** Deterministic office projection. Nothing here invokes a model or invents live events. */
export type Point = {x:number; y:number};
export type OfficeBot = {id:string; name:string; title:string; color:string; shape:string; character?:{name:string;avatar_url:string}|null};
export type OfficeEvent = {id:number; bot_id:string|null; run_id:string|null; type:string; payload:Record<string,unknown>; created_at:number};
export type Motion = {path:Point[]; at:number};
export type OfficeCharacter = {bot:OfficeBot; state:string; motion:Motion; bubble:string; bubbleAt:number};
export const WIDTH=40, HEIGHT=24, STEP_MS=180;
const key=(p:Point)=>`${p.x},${p.y}`;
export const desk=(index:number):Point=>({x:2+(index%10)*3,y:5+Math.floor(index/10)*3});
export const seat=(index:number):Point=>({x:33+(index%5),y:5+(Math.floor(index/5)%5)});
export function obstacles(count:number):Set<string>{
  const blocks=new Set<string>();
  for(let y=2;y<=14;y++)if(y!==8)blocks.add(`30,${y}`);
  for(let i=0;i<count;i++){const p=desk(i);blocks.add(`${p.x},${p.y-1}`)}
  return blocks;
}
export function pathfind(from:Point,to:Point,blocked:Set<string>):Point[]{
  const inside=(p:Point)=>p.x>=0&&p.y>=0&&p.x<WIDTH&&p.y<HEIGHT;
  if(!inside(from)||!inside(to)||blocked.has(key(to)))return [from];
  const frontier=[from],came=new Map<string,Point>(),cost=new Map<string,number>([[key(from),0]]);
  const heuristic=(p:Point)=>Math.abs(p.x-to.x)+Math.abs(p.y-to.y);
  while(frontier.length){
    frontier.sort((a,b)=>(cost.get(key(a))!+heuristic(a))-(cost.get(key(b))!+heuristic(b))||a.y-b.y||a.x-b.x);
    const current=frontier.shift()!;
    if(current.x===to.x&&current.y===to.y){const path=[current];while(came.has(key(path[0])))path.unshift(came.get(key(path[0]))!);return path}
    for(const next of [{x:current.x+1,y:current.y},{x:current.x,y:current.y+1},{x:current.x-1,y:current.y},{x:current.x,y:current.y-1}]){
      if(!inside(next)||blocked.has(key(next)))continue;
      const nextCost=cost.get(key(current))!+1;
      if(nextCost<(cost.get(key(next))??Infinity)){cost.set(key(next),nextCost);came.set(key(next),current);frontier.push(next)}
    }
  }
  return [from];
}
export function positionAt(motion:Motion,now:number,reduced=false):Point{
  const p=motion.path;if(p.length===1||reduced)return p[p.length-1];
  const progress=Math.max(0,(now-motion.at)/STEP_MS),index=Math.min(Math.floor(progress),p.length-1);
  if(index===p.length-1)return p[index];
  const t=progress-index;return {x:p[index].x+(p[index+1].x-p[index].x)*t,y:p[index].y+(p[index+1].y-p[index].y)*t};
}
export function projectOffice(bots:OfficeBot[],events:OfficeEvent[],now:number):OfficeCharacter[]{
  const blocked=obstacles(bots.length);
  const characters=bots.map((bot,i)=>({bot,state:'idle',motion:{path:[desk(i)],at:0},bubble:'',bubbleAt:0}));
  const byId=new Map(characters.map((c,i)=>[c.bot.id,{character:c,index:i}]));
  const move=(c:OfficeCharacter,target:Point,at:number)=>{
    const current=positionAt(c.motion,at),start={x:Math.round(current.x),y:Math.round(current.y)};
    c.motion={path:pathfind(start,target,blocked),at};
  };
  for(const e of events){
    const at=e.created_at*1000;if(at>now)continue;
    if(e.type==='group.session_started'||e.type==='group.session_ended'){
      const ids=Array.isArray(e.payload.participants)?e.payload.participants:[];
      ids.forEach((id,seatIndex)=>{if(typeof id!=='string')return;const found=byId.get(id);if(!found)return;
        found.character.state=e.type==='group.session_started'?'meeting':'idle';
        move(found.character,e.type==='group.session_started'?seat(seatIndex):desk(found.index),at);
      });continue;
    }
    if(!e.bot_id)continue;
    const found=byId.get(e.bot_id);if(!found)continue;
    const c=found.character;
    if(e.type==='bot.state_changed'&&typeof e.payload.state==='string'){
      c.state=e.payload.state;move(c,desk(found.index),at);
    }else if(e.type==='message.sent'&&typeof e.payload.summary==='string'){
      c.bubble=e.payload.summary;c.bubbleAt=at;
    }else if(e.type==='error.raised')c.state='error';
  }
  return characters;
}
export function demoEvents(start:number):OfficeEvent[]{
  const e=(id:number,seconds:number,type:string,bot_id:string|null,payload:Record<string,unknown>):OfficeEvent=>({id,created_at:(start+seconds*1000)/1000,type,bot_id,run_id:null,payload});
  return [
    e(1,0,'group.session_started',null,{participants:['demo-1','demo-2','demo-3']}),
    e(2,3,'message.sent','demo-1',{role:'assistant',summary:'Demo: let’s plan this together.'}),
    e(3,6,'message.sent','demo-2',{role:'assistant',summary:'Demo: I’ll gather the details.'}),
    e(4,9,'message.sent','demo-3',{role:'assistant',summary:'Demo: I’ll prepare a draft.'}),
    e(5,13,'group.session_ended',null,{participants:['demo-1','demo-2','demo-3']}),
    e(6,16,'bot.state_changed','demo-1',{state:'working'}),
    e(7,16,'bot.state_changed','demo-2',{state:'working'}),
    e(8,16,'bot.state_changed','demo-3',{state:'working'}),
    e(9,22,'bot.state_changed','demo-1',{state:'done'}),
    e(10,24,'bot.state_changed','demo-2',{state:'done'}),
    e(11,26,'bot.state_changed','demo-3',{state:'done'}),
  ];
}
