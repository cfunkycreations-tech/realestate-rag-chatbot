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
    const result = await fetch(url, {method: request.method, headers, body: ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer(), redirect: 'manual', cache: 'no-store'});
    const outgoing = new Headers();
    for (const name of ['content-type', 'content-disposition', 'cache-control', 'set-cookie', 'x-accel-buffering', 'x-content-type-options']) {
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
