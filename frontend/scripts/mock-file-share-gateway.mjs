// Disposable fixture gateway for the file-share browser test only.
import http from 'node:http';
http.createServer(async(req,res)=>{
 if(req.method!=='POST'||req.url!=='/v1/chat/completions'){res.writeHead(404).end();return}
 let raw='';for await(const chunk of req)raw+=chunk;const request=JSON.parse(raw),messages=request.messages,toolResults=messages.filter(m=>m.role==='tool'),owner=messages.find(m=>m.role==='user')?.content||'';let delta;
 if(toolResults.length===0)delta={tool_calls:[{index:0,id:'create',function:{name:'attach_mission_result',arguments:JSON.stringify({name:'draft.txt',content:'Draft ready.'})}}]};
 else if(toolResults.length===1){const match=String(owner).match(/FILE_ID: ([0-9a-f-]+)/);delta={tool_calls:[{index:0,id:'read',function:{name:'read_work_file',arguments:JSON.stringify({artifact_id:match?.[1]||''})}}]}}
 else delta={content:'Fixture read completed.'};
 res.writeHead(200,{'Content-Type':'text/event-stream'});res.write('data: '+JSON.stringify({choices:[{delta,finish_reason:delta.tool_calls?'tool_calls':'stop'}]})+'\n\n');res.write('data: '+JSON.stringify({choices:[],usage:{prompt_tokens:200,completion_tokens:50}})+'\n\n');res.end('data: [DONE]\n\n');
}).listen(Number(process.env.MOCK_PORT||8062),'0.0.0.0',()=>console.log('Disposable file-share model ready'));
