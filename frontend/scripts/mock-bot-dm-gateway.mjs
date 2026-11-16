// Disposable fixture only; never use for a real installation.
import http from 'node:http';
http.createServer(async(req,res)=>{
 if(req.method!=='POST'||req.url!=='/v1/chat/completions'){res.writeHead(404).end();return}
 let raw='';for await(const chunk of req)raw+=chunk;const payload=JSON.parse(raw),last=payload.messages.filter(m=>m.role==='user').at(-1)?.content||'',afterTool=payload.messages.at(-1)?.role==='tool';let delta,finish='stop';
 if(last.startsWith('Write a direct message'))delta={content:'Sender asks the receiver for the fixture plan.'};
 else if(afterTool)delta={content:'Receiver replies after the tool review.'};
 else {delta={tool_calls:[{index:0,id:'dm-fixture',function:{name:'write_note',arguments:JSON.stringify({filename:'dm.txt',content:'Fixture DM note.'})}}]};finish='tool_calls'}
 res.writeHead(200,{'Content-Type':'text/event-stream'});for(const c of [{choices:[{delta,finish_reason:finish}]},{choices:[],usage:{prompt_tokens:200,completion_tokens:50}}])res.write('data: '+JSON.stringify(c)+'\n\n');res.end('data: [DONE]\n\n');
}).listen(Number(process.env.MOCK_PORT||8066),'0.0.0.0',()=>console.log('Disposable Bot DM gateway ready'));
