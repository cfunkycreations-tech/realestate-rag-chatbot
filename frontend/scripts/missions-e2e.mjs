// Fresh disposable installation only; requires mock-tool-gateway.mjs.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url)),base=process.env.E2E_URL,token=process.env.E2E_SETUP_TOKEN,gateway=process.env.E2E_GATEWAY_URL;
if(!base||!token||!gateway)throw Error('Set E2E_URL, E2E_SETUP_TOKEN and E2E_GATEWAY_URL for a fresh disposable installation.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}),req=page.request,errors=[];page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await (await req.get(base+'/api/auth/status')).json()).setup,false);
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 const zip=fs.readFileSync(path.join(here,'../tests/fixtures/identity-characters.zip'));
 assert.equal((await (await req.post(base+'/api/vault/import',{multipart:{file:{name:'sprites.zip',mimeType:'application/zip',buffer:zip}}})).json()).added,2);
 const bot=await (await req.post(base+'/api/bots',{data:{name:'Fixture',title:'Editor'}})).json();assert(bot.character);
 await req.put(base+'/api/settings/gateways/custom',{data:{url:gateway}});
 const settings=await (await req.get(base+'/api/settings')).json();settings.profiles.smart=[{gateway:'custom',model:'fixture'}];await req.put(base+'/api/settings/profiles',{data:settings.profiles});
 await req.put(base+'/api/budget/prices/smart',{data:{prompt:'1',completion:'2',max_prompt_tokens:16384,max_completion_tokens:512}});
 await page.goto(base);await page.getByRole('button',{name:'Missions',exact:true}).click();await page.getByRole('heading',{name:'No missions yet'}).waitFor();
 await page.getByRole('button',{name:'+ New mission'}).click();await page.getByLabel('Mission title').fill('Approve mission');await page.getByLabel('Instructions').fill('Create an actual note.');
 await page.screenshot({path:path.join(here,'../../docs/screenshots/missions-form-desktop.png')});await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(here,'../../docs/screenshots/missions-form-mobile.png')});
 await page.getByRole('button',{name:'Create mission'}).click();await page.getByText('Needs your approval').waitFor({timeout:15000});
 await page.getByRole('button',{name:'Approve once'}).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(here,'../../docs/screenshots/missions-approval-mobile.png')});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.setViewportSize({width:1440,height:900});await page.getByRole('button',{name:'Approve once'}).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(here,'../../docs/screenshots/missions-approval-desktop.png')});
 await page.getByRole('button',{name:'Approve once'}).click();await page.getByText('Fixture response after the tool result.').waitFor({timeout:15000});
 let list=await (await req.get(base+'/api/missions')).json();assert.equal(list[0].status,'done');assert.equal(list[0].runs.length,1);assert.equal(list[0].cost_usd,0.0006);
 await page.getByRole('button',{name:'Gallery',exact:true}).click();await page.locator('#quick-mission').fill('Please deny a fixture note');await page.getByRole('button',{name:'Send quick mission'}).click();
 await page.getByRole('heading',{name:'Missions',exact:true}).waitFor();await page.getByRole('button',{name:'Deny',exact:true}).waitFor({timeout:15000});await page.getByRole('button',{name:'Deny',exact:true}).click();
 await page.getByText('Fixture response after the tool result.').waitFor({timeout:15000});list=await (await req.get(base+'/api/missions')).json();assert.equal(list.length,2);assert.equal(list[0].title,'Please deny a fixture note');assert.equal(list[0].status,'done');
 await req.put(base+'/api/budget/limits/account',{data:{daily:'0',monthly:null}});
 await page.getByRole('button',{name:'+ New mission'}).click();await page.getByLabel('Mission title').fill('Blocked mission');await page.getByLabel('Instructions').fill('Must not call the gateway');await page.getByRole('button',{name:'Create mission'}).click();
 await page.getByRole('alert').filter({hasText:'daily budget cap'}).waitFor({timeout:15000});list=await (await req.get(base+'/api/missions')).json();assert.equal(list[0].status,'failed');assert.equal(list[0].runs.length,0);
 await req.put(base+'/api/budget/limits/account',{data:{daily:'5',monthly:null}});
 await page.getByRole('button',{name:'+ New mission'}).click();await page.getByLabel('Mission title').fill('Cancel mission');await page.getByLabel('Instructions').fill('Wait for approval');await page.getByRole('button',{name:'Create mission'}).click();await page.getByRole('button',{name:'Cancel mission',exact:true}).waitFor();await page.getByText('Needs your approval').waitFor({timeout:15000});await page.getByRole('button',{name:'Cancel mission',exact:true}).click();await page.getByRole('alert').filter({hasText:'Response stopped.'}).waitFor({timeout:15000});
 assert.deepEqual(errors,[]);console.log('Missions: create, approval, result, Quick Mission, denial, cap refusal and cancellation passed on desktop and 390px.');
}finally{await browser.close()}
