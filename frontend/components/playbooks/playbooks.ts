// Ten "What you get" playbooks. Every table, number and message below is SAMPLE OUTPUT shown to explain the idea; none of it is the owner's data.
export type Step={name:string;hint:string};
export type Playbook={
 id:string;n:string;name:string;icon:string;accent:string;
 head:[string,string,string?];sub:[string,string,string];  // headline: plain + accent (+ tail); subhead: before, bold, after
 pill:string;steps:Step[];
 runs:string;replaces:string;never:string;ruleLabel:string;rule:string;
 cron:string;brief:string;
 reality:{ready:boolean;text:string};
};

const S=(rows:[string,string][]):Step[]=>rows.map(([name,hint])=>({name,hint}));

export const PLAYBOOKS:Playbook[]=[
 {id:'second-brain',n:'01',name:'Second Brain',icon:'brain',accent:'#8ec5ff',head:['Saved once. ','Found when it matters.'],sub:['Send it anything you save. It reads it in full, links it by idea and ','brings it back',' when you work on that topic.'],pill:'LINKING',
  steps:S([['Capture','links, PDFs'],['Read','in full'],['Store','one record'],['Link','by idea'],['Conflicts','flag them'],['Surface','when relevant'],['Review','weekly'],['Answer','with links']]),
  runs:'always on, weekly review',replaces:'a notes app you never update',never:'shares your notes',ruleLabel:'CAPTURES',rule:'links, posts, PDFs, notes, voice memos',cron:'0 9 * * 1',
  brief:'You are my Second Brain. Each week, read the notes and saved material I give you in full, store each item once, link items by idea (not keyword), flag any that contradict each other, and write a weekly review: how many items you read, the 3 best ideas, and duplicates. When I ask a question, answer from my saved items first and cite each one; say so if you had to look elsewhere. Never share my notes outside this app.',
  reality:{ready:true,text:'Works today with Notes and learned memory. Paste or attach what you want kept; nothing is fetched on its own.'}},
 {id:'build-agent',n:'02',name:'Build-Anything Agent',icon:'build',accent:'#7ee0c3',head:['It proves it works ','before',' it hands it over'],sub:['Describe a tool in plain words. It asks 5 questions, writes a spec you approve and ','shows a real run',' before it hands over.'],pill:'CHECKING',
  steps:S([['Describe','plain words'],['Ask','5 questions'],['Spec','1 page'],['Build','smallest version'],['Test','real input'],['Prove','real output'],['Fix','max 3 loops'],['Hand over','3-step run']]),
  runs:'on demand',replaces:'a contract dev for small tools',never:'deploys or spends without OK',ruleLabel:'THE RULE',rule:'max 3 fix loops, then it says what broke',cron:'0 10 * * 1',
  brief:'You build small tools. When I describe one, first ask me exactly 5 questions (inputs, outputs, who uses it, where it runs, what done means), then write a one-page spec and wait for my approval before writing any code. Build the smallest working version, test it on real input, and show me a real run. Fix failures at most 3 times, then explain what broke. Hand over with a 3-step how-to-run, a known limit and a next feature. Never deploy anything or spend money without my approval.',
  reality:{ready:true,text:'Works today with missions and the offline computer workspace. Each command still needs your approval.'}},
 {id:'swarm',n:'03',name:'Funk Swarm',icon:'swarm',accent:'#ff9a7a',head:['One orchestrator. ','A team of bots.'],sub:['One orchestrator splits your question into tasks, runs ','up to 10 bots in parallel',' and merges their work into one report.'],pill:'RUNNING',
  steps:S([['Goal','one question'],['Plan','split tasks'],['Spawn','up to 10'],['Brief','one job each'],['Run','in parallel'],['Ledger','claim + source'],['Reconcile','show conflicts'],['Report','answer first']]),
  runs:'on demand, up to 10 agents',replaces:'a small research team',never:'hides a disagreement',ruleLabel:'THE RULE',rule:'conflicts are shown, never averaged',cron:'0 9 * * 5',
  brief:'You are the orchestrator of a research swarm. Take my one question, split it into at most 10 tasks, and give each helper a single brief: the one thing it answers, the only sources it may read, the format (claim, source, confidence) and a deadline. Keep a ledger of every claim with its source and confidence. Re-check the top 10 claims against their sources. Where helpers disagree, show both and never average them. Report answer first, then evidence, open conflicts and next steps.',
  reality:{ready:true,text:'Works today with multi-Bot missions and handoffs. Every helper uses its own Bot, budget and tool approvals.'}},
 {id:'morning-brief',n:'04',name:'Morning Brief',icon:'sun',accent:'#f4c46a',head:['Everything since last night, ','on one page'],sub:['Email takes ','28% of the workweek',' and searching another ~20%. One page at 07:30 takes the first chunk back.'],pill:'RANKING',
  steps:S([['Sources','inbox, chats'],['Read','since last brief'],['Calendar','today'],['Owed','both ways'],['Stale','3+ days'],['Rank','decide first'],['Write','one page'],['Deliver','07:30']]),
  runs:'every day at 07:30',replaces:'a chief of staff\'s morning',never:'replies or accepts for you',ruleLabel:'THE NUMBER',rule:'~19 of 40 hours on email and searching',cron:'30 7 * * *',
  brief:'Every morning, write me one page from the material I give you since the last brief. Order it: 1 Decide (what is waiting on me), 2 Reply (who is waiting and how many days), 3 Meetings today (flag back-to-back or missing agendas), 4 Owed to me, 5 News (one line and a link each for my topics). If nothing is new, answer with exactly two words: clear morning. Never reply to, accept or decline anything for me.',
  reality:{ready:false,text:'Needs a source: it reads what you paste or attach, or what a connector you add provides. Funk Bot does not read your inbox by itself.'}},
 {id:'repurposer',n:'05',name:'Content Repurposer',icon:'loop',accent:'#ff9fb8',head:['Your best ideas, ','14 days of drafts'],sub:['It pulls your outlier posts and rewrites each idea natively for X, LinkedIn, Threads and Instagram, ','inside each limit.',''],pill:'ADAPTING',
  steps:S([['Source','top 10 posts'],['Read','in full'],['Extract','10 ideas'],['Dedupe','no repeats'],['Adapt','per platform'],['Fit','size limits'],['Calendar','14 days'],['Approve','you post']]),
  runs:'weekly, 14 days ahead',replaces:'a repurposing freelancer',never:'publishes anything',ruleLabel:'THE NUMBER',rule:'7 platforms, 280 to 5,000 characters',cron:'0 9 * * 1',
  brief:'Each week, take the top posts I give you, read them in full, extract up to 10 distinct ideas, drop repeats, and rewrite each idea natively for X (280 characters), LinkedIn (3,000), Threads (500) and Instagram (2,200, hook plus carousel). Lay them out as a 14-day calendar and mark the strongest. Check every draft fits its limit. Never publish or schedule anything; I post.',
  reality:{ready:false,text:'Needs your posts pasted or attached. It drafts only; publishing to any platform is not built and never happens without you.'}},
 {id:'subscription-auditor',n:'06',name:'Subscription Auditor',icon:'wallet',accent:'#ffab6e',head:['$1,086 a year in subscriptions. ','$690 to save.'],sub:['People guess they spend ','$86 a month',' on subscriptions and pay $219. It finds every charge in one pass of your inbox.'],pill:'AUDITING',
  steps:S([['Inbox','12 months'],['Find','every charge'],['Normalize','per year'],['Usage','used or not'],['Drift','price hikes'],['Rank','by cost'],['Draft','cancel notes'],['Approve','you decide']]),
  runs:'monthly',replaces:'a yearly money audit',never:'cancels or pays by itself',ruleLabel:'THE NUMBER',rule:'$86 guessed vs $219 paid each month',cron:'0 9 1 * *',
  brief:'Once a month, go through the receipts and statements I give you for the last 12 months. List every recurring charge, normalise it to a yearly cost, note whether I used it, flag price increases, rank by cost, and give a verdict: keep, cancel or downgrade. Draft a short cancellation note for each cancel, with a reply to a likely retention offer. Show the total and what I would save. Never cancel, pay or contact anyone yourself.',
  reality:{ready:false,text:'Needs receipts or statements you paste or attach. It never gets into your bank or email on its own, and it cancels nothing.'}},
 {id:'group-chat-manager',n:'07',name:'Group Chat Manager',icon:'chat',accent:'#b9a2ff',head:['412 messages in. ','6 items out.'],sub:['The average workday has ','275 interruptions.',' It reads Telegram, Discord, Slack and WhatsApp and sends you two digests.'],pill:'READING',
  steps:S([['Connect','pick groups'],['Read','everything'],['Filter','signal only'],['Dedupe','once per item'],['Weigh','key people first'],['Draft','replies'],['Digest','twice a day'],['Mute','the rest']]),
  runs:'digests at 09:00 and 18:00',replaces:'reading every group chat',never:'sends without your OK',ruleLabel:'THE NUMBER',rule:'275 interruptions in an average workday',cron:'0 9,18 * * *',
  brief:'Twice a day, read the group-chat text I give you, drop noise, merge repeats so the same news appears once, and weigh messages from my key people first. Send me a digest of the items that matter, each tagged REPLY, DEADLINE, DECISION, DATA or FYI. For anything that needs my reply, draft one short reply for me to approve, edit or skip. Never send a message yourself.',
  reality:{ready:false,text:'Needs the chat text pasted or attached. Reading Telegram, Discord, Slack or WhatsApp directly is not built.'}},
 {id:'lead-builder',n:'08',name:'Lead List Builder',icon:'target',accent:'#d7ee6a',head:['50 leads. ','Each one with proof.'],sub:['Every lead comes with a public, dated signal and a link to prove it. ','No evidence, no row.',' It stops at 50 qualified leads.'],pill:'VERIFYING',
  steps:S([['ICP','who to find'],['Search','matching companies'],['Validate','real signal'],['Enrich','right person'],['Dedupe','one row each'],['Score','fit + timing'],['Draft','4-line opener'],['Stop','at 50']]),
  runs:'on demand, stops at 50',replaces:'hours of manual prospecting',never:'guesses emails or sends',ruleLabel:'ASKS ONCE',rule:'offer, role, size, region, 3 fit signals',cron:'0 9 * * 1',
  brief:'Build a lead list. First confirm my offer, target role, company size, region and 3 fit signals. Search public sources only. Keep a lead only if it has a public, dated signal with a link; no evidence means no row. Name the person by role from public contact information only; never guess an email address. Remove duplicates, score fit and timing, stop at 50 qualified leads, and report how many were found and dropped and why. Draft a 4-line opener for each but never send anything.',
  reality:{ready:true,text:'Works today with web search and page fetching, which stay owner-approved and limited to the sites you allow.'}},
 {id:'competitor-monitor',n:'09',name:'Competitor Monitor',icon:'eye',accent:'#8aa8ff',head:['Only what moved ','this week'],sub:['It snapshots every rival once, then checks pricing pages, changelogs and job boards against that baseline ','every day.',''],pill:'DIFFING',
  steps:S([['List','5-10 rivals'],['Sources','site, price, jobs'],['Baseline','first snapshot'],['Watch','every day'],['Diff','only changes'],['Score','high / low'],['Report','weekly table'],['Silence','no padding']]),
  runs:'daily check, weekly report',replaces:'a market analyst\'s weekly',never:'pads a slow week',ruleLabel:'ASKS ONCE',rule:'5-10 competitors, then finds every source',cron:'0 8 * * *',
  brief:'Monitor my competitors. Ask me once for 5 to 10 rivals, then find each one\'s pricing page, changelog and job board. Take a baseline snapshot the first time, then check each source daily and record only real changes. Each Friday report a table: who, type, what, before and after, impact (high, medium, low) and source link, followed by one-sentence implications for us. If a rival did nothing material, list them in one line. Never pad a slow week.',
  reality:{ready:true,text:'Works today with approved web fetching of the pages you allow and a daily routine. It compares against the last snapshot it saved.'}},
 {id:'x-assistant',n:'10',name:'Personal X Assistant',icon:'bird',accent:'#c3b6ff',head:['Your queue at ','08:00','. Approve, edit or kill.'],sub:['Your researcher, writer and hook specialist for X. It learns your voice from your last 50 posts and hands you ','one queue a day.',''],pill:'DRAFTING',
  steps:S([['Voice','learn my style'],['Scan','20 accounts'],['Hooks','reply openings'],['Draft','3 posts'],['Triage','DMs + mentions'],['Track','what won'],['Queue','one list'],['Approve','I post']]),
  runs:'daily at 08:00',replaces:'a social media assistant',never:'posts, replies or DMs for you',ruleLabel:'ASKS ONCE',rule:'niche, 20 accounts, posting times, 3 best posts',cron:'0 8 * * *',
  brief:'Every morning at 08:00, hand me one queue. Learn my voice from the last 50 posts I give you. Draft 3 posts in that voice, each with its angle (outlier, my own winner with a new angle, or trending in my niche), under 280 characters and without hashtags. Draft reply openings that add a point, never just "great post". Sort the DMs and mentions I give you into needs me, reply drafted and ignore, with deals and press first. Report which posts beat my median and the pattern. Never post, reply or send a DM yourself.',
  reality:{ready:false,text:'Needs your posts and mentions pasted or attached. Reading or posting to X is not built; you copy approved drafts yourself.'}},
];

export function headline(p:Playbook){return p.head}
export const hasEverything=(p:Playbook)=>p.steps.length===8&&Boolean(p.runs&&p.replaces&&p.never&&p.rule&&p.ruleLabel);
