// One guided demo per function of the app. EVERYTHING here is SAMPLE content shown to explain the idea.
// Nothing in a demo calls a model, spends money, or touches the owner's real data.
export type Row={k:'you'|'bot'|'do'|'ok'|'hold'|'stat'|'note';who?:string;t:string};
export type DemoStep={name:string;say:string;rows:Row[]};
export type Demo={id:string;name:string;group:'Team'|'Work'|'Automation'|'Control';accent:string;line:string;open:{label:string;view?:string;settings?:string};steps:DemoStep[]};

const you=(t:string):Row=>({k:'you',t}),bot=(who:string,t:string):Row=>({k:'bot',who,t}),doing=(t:string):Row=>({k:'do',t}),ok=(t:string):Row=>({k:'ok',t});
const hold=(t:string):Row=>({k:'hold',t}),stat=(t:string):Row=>({k:'stat',t}),note=(t:string):Row=>({k:'note',t});
const S=(name:string,say:string,...rows:Row[]):DemoStep=>({name,say,rows});

export const DEMOS:Demo[]=[
 {id:'office',name:'Office',group:'Team',accent:'#7ee0c3',line:'A live window into your team: who is working, who is idle, what just happened.',open:{label:'Open the Office',view:'office'},steps:[
  S('See the team','Every Bot appears as a character. Busy ones move; idle ones wait.',stat('Mia · working'),stat('Tom · idle'),stat('Ava · idle')),
  S('Work starts','When you give a Bot a task, its card changes to working.',you('Mia, summarise this week’s notes.'),doing('Mia started a run')),
  S('Real events only','The activity feed shows recorded events, never invented ones.',ok('09:24 Mia finished a run'),note('Nothing appears here unless it really happened.')),
  S('Open anyone','Click a Bot to chat or give it a mission.',bot('Mia','Done. Three themes this week, with the notes that back each one.'))]},
 {id:'roster',name:'Roster & chat',group:'Team',accent:'#8ec5ff',line:'Talk to one Bot at a time, with its own memory and chat threads.',open:{label:'Open the Roster',view:'roster'},steps:[
  S('Pick a Bot','Your Bots are listed on the left. Search to find one.',stat('13 Bots · search “research”')),
  S('Ask','Type a message. Attach files if you want the Bot to read them.',you('Can you compare these two quotes?')),
  S('It works, you watch','The answer streams in. Anything risky pauses for your approval first.',bot('Riff','Quote B is $420 cheaper but drops the warranty. Want a table?'),hold('Waiting for you: send this comparison by email?')),
  S('Threads and memory','Each chat is a thread. A Bot can learn facts you tell it to keep.',ok('Remembered: “Prefers short answers.”'))]},
 {id:'gallery',name:'Gallery',group:'Team',accent:'#c9a8ff',line:'Your Bots as cards with their sprite, status and last activity.',open:{label:'Open the Gallery',view:'gallery'},steps:[
  S('Browse','Cards show the sprite, name, job and a real status light.',stat('Bassbeard · Chief of Staff'),stat('Goldie · Community Manager')),
  S('Status is real','A green light means a run is active; grey means idle.',stat('● Riff — run active'),stat('○ Jivewave — idle')),
  S('Open or manage','Click a card for the spotlight chat, or use the card menu.',doing('Spotlight: Riff'))]},
 {id:'missions',name:'Missions',group:'Work',accent:'#f4c46a',line:'Bigger jobs with an owner, steps, approvals and a clear finish.',open:{label:'Open Missions',view:'missions'},steps:[
  S('Create','Describe the outcome and pick who does it.',you('Research three competitors and draft a one-page comparison.')),
  S('It runs','The Bot works through it. You can watch each step.',doing('Step 1: collect public facts'),doing('Step 2: draft the page')),
  S('You approve','Anything that sends, spends or changes something waits for you.',hold('Approve: save draft to Notes?')),
  S('Finish','The mission is marked done with its result attached.',ok('Done. Comparison saved.'))]},
 {id:'group-chats',name:'Group chats',group:'Team',accent:'#ff9a7a',line:'Several Bots and you in one conversation, each in their own role.',open:{label:'Open Group chats',view:'group-chats'},steps:[
  S('Make a group','Choose the Bots and give the group a purpose.',stat('Launch team: Riff, Goldie, Jivewave')),
  S('Ask the room','Post once; each Bot answers from its own job.',you('Is the launch ready?'),bot('Riff','Research is done.'),bot('Goldie','Community post is drafted.')),
  S('Disagreement is shown','If two Bots differ, you see both; nothing is averaged.',bot('Jivewave','Analytics says Friday beats Monday.'),note('Different from Goldie’s Monday plan, so both are shown.'))]},
 {id:'bot-dms',name:'Bot DMs',group:'Team',accent:'#b7e07e',line:'Bots message each other; you can read every message.',open:{label:'Open Bot DMs',view:'bot-dms'},steps:[
  S('A Bot asks a peer','One Bot can ask another for help.',bot('Mia','Riff, can you check these figures?')),
  S('The reply','The other Bot answers in the same thread.',bot('Riff','Two of the five are off. Details attached.')),
  S('You can read it','Every DM is visible to you. Messages never raise anyone’s permissions.',note('Visible to you. Grants no new access.'))]},
 {id:'family',name:'Family (careers, council, mentoring)',group:'Team',accent:'#a5f3d0',line:'Bots with careers, mentors and a council that recommends, never overrides you.',open:{label:'Open Family',view:'family'},steps:[
  S('Hire by career','Pick a role; the Bot gets the role’s starting instructions.',you('Hire: Operations Analyst'),ok('New Bot created with its career')),
  S('Mentoring','A senior Bot can coach a junior one with training missions.',doing('Training mission: weekly report')),
  S('Council','Bots can propose changes. Votes are advice only.',bot('Riff','Proposal: weekly review on Fridays.'),hold('Needs your decision. Nothing changed yet.')),
  S('Limits stay yours','Rank, tier or votes never raise spending or security authority.',note('Budgets and approvals stay exactly as you set them.'))]},
 {id:'cockpit',name:'Cockpit',group:'Control',accent:'#8ec5ff',line:'One screen of real numbers: Bots, missions, spending, approvals.',open:{label:'Open the Cockpit',view:'cockpit'},steps:[
  S('Workforce','Counts come from your own records.',stat('BOTS CONFIGURED 13'),stat('MISSIONS 2 active · 4 done')),
  S('Spending','Spent today and this month against your caps.',stat('SPENT TODAY $0.31 of $5.00'),stat('THIS MONTH $4.12')),
  S('Click a tile','Each tile opens the section behind it.',doing('MISSIONS → opens Missions')),
  S('Honest gaps','A source that is not connected says so and shows nothing.',note('Gumroad: Not connected. No figures shown.'))]},
 {id:'playbooks',name:'Playbooks',group:'Work',accent:'#f4c46a',line:'Ten ready-made ways to use your team, each with a paused routine you review.',open:{label:'Open Playbooks',view:'playbooks'},steps:[
  S('Choose a playbook','Each page shows what it does in 8 steps.',stat('02 Build-Anything Agent')),
  S('Pick a Bot','Choosing a Bot only changes the picture.',stat('Bot for this playbook: Mia')),
  S('Set up','Creates a routine that starts PAUSED.',doing('Routine created (paused)')),
  S('You review','Nothing runs until you resume it.',hold('Paused. Resume when you are ready.'))]},
 {id:'projects',name:'Projects',group:'Work',accent:'#7ee0c3',line:'Group files, notes and missions around one goal.',open:{label:'Open Projects',view:'projects'},steps:[
  S('Start a project','Name it and set the goal.',you('Project: Spring launch')),
  S('Attach work','Missions, notes and files live together.',stat('3 missions · 5 notes · 2 files')),
  S('See progress','Status rolls up from the real missions inside.',ok('2 of 3 missions done'))]},
 {id:'analytics',name:'Analytics',group:'Control',accent:'#8ec5ff',line:'Usage and cost per Bot, per day, from recorded runs.',open:{label:'Open Analytics',view:'analytics'},steps:[
  S('Usage','Runs, tokens and cost are counted from real records.',stat('Runs this week: 41'),stat('Tokens: 182k')),
  S('By Bot','See which Bot used what.',stat('Riff $0.18 · Mia $0.09 · Tom $0.04')),
  S('Unknown stays unknown','If a provider gave no price, it says so instead of guessing.',note('Cost unknown for 2 runs.'))]},
 {id:'lab',name:'Lab',group:'Work',accent:'#ff9a7a',line:'Try an instruction change on a Bot and compare before you keep it.',open:{label:'Open the Lab',view:'lab'},steps:[
  S('Pick a Bot and a change','Write a new version of the instructions.',you('Try: “Answer in three bullets.”')),
  S('Run the test','The same prompts run with the old and new text.',doing('Old vs new on 3 test prompts')),
  S('Compare','You read both results side by side.',bot('Old','A long paragraph…'),bot('New','• Point one • Point two • Point three')),
  S('Apply or not','Applying saves the old text too, so you can restore it.',ok('Applied. Previous version kept.'))]},
 {id:'skills',name:'Skills',group:'Work',accent:'#c9a8ff',line:'Reusable know-how you can give to any Bot.',open:{label:'Open Skills',view:'skills'},steps:[
  S('Write a skill','A skill is a saved set of instructions.',you('Skill: “Weekly report format”')),
  S('Give it to a Bot','Attach it to the Bots that should use it.',ok('Attached to Mia')),
  S('It is used','The Bot follows the skill when it fits.',bot('Mia','Using your weekly report format.'))]},
 {id:'routines',name:'Routines',group:'Automation',accent:'#b7e07e',line:'Work that repeats on a schedule, with approval where it matters.',open:{label:'Open Routines',view:'routines'},steps:[
  S('Schedule','Pick the Bot, the instructions and when.',you('Every Monday 9:00: summarise last week.')),
  S('It fires','At the time, a run starts by itself.',doing('Monday 09:00 · run started')),
  S('Approval','Risky steps wait in your Inbox.',hold('Needs approval: send the summary?')),
  S('Pause anytime','One switch pauses a routine.',ok('Paused by you.'))]},
 {id:'workflows',name:'Workflows',group:'Automation',accent:'#7ee0c3',line:'Chain steps across Bots: one finishes, the next begins.',open:{label:'Open Workflows',view:'workflows'},steps:[
  S('Design the chain','Step 1 research, step 2 draft, step 3 review.',stat('Research → Draft → Review')),
  S('Run it','Each step hands its result to the next.',doing('Research done'),doing('Draft running')),
  S('See health','Success rate comes from real runs.',stat('Last 7 days: 9 ok · 1 failed'))]},
 {id:'inbox',name:'Inbox & approvals',group:'Control',accent:'#ff9a7a',line:'Everything waiting on you, in one place.',open:{label:'Open the Inbox',view:'inbox'},steps:[
  S('Things arrive','Approvals, follow-ups and notices land here.',hold('Tool request: write file report.md'),note('Follow-up due: call vendor')),
  S('Decide','Approve or decline. Declining costs nothing.',ok('Approved once')),
  S('It continues','The Bot carries on after your answer.',bot('Mia','File saved.'))]},
 {id:'vault',name:'Character Vault',group:'Team',accent:'#c9a8ff',line:'Sprites and characters for your Bots, kept separate from their careers.',open:{label:'Open the Vault',settings:'vault'},steps:[
  S('Import','Add characters from a pack.',stat('361 characters imported')),
  S('Assign','Give a Bot a sprite; its name can come from the character.',ok('Riff II ← “Riff”')),
  S('Clean up','Purge unused sprites in one click; sprites in use are kept.',note('Purge removes 330 available, keeps 31 in use.'))]},
 {id:'budget',name:'Budget & Economy',group:'Control',accent:'#f4c46a',line:'Daily and monthly caps, alerts, and cheaper models when you want them.',open:{label:'Open Budget',settings:'budget'},steps:[
  S('Set caps','A daily and monthly limit for the account and each Bot.',stat('Daily $5.00 · Monthly $60.00')),
  S('Every run is reserved','Before a run, its maximum cost is reserved. Over the cap: it does not start.',hold('Blocked: would exceed today’s cap.')),
  S('Economy mode','Optionally cap the model tier to save money.',ok('Economy on: Standard ceiling')),
  S('Alerts','You are warned at thresholds.',note('80% of today’s cap used.'))]},
 {id:'models',name:'Models & pin',group:'Control',accent:'#8ec5ff',line:'Choose a model profile, or pin one exact model to a Bot.',open:{label:'Open model profiles',settings:'profiles'},steps:[
  S('Profiles','Five profiles map to models you choose in Settings.',stat('smart → your chosen model')),
  S('Pin a model','In Edit identity, pin one exact model to one Bot.',you('Mia → vendor/my-model')),
  S('Your limits still win','Caps and the Economy ceiling still apply to a pinned Bot.',note('Pinned Bot lowered to the ceiling if it is set.'))]},
 {id:'connectors',name:'Connectors',group:'Automation',accent:'#7ee0c3',line:'Let Bots use outside services through tools you approve.',open:{label:'Open Connectors',settings:'connectors'},steps:[
  S('Add one','Give it a name and address. Keys stay on the server.',stat('GitHub · enabled')),
  S('Allow tools','Choose which tools Bots may call.',ok('Allowed: list_issues')),
  S('Each call asks','Calls still follow your approval setting.',hold('Approve: list_issues on my repo?'))]},
 {id:'computer',name:'Computer workspace',group:'Work',accent:'#c9a8ff',line:'An offline sandbox where Bots can run commands, with you in control.',open:{label:'Open Office (computer controls)',view:'office'},steps:[
  S('Sandbox','Bots work in an isolated computer with no internet.',stat('Computer idle · offline sandbox')),
  S('Command asks','Each command waits for your approval.',hold('Run: python report.py ?')),
  S('Stop anytime','Stop computer or the kill switch halts it.',ok('Stopped.'))]},
 {id:'evaluations',name:'Evaluations',group:'Team',accent:'#a5f3d0',line:'Free, rule-based checks on each Bot. Certifications are labels only.',open:{label:'Open Evaluations',view:'family'},steps:[
  S('Evaluate','One click runs checks on every Bot. No model calls, $0.00.',doing('2 Bots evaluated · Cost $0.00')),
  S('Results','Each Bot shows passed or failed checks, with evidence.',stat('Instruction compliance: Passed')),
  S('Certification label','A label like “Competent” is shown from the results.',note('A label never raises any limit.')),
  S('Restore instructions','Every edit saves the old text; restore it any time.',ok('Restored. The replaced text was saved too.'))]},
 {id:'backup',name:'Backup & restore',group:'Control',accent:'#b7e07e',line:'Download a backup of your workspace and restore it later.',open:{label:'Open Backup',settings:'backup'},steps:[
  S('Back up','Download everything as one file.',ok('funkbot-backup.tar created')),
  S('Upgrades back up too','UPGRADE.bat saves your data volumes before it changes anything.',note('Volumes copied to _volume_backups.')),
  S('Restore','Restore into a fresh install if you need to.',ok('Restored.'))]},
 {id:'safety',name:'Pause, stop & kill switch',group:'Control',accent:'#ff9a7a',line:'You can halt everything instantly.',open:{label:'Open the Office',view:'office'},steps:[
  S('Pause all Bots','Blocks new work until you resume.',hold('All Bots paused.')),
  S('Stop computer','Ends the sandbox session.',ok('Computer stopped.')),
  S('Kill switch','Cuts off Bot tool use at once.',ok('Kill switch on. Nothing can act.'))]},
];
