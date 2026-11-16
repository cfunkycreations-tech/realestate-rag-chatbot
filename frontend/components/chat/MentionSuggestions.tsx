'use client';
import {useEffect,useState} from 'react';
import {flushSync} from 'react-dom';
import {insertMention,mentionTrigger,type Mention} from './mentions';
import type {RefObject,Dispatch,SetStateAction,KeyboardEvent} from 'react';

export function useMentionSuggestions(text:string,setText:Dispatch<SetStateAction<string>>,inputRef:RefObject<HTMLTextAreaElement|null>){
 const [cursor,setCursor]=useState(0),[items,setItems]=useState<Mention[]>([]),[index,setIndex]=useState(0),[dismissed,setDismissed]=useState(false),[focused,setFocused]=useState(false),[lookup,setLookup]=useState<string|undefined>(undefined);
 const trigger=mentionTrigger(text,cursor),query=trigger?.query;
 useEffect(()=>{if(query===undefined||dismissed||!focused)return;const ac=new AbortController();const timer=setTimeout(()=>{fetch('/api/mentions?q='+encodeURIComponent(query),{signal:ac.signal}).then(async response=>{if(!response.ok)throw Error('Could not load mentions');return response.json()}).then(data=>{if(!ac.signal.aborted){setItems(data);setLookup(query);setIndex(0)}}).catch(()=>{if(!ac.signal.aborted)setItems([])})},120);return()=>{clearTimeout(timer);ac.abort()}},[query,dismissed,focused]);
 const visible=!!trigger&&!dismissed&&focused&&lookup===query&&items.length>0;
 function choose(item:Mention){if(!trigger)return;const result=insertMention(text,trigger,item);flushSync(()=>{setText(result.text);setCursor(result.cursor);setItems([]);setLookup(undefined);setDismissed(false)});inputRef.current?.focus();inputRef.current?.setSelectionRange(result.cursor,result.cursor)}
 function keyDown(e:KeyboardEvent<HTMLTextAreaElement>){
  if(!visible)return false;
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();setIndex(i=>(i+(e.key==='ArrowDown'?1:-1)+items.length)%items.length);return true}
  if(e.key==='Escape'){e.preventDefault();setDismissed(true);return true}
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();choose(items[index]||items[0]);return true}
  return false;
 }
 return {visible,items,index,choose,keyDown,onChange:(position:number)=>{setCursor(position);setDismissed(false)},onSelect:(position:number)=>{setCursor(position);setDismissed(false)},onFocus:()=>setFocused(true),onBlur:()=>setFocused(false)};
}
export default function MentionSuggestions({items,index,onChoose}:{items:Mention[];index:number;onChoose:(item:Mention)=>void}){
 return <div className="skill-suggestions mention-suggestions" aria-label="Workspace mention suggestions"><p className="field-hint">Mentioning shares item metadata with this Bot’s model; it does not start work or authorize actions. Use arrows and Enter to select.</p>{items.map((item,i)=><button type="button" key={`${item.kind}:${item.id}`} className={i===index?'selected':''} onMouseDown={e=>e.preventDefault()} onClick={()=>onChoose(item)}><strong>@{item.name}</strong> · {item.kind}</button>)}</div>;
}
