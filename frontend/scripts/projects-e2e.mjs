// Use only a fresh disposable installation and the mock tool gateway.
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
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 const zip=fs.readFileSync(path.join(here,'../tests/fixtures/identity-characters.zip'));
 await req.post(base+'/api/vault/import',{multipart:{file:{name:'sprites.zip',mimeType:'application/zip',buffer:zip}}});
 const bot=await (await req.post(base+'/api/bots',{data:{name:'Fixture',title:'Editor'}})).json();assert(bot.character);
 await req.put(base+'/api/settings/gateways/custom',{data:{url:gateway}});const settings=await (await req.get(base+'/api/settings')).json();settings.profiles.smart=[{gateway:'custom',model:'fixture'}];await req.put(base+'/api/settings/profiles',{data:settings.profiles});await req.put(base+'/api/budget/prices/smart',{data:{prompt:'1',completion:'2',max_prompt_tokens:16384,max_completion_tokens:512}});
 const id=(await (await req.post(base+'/api/missions',{data:{title:'Real linked mission',instructions:'Create a note',bot_id:bot.id}})).json()).id;
 let mission;for(let i=0;i<100;i++){mission=await (await req.get(base+'/api/missions/'+id)).json();if(mission.status==='waiting_approval')break;await new Promise(r=>setTimeout(r,100))}assert.equal(mission.status,'waiting_approval');const run=mission.runs[0].run_id;const calls=await (await req.get(base+'/api/jobs/'+run+'/tool-calls')).json();await req.post(base+`/api/jobs/${run}/tool-calls/${calls[0].id}/decision`,{data:{decision:'approve_once'}});
 for(let i=0;i<100;i++){mission=await (await req.get(base+'/api/missions/'+id)).json();if(mission.status==='done')break;await new Promise(r=>setTimeout(r,100))}assert.equal(mission.status,'done');
 await page.goto(base);await page.getByRole('button',{name:'Projects',exact:true}).click();await page.getByRole('heading',{name:'No projects yet'}).waitFor();await page.getByRole('button',{name:'+ New project'}).click();await page.getByLabel('Project name').fill('Fixture project');await page.getByLabel('Description').fill('A real project');await page.getByLabel('Owner Bot').selectOption(bot.id);
 await page.screenshot({path:path.join(here,'../../docs/screenshots/projects-form-desktop.png')});await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(here,'../../docs/screenshots/projects-form-mobile.png')});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.getByRole('button',{name:'Save project'}).click();await page.getByRole('heading',{name:'Fixture project'}).waitFor();
 await page.getByLabel('Link existing mission').selectOption(id);await page.getByRole('button',{name:'Link mission'}).click();await page.getByText('Fixture response after the tool result.').waitFor();await page.getByLabel('Add a note').fill('Real project note');await page.getByRole('button',{name:'Add note'}).click();await page.getByText('Real project note').waitFor();await page.getByRole('button',{name:'approved.txt'}).click();await page.getByText('A real approved fixture note.').waitFor();
 await page.setViewportSize({width:1440,height:900});await page.screenshot({path:path.join(here,'../../docs/screenshots/projects-detail-desktop.png')});await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(here,'../../docs/screenshots/projects-detail-mobile.png')});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.getByRole('button',{name:'Real linked mission'}).click();await page.getByRole('heading',{name:'Missions',exact:true}).waitFor();assert.deepEqual(errors,[]);console.log('Projects creation, linking, results, notes and workspace preview passed on desktop and 390px.');
}finally{await browser.close()}
