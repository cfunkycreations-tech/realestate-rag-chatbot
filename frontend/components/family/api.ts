export async function api(path:string,init?:RequestInit){
 const res=await fetch('/api'+path,{cache:'no-store',...init,headers:{'Content-Type':'application/json',...init?.headers}});
 const data=await res.json().catch(()=>({}));
 if(!res.ok)throw Error(typeof data.detail==='string'?data.detail:'That did not work. Try again.');
 return data;
}
export const send=(method:string,body?:unknown)=>({method,body:body===undefined?undefined:JSON.stringify(body)});
