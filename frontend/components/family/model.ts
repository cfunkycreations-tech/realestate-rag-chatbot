// Pure display helpers for the Family Council, Career Center and Mentorship views.
// They only format values the backend counted; nothing is estimated or invented here.
export type Criterion={key:string;name:string;need:number;have:number|null;met:boolean};
export type Eligibility={level:string;target:string|null;eligible:boolean;criteria:Criterion[];reason?:string};
export type Vote={id:string;voter_name:string;vote:'approve'|'reject'|'abstain';rationale:string;evidence:{cited_missions_verified_to_exist:string[];cited_missions_discarded:number}};
export type Tally={approve:number;reject:number;abstain:number;members:number;quorum:number;quorum_met:boolean};
export type Proposal={id:string;title:string;body:string;kind:string;proposer:string;status:string;requires_owner:boolean;tally:Tally|null;rationale:string;votes:Vote[];created_at:number};

const LEVELS:Record<string,string>={trainee:'Trainee',junior:'Junior',specialist:'Specialist',senior:'Senior',lead:'Lead',principal:'Principal'};
export const levelLabel=(k:string)=>LEVELS[k]||k;
export const LEVEL_ORDER=['trainee','junior','specialist','senior','lead','principal'];

const STATUS:Record<string,string>={open:'Open',passed:'Passed (recommendation)',rejected:'Not approved',escalated:'Needs your decision',withdrawn:'Withdrawn',owner_approved:'You approved',owner_rejected:'You declined',
 planned:'Ready to start',running:'In session',done:'Finished',failed:'Failed',cancelled:'Stopped',pending:'Waiting for you',approved:'Approved',active:'Active',graduated:'Graduated',ended:'Ended'};
export const statusLabel=(s:string)=>STATUS[s]||s;

export function usd(value:string|null|undefined){
 if(value==null)return 'Not available';
 const n=Number(value);
 if(!Number.isFinite(n))return 'Not available';
 return n===0?'$0.00':n<1?`$${n.toFixed(4)}`:`$${n.toFixed(2)}`;
}
export const percent=(n:number|null|undefined)=>n==null?'No data yet':`${n}%`;

export function tallyText(t:Tally|null){
 if(!t)return 'No votes yet';
 const base=`${t.approve} for, ${t.reject} against, ${t.abstain} abstained`;
 return t.quorum_met?base:`${base}. No quorum (needs ${t.quorum} votes for or against)`;
}
export function eligibilityText(e:Eligibility,labels=levelLabel){
 if(!e.target)return 'Already at the highest level.';
 const missing=e.criteria.filter(c=>!c.met).length;
 return e.eligible?`Meets every requirement for ${labels(e.target)}. Needs your approval.`:`${missing} requirement${missing===1?'':'s'} still to meet for ${labels(e.target)}.`;
}
export function criterionText(c:Criterion){return `${c.name}: ${c.have==null?'no data':c.have} of ${c.need}`}
export function voteWord(v:string){return v==='approve'?'For':v==='reject'?'Against':'Abstained'}
