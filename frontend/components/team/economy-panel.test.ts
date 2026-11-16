import {describe,expect,it} from 'vitest';
import {describeSpend,parseThresholds} from './EconomyPanel';

describe('economy panel helpers',()=>{
 it('parses, sorts and de-duplicates alert thresholds',()=>{
  expect(parseThresholds('80, 50 100 50')).toEqual([50,80,100]);
 });
 it('rejects thresholds outside 1-100 or fractions or too many',()=>{
  expect(()=>parseThresholds('0,50')).toThrow(/whole percentages/);
  expect(()=>parseThresholds('101')).toThrow();
  expect(()=>parseThresholds('12.5')).toThrow();
  expect(()=>parseThresholds('')).toThrow();
  expect(()=>parseThresholds('1 2 3 4 5 6 7')).toThrow();
 });
 it('describes spend, errors and missing caps',()=>{
  expect(describeSpend()).toBe('No cap set');
  expect(describeSpend({spent:'0.0003',cap:'5',percent:0})).toBe('$0.0003 of $5.00 (0%)');
  expect(describeSpend({cap:'5',error:'Spend cannot be verified.'})).toBe('Spend cannot be verified.');
 });
});
