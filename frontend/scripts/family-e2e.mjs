// Use ONLY a fresh disposable installation. Drives the real Family views (Career Center, Council, Mentorship); no model request is made.
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
 const mk=async n=>(await (await req.post(base+'/api/bots',{data:{name:n,title:'Helper'}})).json()).id;
 const [a,b,c]=[await mk('Mia'),await mk('Tom'),await mk('Zed')];
 await page.goto(base);await page.getByRole('heading',{name:'Your team, at a glance.'}).waitFor();
 const noScroll=async label=>assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal scroll: '+label);

 // Career Center: real zero data, nothing invented.
 await page.getByRole('button',{name:/^Family$/}).click();
 await page.getByRole('heading',{name:'Family'}).waitFor();
 await page.getByRole('list',{name:'Career levels'}).waitFor();
 const miaCard=page.locator('article[aria-label="Mia"]');await miaCard.waitFor();
 assert.match(await miaCard.innerText(),/Trainee[\s\S]*No data yet/);
 await miaCard.locator('.bc-head').click();
 const profile=page.getByLabel('Mia profile');await profile.waitFor();
 assert.match(await profile.innerText(),/still to meet for Junior/);
 assert.equal(await profile.getByRole('button',{name:/^Recommend for Junior/}).isDisabled(),true,'cannot recommend without evidence');
 await page.getByRole('button',{name:/Run this period/}).click();await page.getByText(/0 new reviews built/).waitFor();
 await page.screenshot({path:path.join(shots,'family-career-desktop.png')});

 // Promotion is owner-approved and only a label.
 const rid=(await (await req.post(`${base}/api/career/${a}/recommendations`,{data:{to_level:'junior',source:'owner',rationale:'Strong start'}})).json()).id;
 await page.reload();await page.getByRole('button',{name:/^Family$/}).click();
 await page.locator('article[aria-label="Mia"] .bc-head').click();
 await page.getByText(/Waiting for you/).first().waitFor();
 await page.getByRole('button',{name:'Approve promotion'}).click();await page.getByText(/No permissions changed/).first().waitFor();
 assert.equal((await (await req.get(`${base}/api/career/${a}`)).json()).level,'junior');
 assert.ok(rid);

 // Council: off by default; the cost gate is real.
 await page.getByRole('tab',{name:'Family Council'}).click();
 const toggle=page.getByLabel('Allow council meetings');await toggle.waitFor();
 assert.equal(await toggle.isChecked(),false);
 assert.equal(await page.getByRole('button',{name:/Plan a meeting/}).isDisabled(),true);
 await toggle.click();await page.getByText('Saved.').waitFor();
 for(const name of ['Mia','Tom']) await page.getByRole('group',{name:/Council members/}).getByLabel(name).check();
 await page.getByRole('button',{name:'Save members'}).click();await page.getByText('Members saved.').waitFor();
 await page.getByLabel('Title').fill('Friday stand-up notes');await page.getByLabel('What should change, and why?').fill('Post a short summary every Friday.');
 await page.getByRole('button',{name:'Add proposal'}).click();await page.getByText('Proposal added.').waitFor();
 await page.getByRole('button',{name:/Plan a meeting/}).click();
 await page.getByRole('alert').filter({hasText:/no configured model price/}).waitFor();
 assert.equal((await req.put(base+'/api/budget/prices/smart',{data:{prompt:'1',completion:'2',max_prompt_tokens:16384,max_completion_tokens:512}})).status(),200);
 await page.getByLabel('Spending cap per meeting (USD)').fill('1');await page.getByRole('button',{name:'Save cap'}).click();await page.getByText('Saved.').waitFor();
 await page.getByRole('button',{name:/Plan a meeting/}).click();
 const plan=page.getByRole('group',{name:'Meeting cost'});await plan.waitFor();
 assert.match(await plan.innerText(),/Worst-case cost: \$0\.\d{4}/);assert.match(await plan.innerText(),/Mia, Tom/);
 await page.screenshot({path:path.join(shots,'family-council-desktop.png')});
 await plan.getByRole('button',{name:'Cancel'}).click();await page.getByText('Meeting cancelled.').waitFor();
 assert.equal((await (await req.get(base+'/api/council')).json()).meetings[0].status,'cancelled');
 await page.getByText('Friday stand-up notes').first().waitFor();

 // Mentorship: the mentor must outrank the trainee; training shows its worst-case cost first.
 await page.getByRole('tab',{name:'Mentorship'}).click();
 await page.getByRole('heading',{name:'No mentorships yet'}).waitFor();
 await page.getByLabel('Mentor',{exact:true}).selectOption(c);await page.getByLabel('Trainee').selectOption(b);
 await page.getByLabel(/Skill objectives/).fill('Proofreading');
 await page.getByRole('button',{name:'Start mentorship'}).click();
 await page.getByRole('alert').filter({hasText:/higher career level/}).waitFor();
 await page.getByLabel('Mentor',{exact:true}).selectOption(a);
 await page.getByRole('button',{name:'Start mentorship'}).click();await page.getByText('Mentorship started.').waitFor();
 const card=page.locator('article[aria-label="Mia mentors Tom"]');await card.waitFor();
 assert.match(await card.innerText(),/0 of 2 training missions completed/);
 assert.equal(await card.getByRole('button',{name:'Graduate'}).isDisabled(),true,'cannot graduate without demonstrated work');
 await card.getByRole('button',{name:'Start a training mission'}).click();
 await card.getByText(/Worst-case cost: \$0\.\d{4}/).waitFor();
 await page.screenshot({path:path.join(shots,'family-mentorship-desktop.png')});

 // Phone width: nothing overflows on any tab.
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(300);
 for(const tab of ['Mentorship','Family Council','Career Center']){await page.getByRole('tab',{name:tab}).click();await page.waitForTimeout(250);await noScroll(tab)}
 await page.screenshot({path:path.join(shots,'family-career-mobile.png')});
 assert.deepEqual(errors,[]);
 console.log('Family views passed: career center, owner-approved label-only promotion, council cost gate, mentorship rules, 390px.');
}finally{await browser.close()}
