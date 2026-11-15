"""Constrained, stateless MCP streamable-HTTP subset for public HTTPS servers.

Every request resolves and pins a public address, validates TLS against the
original host, and refuses redirects, proxies, compression and large data.
A bounded SSE response to a POST may contain progress notifications and one
matching response; server-initiated requests and separate GET streams are not supported.
Results are untrusted. Stdio/local MCP servers are intentionally not supported.
"""
import asyncio
import ipaddress
import json
import socket
import ssl
from urllib.parse import urlsplit

import h11
from .tools import ToolError, canonical_host, public_address, validate_target

MAX_RESPONSE=256*1024


def validate_endpoint(url):
    try:
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
            raise ToolError('Use a public HTTPS MCP endpoint without credentials, query, or fragment.')
        host=canonical_host(parsed.hostname)
        validate_target(url,[host],[])
        return url
    except (ValueError,TypeError) as exc:
        raise ToolError('Use a public HTTPS MCP endpoint without credentials, query, or fragment.') from exc


class _SSEReply:
    """Parse bounded SSE frames until the response to this POST arrives.

    Server notifications are ignored, not treated as instructions. Requests
    from the server require a reply and are rejected instead of being executed.
    """
    def __init__(self, expected_id):
        if expected_id is None: raise ToolError('Unexpected connector event stream.')
        self.expected_id=expected_id
        self.line=bytearray();self.lines=[];self.total=0;self.after_cr=False;self.first_line=True

    def _line(self):
        line=bytes(self.line);self.line.clear()
        if self.first_line:
            self.first_line=False
            if line.startswith(b'\xef\xbb\xbf'): line=line[3:]
        if line:
            field,_,value=line.partition(b':')
            if field==b'data': self.lines.append(value[1:] if value.startswith(b' ') else value)
            return None
        if not self.lines: return None
        message=b'\n'.join(self.lines);self.lines.clear()
        try: obj=json.loads(message)
        except (ValueError,UnicodeDecodeError,RecursionError) as exc: raise ToolError('Invalid connector event stream.') from exc
        if not isinstance(obj,dict) or obj.get('jsonrpc')!='2.0': raise ToolError('Invalid connector event stream.')
        if 'method' in obj:
            if 'id' in obj: raise ToolError('Connector server requests are not supported.')
            return None
        if type(obj.get('id')) is not type(self.expected_id) or obj['id']!=self.expected_id: raise ToolError('Connector response ID does not match.')
        return message

    def feed(self, chunk):
        self.total+=len(chunk)
        if self.total>MAX_RESPONSE: raise ToolError('Connector response is too large.')
        # SSE lines may end in CR, LF or CRLF, including across network reads.
        for byte in chunk:
            if self.after_cr:
                self.after_cr=False
                if byte==10: continue
            if byte in (10,13):
                self.after_cr=byte==13
                reply=self._line()
                if reply is not None: return reply
            else: self.line.append(byte)
        return None


async def _request(url, token, payload, session_id=None, protocol_version=None):
    validate_endpoint(url)
    scheme,host,port,path=validate_target(url,[canonical_host(urlsplit(url).hostname)],[])
    try: resolved=await asyncio.get_running_loop().getaddrinfo(host,port,family=socket.AF_UNSPEC,type=socket.SOCK_STREAM)
    except OSError as exc: raise ToolError('Could not resolve connector host.') from exc
    addresses=list(dict.fromkeys(item[4][0] for item in resolved))
    try:
        if not addresses or any(not public_address(ipaddress.ip_address(address)) for address in addresses): raise ToolError('Private and non-public connector addresses are blocked.')
    except ValueError as exc:
        if isinstance(exc,ToolError): raise
        raise ToolError('Invalid connector address.') from exc
    body=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
    if len(body)>32*1024: raise ToolError('Connector request is too large.')
    if token and (len(token)>4096 or any(ord(ch)<33 or ord(ch)>126 for ch in token)): raise ToolError('Invalid connector token.')
    if session_id and (len(session_id)>256 or any(ord(ch)<33 or ord(ch)>126 for ch in session_id)): raise ToolError('Invalid connector session.')
    try:
        reader,writer=await asyncio.open_connection(addresses[0],port,ssl=ssl.create_default_context(),server_hostname=host)
        try:
            connection=h11.Connection(h11.CLIENT,max_incomplete_event_size=16384)
            authority=f'[{host}]' if ':' in host else host
            if port!=443: authority+=f':{port}'
            headers=[('Host',authority),('User-Agent','FunkBot/1.0'),('Content-Type','application/json'),('Accept','application/json, text/event-stream'),('Accept-Encoding','identity'),('Connection','close'),('Content-Length',str(len(body)))]
            if token: headers.append(('Authorization','Bearer '+token))
            if session_id: headers.append(('Mcp-Session-Id',session_id))
            if protocol_version: headers.append(('MCP-Protocol-Version',protocol_version))
            connection_data=connection.send(h11.Request(method='POST',target=path,headers=headers))
            writer.write(connection_data+connection.send(h11.Data(data=body))+connection.send(h11.EndOfMessage()));await writer.drain()
            data=bytearray();status=None;response_headers={};sse=None
            while True:
                event=connection.next_event()
                if event is h11.NEED_DATA:
                    chunk=await reader.read(8192);connection.receive_data(chunk);continue
                if isinstance(event,h11.InformationalResponse): continue
                if isinstance(event,h11.Response):
                    status=event.status_code;response_headers={k.decode('ascii').lower():v.decode('latin1') for k,v in event.headers}
                    if status<200 or status>=300: raise ToolError('Connector returned a non-success status; redirects are not followed.')
                    if response_headers.get('content-encoding','').lower() not in ('','identity'): raise ToolError('Compressed connector responses are not supported.')
                    content_type=response_headers.get('content-type','').split(';',1)[0].strip().lower()
                    allowed=('', 'application/json', 'text/event-stream')
                    if content_type not in allowed and not (payload.get('id') is None and status in (202,204) and content_type=='text/plain'): raise ToolError('This connector uses an unsupported response format.')
                    if content_type=='text/event-stream': sse=_SSEReply(payload.get('id'))
                    try:
                        if int(response_headers.get('content-length','0'))>MAX_RESPONSE: raise ToolError('Connector response is too large.')
                    except ValueError as exc:
                        if isinstance(exc,ToolError): raise
                        raise ToolError('Invalid connector response length.') from exc
                elif isinstance(event,h11.Data):
                    if sse is not None:
                        reply=sse.feed(event.data)
                        if reply is not None: return reply,response_headers
                    else:
                        data.extend(event.data)
                        if len(data)>MAX_RESPONSE: raise ToolError('Connector response is too large.')
                elif isinstance(event,h11.EndOfMessage):
                    if status is None: raise ToolError('Connector returned an invalid response.')
                    if sse is not None: raise ToolError('Connector event stream ended before its response.')
                    return bytes(data),response_headers
                elif isinstance(event,h11.ConnectionClosed): raise ToolError('Connector closed its response unexpectedly.')
        finally:
            writer.close()
            try: await asyncio.wait_for(writer.wait_closed(),timeout=1)
            except (OSError,asyncio.TimeoutError): pass
    except (OSError,h11.RemoteProtocolError,h11.LocalProtocolError,UnicodeError) as exc:
        raise ToolError('Could not safely connect to the MCP server.') from exc


async def request(url,token,payload,session_id=None,protocol_version=None):
    try: return await asyncio.wait_for(_request(url,token,payload,session_id,protocol_version),timeout=12)
    except asyncio.TimeoutError as exc: raise ToolError('Connector request timed out.') from exc


def parse_rpc(raw,expected_id):
    try: result=json.loads(raw)
    except (ValueError,UnicodeError,RecursionError) as exc: raise ToolError('Connector did not return valid JSON.') from exc
    if not isinstance(result,dict) or result.get('jsonrpc')!='2.0' or (type(result.get('id')) is not type(expected_id) or result.get('id')!=expected_id) or 'error' in result or not isinstance(result.get('result'),dict): raise ToolError('Connector returned an invalid or unsuccessful MCP response.')
    return result['result']


async def exchange(url,token,method,params):
    raw,headers=await request(url,token,{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'Funk Bot','version':'1.0'}}})
    init=parse_rpc(raw,1)
    version=init.get('protocolVersion')
    if version not in ('2024-11-05','2025-03-26','2025-06-18'): raise ToolError('Unsupported MCP protocol version.')
    session=headers.get('mcp-session-id')
    await request(url,token,{'jsonrpc':'2.0','method':'notifications/initialized'},session,version)
    raw,_=await request(url,token,{'jsonrpc':'2.0','id':2,'method':method,'params':params},session,version)
    return parse_rpc(raw,2)


async def list_tools(url,token):
    result=await exchange(url,token,'tools/list',{})
    tools=result.get('tools')
    if not isinstance(tools,list) or len(tools)>100: raise ToolError('Invalid connector tool list.')
    return [{'name':tool['name'],'description':str(tool.get('description',''))[:500], 'input_schema':tool.get('inputSchema',{})} for tool in tools if isinstance(tool,dict) and isinstance(tool.get('name'),str) and len(tool['name'])<=128 and isinstance(tool.get('inputSchema',{}),dict)]


async def call_tool(url,token,name,arguments):
    result=await exchange(url,token,'tools/call',{'name':name,'arguments':arguments})
    if result.get('isError'): raise ToolError('Connector reported a tool error.')
    return result
