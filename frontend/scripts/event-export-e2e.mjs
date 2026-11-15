// Fresh disposable installation; exports an honestly empty event log.
import assert from 'node:assert/strict';import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url)),base=process.env.E2E_URL,token=process.env.E2E_SETUP_TOKEN;if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await page.request.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 await page.goto(base);await page.getByRole('button',{name:'Open settings'}).click();await page.getByRole('button',{name:'Tool audit',exact:true}).click();await page.getByText('No tool calls recorded yet.').waitFor();
 const downloadPromise=page.waitForEvent('download');await page.getByRole('link',{name:'Export events JSON'}).click();const download=await downloadPromise;assert.equal(download.suggestedFilename(),'funk-bot-events.json');assert.deepEqual(JSON.parse(fs.readFileSync(await download.path(),'utf8')),[]);
 const csvPromise=page.waitForEvent('download');await page.getByRole('link',{name:'Export events CSV'}).click();const csv=await csvPromise;assert(fs.readFileSync(await csv.path(),'utf8').startsWith('id,bot_id,run_id,type,payload,created_at'));
 await page.screenshot({path:path.join(here,'../../docs/screenshots/event-export-desktop.png')});await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(here,'../../docs/screenshots/event-export-mobile.png')});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);console.log('Empty event export JSON/CSV and desktop/mobile screenshots passed.');
}finally{await browser.close()}
