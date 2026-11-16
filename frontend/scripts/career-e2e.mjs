// Use ONLY a fresh disposable installation. This test creates Bots, imports art and installs role presets.
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
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}), req=page.request;
 const status=await (await req.get(base+'/api/auth/status')).json();
 assert.equal(status.setup,false,'This test requires a fresh disposable installation.');
 let response=await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}});assert.equal(response.status(),200);
 response=await req.post(base+'/api/vault/import',{multipart:{file:{name:'characters.zip',mimeType:'application/zip',buffer:fs.readFileSync(path.join(here,'../tests/fixtures/identity-characters.zip'))}}});assert.equal((await response.json()).added,2);
 const dialog=page.getByRole('dialog').first(), newBot=()=>page.getByRole('button',{name:'New Bot',exact:true}).first().click();
 await page.goto(base);await newBot();
 // A fresh install has no role library, so the classic form is still the default.
 await page.getByLabel('Job title (or custom job)').waitFor();
 await page.getByRole('tab',{name:'Hire by career'}).click();await page.getByText('No role library yet').waitFor();
 await page.screenshot({path:path.join(shots,'career-empty-desktop.png')});
 await page.getByRole('button',{name:'Install 9 starter roles'}).click();await page.getByText('9 added').waitFor();
 await page.getByLabel('Search roles').fill('dev');await page.getByRole('option',{name:'Developer'}).click();
 await page.getByRole('heading',{name:'Developer'}).waitFor();await page.screenshot({path:path.join(shots,'career-choose-desktop.png')});
 await page.getByRole('button',{name:'Hire Developer'}).click();await page.getByText('A NEW EMPLOYEE HAS ARRIVED').waitFor();await page.getByText('Hired as').waitFor();
 await page.screenshot({path:path.join(shots,'career-reveal-desktop.png')});await page.getByRole('button',{name:'Meet your Bot'}).click();
 let bots=await (await req.get(base+'/api/bots')).json();assert.equal(bots.length,1);
 const hired=bots[0];assert.equal(hired.title,'Developer');assert.equal(hired.name,hired.character.name);assert.match(hired.personality,/PROFESSIONAL INSTRUCTIONS/);
 let career=(await (await req.get(`${base}/api/bots/${hired.id}/career`)).json()).career;
 assert.equal(career.preset_id,'developer');assert.equal(career.history[0].detail.birth_mode,'choose');
 await page.getByRole('button',{name:'Close spotlight'}).click();
 // With a library present the career tab opens by default; surprise picks role and character.
 await newBot();await page.getByLabel('Search roles').waitFor();await page.getByRole('button',{name:'Surprise me'}).click();
 await page.getByText('Hired as').waitFor();await page.getByRole('button',{name:'Meet your Bot'}).click();
 bots=await (await req.get(base+'/api/bots')).json();assert.equal(bots.length,2);
 const surprise=bots.find(b=>b.id!==hired.id);career=(await (await req.get(`${base}/api/bots/${surprise.id}/career`)).json()).career;
 assert.equal(career.history[0].detail.birth_mode,'surprise');assert.equal(surprise.title,career.career.title);
 await page.getByRole('button',{name:'Close spotlight'}).click();
 // The classic custom flow is unchanged and creates a Bot with no career record.
 await newBot();await page.getByRole('tab',{name:'Custom Bot'}).click();await page.getByRole('button',{name:'Editor',exact:true}).click();
 await dialog.getByRole('button',{name:'Create Bot',exact:true}).click();
 await page.getByRole('button',{name:'Meet your Bot'}).click();
 bots=await (await req.get(base+'/api/bots')).json();assert.equal(bots.length,3);
 const custom=bots.find(b=>b.title==='Editor'&&!b.personality.includes('PROFESSIONAL INSTRUCTIONS'));assert(custom,'custom Bot was created by the classic form');
 assert.equal((await (await req.get(`${base}/api/bots/${custom.id}/career`)).json()).career,null);
 await page.getByRole('button',{name:'Close spotlight'}).click();
 // 390px: the hiring dialog must fit without horizontal scrolling.
 await page.setViewportSize({width:390,height:844});await page.reload();await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 await page.getByRole('button',{name:'Open sidebar'}).click();await newBot();await page.getByLabel('Search roles').waitFor();await page.getByRole('option',{name:'Researcher'}).click();
 await page.screenshot({path:path.join(shots,'career-choose-mobile-390.png')});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal overflow at 390px');
 console.log('Career hiring flow (choose, surprise, classic) and desktop/390px screenshots passed.');
}finally{await browser.close()}
