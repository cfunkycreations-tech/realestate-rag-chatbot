// Use ONLY a fresh disposable installation. Checks the character spotlight is not clipped on a short window.
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
 const page=await browser.newPage({viewport:{width:1709,height:770}}), req=page.request;
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 assert.equal((await req.post(base+'/api/bots',{data:{name:'Lumen Cap',title:'Community Manager'}})).status(),200);
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 await page.locator('.bot-card-open').first().click();
 const panel=page.locator('.spotlight-panel');await panel.waitFor();
 // The composer must be reachable: either visible already or by scrolling the panel.
 const composer=page.getByLabel('Message your Bot');await composer.scrollIntoViewIfNeeded();
 const p=await panel.boundingBox(),c=await composer.boundingBox();
 assert(c.y+c.height<=p.y+p.height+1&&c.y>=p.y,'message box is inside the visible window');
 assert(p.width>1100,'window is wide');
 await page.screenshot({path:path.join(shots,'spotlight-short-window.png')});
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(200);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 console.log('Spotlight is not clipped on a 770px-high window and fits 390px.');
}finally{await browser.close()}
