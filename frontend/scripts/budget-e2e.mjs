// Only run against a fresh disposable installation. Creates Bots and imports art.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url)),base=process.env.E2E_URL,token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN for a fresh disposable installation.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}),req=page.request,errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await (await req.get(base+'/api/auth/status')).json()).setup,false);
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 const zip=fs.readFileSync(path.join(here,'../tests/fixtures/identity-characters.zip'));
 assert.equal((await (await req.post(base+'/api/vault/import',{multipart:{file:{name:'sprites.zip',mimeType:'application/zip',buffer:zip}}})).json()).added,2);
 const created=await (await req.post(base+'/api/bots',{data:{name:'Fixture',title:'Editor'}})).json();assert(created.character);
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 await page.getByRole('button',{name:'Open settings'}).click();await page.getByRole('button',{name:'Budget',exact:true}).click();
 await page.getByRole('heading',{name:'Account limits'}).waitFor();
 assert.equal(await page.getByLabel('Account daily USD').inputValue(),'5');
 await page.getByLabel('Account daily USD').fill('0');await page.getByRole('button',{name:'Save Account limits'}).click();await page.getByText('Saved.',{exact:true}).waitFor();
 await page.getByLabel('smart input USD per million').fill('1');await page.getByLabel('smart output USD per million').fill('2');await page.getByRole('button',{name:'Save smart price'}).click();
 await page.waitForFunction(()=>document.querySelector('[aria-label="smart input USD per million"]')?.value==='1');
 await page.locator('.settings-body').evaluate(el=>{el.scrollTop=0});await page.screenshot({path:path.join(here,'../../docs/screenshots/budget-settings-desktop.png')});
 await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).click();
 await page.locator('.bot-card-open').first().click();await page.getByLabel('Message your Bot').fill('This should be refused');await page.getByRole('button',{name:'Send message'}).click();
 await page.getByText(/daily budget cap would be exceeded/).waitFor();
 assert.equal((await (await req.get(base+`/api/bots/${created.id}/messages`)).json()).length,0);
 await page.screenshot({path:path.join(here,'../../docs/screenshots/budget-refusal-desktop.png')});
 await page.getByRole('button',{name:'Close spotlight'}).click();await page.locator('#quick-mission').fill('Quick refusal');await page.getByRole('button',{name:'Send quick mission'}).click();await page.getByRole('heading',{name:'Missions',exact:true}).waitFor();await page.getByRole('alert').filter({hasText:'daily budget cap'}).waitFor();assert.equal((await (await req.get(base+`/api/bots/${created.id}/messages`)).json()).length,0);await page.setViewportSize({width:390,height:844});
 await page.getByRole('navigation',{name:'Team navigation'}).getByRole('button',{name:'Gallery',exact:true}).click();await page.getByRole('button',{name:'Open settings'}).click();await page.getByRole('button',{name:'Budget',exact:true}).click();await page.getByRole('heading',{name:'Account limits'}).waitFor();
 await page.screenshot({path:path.join(here,'../../docs/screenshots/budget-settings-mobile.png')});
 await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).click();await page.locator('.bot-card-open').first().click();await page.getByLabel('Message your Bot').fill('This should be refused');await page.getByRole('button',{name:'Send message'}).click();await page.getByText(/daily budget cap would be exceeded/).waitFor();
 await page.screenshot({path:path.join(here,'../../docs/screenshots/budget-refusal-mobile.png')});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);console.log('Budget settings and cap refusal passed at desktop and 390px; no model request was made.');
}finally{await browser.close()}
