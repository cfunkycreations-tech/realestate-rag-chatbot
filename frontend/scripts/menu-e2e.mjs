// Use ONLY a fresh disposable installation. Checks the Bot options dropdown is not covered (at 1440, 663 and 390 wide) and the model pin control.
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
 const bot=(await (await req.post(base+'/api/bots',{data:{name:'Mia',title:'Helper',personality:'x'}})).json()).id;
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 for(const [w,h] of [[1440,900],[663,780],[390,844]]){
  await page.setViewportSize({width:w,height:h});
  await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
  await page.locator('.bot-card-open').first().click();
  await page.getByRole('button',{name:'Bot options'}).first().click();
  const item=page.locator('.dropdown button',{hasText:'Edit identity'}).first();await item.waitFor();
  for(const label of ['Edit identity','Delete Bot']){
   const el=page.locator('.dropdown button',{hasText:label}).first();
   const box=await el.boundingBox();
   const top=await page.evaluate(([x,y])=>{const e=document.elementFromPoint(x,y);return !!e&&!!e.closest('.dropdown')},[box.x+box.width/2,box.y+box.height/2]);
   assert(top,`${label} is covered at ${w}px`);
  }
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`horizontal scroll at ${w}px`);
  await page.screenshot({path:path.join(shots,`bot-menu-${w}.png`)});
  await page.keyboard.press('Escape');
 }
 // Model pin through the real control.
 await page.setViewportSize({width:1440,height:900});await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 await page.locator('.bot-card-open').first().click();
 await page.getByRole('button',{name:'Bot options'}).first().click();
 await page.locator('.dropdown button',{hasText:'Edit identity'}).first().click();
 await page.getByLabel('Pin an exact model (optional)').fill('vendor/my-model');
 await page.getByRole('button',{name:'Pin model'}).click();
 await page.getByText(/Pinned\. This Bot now uses that model/).waitFor();
 assert.deepEqual((await (await req.get(base+`/api/bots/${bot}/model-pin`)).json()).pin,{gateway:'openrouter',model:'vendor/my-model'});
 await page.getByRole('button',{name:'Unpin'}).click();
 await page.getByText(/Unpinned/).waitFor();
 assert.equal((await (await req.get(base+`/api/bots/${bot}/model-pin`)).json()).pin,null);
 assert.deepEqual(errors,[]);
 console.log('Menu + model pin passed at 1440, 663 and 390.');
}finally{await browser.close()}
