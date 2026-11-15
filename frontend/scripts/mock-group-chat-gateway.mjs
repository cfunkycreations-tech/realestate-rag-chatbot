// Disposable test gateway. Never use for a real installation.
import http from 'node:http';
const port=Number(process.env.MOCK_PORT||8044);
http.createServer(async(req,res)=>{if(req.method!=='POST'||req.url!=='/v1/chat/completions'){res.writeHead(404).end();return}let raw='';for await(const chunk of req)raw+=chunk;const payload=JSON.parse(raw),last=payload.messages.filter(m=>m.role==='user').at(-1)?.content||'',hasTool=payload.messages.at(-1)?.role==='tool';let delta,finish='stop';
 if(last.startsWith('You are the group Chief. Read'))delta={content:'Chief plan: research the question.'};
 else if(last.startsWith('You are the group Chief. Synthesize'))delta={content:'Chief summary of the actual group contribution.'};
 else if(hasTool)delta={content:'Member research completed after review.'};
 else {delta={tool_calls:[{index:0,id:'call-group-chat',function:{name:'write_note',arguments:JSON.stringify({filename:'group-chat.txt',content:'Actual group chat note.'})}}]};finish='tool_calls'}
 res.writeHead(200,{'Content-Type':'text/event-stream'});for(const chunk of [{choices:[{delta,finish_reason:finish}]},{choices:[],usage:{prompt_tokens:200,completion_tokens:50}}])res.write('data: '+JSON.stringify(chunk)+'\n\n');res.end('data: [DONE]\n\n');
}).listen(port,'0.0.0.0',()=>console.log(`Disposable group chat gateway on ${port}`));
