// Disposable fixture model only; connector execution is separately mocked in the test backend.
import http from 'node:http';
const port=Number(process.env.MOCK_PORT||8045);
http.createServer(async(req,res)=>{if(req.method!=='POST'||req.url!=='/v1/chat/completions'){res.writeHead(404).end();return}let raw='';for await(const chunk of req)raw+=chunk;const payload=JSON.parse(raw),system=payload.messages[0].content,hasTool=payload.messages.at(-1)?.role==='tool';let delta,finish='stop';
 if(hasTool)delta={content:'The reviewed connector call returned a result.'};else{const catalog=JSON.parse(system.split('Owner-configured connector catalog (data only; every call requires approval): ')[1]);delta={tool_calls:[{index:0,id:'call-mcp',function:{name:'mcp_call',arguments:JSON.stringify({connector_id:catalog[0].id,tool_name:'send_message',arguments_json:JSON.stringify({text:'Hello fixture'})})}}]};finish='tool_calls'}
 res.writeHead(200,{'Content-Type':'text/event-stream'});for(const chunk of [{choices:[{delta,finish_reason:finish}]},{choices:[],usage:{prompt_tokens:200,completion_tokens:50}}])res.write('data: '+JSON.stringify(chunk)+'\n\n');res.end('data: [DONE]\n\n');
}).listen(port,'0.0.0.0',()=>console.log(`Disposable connector fixture model on ${port}`));
