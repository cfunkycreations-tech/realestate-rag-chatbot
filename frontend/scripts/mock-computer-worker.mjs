// Fixture ONLY: acknowledges requests, never executes commands, waits for disconnect.
import net from 'node:net';
import fs from 'node:fs';
const socketPath=process.env.MOCK_COMPUTER_SOCKET;
if(!socketPath)throw Error('Set MOCK_COMPUTER_SOCKET to a disposable Unix socket path.');
if(fs.existsSync(socketPath))throw Error('Fixture socket path already exists; choose a fresh disposable path.');
net.createServer(socket=>{
 socket.write('{"ready":1}\n');let data='';
 socket.on('data',chunk=>{data+=chunk;if(data.includes('\n'))console.log('Fixture received a computer command; waiting for disconnect.')});
 socket.on('end',()=>console.log('Fixture observed cancellation.'));
}).listen(socketPath,()=>console.log('Disposable computer worker fixture ready'));
