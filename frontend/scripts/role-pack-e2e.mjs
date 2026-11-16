// Use ONLY a fresh disposable installation. Uploads the real 59-role pack through the hiring dialog.
import assert from 'node:assert/strict';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url));
const shots=process.env.E2E_SHOTS||path.join(here,'../../docs/screenshots');
const pack=path.join(here,'../../docs/role-pack/Funk_Bot_59_Employee_DNA_Role_Pack.json');
const base=process.env.E2E_URL, token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN for a fresh disposable installation.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}), req=page.request;
 assert.equal((await (await req.get(base+'/api/auth/status')).json()).setup,false,'This test requires a fresh disposable installation.');
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 await page.goto(base);await page.getByRole('button',{name:'New Bot',exact:true}).first().click();
 await page.getByRole('tab',{name:'Hire by career'}).click();await page.getByText('No role library yet').waitFor();
 await page.locator('input[type=file]').setInputFiles(pack);
 await page.getByText('59 added').waitFor();await page.getByLabel('Search roles').waitFor();
 await page.getByLabel('Search roles').fill('security');await page.getByRole('option',{name:'Security Engineer'}).click();
 await page.getByRole('heading',{name:'Security Engineer'}).waitFor();
 await page.screenshot({path:path.join(shots,'role-pack-imported-desktop.png')});
 const list=await (await req.get(base+'/api/role-presets')).json();
 assert.equal(list.length,59);assert.equal(new Set(list.map(p=>p.department)).size,6);
 console.log('Real 59-role pack uploaded through the UI: 59 roles in 6 departments.');
}finally{await browser.close()}
