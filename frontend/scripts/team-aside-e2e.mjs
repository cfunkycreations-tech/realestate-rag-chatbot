// Use ONLY a fresh disposable installation. Checks the Activity panel is roomy and scrolls inside itself.
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
 const events=Array.from({length:40},(_,i)=>({id:i+1,bot_id:null,type:'computer.domains_changed',payload:{revision:i},created_at:1700000000+i}));
 await page.route('**/api/team/overview*',r=>r.fulfill({json:{bots:17,runs_today:0,last_activity:1700000040,events,states:{}}}));
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 const list=page.locator('.command-aside .team-activity');await page.locator('.command-aside .team-event').first().waitFor();
 const box=await list.boundingBox();
 assert(box.height>=200,'Activity list is at least 200px tall, got '+box.height);
 const m=await list.evaluate(el=>({sh:el.scrollHeight,ch:el.clientHeight}));
 assert(m.sh>m.ch,'Activity scrolls inside its own panel');
 await list.evaluate(el=>{el.scrollTop=el.scrollHeight});
 assert(await list.evaluate(el=>el.scrollTop>0),'Activity list actually scrolls');
 await page.screenshot({path:path.join(shots,'team-aside-desktop.png')});
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(300);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal scroll at 390px');
 const h=(await page.locator('.command-aside .team-activity').boundingBox()).height;
 assert(h>=200,'Activity is tall enough on a phone, got '+h);
 console.log('Activity panel is roomy and scrolls on its own at desktop and 390px.');
}finally{await browser.close()}
