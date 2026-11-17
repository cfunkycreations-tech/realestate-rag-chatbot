// Use ONLY a fresh disposable installation. Checks the Bot-started conversation view and the messaging settings; no model request is made.
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
 const a=(await (await req.post(base+'/api/bots',{data:{name:'Dev',title:'Developer'}})).json()).id;
 const b=(await (await req.post(base+'/api/bots',{data:{name:'Sec',title:'Security Engineer'}})).json()).id;
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();

 // Empty state first: real data, nothing invented.
 await page.getByRole('button',{name:/^Bot DMs$/}).click();
 await page.getByRole('tab',{name:'Started by Bots'}).click();
 await page.getByText('No Bot-started conversations yet').waitFor();
 await page.getByText(/currently turned off/).waitFor();

 // A realistic payload (rendering only; the numbers themselves are covered by backend tests).
 const usage={prompt_tokens:1200,completion_tokens:80,usd:'0.0123',unverified_rounds:0,model_rounds:1,basis:'configured prices, not a provider invoice'};
 await page.route('**/api/bot-messages',r=>r.fulfill({json:{settings:{enabled:true},refused:[{sender_id:a,receiver_id:b,kind:'ask_question',detail:'Cooldown: wait before messaging this Bot again.',created_at:1700000000}],threads:[
  {dm_id:'t1',subject:'Bot message: Security concern',initiator_id:a,initiator_name:'Dev',receiver_id:b,receiver_name:'Sec',kind:'request_review',mission_id:'m1',mission_title:'Ship login',project_id:null,status:'done',error:null,messages_sent:1,outcome:'The form is safe; escape the username.',usage,updated_at:1700000100},
  {dm_id:'t2',subject:'Bot message: Need keys',initiator_id:b,initiator_name:'Sec',receiver_id:a,receiver_name:'Dev',kind:'escalate_blocker',mission_id:null,mission_title:null,project_id:null,status:'failed',error:'The reply timed out.',messages_sent:1,outcome:null,usage:{...usage,model_rounds:0,prompt_tokens:0,completion_tokens:0,usd:'0'},updated_at:1700000200}]}}));
 await page.route('**/api/bot-dms/t1',r=>r.fulfill({json:{dm:{id:'t1',name:'x',sender_id:a,receiver_id:b},messages:[{id:'1',bot_id:a,role:'sender',content:'[request review] Security concern\n\nPlease check.',created_at:1},{id:'2',bot_id:b,role:'receiver',content:'The form is safe.',created_at:2}],turns:[]}}));
 await page.reload();await page.getByRole('button',{name:/^Bot DMs$/}).click();await page.getByRole('tab',{name:'Started by Bots'}).click();
 const card=page.locator('.bc-card',{hasText:'Security concern'});await card.waitFor();
 const text=await card.innerText();
 assert.match(text,/Dev\s*→\s*Sec/);assert.match(text,/Requested a review/);assert.match(text,/Ship login/);assert.match(text,/1,200 in · 80 out/);assert.match(text,/\$0\.0123/);assert.match(text,/The form is safe/);
 const failed=await page.locator('.bc-card',{hasText:'Need keys'}).innerText();
 assert.match(failed,/Escalated a blocker/);assert.match(failed,/No tokens recorded/);assert.match(failed,/No model use yet/);assert.match(failed,/timed out/);
 await card.locator('.bc-head').click();await card.getByText('Sec replied').waitFor();
 await page.getByText('Blocked attempts (1)').click();await page.getByText(/Cooldown: wait/).waitFor();
 await page.screenshot({path:path.join(shots,'bot-conversations-desktop.png')});

 // Phone width: nothing overflows.
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(300);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal scroll at 390px');
 await page.screenshot({path:path.join(shots,'bot-conversations-mobile.png')});
 await page.setViewportSize({width:1440,height:900});

 // Settings: messaging is off by default and the toggle is real.
 assert.equal((await (await req.get(base+'/api/settings/bot-comms')).json()).enabled,false);
 await page.getByRole('button',{name:'Open settings'}).click();
 await page.getByRole('button',{name:'Web access'}).click();
 const enable=page.getByLabel('Allow Bots to start conversations');await enable.scrollIntoViewIfNeeded();
 assert.equal(await enable.isChecked(),false);
 await enable.click();await page.getByText('Saved.').waitFor();
 assert.equal((await (await req.get(base+'/api/settings/bot-comms')).json()).enabled,true);
 await page.getByLabel('Sending Bot').last().selectOption(a);await page.getByLabel('Receiving Bot').last().selectOption(b);
 await page.getByRole('button',{name:'Approve pair'}).last().click();
 await page.locator('.tool-policy-row',{hasText:'Dev → Sec'}).waitFor();
 assert.equal((await (await req.get(base+'/api/settings/comm-links')).json()).length,1);
 await page.screenshot({path:path.join(shots,'bot-comms-settings-desktop.png')});
 assert.deepEqual(errors,[]);
 console.log('Bot conversations and messaging settings passed: empty, real data, history, blocked attempts, 390px, settings toggle and pair.');
}finally{await browser.close()}
