// Use ONLY a fresh disposable installation. This test creates Bots and imports art.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url));
const base=process.env.E2E_URL, token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN for a fresh disposable installation.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}), req=page.request;
 const status=await (await req.get(base+'/api/auth/status')).json();
 assert.equal(status.setup,false,'This test requires a fresh disposable installation.');
 let response=await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}});assert.equal(response.status(),200);
 response=await req.post(base+'/api/bots',{data:{name:'Original',title:'Researcher'}});const id=(await response.json()).id;
 response=await req.post(base+'/api/vault/import',{multipart:{file:{name:'characters.zip',mimeType:'application/zip',buffer:fs.readFileSync(path.join(here,'../tests/fixtures/identity-characters.zip'))}}});assert.equal((await response.json()).added,2);
 await page.goto(base);await page.getByRole('button',{name:'Open Original spotlight'}).click();await page.getByRole('button',{name:'Give me a sprite'}).click();
 await page.getByText('Keep the current name: Original').click();await page.getByRole('button',{name:'Draw sprite'}).click();await page.getByRole('button',{name:'Meet your Bot'}).click();
 await page.getByRole('dialog',{name:'Original spotlight'}).getByText('Researcher',{exact:true}).first().waitFor();await page.getByText('Archetype: Moon Wizard').waitFor();
 await page.getByRole('button',{name:'Edit job title'}).click();await page.getByLabel('Job title (or custom job)').fill('Project Manager');await page.getByRole('button',{name:'Save changes'}).click();
 await page.getByRole('dialog',{name:'Original spotlight'}).getByText('Project Manager',{exact:true}).first().waitFor();await page.getByRole('button',{name:'Close spotlight'}).click();
 await page.getByRole('button',{name:'New Bot',exact:true}).click();await page.getByRole('button',{name:'Editor',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'Create Bot',exact:true}).click();await page.getByRole('button',{name:'Meet your Bot'}).click();
 const bots=await (await req.get(base+'/api/bots')).json(),existing=bots.find(b=>b.id===id),fresh=bots.find(b=>b.id!==id);
 assert.equal(existing.name,'Original');assert.equal(existing.title,'Project Manager');assert.equal(fresh.title,'Editor');assert.equal(fresh.name,fresh.character.name);
 await page.getByRole('dialog',{name:`${fresh.name} spotlight`}).getByText('Editor',{exact:true}).first().waitFor();await page.getByText('Archetype: Moon Wizard').waitFor();
 await page.screenshot({path:path.join(here,'../../docs/screenshots/slice5-step0-desktop.png')});await page.getByRole('button',{name:'Close spotlight'}).click();
 await page.setViewportSize({width:390,height:844});await page.reload();await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();await page.getByRole('button',{name:`Open ${fresh.name} spotlight`}).click();
 await page.getByRole('dialog',{name:`${fresh.name} spotlight`}).getByText('Editor',{exact:true}).first().waitFor();await page.screenshot({path:path.join(here,'../../docs/screenshots/slice5-step0-mobile-390.png')});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));console.log('Identity flow and desktop/390px screenshots passed.');
}finally{await browser.close()}
