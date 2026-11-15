// Disposable deterministic OpenAI-compatible gateway for tool E2E tests only.
import http from 'node:http';
const port=Number(process.env.MOCK_PORT||8030);
http.createServer(async(req,res)=>{
 if(req.method!=='POST'||req.url!=='/v1/chat/completions'){res.writeHead(404).end();return}
 let raw='';for await(const data of req)raw+=data;const payload=JSON.parse(raw);
 const lastUser=payload.messages.filter(m=>m.role==='user').at(-1)?.content||'';
 const hasTool=payload.messages.at(-1)?.role==='tool';
 const chunks=[];
 if(!hasTool){
  const isFetch=lastUser.includes('fetch loopback');
  const args=isFetch?{url:'http://127.0.0.1:8030/private'}:{filename:lastUser.includes('deny')?'denied.txt':'approved.txt',content:'A real approved fixture note.'};
  chunks.push({choices:[{delta:{tool_calls:[{index:0,id:'fixture-call',function:{name:isFetch?'web_fetch':'write_note',arguments:JSON.stringify(args)}}]},finish_reason:null}]});
  chunks.push({choices:[{delta:{},finish_reason:'tool_calls'}]});
 }else chunks.push({choices:[{delta:{content:'Fixture response after the tool result.'},finish_reason:'stop'}]});
 chunks.push({choices:[],usage:{prompt_tokens:200,completion_tokens:50}});
 res.writeHead(200,{'Content-Type':'text/event-stream'});for(const chunk of chunks)res.write('data: '+JSON.stringify(chunk)+'\n\n');res.end('data: [DONE]\n\n');
}).listen(port,'0.0.0.0',()=>console.log(`Disposable mock gateway listening on ${port}`));
