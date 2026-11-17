import {describe,expect,it} from 'vitest';
import {criterionText,eligibilityText,levelLabel,percent,statusLabel,tallyText,usd,voteWord,type Eligibility,type Tally} from './model';

const tally=(o:Partial<Tally>={}):Tally=>({approve:2,reject:1,abstain:0,members:3,quorum:2,quorum_met:true,...o});

describe('Family labels',()=>{
 it('names levels and statuses plainly and falls back readably',()=>{
  expect(levelLabel('specialist')).toBe('Specialist');
  expect(levelLabel('mystery')).toBe('mystery');
  expect(statusLabel('escalated')).toBe('Needs your decision');
  expect(statusLabel('passed')).toBe('Passed (recommendation)');
 });
 it('never invents money or percentages',()=>{
  expect(usd(null)).toBe('Not available');
  expect(usd('abc')).toBe('Not available');
  expect(usd('0')).toBe('$0.00');
  expect(usd('0.0348')).toBe('$0.0348');
  expect(usd('12.5')).toBe('$12.50');
  expect(percent(null)).toBe('No data yet');
  expect(percent(0)).toBe('0%');
 });
 it('describes votes and quorum honestly',()=>{
  expect(tallyText(null)).toBe('No votes yet');
  expect(tallyText(tally())).toBe('2 for, 1 against, 0 abstained');
  expect(tallyText(tally({approve:1,reject:0,abstain:2,quorum_met:false}))).toContain('No quorum (needs 2 votes');
  expect(voteWord('approve')).toBe('For');
  expect(voteWord('abstain')).toBe('Abstained');
 });
 it('summarises promotion eligibility without implying authority',()=>{
  const base:Eligibility={level:'trainee',target:'junior',eligible:false,criteria:[{key:'done',name:'Completed missions',need:3,have:1,met:false},{key:'verified',name:'Verified',need:1,have:null,met:false},{key:'days',name:'Days',need:0,have:5,met:true}]};
  expect(eligibilityText(base)).toBe('2 requirements still to meet for Junior.');
  expect(eligibilityText({...base,criteria:base.criteria.slice(0,1)})).toBe('1 requirement still to meet for Junior.');
  expect(eligibilityText({...base,eligible:true})).toBe('Meets every requirement for Junior. Needs your approval.');
  expect(eligibilityText({...base,target:null})).toBe('Already at the highest level.');
  expect(criterionText(base.criteria[1])).toBe('Verified: no data of 1');
 });
});
