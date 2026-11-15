import { NextRequest } from 'next/server';

// Resolve the backend at runtime, not at image-build time. Browsers only ever
// talk to their own origin; the backend is not exposed by Compose.
async function proxy(request: NextRequest, {params}: {params: Promise<{path: string[]}>}) {
  const {path} = await params;
  const backend = (process.env.BACKEND_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
  const url = `${backend}/api/${path.map(encodeURIComponent).join('/')}${request.nextUrl.search}`;
  const headers = new Headers();
  for (const name of ['content-type', 'cookie', 'accept']) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    let body: ArrayBuffer | undefined;
    if (!['GET', 'HEAD'].includes(request.method)) {
      if (request.method === 'POST' && request.body && ((path.length === 5 && path[0] === 'bots' && path[2] === 'chats' && path[4] === 'attachments') || (path.length === 2 && path[0] === 'workspace' && path[1] === 'restore'))) {
        const maxBytes=path[0]==='workspace'?260*1024*1024:2*1024*1024+65536;
        // Bound multipart buffering at the public proxy even without Content-Length.
        const reader=request.body.getReader(), chunks:Uint8Array[]=[];let total=0;
        while (true) {
          const {done,value}=await reader.read();if(done)break;
          total+=value.byteLength;
          if(total>maxBytes){await reader.cancel();return Response.json({detail:'Upload request is too large.'},{status:413})}
          chunks.push(value);
        }
        const bytes=new Uint8Array(total);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength}body=bytes.buffer;
      } else body=await request.arrayBuffer();
    }
    const result = await fetch(url, {method: request.method, headers, body, redirect: 'manual', cache: 'no-store'});
    const outgoing = new Headers();
    for (const name of ['content-type', 'content-disposition', 'cache-control', 'set-cookie', 'x-accel-buffering', 'x-content-type-options', 'content-security-policy']) {
      const value = result.headers.get(name);
      if (value) outgoing.set(name, value);
    }
    return new Response(result.body, {status: result.status, headers: outgoing});
  } catch {
    return Response.json({detail: 'Cannot reach Funk Bot backend.'}, {status: 502});
  }
}
export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
