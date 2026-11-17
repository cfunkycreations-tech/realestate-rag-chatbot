import {describe,expect,it} from 'vitest';
import {costLabel,kindLabel,outcomeLabel,statusLabel,tokenLabel,type Thread,type Usage} from './model';

const usage=(o:Partial<Usage>={}):Usage=>({prompt_tokens:0,completion_tokens:0,usd:'0',unverified_rounds:0,model_rounds:0,basis:'configured prices, not a provider invoice',...o});
const thread=(o:Partial<Thread>={}):Thread=>({dm_id:'d',subject:'s',initiator_id:'a',initiator_name:'Dev',receiver_id:'b',receiver_name:'Sec',kind:'request_review',mission_id:null,mission_title:null,project_id:null,status:'done',error:null,messages_sent:1,outcome:'Looks safe.',usage:usage(),updated_at:1,...o});

describe('Bot conversation labels',()=>{
 it('names every purpose in plain words and falls back readably',()=>{
  expect(kindLabel('request_review')).toBe('Requested a review');
  expect(kindLabel('something_new')).toBe('something new');
 });
 it('never invents usage or cost',()=>{
  expect(costLabel(usage())).toBe('No model use yet');
  expect(tokenLabel(usage())).toBe('No tokens recorded');
  expect(costLabel(usage({usd:'0.0123',model_rounds:1}))).toBe('$0.0123');
  expect(costLabel(usage({usd:'0.5',model_rounds:2,unverified_rounds:1}))).toBe('$0.5000 + 1 unverified');
  expect(tokenLabel(usage({prompt_tokens:1200,completion_tokens:80,model_rounds:1}))).toBe('1,200 in · 80 out');
 });
 it('reports the real outcome',()=>{
  expect(outcomeLabel(thread())).toBe('Reply: Looks safe.');
  expect(outcomeLabel(thread({status:'failed',error:'The reply timed out.'}))).toBe('The reply timed out.');
  expect(outcomeLabel(thread({status:'running'}))).toBe('Waiting for the reply…');
  expect(statusLabel('done')).toBe('Answered');
 });
});
