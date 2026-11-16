"""MCP newline-JSON stdio transport for explicitly configured local commands.

The process is NOT sandboxed; only use trusted owner-configured servers.
"""
import asyncio
import json
import os
import signal
from .tools import ToolError
from .mcp_http import parse_rpc

MAX_LINE=256*1024

async def exchange(command,arguments,method,params):
    proc=None
    try:
        env={k:os.environ[k] for k in ('PATH','HOME','LANG','TMPDIR','SYSTEMROOT') if k in os.environ}
        proc=await asyncio.create_subprocess_exec(command,*arguments,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env=env,limit=MAX_LINE+1,start_new_session=True)
        async def send(value):
            proc.stdin.write(json.dumps(value,ensure_ascii=True,separators=(',',':')).encode()+b'\n')
            await proc.stdin.drain()
        async def receive(identifier):
            for _ in range(100):
                line=await proc.stdout.readline()
                if not line or len(line)>MAX_LINE: raise ToolError('Invalid stdio connector response.')
                try: msg=json.loads(line)
                except (ValueError,RecursionError): raise ToolError('Invalid stdio connector response.') from None
                if isinstance(msg,dict) and msg.get('id')==identifier: return parse_rpc(line,identifier)
            raise ToolError('Too many connector messages.')
        async with asyncio.timeout(30):
            await send({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'Funk Bot','version':'1.0'}}})
            initialized=await receive(1)
            if not isinstance(initialized.get('protocolVersion'),str): raise ToolError('Invalid connector initialization.')
            await send({'jsonrpc':'2.0','method':'notifications/initialized'})
            await send({'jsonrpc':'2.0','id':2,'method':method,'params':params})
            return await receive(2)
    except (OSError,ValueError,TimeoutError) as exc:
        raise ToolError('Local connector failed or timed out.') from exc
    finally:
        if proc:
            try: os.killpg(proc.pid,signal.SIGKILL)
            except (ProcessLookupError,PermissionError): pass
            await proc.wait()

async def list_tools(command,arguments):
    result=await exchange(command,arguments,'tools/list',{})
    values=result.get('tools')
    if not isinstance(values,list) or len(values)>100: raise ToolError('Invalid connector tool list.')
    return [{'name':t['name'],'description':str(t.get('description',''))[:500],'input_schema':t.get('inputSchema',{})} for t in values if isinstance(t,dict) and isinstance(t.get('name'),str) and len(t['name'])<=128 and isinstance(t.get('inputSchema',{}),dict)]

async def call_tool(command,arguments,name,params):
    result=await exchange(command,arguments,'tools/call',{'name':name,'arguments':params})
    if result.get('isError'): raise ToolError('Connector reported a tool error.')
    return result
