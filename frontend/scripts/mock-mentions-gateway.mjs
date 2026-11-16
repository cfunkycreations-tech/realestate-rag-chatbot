// Disposable model fixture. Captures the last request for browser assertions.
import http from 'node:http';let last=null;
http.createServer(async(req,res)=>{
 if(req.method==='GET'&&req.url==='/last'){res.writeHead(200,{'Content-Type':'application/json'}).end(JSON.stringify(last));return}
 if(req.method!=='POST'||req.url!=='/v1/chat/completions'){res.writeHead(404).end();return}
 let raw='';for await(const chunk of req)raw+=chunk;last=JSON.parse(raw);res.writeHead(200,{'Content-Type':'text/event-stream'});for(const c of [{choices:[{delta:{content:'I can use those workspace references.'},finish_reason:'stop'}]},{choices:[],usage:{prompt_tokens:200,completion_tokens:50}}])res.write('data: '+JSON.stringify(c)+'\n\n');res.end('data: [DONE]\n\n');
}).listen(Number(process.env.MOCK_PORT||8070),'0.0.0.0',()=>console.log('Disposable mentions model ready'));
