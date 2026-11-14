import {describe,expect,it} from 'vitest';
import {demoEvents,desk,obstacles,pathfind,positionAt,projectOffice,seat,OfficeBot,OfficeEvent} from './office-state';

const bots:OfficeBot[]=[
  {id:'demo-1',name:'Scout',title:'Researcher',color:'blue',shape:'round'},
  {id:'demo-2',name:'Milo',title:'Writer',color:'peach',shape:'round'},
  {id:'demo-3',name:'Nova',title:'Planner',color:'mint',shape:'round'},
];

describe('office pathfinding',()=>{
  it('finds a deterministic route through the meeting room doorway',()=>{
    const blocks=obstacles(bots.length),route=pathfind(desk(0),seat(0),blocks);
    expect(route[0]).toEqual(desk(0));expect(route.at(-1)).toEqual(seat(0));
    expect(route.some(p=>p.x===30&&p.y===8)).toBe(true);
    expect(route.every(p=>!blocks.has(`${p.x},${p.y}`))).toBe(true);
    expect(pathfind(desk(0),seat(0),blocks)).toEqual(route);
  });
  it('stays put when the target is blocked',()=>{
    const start={x:0,y:0};expect(pathfind(start,{x:1,y:0},new Set(['1,0']))).toEqual([start]);
  });
});

describe('office event projection',()=>{
  it('does not invent work without events',()=>{
    const scene=projectOffice(bots,[],123456);
    expect(scene.map(c=>c.state)).toEqual(['idle','idle','idle']);
    expect(scene.map(c=>c.motion.path)).toEqual(bots.map((_,i)=>[desk(i)]));
  });
  it('uses real message content and status without invoking a model',()=>{
    const events:OfficeEvent[]=[
      {id:1,bot_id:'demo-2',run_id:'r',type:'bot.state_changed',payload:{state:'working'},created_at:1},
      {id:2,bot_id:'demo-2',run_id:'r',type:'message.sent',payload:{summary:'Exact recorded text',role:'assistant'},created_at:2},
    ];
    const scene=projectOffice(bots,events,3000);
    expect(scene[1].state).toBe('working');expect(scene[1].bubble).toBe('Exact recorded text');
    expect(scene[0].state).toBe('idle');
  });
  it('replays demo gathering and dispersal deterministically',()=>{
    const start=1_000_000,events=demoEvents(start);
    const gathering=projectOffice(bots,events,start+1000);
    expect(gathering.map(c=>c.state)).toEqual(['meeting','meeting','meeting']);
    expect(gathering.map(c=>c.motion.path.at(-1))).toEqual(bots.map((_,i)=>seat(i)));
    const dispersed=projectOffice(bots,events,start+15000);
    expect(dispersed.map(c=>c.state)).toEqual(['idle','idle','idle']);
    expect(dispersed.map(c=>c.motion.path.at(-1))).toEqual(bots.map((_,i)=>desk(i)));
    expect(projectOffice(bots,events,start+18000)).toEqual(projectOffice(bots,events,start+18000));
  });
  it('reduced motion jumps directly to the target',()=>{
    const motion={path:[{x:0,y:0},{x:1,y:0},{x:2,y:0}],at:1000};
    expect(positionAt(motion,1000,true)).toEqual({x:2,y:0});
    expect(positionAt(motion,1090,false)).toEqual({x:0.5,y:0});
  });
});
