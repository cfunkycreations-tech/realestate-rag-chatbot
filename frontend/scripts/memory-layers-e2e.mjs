// Run against a fresh disposable installation. No model call is made.
import assert from 'node:assert/strict';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url)),base=process.env.E2E_URL,token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN for a fresh installation.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}),req=page.request,errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 assert.equal((await req.post(base+'/api/bots',{data:{name:'Test Bot',title:'Editor'}})).status(),200);
 const project=await (await req.post(base+'/api/projects',{data:{name:'Test project'}})).json();
 await page.goto(base);await page.getByRole('button',{name:'Lab',exact:true}).click();
 const section=page.locator('section').filter({has:page.getByRole('heading',{name:'Shared and project memory'})});
 await section.getByLabel('New layer memory').fill('A shared preference');await section.getByRole('button',{name:'Add layer memory'}).click();await section.getByText('A shared preference').waitFor();
 await section.getByRole('button',{name:'Edit memory: A shared preference'}).click();await section.getByLabel('Edit layer memory').fill('An updated shared preference');await section.getByRole('button',{name:'Save layer memory'}).click();await section.getByText('An updated shared preference').waitFor();
 await section.getByLabel('Memory layer').selectOption(project.id);await section.getByText('No entries in this layer.').waitFor();
 await section.getByLabel('New layer memory').fill('A project-only fact');await section.getByRole('button',{name:'Add layer memory'}).click();await section.getByText('A project-only fact').waitFor();
 await section.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(here,'../../docs/screenshots/memory-layers-desktop.png')});
 await page.setViewportSize({width:390,height:844});await section.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(here,'../../docs/screenshots/memory-layers-mobile.png')});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await section.getByRole('button',{name:'Delete memory: A project-only fact'}).click();await section.getByText('No entries in this layer.').waitFor();
 await section.getByLabel('Memory layer').selectOption('shared');await section.getByText('An updated shared preference').waitFor();
 assert.equal((await (await req.get(base+`/api/projects/${project.id}/memory`)).json()).length,0);
 assert.deepEqual(errors,[]);console.log('Shared and project memory UI CRUD and desktop/mobile screenshots passed.');
}finally{await browser.close()}
