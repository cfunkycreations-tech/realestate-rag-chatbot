// Use ONLY a fresh disposable installation. Exercises the Mission Control banner gauges; no model request is made.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url));
const shots=process.env.E2E_SHOTS||path.join(here,'../../docs/screenshots');
const base=process.env.E2E_URL, token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN for a fresh disposable installation.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
const hud=(page,label)=>page.locator('.hud-instrument',{hasText:label});
const refresh=page=>page.evaluate(()=>window.dispatchEvent(new Event('funkbot:refresh')));
try{
 const page=await browser.newPage({viewport:{width:1440,height:900}}), req=page.request, errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await (await req.get(base+'/api/auth/status')).json()).setup,false,'This test requires a fresh disposable installation.');
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 const banner=path.join(here,'../../docs/screenshots/banner-hero-desktop.png');
 if(fs.existsSync(banner))assert.equal((await req.put(base+'/api/settings/banner',{multipart:{file:{name:'banner.png',mimeType:'image/png',buffer:fs.readFileSync(banner)}}})).status(),200);
 for(const name of ['Alpha','Beta','Gamma'])assert.equal((await req.post(base+'/api/bots',{data:{name,title:'Editor'}})).status(),200);
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();

 // Zero activity: real counts, no invented percentages.
 await hud(page,'BOTS').waitFor();
 assert.match(await hud(page,'BOTS').innerText(),/0\/3/);
 assert.match(await hud(page,'MISSION COMPLETION').innerText(),/No data/);
 assert.match(await hud(page,'WORKFLOW HEALTH').innerText(),/No data/);
 assert.match(await hud(page,'AI SPEND TODAY').innerText(),/\$0\.0000/);
 assert.match(await hud(page,'TASK ACTIVITY').innerText(),/Idle/);
 assert.match(await hud(page,'ATTENTION').innerText(),/All clear/);
 assert.match(await hud(page,'AI SPEND TODAY').getAttribute('title'),/daily cap/);
 await page.screenshot({path:path.join(shots,'mission-control-desktop.png')});

 // Pause All Bots still works and the gauge follows without waiting for the next poll.
 page.once('dialog',d=>d.accept());
 await page.getByRole('button',{name:'Pause all Bots'}).click();
 await hud(page,'BOTS').getByText('PAUSED').waitFor();
 await page.screenshot({path:path.join(shots,'mission-control-paused-desktop.png')});
 await page.getByRole('button',{name:'Resume Bots'}).click();await hud(page,'BOTS').getByText('0/3').waitFor();

 // Navigation: each gauge opens its existing page.
 await hud(page,'MISSION COMPLETION').click();await page.getByRole('heading',{name:'Missions',exact:true}).waitFor();
 await hud(page,'ATTENTION').click();await page.getByRole('heading',{name:/Inbox/}).first().waitFor();
 await hud(page,'WORKFLOW HEALTH').click();await page.getByRole('heading',{name:/Workflows/}).first().waitFor();
 await hud(page,'AI SPEND TODAY').click();await page.getByRole('heading',{name:'Economy Mode'}).waitFor();
 await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).click();

 // Realistic busy payload (rendering only; the counts themselves are covered by backend tests).
 await page.route('**/api/mission-control',r=>r.fulfill({json:{generated_at:1,paused:false,bots:{configured:3,active:2,waiting_approval:1},missions:{done:8,failed:2,completion:80,window_days:7},workflow:{health:95,done:19,failed:1,routines_scheduled:2,workflows_saved:1,window_days:7},spending:{connected:true,spent:'4.2',cap:'5',percent:84,economy:true},activity:{running:2,queued:3,active_runs:2},attention:{approvals:1,failures:1,messages:2,total:4}}}));
 await refresh(page);
 await hud(page,'BOTS').getByText('2/3').waitFor();
 assert.match(await hud(page,'AI SPEND TODAY').innerText(),/\$4\.20/);
 assert.match(await hud(page,'ATTENTION').innerText(),/4/);
 await page.screenshot({path:path.join(shots,'mission-control-busy-desktop.png')});

 // Unavailable data source.
 await page.unroute('**/api/mission-control');await page.route('**/api/mission-control',r=>r.fulfill({status:500,json:{detail:'x'}}));
 await refresh(page);
 await hud(page,'BOTS').getByText('Not connected').waitFor();

 // Compact, hidden, and persisted across reload.
 await page.unroute('**/api/mission-control');
 await page.getByRole('button',{name:/Mission Control gauges: full/}).click();
 await page.getByRole('button',{name:/Mission Control gauges: compact/}).waitFor();
 assert.equal(await page.locator('.hud-text em').count(),0);
 await page.screenshot({path:path.join(shots,'mission-control-compact-desktop.png')});
 await page.getByRole('button',{name:/Mission Control gauges: compact/}).click();
 await page.getByRole('button',{name:/Mission Control gauges: hidden/}).waitFor();
 assert.equal(await page.locator('.hud-instrument').count(),0);
 await page.reload();await page.getByRole('button',{name:/Mission Control gauges: hidden/}).waitFor();
 await page.getByRole('button',{name:/Mission Control gauges: hidden/}).click();await hud(page,'BOTS').waitFor();
 // Settings and pause controls stay reachable.
 await page.getByRole('button',{name:'Open settings'}).waitFor();await page.getByRole('button',{name:/Pause all Bots|Resume Bots/}).waitFor();

 // Small screen: nothing overflows, instruments stay inside the banner, and clusters do not overlap.
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(300);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal page scroll at 390px');
 const box=await page.locator('.command-banner').boundingBox(),left=await page.locator('.hud-left').boundingBox(),right=await page.locator('.hud-right').boundingBox();
 assert(left.x>=box.x&&right.x+right.width<=box.x+box.width+1,'HUD stays inside the banner');
 assert(left.x+left.width<=right.x,'left and right clusters do not overlap');
 await page.screenshot({path:path.join(shots,'mission-control-mobile.png')});

 // Reduced motion removes animation.
 await page.emulateMedia({reducedMotion:'reduce'});
 assert.equal(await page.locator('.hud-instrument').first().evaluate(el=>parseFloat(getComputedStyle(el).transitionDuration)<0.001),true);
 assert.deepEqual(errors,[]);
 console.log('Mission Control passed: zero data, pause, navigation, busy and unavailable states, compact/hidden, 390px, reduced motion.');
}finally{await browser.close()}
