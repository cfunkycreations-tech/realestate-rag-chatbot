import {describe,it,expect} from 'vitest';
import {identityLabel,jobTitle} from './identity';
describe('name and job title',()=>{
 it('uses the job instead of a sprite archetype',()=>{const bot={name:'Muffin',title:'Project Manager',character:{role:'Space wizard'}};expect(jobTitle(bot)).toBe('Project Manager');expect(identityLabel(bot)).toBe('Muffin — Project Manager')});
 it('does not shorten long names or jobs and labels missing jobs honestly',()=>{const bot={name:'A'.repeat(120),title:'B'.repeat(100)};expect(identityLabel(bot)).toBe(`${bot.name} — ${bot.title}`);expect(jobTitle({name:'A',title:''})).toBe('No job title')});
});
