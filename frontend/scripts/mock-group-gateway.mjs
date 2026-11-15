// Disposable deterministic gateway for group browser tests only.
import http from 'node:http';
const port=Number(process.env.MOCK_PORT||8031);
http.createServer(async(req,res)=>{
 if(req.method!=='POST'||req.url!=='/v1/chat/completions'){res.writeHead(404).end();return}
 let raw='';for await(const data of req)raw+=data;const payload=JSON.parse(raw),last=payload.messages.filter(m=>m.role==='user').at(-1)?.content||'',hasTool=payload.messages.at(-1)?.role==='tool';let delta,finish='stop';
 if(last.startsWith('You are Chief of Staff')){const roster=JSON.parse(last.split('\nBots: ')[1].split('\nMission: ')[0]);delta={content:JSON.stringify({tasks:roster.map(bot=>({bot_id:bot.id,instructions:'Research the fixture question'}))})}}
 else if(last.startsWith('Synthesize the following'))delta={content:'Chief synthesis of the actual member reply.'};
 else if(hasTool)delta={content:'Member completed the fixture research.'};
 else {delta={tool_calls:[{index:0,id:'call-group',function:{name:'write_note',arguments:JSON.stringify({filename:'group.txt',content:'Actual group note.'})}}]};finish='tool_calls'}
 const chunks=[{choices:[{delta,finish_reason:finish}]},{choices:[],usage:{prompt_tokens:200,completion_tokens:50}}];res.writeHead(200,{'Content-Type':'text/event-stream'});for(const c of chunks)res.write('data: '+JSON.stringify(c)+'\n\n');res.end('data: [DONE]\n\n');
}).listen(port,'0.0.0.0',()=>console.log(`Disposable group gateway listening on ${port}`));
