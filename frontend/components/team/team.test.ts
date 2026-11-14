import {describe,it,expect} from 'vitest';
import {collections,sidebarCollections,describeEvent,timeLabel} from './TeamDashboard';
const bot=(id:string,tags:string[])=>({id,name:id,title:'',color:'blue',shape:'round',character:{name:id,role:'',tags,avatar_url:'/api/bots/'+id+'/avatar'}});
describe('team data',()=>{
 it('groups real tags without duplicates and keeps untagged Bots',()=>{const groups=collections([bot('a',['Space','space','Art']),bot('b',['SPACE']),bot('c',[])]);expect(groups.find(([n])=>n==='Space')?.[1].map(b=>b.id)).toEqual(['a','b']);expect(groups.find(([n])=>n==='Uncategorized')?.[1][0].id).toBe('c')});
 it('hides Uncategorized only when it is the sole collection',()=>{expect(sidebarCollections([bot('a',[])])).toEqual([]);expect(sidebarCollections([bot('a',[]),bot('b',['Art'])]).map(([name])=>name)).toContain('Uncategorized')});
 it('renders recorded messages without inventing activity',()=>{expect(describeEvent({id:1,bot_id:'a',type:'message.sent',payload:{summary:'hello'},created_at:1},new Map([['a','A']]))).toBe('A: hello');expect(timeLabel(null)).toBe('No recorded activity')});
});
