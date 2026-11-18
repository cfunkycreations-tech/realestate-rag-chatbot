import {describe,expect,it} from 'vitest';
import {DEMOS} from './demos';

const NAV=['office','roster','gallery','missions','group-chats','bot-dms','family','cockpit','playbooks','projects','analytics','lab','skills','routines','workflows','inbox'];
const TABS=['gateways','profiles','usage','vault','appearance','budget','web','audit','backup','connectors'];

describe('demos',()=>{
 it('has unique ids and 3+ steps with a say line and at least one row each',()=>{
  expect(new Set(DEMOS.map(d=>d.id)).size).toBe(DEMOS.length);
  for(const d of DEMOS){expect(d.steps.length).toBeGreaterThanOrEqual(3);for(const s of d.steps){expect(s.say.length).toBeGreaterThan(10);expect(s.rows.length).toBeGreaterThan(0)}}
 });
 it('every open target is a real screen or settings tab',()=>{
  for(const d of DEMOS){const {view,settings}=d.open;expect(Boolean(view)!==Boolean(settings)).toBe(true);if(view)expect(NAV).toContain(view);if(settings)expect(TABS).toContain(settings)}
 });
 it('covers every navigation screen',()=>{
  const covered=new Set(DEMOS.map(d=>d.id));
  for(const v of NAV.filter(v=>v!=='inbox'||true))expect(covered.has(v)||covered.has(v.replace('-chats','-chats')),`no demo for ${v}`).toBe(true);
 });
});
