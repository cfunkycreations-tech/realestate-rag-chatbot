// Use ONLY a fresh disposable installation. Exercises the Economy panel; no model request is made.
import assert from 'node:assert/strict';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url));
const shots=process.env.E2E_SHOTS||path.join(here,'../../docs/screenshots');
const base=process.env.E2E_URL, token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN for a fresh disposable installation.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}), req=page.request, errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await (await req.get(base+'/api/auth/status')).json()).setup,false,'This test requires a fresh disposable installation.');
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 assert.equal((await req.post(base+'/api/bots',{data:{name:'Fixture',title:'Editor'}})).status(),200);
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();await page.getByRole('button',{name:'Open settings'}).click();await page.getByRole('button',{name:'Budget',exact:true}).click();
 await page.getByRole('heading',{name:'Economy Mode'}).waitFor();
 await page.getByText('Economy Mode off').waitFor();
 await page.getByLabel('Economy Mode',{exact:true}).click();await page.getByText('Economy Mode is on.').waitFor();
 assert.equal((await (await req.get(base+'/api/economy')).json()).economy.enabled,true);
 await page.getByLabel('Ceiling tier').selectOption('LIGHT');await page.waitForFunction(()=>document.querySelector('[aria-label="Ceiling tier"]').value==='LIGHT');
 await page.getByLabel('Alert thresholds').fill('0, 50');await page.getByRole('button',{name:'Save alert thresholds'}).click();
 await page.getByText(/whole percentages/).waitFor();
 await page.getByLabel('Alert thresholds').fill('90, 25');await page.getByRole('button',{name:'Save alert thresholds'}).click();await page.getByText('Saved.',{exact:true}).waitFor();
 assert.deepEqual((await (await req.get(base+'/api/economy')).json()).alerts.thresholds,[25,90]);
 // OmniRoute is never assumed free.
 await page.getByLabel('Flag gateway').selectOption('omniroute');await page.getByLabel('Flag model').fill('auto');await page.getByRole('button',{name:'Mark as free or local'}).click();
 await page.getByText(/OmniRoute is a router/).waitFor();
 await page.getByLabel('Flag gateway').selectOption('custom');await page.getByLabel('Flag model').fill('llama3');await page.getByRole('button',{name:'Mark as free or local'}).click();
 await page.getByText(/llama3 · custom · local/).waitFor();
 await page.getByLabel('Group usage by').selectOption('model');await page.getByText('No usage in this period.').waitFor();
 await page.getByRole('heading',{name:'Free or local models'}).scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(shots,'economy-settings-desktop.png')});
 await page.setViewportSize({width:390,height:844});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal page scroll at 390px');
 await page.screenshot({path:path.join(shots,'economy-settings-mobile.png')});
 assert.deepEqual(errors,[]);
 console.log('Economy panel works at desktop and 390px; Economy Mode, alerts and model flags persisted; OmniRoute refused as free.');
}finally{await browser.close()}
