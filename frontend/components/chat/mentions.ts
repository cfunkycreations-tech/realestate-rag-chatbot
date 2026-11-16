export type Mention={kind:'bot'|'group'|'routine'|'connector';id:string;name:string};
export type Trigger={start:number;end:number;query:string};
export function mentionTrigger(text:string,cursor:number):Trigger|null{
 if(cursor<0||cursor>text.length)return null;
 const match=/(?:^|[\s(])@([^\s@{}]{0,80})$/u.exec(text.slice(0,cursor));
 return match?{start:cursor-match[1].length-1,end:cursor,query:match[1]}:null;
}
export function insertMention(text:string,trigger:Trigger,item:Mention){
 const safe=item.name.replace(/[}\r\n]/g,' ').trim().slice(0,160)||item.kind;
 const value=`@{${item.kind}:${item.id}|${safe}} `;
 return {text:text.slice(0,trigger.start)+value+text.slice(trigger.end),cursor:trigger.start+value.length};
}
export function displayMentions(text:string){return text.replace(/@\{(?:bot|group|routine|connector):[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\|([^}\r\n]{1,160})\}/g,'@$1')}
