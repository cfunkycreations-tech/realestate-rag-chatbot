// Disposable local backend with FUNK_ENABLE_RESTORE_RESTART=1 only.
import assert from 'node:assert/strict';import path from 'node:path';import {fileURLToPath} from 'node:url';import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url)),base=process.env.E2E_URL,token=process.env.E2E_SETUP_TOKEN;if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}),req=page.request,errors=[];page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 await req.post(base+'/api/bots',{data:{name:'Before Backup',title:'Tester'}});await req.put(base+'/api/control/pause',{data:{paused:true}});
 await page.goto(base);await page.getByRole('button',{name:'Open settings'}).click();const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:'Backup',exact:true}).click();
 const downloadEvent=page.waitForEvent('download');await dialog.getByRole('button',{name:'Download workspace backup'}).click();const file=await (await downloadEvent).path();assert(file);
 await req.post(base+'/api/bots',{data:{name:'After Backup',title:'Tester'}});await dialog.getByLabel('Workspace backup ZIP').setInputFiles(file);await dialog.getByRole('button',{name:'Restore and restart'}).waitFor();
 await dialog.locator('.backup-settings').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(here,'../../docs/screenshots/restore-desktop.png')});await page.setViewportSize({width:390,height:844});await dialog.getByRole('button',{name:'Restore and restart'}).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(here,'../../docs/screenshots/restore-mobile.png')});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 page.once('dialog',d=>d.accept());await dialog.getByRole('button',{name:'Restore and restart'}).click();await page.getByRole('button',{name:'Sign in'}).waitFor({timeout:35000});await page.getByLabel('Password').fill('disposable-test-password');await page.getByRole('button',{name:'Sign in'}).click();await page.getByRole('button',{name:'Open Before Backup spotlight'}).waitFor();assert.equal(await page.getByRole('button',{name:'Open After Backup spotlight'}).count(),0);
 assert.equal((await (await req.get(base+'/api/control/pause')).json()).paused,true);assert.deepEqual(errors,[]);console.log('One-click restore, restart, session invalidation and preserved backup passed.');
}finally{await browser.close()}
