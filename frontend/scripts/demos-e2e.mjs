// Use ONLY a fresh disposable installation. Plays every demo (with reduced motion on) and checks nothing is written.
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
 const ctx=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
 const page=await ctx.newPage(), req=page.request, errors=[], writes=[];
 page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 await req.post(base+'/api/bots',{data:{name:'Mia',title:'Helper'}});
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 await page.getByRole('button',{name:/^Demos$/}).click();
 await page.getByRole('heading',{name:'Demos',level:1}).waitFor();
 page.on('request',r=>{if(r.method()!=='GET'&&r.url().includes('/api/'))writes.push(r.method()+' '+r.url())});
 const tabs=page.locator('.dm-tabs button');const n=await tabs.count();
 assert(n>=24,`expected 24+ demos, saw ${n}`);
 const play=page.locator('.dm-play');
 for(let i=0;i<n;i++){
  await tabs.nth(i).click();                                   // selecting a demo starts it
  await play.filter({hasText:/Pause/}).waitFor({timeout:3000});
  const total=await page.locator('.dm-steps li').count();
  await page.locator('.dm-steps li button.on small',{hasText:String(total).padStart(2,'0')}).waitFor({timeout:total*3600+3000});
  await play.filter({hasText:/Replay/}).waitFor({timeout:4500});
  assert((await page.locator('.dm-row').count())>=total,'rows were revealed');
 }
 await page.screenshot({path:path.join(shots,'demos-last.png')});
 // Pause really pauses; Replay restarts.
 await tabs.first().click();await play.filter({hasText:/Pause/}).waitFor();await play.click();
 const held=await page.locator('.dm-steps li button.on small').innerText();await page.waitForTimeout(3600);
 assert.equal(await page.locator('.dm-steps li button.on small').innerText(),held,'paused stays put');
 assert.equal((await play.innerText()).trim(),'Play');
 // "Open" buttons reach the real screens.
 await tabs.filter({hasText:/^Missions$/}).click();await page.getByRole('button',{name:/Open Missions/}).click();
 await page.getByRole('heading',{name:/Missions/}).first().waitFor();
 await page.getByRole('button',{name:/^Demos$/}).click();
 await tabs.filter({hasText:/Budget/}).click();await page.getByRole('button',{name:/Open Budget/}).click();
 await page.getByRole('dialog').waitFor();
 assert.deepEqual(writes,[],'demos wrote nothing');
 assert.deepEqual(errors,[]);
 console.log(`Demos passed: ${n} demos played to the end with reduced motion, pause works, Open buttons work, nothing written.`);
}finally{await browser.close()}
