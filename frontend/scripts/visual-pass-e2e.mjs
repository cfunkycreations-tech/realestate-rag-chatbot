// Run only against a fresh, disposable installation: this creates Bots and imports artwork.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
const here=path.dirname(fileURLToPath(import.meta.url));
const base=process.env.E2E_URL,token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN for a fresh disposable installation.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'}),req=page.request,errors=[],chatRequests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',request=>{if(request.method()==='POST'&&request.url().includes('/chat'))chatRequests.push(request.url())});
 assert.equal((await (await req.get(base+'/api/auth/status')).json()).setup,false,'Fresh installation required.');
 assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 const fallback=await (await req.post(base+'/api/bots',{data:{name:'Fallback',title:'Researcher'}})).json();
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();await page.locator('.sidebar .bot-row').first().waitFor();assert.equal(await page.locator('.collection-entry').count(),0,'A sole Uncategorized group is hidden');
 const zip=fs.readFileSync(path.join(here,'../tests/fixtures/identity-characters.zip'));
 const imported=await req.post(base+'/api/vault/import',{multipart:{file:{name:'characters.zip',mimeType:'application/zip',buffer:zip}}});assert.equal((await imported.json()).added,2);
 for(let i=1;i<=12;i++){
  const body={name:`Fixture ${i}`,title:i%2?'Editor':'Researcher',personality:'Test instructions',color:'lavender',shape:'round',profile:'smart'};
  const created=await (await req.post(base+'/api/bots',{data:body})).json();assert(created.character);
  assert.equal((await req.put(base+'/api/bots/'+created.id,{data:body})).status(),200);
 }
 const bots=await (await req.get(base+'/api/bots')).json();assert.equal(bots.filter(bot=>bot.character).length,12);assert.equal(bots.find(b=>b.id===fallback.id).character,null);
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();await page.locator('.sidebar .bot-row img').first().waitFor();
 assert.equal(await page.locator('.workspace-tabs').count(),0);assert.equal(await page.getByRole('navigation',{name:'Team navigation'}).count(),1);
 assert.equal(await page.locator('.sidebar .bot-row').count(),13);assert.equal(await page.locator('.sidebar .bot-row img').count(),12);
 assert.equal(await page.locator('.sidebar .bot-row .avatar-face').count(),1);assert.equal(await page.locator('.bot-card .avatar-face').count(),1);
 const colors=await page.evaluate(()=>{const css=s=>getComputedStyle(document.querySelector(s));const props=s=>({bg:css(s).backgroundColor,border:css(s).borderColor,color:css(s).color});return {sidebar:props('.sidebar'),row:props('.sidebar .bot-row.active'),gallery:props('.bot-card.selected'),search:props('.sidebar .search'),settings:props('.sidebar .settings-button'),tokens:getComputedStyle(document.documentElement).getPropertyValue('--command-frame-bright').trim()}});
 assert.equal(colors.row.border,colors.gallery.border,'selected row and card must share the gold frame');
 const old=['rgb(23, 23, 24)','rgb(34, 34, 36)','rgb(41, 38, 46)','rgb(29, 29, 31)','rgb(48, 48, 50)'];
 for(const [key,value] of Object.entries(colors))if(typeof value==='object')for(const color of Object.values(value))assert(!old.includes(color),`old gray ${color} in ${key}`);
 const toggle=page.getByRole('button',{name:'Collapse Test'});await toggle.click();assert.equal(await page.locator('.sidebar .bot-row img').count(),0);await page.getByRole('button',{name:'Expand Test'}).click();
 await page.locator('.sidebar .bot-row').filter({hasText:'Fixture 2'}).click();await page.getByRole('dialog',{name:'Fixture 2 spotlight'}).waitFor();await page.getByRole('button',{name:'Close spotlight'}).click();
 assert.equal(await page.locator('.sidebar .bot-row.active').getAttribute('aria-pressed'),'true');assert.equal(await page.getByRole('button',{name:'Open Fixture 2 spotlight'}).getAttribute('aria-pressed'),'true');
 await page.getByRole('button',{name:'Open Fixture 3 spotlight'}).click();await page.getByRole('button',{name:'Close spotlight'}).click();assert((await page.locator('.sidebar .bot-row.active').innerText()).includes('Fixture 3'));
 const scroll=await page.locator('.sidebar .bot-list').evaluate(el=>{el.scrollTop=el.scrollHeight;return {height:el.clientHeight,total:el.scrollHeight,top:el.scrollTop}});assert(scroll.total>scroll.height&&scroll.top>0,'Bot list should remain scrollable');assert(await page.getByRole('button',{name:'Settings',exact:true}).isVisible());await page.locator('.sidebar .bot-list').evaluate(el=>{el.scrollTop=0});
 const target=path.resolve(here,'../../docs/screenshots');const shot=async name=>page.screenshot({path:path.join(target,`visual-${name}.png`)});
 await page.waitForTimeout(300);await shot('gallery-desktop');
 const nav=page.getByRole('navigation',{name:'Team navigation'});await nav.getByRole('button',{name:'Roster',exact:true}).click();await shot('roster-desktop');
 await nav.getByRole('button',{name:'Office',exact:true}).click();await page.getByText('LIVE · REAL EVENTS ONLY').waitFor();await page.waitForTimeout(300);await shot('office-desktop');
 const canvas=page.locator('.office-scene canvas');await page.waitForTimeout(1000);await page.emulateMedia({reducedMotion:'no-preference'});await page.waitForTimeout(100);const animated1=await canvas.evaluate(el=>el.toDataURL());await page.waitForTimeout(350);const animated2=await canvas.evaluate(el=>el.toDataURL());assert.notEqual(animated1,animated2,'Idle sprites should bob when motion is allowed');await page.emulateMedia({reducedMotion:'reduce'});await page.waitForTimeout(150);const still1=await canvas.evaluate(el=>el.toDataURL());await page.waitForTimeout(350);const still2=await canvas.evaluate(el=>el.toDataURL());assert.equal(still1,still2,'Reduced motion should stop idle bobbing');
 const dimensions=await page.locator('.office-scene canvas').evaluate(el=>[el.width,el.height]);assert.deepEqual(dimensions,[1280,768]);
 await page.setViewportSize({width:390,height:844});await nav.getByRole('button',{name:'Gallery',exact:true}).click();await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();await shot('gallery-mobile');
 await page.getByRole('button',{name:'Open sidebar'}).click();await page.locator('.sidebar .bot-row img').first().waitFor();await shot('drawer-mobile');
 await page.keyboard.press('Escape');assert.equal(await page.getByRole('button',{name:'Open sidebar'}).getAttribute('aria-expanded'),'false');
 await nav.getByRole('button',{name:'Roster',exact:true}).click();await shot('roster-mobile');
 await nav.getByRole('button',{name:'Office',exact:true}).click();await page.getByText('LIVE · REAL EVENTS ONLY').waitFor();await shot('office-mobile');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile page overflows');assert.equal(errors.length,0,errors.join('\n'));assert.deepEqual(chatRequests,[],'Visual browsing must not call a model');
 console.log('Visual pass: 12 sprite Bots, fallback, themed sidebar colors, synced selection, collections, drawer, Gallery/Roster/Office desktop and 390px screenshots passed.');
}finally{await browser.close()}
