import {describe,it,expect} from 'vitest';
import {displayMentions,insertMention,mentionTrigger} from './mentions';

describe('workspace mentions',()=>{
 it('finds only a standalone @ fragment at the caret',()=>{
  expect(mentionTrigger('Hi @Res and later',7)).toEqual({start:3,end:7,query:'Res'});
  expect(mentionTrigger('person@example.com',18)).toBeNull();
  expect(mentionTrigger('(@plan',6)?.query).toBe('plan');
 });
 it('inserts a stable typed id without losing text and renders the label',()=>{
  const item={kind:'bot' as const,id:'12345678-1234-1234-1234-123456789abc',name:'Researcher'};
  const result=insertMention('Hi @Res later',mentionTrigger('Hi @Res later',7)!,item);
  expect(result.text).toBe('Hi @{bot:12345678-1234-1234-1234-123456789abc|Researcher}  later');
  expect(result.text.slice(result.cursor)).toBe(' later');expect(displayMentions(result.text)).toBe('Hi @Researcher  later');
 });
 it('removes token delimiters from the visible label',()=>{
  expect(insertMention('@',mentionTrigger('@',1)!,{kind:'group',id:'x',name:'bad}\nname'}).text).toContain('|bad  name}');
 });
});
