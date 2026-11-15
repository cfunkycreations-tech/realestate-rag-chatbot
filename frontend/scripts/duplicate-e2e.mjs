// Fresh disposable installation only; no model call is made.
import assert from 'node:assert/strict';import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url)),base=process.env.E2E_URL,token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}),req=page.request,errors=[];page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 const zip=fs.readFileSync(path.join(here,'../tests/fixtures/identity-characters.zip'));await req.post(base+'/api/vault/import',{multipart:{file:{name:'sprites.zip',mimeType:'application/zip',buffer:zip}}});
 const bot=await (await req.post(base+'/api/bots',{data:{name:'Test',title:'Editor',profile:'fast'}})).json();assert(bot.character);const name=bot.character.name;
 await req.post(base+`/api/bots/${bot.id}/memory`,{data:{content:'Private fact'}});await page.goto(base);
 await page.getByRole('button',{name:`Open ${name} spotlight`}).click();await page.getByRole('dialog',{name:`${name} spotlight`}).getByRole('button',{name:'Duplicate Bot'}).click();
 await page.getByRole('button',{name:`Open ${name} (copy) spotlight`}).waitFor();const bots=await (await req.get(base+'/api/bots')).json(),copy=bots.find(b=>b.id!==bot.id);
 assert.equal(copy.title,'Editor');assert.equal(copy.profile,'fast');assert(copy.character);assert.equal((await (await req.get(base+`/api/bots/${copy.id}/memory`)).json()).length,0);
 await page.getByRole('button',{name:`Open ${copy.name} spotlight`}).click();await page.screenshot({path:path.join(here,'../../docs/screenshots/duplicate-desktop.png')});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(here,'../../docs/screenshots/duplicate-mobile.png')});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);console.log('Duplicate Bot UI and desktop/mobile screenshots passed.');
}finally{await browser.close()}
