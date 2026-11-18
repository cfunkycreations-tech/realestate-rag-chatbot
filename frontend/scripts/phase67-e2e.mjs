// Use ONLY a fresh disposable installation. Drives Evaluations (Phase 6) and the Cockpit (Phase 7); no model request is made.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url));
const shots=process.env.E2E_SHOTS||path.join(here,'../../docs/screenshots');
const base=process.env.E2E_URL, token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN for a fresh disposable installation.');
const pack=JSON.parse(fs.readFileSync(path.join(here,'../../docs/role-pack/Funk_Bot_59_Employee_DNA_Role_Pack.json'),'utf8'));
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900}}), req=page.request, errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 const mia=(await (await req.post(base+'/api/bots',{data:{name:'Mia',title:'Helper',personality:'My own words.'}})).json()).id;
 await req.post(base+'/api/bots',{data:{name:'Tom',title:'Helper'}});
 assert.equal((await req.post(base+'/api/role-presets/import',{data:{presets:Array.isArray(pack)?pack:(pack.presets||pack.roles)}})).status(),200);
 const preset=(await (await req.get(base+'/api/role-presets')).json());
 const pid=(Array.isArray(preset)?preset:preset.presets)[0].id;
 assert.equal((await req.post(base+'/api/career/attach',{data:{assignments:[{bot_id:mia,preset_id:pid}],confirm:true}})).status(),200);
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();

 // Phase 6: Evaluations. No work yet = Not evaluated; the compliance check really fails (the Bot's own text lacks the role rules) and is recorded.
 await page.getByRole('button',{name:/^Family$/}).click();
 await page.getByRole('tab',{name:'Evaluations'}).click();
 await page.getByRole('button',{name:/Evaluate every Bot/}).click();
 await page.getByText(/2 Bots evaluated, \d+ results? recorded\. Cost: \$0\.00/).waitFor();
 const miaCard=page.locator('article[aria-label="Mia"]');
 await miaCard.getByRole('button',{name:'Details'}).click();
 await miaCard.getByText('Instruction history').waitFor();
 assert.match(await miaCard.innerText(),/Instruction compliance[\s\S]*Failed · 0%|Instruction compliance[\s\S]*Passed/);
 assert.match(await page.locator('article[aria-label="Tom"]').innerText(),/Not Evaluated/);
 await page.screenshot({path:path.join(shots,'evaluations-desktop.png')});
 // Editing instructions keeps the old text; Restore brings it back.
 const bots=await (await req.get(base+'/api/bots')).json();const m=bots.find(b=>b.id===mia);
 assert.equal((await req.put(base+`/api/bots/${mia}`,{data:{name:m.name,title:m.title,color:m.color,shape:m.shape,profile:m.profile,personality:'Rewritten.'}})).status(),200);
 await miaCard.getByRole('button',{name:'Hide'}).click();await miaCard.getByRole('button',{name:'Details'}).click();
 await miaCard.getByRole('button',{name:'Restore'}).first().click();
 await page.getByText(/Restored\. The text it replaced was saved too/).waitFor();
 const after=(await (await req.get(base+'/api/bots')).json()).find(b=>b.id===mia);
 assert.notEqual(after.personality,'Rewritten.');

 // Phase 7: Cockpit has three modes; unconnected sources are honest and show no figures.
 await page.getByRole('button',{name:/^Cockpit$/}).click();
 await page.getByRole('tab',{name:'AI Workforce'}).waitFor();
 await page.getByText('BOTS CONFIGURED').waitFor();
 assert.match(await page.locator('.ck-grid').innerText(),/BOTS CONFIGURED\s+2/);
 await page.screenshot({path:path.join(shots,'cockpit-workforce-desktop.png')});
 await page.getByRole('tab',{name:'Lyricist Pro'}).click();
 await page.getByText(/Not connected\. Add a connector in Settings/).waitFor();
 await page.getByRole('tab',{name:'Business Operations'}).click();
 await page.getByText(/Not connected\. Add a connector in Settings/).waitFor();
 // a tile opens its section
 await page.getByRole('tab',{name:'AI Workforce'}).click();
 await page.getByRole('button',{name:/^MISSIONS:/}).click();
 await page.getByRole('heading',{name:/Missions/}).first().waitFor();
 await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:/^Cockpit$/}).click().catch(()=>{});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal scroll at 390px');
 assert.deepEqual(errors,[]);
 console.log('Phase 6/7 passed: evaluations recorded at $0, instruction restore, cockpit 3 modes, tile navigation, 390px.');
}finally{await browser.close()}
