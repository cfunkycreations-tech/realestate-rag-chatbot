"""Client for the optional isolated, single-use computer worker."""
import asyncio
import json
import os

from .tools import ToolError

SOCKET = '/computer-control/computer.sock'


def enabled():
    return os.environ.get('FUNK_COMPUTER_ENABLED') == '1'


async def execute(command):
    if not enabled():
        raise ToolError('Computer sandbox is disabled.')
    writer = None
    try:
        async with asyncio.timeout(38):
            reader,writer=await asyncio.open_unix_connection(SOCKET,limit=100_000)
            writer.write(json.dumps({'command':command},ensure_ascii=True).encode()+b'\n')
            await writer.drain()
            data=await reader.readline()
            if not data or len(data)>100_000: raise ValueError('Invalid response')
            result=json.loads(data)
            if not isinstance(result,dict) or 'error' in result: raise ValueError('Worker failed')
            if not isinstance(result.get('output'),str) or type(result.get('truncated')) is not bool or type(result.get('timed_out')) is not bool or type(result.get('exit_code')) is not int: raise ValueError('Invalid response')
            return result
    except (OSError, TimeoutError, ValueError, UnicodeError) as exc:
        raise ToolError('Computer sandbox unavailable or interrupted; the command may have run. Do not retry without review.') from exc
    finally:
        if writer:
            writer.close()
            try: await writer.wait_closed()
            except OSError: pass
