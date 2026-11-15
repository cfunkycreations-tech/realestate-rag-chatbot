// Only run against a fresh disposable installation; this imports artwork and creates Bots.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url)),base=process.env.E2E_URL,token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN for a fresh disposable installation.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try {
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}),req=page.request,errors=[];page.on('pageerror',e=>errors.push(e.message));
 assert.equal((await (await req.get(base+'/api/auth/status')).json()).setup,false);
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 const zip=fs.readFileSync(path.join(here,'../tests/fixtures/identity-characters.zip'));
 assert.equal((await (await req.post(base+'/api/vault/import',{multipart:{file:{name:'sprites.zip',mimeType:'application/zip',buffer:zip}}})).json()).added,2);
 for(let i=0;i<8;i++)assert((await (await req.post(base+'/api/bots',{data:{name:`Test ${i}`,title:'Researcher'}})).json()).character);
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 const hero=page.locator('.command-banner');assert.equal(await hero.evaluate(el=>el.getBoundingClientRect().height),240);
 await page.getByRole('button',{name:'Open settings'}).click();await page.getByRole('button',{name:'Appearance',exact:true}).click();
 await page.locator('#banner-file').setInputFiles(path.join(here,'../tests/fixtures/banner-example.png'));
 await page.getByRole('button',{name:'Save banner',exact:true}).click();await page.getByText('Banner saved.',{exact:true}).waitFor();
 const preview=page.getByLabel('Banner preview');const rect=await preview.boundingBox();assert(rect);await page.mouse.move(rect.x+rect.width*.25,rect.y+rect.height*.6);await page.mouse.down();await page.mouse.move(rect.x+rect.width*.7,rect.y+rect.height*.75);await page.mouse.up();
 const x=await page.locator('#banner-x').inputValue(),y=await page.locator('#banner-y').inputValue();assert(Math.abs(Number(x)-70)<=1);assert(Math.abs(Number(y)-75)<=1);
 await page.locator('#banner-zoom').fill('1.5');await page.screenshot({path:path.join(here,'../../docs/screenshots/banner-settings-desktop.png')});
 await page.getByRole('button',{name:'Save placement'}).click();await page.getByText('Placement saved.',{exact:true}).waitFor();
 await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).click();await page.locator('.command-banner .banner-image').waitFor();
 assert.equal(await page.locator('.command-banner .banner-image').evaluate(el=>el.style.transform),'scale(1.5)');await page.screenshot({path:path.join(here,'../../docs/screenshots/banner-hero-desktop.png')});
 await page.locator('.gallery-scroll').evaluate(el=>{el.scrollTop=400});await page.waitForFunction(()=>document.querySelector('.command-banner').classList.contains('collapsed'));assert.equal(await hero.evaluate(el=>el.getBoundingClientRect().height),60);
 await page.reload();await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();await page.locator('.command-banner .banner-image').waitFor();assert.equal(await page.locator('.command-banner .banner-image').evaluate(el=>el.style.transform),'scale(1.5)');
 await page.setViewportSize({width:390,height:844});assert.equal(await hero.evaluate(el=>el.getBoundingClientRect().height),160);await page.screenshot({path:path.join(here,'../../docs/screenshots/banner-hero-mobile.png')});
 await page.getByRole('button',{name:'Open settings'}).click();await page.getByRole('button',{name:'Appearance',exact:true}).click();await preview.waitFor();await page.screenshot({path:path.join(here,'../../docs/screenshots/banner-settings-mobile.png')});
 await page.getByRole('dialog').getByRole('button',{name:'Close',exact:true}).click();await page.locator('.command-center').evaluate(el=>{el.scrollTop=200});await page.waitForFunction(()=>document.querySelector('.command-banner').classList.contains('collapsed'));assert.equal(await hero.evaluate(el=>el.getBoundingClientRect().height),60);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);console.log('Banner upload, preview, drag, zoom, persistence, collapse and desktop/mobile screenshots passed.');
}finally{await browser.close()}
