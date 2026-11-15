// Only use against a fresh disposable installation: creates and deletes Bots.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url)),base=process.env.E2E_URL,token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN for a fresh disposable installation.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}),req=page.request,errors=[];page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await (await req.get(base+'/api/auth/status')).json()).setup,false);
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 assert.equal((await req.put(base+'/api/settings/gateways/openrouter',{data:{url:'https://example.com/v1',key:'disposable-test-secret'}})).status(),200);
 const zip=fs.readFileSync(path.join(here,'../tests/fixtures/identity-characters.zip'));
 assert.equal((await (await req.post(base+'/api/vault/import',{multipart:{file:{name:'sprites.zip',mimeType:'application/zip',buffer:zip}}})).json()).added,2);
 const ids=[];
 for(const name of ['Desktop Bot','Phone Bot','Kept Bot']){
  const body={name,title:'Editor',personality:'Test instructions',color:'lavender',shape:'round',profile:'smart'};
  const bot=await (await req.post(base+'/api/bots',{data:body})).json();assert(bot.character);ids.push(bot.id);
  assert.equal((await req.put(base+'/api/bots/'+bot.id,{data:body})).status(),200);
 }
 await page.goto(base);await page.getByRole('button',{name:'Open Desktop Bot spotlight'}).click();
 const dialog=page.getByRole('dialog',{name:'Desktop Bot spotlight'});await dialog.getByRole('button',{name:'Delete Bot',exact:true}).waitFor();
 await page.screenshot({path:path.join(here,'../../docs/screenshots/delete-bot-desktop.png')});
 let confirmation='';page.once('dialog',d=>{confirmation=d.message();return d.dismiss()});await dialog.getByRole('button',{name:'Delete Bot',exact:true}).click();
 assert(confirmation.includes('conversation')&&confirmation.includes('sprite remains'));assert.equal((await (await req.get(base+'/api/bots')).json()).length,3);
 // A server-side conflict must not remove the Bot or close the spotlight.
 const pattern=`**/api/bots/${ids[0]}`;await page.route(pattern,route=>route.request().method()==='DELETE'?route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'Wait for the current response before deleting this Bot.'})}):route.continue());
 page.once('dialog',d=>d.accept());await dialog.getByRole('button',{name:'Delete Bot',exact:true}).click();await page.getByText('Wait for the current response before deleting this Bot.').waitFor();assert.equal((await (await req.get(base+'/api/bots')).json()).length,3);
 await page.unroute(pattern);page.once('dialog',d=>d.accept());await dialog.getByRole('button',{name:'Delete Bot',exact:true}).click();await dialog.waitFor({state:'detached'});
 assert.deepEqual((await (await req.get(base+'/api/bots')).json()).map(b=>b.id),ids.slice(1));assert.equal((await (await req.get(base+'/api/vault/status')).json()).total,2);
 await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Open Phone Bot spotlight'}).click();const mobile=page.getByRole('dialog',{name:'Phone Bot spotlight'});await mobile.getByRole('button',{name:'Delete Bot',exact:true}).waitFor();
 await page.screenshot({path:path.join(here,'../../docs/screenshots/delete-bot-mobile.png')});page.once('dialog',d=>d.accept());await mobile.getByRole('button',{name:'Delete Bot',exact:true}).click();await mobile.waitFor({state:'detached'});
 assert.deepEqual((await (await req.get(base+'/api/bots')).json()).map(b=>b.id),[ids[2]]);assert.equal((await (await req.get(base+'/api/vault/status')).json()).total,2);assert((await (await req.get(base+'/api/settings')).json()).gateways.openrouter.has_key);
 await page.getByRole('navigation',{name:'Team navigation'}).getByRole('button',{name:'Roster',exact:true}).click();assert(await page.getByRole('button',{name:'Delete Bot',exact:true}).isVisible());
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 console.log('Delete button, cancellation, server refusal, deletion, Vault/key preservation, desktop and 390px passed.');
}finally{await browser.close()}
