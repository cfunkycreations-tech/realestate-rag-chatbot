// Fresh disposable installation; memory commands make no model calls.
import assert from 'node:assert/strict';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url)),base=process.env.E2E_URL,token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}),req=page.request,errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 const bot=await (await req.post(base+'/api/bots',{data:{name:'Memory Tester',title:'Editor'}})).json();
 await page.goto(base);await page.getByRole('button',{name:'Open Memory Tester spotlight'}).click();
 const dialog=page.getByRole('dialog',{name:'Memory Tester spotlight'}),composer=dialog.getByLabel('Message your Bot');
 await dialog.getByText('Memory commands',{exact:true}).click();
 async function command(text,ack){await composer.fill(text);await dialog.getByRole('button',{name:'Send message'}).click();await dialog.getByText(ack,{exact:false}).last().waitFor();}
 await command('!memory remember I like short reports','Saved this Bot memory.');
 await command('!memory show','I like short reports (not pinned)');
 await page.screenshot({path:path.join(here,'../../docs/screenshots/chat-memory-desktop.png')});
 await dialog.getByText('Memory commands',{exact:true}).click();
 await page.setViewportSize({width:390,height:844});await dialog.getByText('I like short reports (not pinned)',{exact:false}).last().scrollIntoViewIfNeeded();await page.screenshot({path:path.join(here,'../../docs/screenshots/chat-memory-mobile.png')});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await command('!memory replace I like short reports => I like detailed reports','Updated the matching Bot memory');
 assert.equal((await (await req.get(base+`/api/bots/${bot.id}/memory`)).json())[0].content,'I like detailed reports');
 await command('!memory forget I like detailed reports','Forgot the matching Bot memory');
 assert.equal((await (await req.get(base+`/api/bots/${bot.id}/memory`)).json()).length,0);
 assert.deepEqual(errors,[]);console.log('Local chat memory remember, show, replace and forget passed on desktop/mobile.');
}finally{await browser.close()}
