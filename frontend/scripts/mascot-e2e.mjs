// Use ONLY a fresh disposable installation. Checks the Funk Bot image shows (logo, login, welcome) and Play works even with reduced motion.
import assert from 'node:assert/strict';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url));
const shots=process.env.E2E_SHOTS||path.join(here,'../../docs/screenshots');
const base=process.env.E2E_URL, token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN for a fresh disposable installation.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
const loaded=sel=>page=>page.evaluate(s=>{const i=document.querySelector(s);return !!i&&i.complete&&i.naturalWidth>0},sel);
try{
 const ctx=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
 const page=await ctx.newPage(), req=page.request, errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base);await page.locator('.auth-mascot').waitFor();
 assert(await loaded('.auth-mascot')(page),'login image loads');
 await page.screenshot({path:path.join(shots,'login-funkbot.png')});
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 await req.post(base+'/api/bots',{data:{name:'Mia',title:'Helper'}});
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 assert(await loaded('.sidebar .brand-mascot')(page),'logo image loads');
 await page.locator('.sidebar .brand').screenshot({path:path.join(shots,'logo-funkbot.png')});
 // Playbooks Play works with reduced motion (the owner's machine has it on).
 await page.getByRole('button',{name:/^Playbooks$/}).click();
 const play=page.locator('.pb-play');await play.waitFor();
 assert.equal(await play.isEnabled(),true,'Play is enabled');
 assert.equal((await play.innerText()).trim(),'Play');
 const active=()=>page.locator('.pb-step.on small').first().innerText();
 const before=await active();await play.click();
 assert.equal((await play.innerText()).trim(),'Pause');
 await page.waitForFunction(b=>document.querySelector('.pb-step.on small')?.textContent!==b,before,{timeout:9000});
 await page.screenshot({path:path.join(shots,'playbooks-play-reduced.png')});
 await play.click();assert.equal((await play.innerText()).trim(),'Play');
 // Normal motion still autoplays.
 const ctx2=await browser.newContext({viewport:{width:1440,height:900}});const p2=await ctx2.newPage();
 await p2.goto(base);
 await p2.locator('input[type=password]').first().fill('disposable-test-password');await p2.keyboard.press('Enter');
 await p2.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 await p2.getByRole('button',{name:/^Playbooks$/}).click();
 await p2.locator('.pb-play',{hasText:'Pause'}).waitFor({timeout:5000});
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 await page.locator('.bot-card-open').first().click();
 await page.locator('.welcome-mascot').first().waitFor();
 assert(await loaded('.welcome-mascot')(page),'welcome image loads');
 assert.deepEqual(errors,[]);
 console.log('Funk Bot image shows; Play works with reduced motion; autoplay unchanged.');
}finally{await browser.close()}
