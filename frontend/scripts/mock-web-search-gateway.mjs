// Mock model only. The browser test denies the search so no external search server is contacted.
import http from 'node:http';
http.createServer(async(req,res)=>{
 if(req.method!=='POST'||req.url!=='/v1/chat/completions'){res.writeHead(404).end();return}
 let raw='';for await(const chunk of req)raw+=chunk;const payload=JSON.parse(raw),afterTool=payload.messages.at(-1)?.role==='tool';const delta=afterTool?{content:'The search was reviewed.'}:{tool_calls:[{index:0,id:'fixture-search',function:{name:'web_search',arguments:JSON.stringify({query:'fixture local housing trends'})}}]};
 res.writeHead(200,{'Content-Type':'text/event-stream'});for(const c of [{choices:[{delta,finish_reason:afterTool?'stop':'tool_calls'}]},{choices:[],usage:{prompt_tokens:200,completion_tokens:50}}])res.write('data: '+JSON.stringify(c)+'\n\n');res.end('data: [DONE]\n\n');
}).listen(Number(process.env.MOCK_PORT||8068),'0.0.0.0',()=>console.log('Disposable search model ready'));
