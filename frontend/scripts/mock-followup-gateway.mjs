// Test-only deterministic mock model. Never use as a production gateway.
import http from 'node:http';
const port=Number(process.env.MOCK_PORT||8042);
http.createServer(async(req,res)=>{
 if(req.method!=='POST'||req.url!=='/v1/chat/completions'){res.writeHead(404).end();return}
 let raw='';for await(const part of req)raw+=part;const payload=JSON.parse(raw);const hasTool=payload.messages.at(-1)?.role==='tool';const chunks=[];
 if(!hasTool){const args={summary:'Finish the fixture research',due:new Date(Date.now()+12000).toISOString()};chunks.push({choices:[{delta:{tool_calls:[{index:0,id:'followup',function:{name:'create_followup',arguments:JSON.stringify(args)}}]},finish_reason:null}]});chunks.push({choices:[{delta:{},finish_reason:'tool_calls'}]})}
 else chunks.push({choices:[{delta:{content:'Follow-up recorded.'},finish_reason:'stop'}]});
 chunks.push({choices:[],usage:{prompt_tokens:200,completion_tokens:50}});res.writeHead(200,{'Content-Type':'text/event-stream'});for(const chunk of chunks)res.write('data: '+JSON.stringify(chunk)+'\n\n');res.end('data: [DONE]\n\n');
}).listen(port,'0.0.0.0',()=>console.log(`Disposable follow-up gateway listening on ${port}`));
