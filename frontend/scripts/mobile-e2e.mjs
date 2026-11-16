// Run on a fresh disposable installation.
import assert from 'node:assert/strict';
import {chromium} from '@playwright/test';
const base=process.env.E2E_URL,token=process.env.E2E_SETUP_TOKEN;
if(!base||!token)throw Error('Set E2E_URL and E2E_SETUP_TOKEN.');
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.E2E_CHROMIUM?{executablePath:process.env.E2E_CHROMIUM}:{})});
try{
 const page=await browser.newPage({viewport:{width:390,height:844}}),req=page.request,errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const auth=await (await req.get(base+'/api/auth/status')).json();
 if(!auth.setup)assert.equal((await req.post(base+'/api/auth/setup',{data:{password:'disposable-test-password',setup_token:token}})).status(),200);
 else assert.equal((await req.post(base+'/api/auth/login',{data:{password:'disposable-test-password'}})).status(),200);
 if((await (await req.get(base+'/api/bots')).json()).length===0)for(const name of ['Mobile Alice','Mobile Bob'])assert.equal((await req.post(base+'/api/bots',{data:{name}})).status(),200);
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 const nav=page.getByRole('navigation',{name:'Team navigation'});
 async function check(label){await page.waitForTimeout(200);const failures=await page.evaluate(()=>[...document.querySelectorAll('button,input,textarea,select')].filter(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);if(!r.width||!r.height||s.visibility==='hidden'||r.top>innerHeight||r.bottom<0)return false;let p=e.parentElement;while(p){const style=getComputedStyle(p);if((style.overflowX==='auto'||style.overflowX==='scroll')&&p.scrollWidth>p.clientWidth)return false;p=p.parentElement}return r.right>innerWidth+1||r.left< -1}).map(e=>`${e.tagName}.${e.className} ${e.textContent?.trim().slice(0,50)} ${Math.round(e.getBoundingClientRect().right)}`));assert.deepEqual(failures,[],`${label}: overflowing controls`);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${label}: page overflow`)}
 for(const name of ['Office','Roster','Gallery','Missions','Group chats','Bot DMs','Projects','Analytics','Lab','Skills','Routines','Workflows','Inbox']){await nav.getByRole('button',{name,exact:false}).click();await check(name)}
 for(const [screen,open] of [['Missions','+ New mission'],['Bot DMs','+ New Bot DM'],['Projects','+ New project'],['Routines','+ New routine'],['Workflows','+ New workflow']]){await nav.getByRole('button',{name:screen,exact:false}).click();await page.getByRole('button',{name:open,exact:true}).click();await check(screen+' form')}
 await nav.getByRole('button',{name:'Gallery',exact:true}).click();await page.getByRole('button',{name:'Open Mobile Alice spotlight'}).click();await check('Bot spotlight and chat');await page.getByRole('button',{name:'Close spotlight'}).click();
 await page.getByRole('button',{name:'Open sidebar'}).click();await check('Sidebar');await page.locator('.drawer-close').click();
 await page.getByRole('button',{name:'Open settings'}).click();for(const tab of ['Gateways','Model profiles','Budget','Web access','Tool audit','Usage','Character Vault','Appearance','Backup','Connectors']){await page.getByRole('button',{name:tab,exact:true}).click();await check('Settings '+tab)}
 assert.deepEqual(errors,[]);console.log('390px navigation and settings controls fit.');
}finally{await browser.close()}
