// Run ONLY against a disposable, already-configured Funk Bot installation.
// E2E_URL and E2E_PASSWORD are required. The script sends a test message.
import assert from 'node:assert/strict';
import {chromium} from '@playwright/test';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const __dirname=path.dirname(fileURLToPath(import.meta.url));
(async () => {
  const base=process.env.E2E_URL, password=process.env.E2E_PASSWORD;
  if(!base||!password) throw Error('Set E2E_URL and E2E_PASSWORD for a disposable test installation.');
  const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}), errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(base);
    await page.getByLabel('Password',{exact:true}).fill(password);
    await page.getByRole('button',{name:'Sign in'}).click();
    await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
    await page.getByText('Team stats',{exact:true}).waitFor();
    await page.locator('.bot-card').first().waitFor();
    await page.waitForFunction(()=>[...document.querySelectorAll('.bot-card img')].every(img=>img.complete));
    await page.screenshot({path:path.resolve(__dirname,'../../docs/screenshots/team-desktop.png')});
    for(const name of ['List','Cluster','Grid']) await page.getByRole('button',{name:`${name} view`}).click();
    const first=page.locator('.bot-card-open').first();const name=(await first.getAttribute('aria-label')).replace(/^Open /,'').replace(/ spotlight$/,'');
    await first.click();await page.getByRole('dialog',{name:`${name} spotlight`}).getByText('Recent activity').waitFor();await page.getByRole('button',{name:'Close spotlight'}).click();
    await page.locator('#quick-mission').fill('Hello from the disposable browser test');
    const response=page.waitForResponse(r=>r.url().includes('/chat')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Send quick mission'}).click();assert.equal((await response).status(),200);
    await page.getByText('Hello from the disposable browser test').first().waitFor({timeout:15000});
    await page.getByRole('button',{name:'Office',exact:true}).first().click();await page.getByText('LIVE · REAL EVENTS ONLY').waitFor();
    assert.equal(await page.getByRole('button',{name:'Try demo'}).count(),0);
    await page.getByRole('button',{name:'Gallery',exact:true}).first().click();
    await page.setViewportSize({width:390,height:844});await page.reload();await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
    await page.locator('.bot-card').first().waitFor();await page.waitForFunction(()=>[...document.querySelectorAll('.bot-card img')].every(img=>img.complete));
    await page.screenshot({path:path.resolve(__dirname,'../../docs/screenshots/team-mobile-390.png')});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'mobile page should not overflow');
    assert.equal(errors.length,0,errors.join('\n'));
    console.log('Desktop and 390px screenshots, gallery, spotlight, Quick Mission and Office passed.');
  } finally {await browser.close()}
})().catch(error=>{console.error(error);process.exit(1)});
