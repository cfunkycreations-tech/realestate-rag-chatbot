// Use ONLY a fresh disposable installation. Drives "Delete all Bots" and "Purge all sprites"; no model request is made.
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
 for(const n of ['Mia','Tom','Zed'])await req.post(base+'/api/bots',{data:{name:n,title:'Helper'}});
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 assert.equal((await (await req.get(base+'/api/bots')).json()).length,3);

 // Purge all sprites lives in Settings > Character Vault and needs the typed word.
 await page.getByRole('button',{name:/^Settings/}).click();
 await page.getByRole('button',{name:'Character Vault',exact:true}).click();
 const purge=page.getByRole('button',{name:'Purge all sprites'});
 await purge.waitFor();
 assert.equal(await purge.isDisabled(),true,'purge is disabled while the Vault is empty');
 await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).click();await page.getByRole('dialog').waitFor({state:'detached'});

 // Delete all Bots: disabled until DELETE ALL is typed exactly; Cancel changes nothing.
 await page.getByRole('button',{name:'Delete all Bots'}).first().waitFor();
 await page.getByRole('button',{name:'Delete all Bots'}).first().click();
 const confirm=page.getByRole('dialog').getByRole('button',{name:'Delete all Bots'});
 const box=page.getByLabel('Type DELETE ALL to confirm');
 assert.equal(await confirm.isDisabled(),true);
 await box.fill('delete all');assert.equal(await confirm.isDisabled(),true,'case matters');
 await page.screenshot({path:path.join(shots,'delete-all-confirm-desktop.png')});
 await page.getByRole('button',{name:'Cancel'}).click();
 assert.equal((await (await req.get(base+'/api/bots')).json()).length,3,'cancel deletes nothing');
 await page.getByRole('button',{name:'Delete all Bots'}).first().click();
 await page.getByLabel('Type DELETE ALL to confirm').fill('DELETE ALL');
 await page.getByRole('dialog').getByRole('button',{name:'Delete all Bots'}).click();
 await page.getByText(/Your roster is looking a little quiet/).waitFor();
 assert.deepEqual(await (await req.get(base+'/api/bots')).json(),[]);
 assert.equal(await page.getByRole('button',{name:'Delete all Bots'}).count(),0,'button hides when no Bots remain');
 assert.deepEqual(errors,[]);
 console.log('Bulk actions passed: delete-all typed confirm, cancel safe, purge gated.');
}finally{await browser.close()}
