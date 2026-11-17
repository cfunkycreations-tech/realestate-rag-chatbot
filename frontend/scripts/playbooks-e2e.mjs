// Use ONLY a fresh disposable installation. Drives the ten Playbook pages; no model request is made.
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
 const page=await browser.newPage({viewport:{width:1440,height:900}}), req=page.request, errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 const mk=async n=>(await (await req.post(base+'/api/bots',{data:{name:n,title:'Helper'}})).json()).id;
 const mia=await mk('Mia');await mk('Tom');
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 const noScroll=async label=>assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal scroll: '+label);
 await page.getByRole('button',{name:/^Playbooks$/}).click();
 const tabs=page.getByRole('tablist',{name:'Playbooks'}).getByRole('tab');
 assert.equal(await tabs.count(),10);
 const expectedHeads=['Saved once.','It proves it works','One orchestrator.','Everything since last night,','Your best ideas,','$1,086 a year in subscriptions.','412 messages in.','50 leads.','Only what moved','Your queue at 08:00.'];

 // Every page: honest SAMPLE OUTPUT label, 8 steps, 4 footer facts, and the owner's Bot at the top left once chosen.
 const pick=page.getByLabel('Bot for this playbook');
 for(let i=0;i<10;i++){
  await tabs.nth(i).click();
  const card=page.locator('article.pb-page-card');
  assert.match(await card.locator('.pb-title').innerText(),new RegExp(expectedHeads[i].replace(/[$.]/g,'\\$&')));
  await card.getByText('SAMPLE OUTPUT',{exact:true}).waitFor();
  assert.equal(await card.locator('.pb-step').count(),8,'8 steps on page '+(i+1));
  assert.equal(await card.locator('.pb-facts>div').count(),4);
  assert.match(await card.locator('.pb-eyebrow').innerText(),new RegExp(`BOT ${String(i+1).padStart(2,'0')} — `));
  await pick.selectOption({label:'Mia'});
  const avatar=card.locator('.pb-bot .avatar.xl');await avatar.waitFor();
  const box=await avatar.boundingBox();assert.ok(box&&box.width>=55&&box.width<=57,'avatar is 2x the mockup icon, got '+(box&&box.width));
  await page.waitForTimeout(150);
  await page.screenshot({path:path.join(shots,`playbook-${String(i+1).padStart(2,'0')}-desktop.png`)});
 }
 const saved=(await (await req.get(base+'/api/playbooks/assignments')).json()).assignments;
 assert.equal(Object.keys(saved).length,10);assert.ok(Object.values(saved).every(v=>v===mia));

 // The highlight cycles on its own, and Pause stops it.
 await tabs.nth(0).click();
 const active=async()=>page.locator('.pb-step.on b').innerText();
 const first=await active();await page.waitForFunction(f=>document.querySelector('.pb-step.on b')?.textContent!==f,first,{timeout:8000});
 await page.locator('.pb-play').click();const held=await active();await page.waitForTimeout(3000);assert.equal(await active(),held,'paused highlight stays put');

 // "Set up" only creates a PAUSED routine; nothing runs and no model request is made.
 await tabs.nth(3).click();
 await page.getByRole('button',{name:'Set up as a paused routine'}).click();
 await page.getByText(/Created a PAUSED routine for Mia/).waitFor();
 const routines=await (await req.get(base+'/api/routines')).json();
 const list=Array.isArray(routines)?routines:routines.routines;
 assert.equal(list.length,1);assert.equal(list[0].paused,1);assert.match(list[0].title,/Morning Brief playbook/);assert.equal(list[0].cron,'30 7 * * *');
 assert.deepEqual(await (await req.get(base+'/api/missions')).json().then(m=>Array.isArray(m)?m:m.missions||[]),[],'no mission was started');

 // Phone width: no page scrolls sideways (tables scroll inside their own card).
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(300);
 for(let i=0;i<10;i++){await tabs.nth(i).click();await page.waitForTimeout(200);await noScroll('playbook '+(i+1));
  if([0,5,8].includes(i))await page.screenshot({path:path.join(shots,`playbook-${String(i+1).padStart(2,'0')}-mobile.png`)})}
 assert.deepEqual(errors,[]);
 console.log('Playbooks passed: 10 pages, avatar 2x, sample label, 8 steps, paused-routine setup, 390px.');
}finally{await browser.close()}
