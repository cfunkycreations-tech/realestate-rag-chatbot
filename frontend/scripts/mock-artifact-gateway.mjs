// Local fixture gateway for disposable browser tests only.
import http from 'node:http';
http.createServer(async(req,res)=>{
 if(req.method!=='POST'||req.url!=='/v1/chat/completions'){res.writeHead(404).end();return}
 let raw='';for await(const chunk of req)raw+=chunk;const request=JSON.parse(raw),last=request.messages.at(-1);const delta=last.role==='tool'?{content:'The draft is attached.'}:{tool_calls:[{index:0,id:'fixture-artifact',function:{name:'attach_mission_result',arguments:JSON.stringify({name:'draft.md',content:'# Draft\nActual fixture result.'})}}]};
 res.writeHead(200,{'Content-Type':'text/event-stream'});res.write('data: '+JSON.stringify({choices:[{delta,finish_reason:last.role==='tool'?'stop':'tool_calls'}]})+'\n\n');res.write('data: '+JSON.stringify({choices:[],usage:{prompt_tokens:200,completion_tokens:50}})+'\n\n');res.end('data: [DONE]\n\n');
}).listen(Number(process.env.MOCK_PORT||8061),'0.0.0.0',()=>console.log('Disposable artifact model ready'));
