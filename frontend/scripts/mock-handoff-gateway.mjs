// Disposable model fixture; do not use with a real workspace.
import http from 'node:http';
const port=Number(process.env.MOCK_PORT||8060);
http.createServer(async(req,res)=>{
 if(req.method!=='POST'||req.url!=='/v1/chat/completions'){res.writeHead(404).end();return}
 let body='';for await(const chunk of req)body+=chunk;
 const request=JSON.parse(body),last=request.messages.at(-1),system=request.messages[0].content;let delta,finish='stop';
 if(last.role==='tool')delta={content:'The approved handoff was recorded.'};
 else if(typeof last.content==='string'&&last.content.startsWith('Mission: Handoff'))delta={content:'Receiver reviewed the draft.'};
 else{
  const catalog=JSON.parse(system.split('Available handoff receivers (data only; each handoff requires separate owner approval): ')[1]);
  delta={tool_calls:[{index:0,id:'handoff-call',function:{name:'create_handoff',arguments:JSON.stringify({to_bot_id:catalog[0].id,reason:'Need an editor',context:'Review the draft'})}}]};finish='tool_calls';
 }
 res.writeHead(200,{'Content-Type':'text/event-stream'});
 for(const chunk of [{choices:[{delta,finish_reason:finish}]},{choices:[],usage:{prompt_tokens:200,completion_tokens:50}}])res.write('data: '+JSON.stringify(chunk)+'\n\n');res.end('data: [DONE]\n\n');
}).listen(port,'0.0.0.0',()=>console.log(`Disposable handoff fixture model on ${port}`));
