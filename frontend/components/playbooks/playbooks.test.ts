import {describe,expect,it} from 'vitest';
import {PLAYBOOKS,hasEverything} from './playbooks';
import {STAGES} from './Stages';

describe('playbooks',()=>{
 it('has the ten pages with eight steps and every footer field',()=>{
  expect(PLAYBOOKS).toHaveLength(10);
  expect(PLAYBOOKS.map(p=>p.n)).toEqual(['01','02','03','04','05','06','07','08','09','10']);
  for(const p of PLAYBOOKS){expect(hasEverything(p),p.id).toBe(true);expect(p.steps.every(s=>s.name&&s.hint),p.id).toBe(true)}
 });
 it('has unique ids, a stage renderer, a brief and a cron for each',()=>{
  expect(new Set(PLAYBOOKS.map(p=>p.id)).size).toBe(10);
  for(const p of PLAYBOOKS){expect(typeof STAGES[p.id],p.id).toBe('function');expect(p.brief.length,p.id).toBeGreaterThan(80);expect(p.cron.split(' '),p.id).toHaveLength(5)}
 });
 it('never promises to send, post, publish or cancel on the owner’s behalf',()=>{
  for(const p of PLAYBOOKS){expect(p.brief.toLowerCase(),p.id).toMatch(/never|do not|don't/);expect(p.never.length,p.id).toBeGreaterThan(5)}
 });
 it('says plainly which playbooks still need a source',()=>{
  const needs=PLAYBOOKS.filter(p=>!p.reality.ready).map(p=>p.n);
  expect(needs).toEqual(['04','05','06','07','10']);
 });
});
