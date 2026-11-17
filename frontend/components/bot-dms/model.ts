// Pure display helpers for Bot-started conversations. Real recorded values only; nothing is guessed.
export type Usage={prompt_tokens:number;completion_tokens:number;usd:string;unverified_rounds:number;model_rounds:number;basis:string};
export type Thread={dm_id:string;subject:string;initiator_id:string|null;initiator_name:string|null;receiver_id:string|null;receiver_name:string|null;kind:string;mission_id:string|null;mission_title:string|null;project_id:string|null;status:string;error:string|null;messages_sent:number;outcome:string|null;usage:Usage;updated_at:number};
export type Refused={sender_id:string|null;receiver_id:string|null;kind:string;detail:string|null;created_at:number};

const KINDS:Record<string,string>={request_help:'Asked for help',ask_question:'Asked a question',share_finding:'Shared a finding',request_review:'Requested a review',escalate_blocker:'Escalated a blocker',recommend_collaborator:'Recommended a collaborator',coordinate_task:'Coordinated a task',request_mentorship:'Asked for mentorship',nominate_colleague:'Nominated a colleague',resolve_disagreement:'Asked to resolve a disagreement'};
export const kindLabel=(k:string)=>KINDS[k]||k.split('_').join(' ');
const STATUS:Record<string,string>={queued:'Waiting',running:'In progress',done:'Answered',failed:'Failed',cancelled:'Stopped',unknown:'Unknown'};
export const statusLabel=(s:string)=>STATUS[s]||s;
export const isLive=(s:string)=>s==='queued'||s==='running';
export function costLabel(u:Usage){
 const n=Number(u.usd);
 const base=Number.isFinite(n)?(n===0&&u.model_rounds===0?'No model use yet':`$${n<1?n.toFixed(4):n.toFixed(2)}`):'Unavailable';
 return u.unverified_rounds?`${base} + ${u.unverified_rounds} unverified`:base;
}
export function tokenLabel(u:Usage){return u.model_rounds===0?'No tokens recorded':`${u.prompt_tokens.toLocaleString('en-US')} in · ${u.completion_tokens.toLocaleString('en-US')} out`}
export function outcomeLabel(t:Thread){
 if(t.status==='done')return t.outcome?`Reply: ${t.outcome}`:'Answered';
 if(t.status==='failed'||t.status==='cancelled')return t.error||statusLabel(t.status);
 return isLive(t.status)?'Waiting for the reply…':'';
}
