// Use ONLY a fresh disposable installation. Gives careers to existing Bots; no model request is made.
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
 const mk=async n=>(await (await req.post(base+'/api/bots',{data:{name:n,title:'Old job',personality:'My own words.'}})).json()).id;
 const ids=[await mk('Mia'),await mk('Tom')];
 const imp=await req.post(base+'/api/role-presets/import',{data:{presets:Array.isArray(pack)?pack:(pack.presets||pack.roles)}});
 assert.equal(imp.status(),200,'role pack imports');
 const before=JSON.stringify((await (await req.get(base+'/api/bots')).json()).sort((a,b)=>a.id.localeCompare(b.id)));
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 await page.getByRole('button',{name:/^Family$/}).click();
 await page.getByRole('tab',{name:/Career/i}).click().catch(()=>{});
 const card=page.getByRole('region',{name:'Bots without a career'}).or(page.locator('section[aria-label="Bots without a career"]'));
 await card.waitFor();
 assert.match(await card.innerText(),/Bots without a career \(2\)/);
 const preview=card.getByRole('button',{name:/^Preview/});
 assert.equal(await preview.isDisabled(),true,'nothing chosen yet');
 const opts=await card.locator('#att-bulk option').count();assert.ok(opts>5,'presets are listed');
 await card.locator('#att-bulk').selectOption({index:1});
 await preview.click();
 await card.getByRole('region',{name:'Preview'}).waitFor();
 assert.match(await card.innerText(),/Unchanged: Name, Job title, Personality/);
 assert.equal((await (await req.get(base+`/api/bots/${ids[0]}/career`)).json()).career,null,'preview writes nothing');
 await page.screenshot({path:path.join(shots,'attach-careers-preview-desktop.png')});
 await card.getByRole('button',{name:/^Add career to 2 Bots/}).click();
 await page.getByText(/Added a career to 2 Bots/).waitFor();
 for(const id of ids){const c=(await (await req.get(base+`/api/bots/${id}/career`)).json()).career;assert.ok(c&&c.history[0].event==='attached');}
 const after=JSON.stringify((await (await req.get(base+'/api/bots')).json()).sort((a,b)=>a.id.localeCompare(b.id)));
 assert.equal(after,before,'names, job titles and personalities are untouched');
 assert.deepEqual(errors,[]);
 console.log('Attach careers passed: preview writes nothing, apply adds careers beside 2 Bots, Bot rows unchanged.');
}finally{await browser.close()}
