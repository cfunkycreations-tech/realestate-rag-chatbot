'use client';
import {useState} from 'react';
import CouncilPanel from './CouncilPanel';
import CareerCenter from './CareerCenter';
import MentorshipPanel from './MentorshipPanel';
import type {TeamBot} from '../team/TeamDashboard';

const TABS=[['council','Family Council'],['careers','Career Center'],['mentorship','Mentorship']] as const;
type Tab=typeof TABS[number][0];

export default function FamilyView({bots}:{bots:TeamBot[]}){
 const [tab,setTab]=useState<Tab>('careers');
 return <div className="missions-view family-view"><header className="missions-heading"><div><p className="eyebrow">YOUR AI FAMILY</p><h1>Family</h1><p>Careers, mentors and the council. Levels are labels, votes are recommendations, and you stay in charge of every permission, budget and secret.</p></div></header>
  <div className="bc-tabs" role="tablist" aria-label="Family sections">{TABS.map(([key,label])=><button key={key} type="button" role="tab" id={`fam-tab-${key}`} aria-selected={tab===key} aria-controls="fam-body" className={tab===key?'active':''} onClick={()=>setTab(key)}>{label}</button>)}</div>
  <div id="fam-body" role="tabpanel" aria-labelledby={`fam-tab-${tab}`}>{tab==='council'?<CouncilPanel bots={bots}/>:tab==='careers'?<CareerCenter bots={bots}/>:<MentorshipPanel bots={bots}/>}</div>
 </div>;
}
