"""Opt-in HTTPS CONNECT broker for the network-isolated browser container.

The broker pins a public DNS result and permits only exact, owner-allowlisted
hosts that were individually approved in the current desktop session. TLS is
end-to-end between Chromium and the destination; the broker cannot inspect it.
"""
import asyncio
import ipaddress
import json
import os
import re
import socket
import stat
from urllib.parse import urlsplit

from .tools import ToolError, canonical_host, public_address
from .tool_policy import WebPolicy

SOCKET='/computer-control/browser-proxy.sock'
MAX_CONNECTIONS=12
MAX_BYTES=20*1024*1024

def enabled(): return os.environ.get('FUNK_COMPUTER_BROWSER_NETWORK')=='1'


def policy(c):
    row=c.execute("SELECT value FROM config WHERE key='computer_browser_domains'").fetchone()
    if not row: return {'domains':[],'revision':0}
    try:
        value=json.loads(row['value'])
        if set(value)!={'domains','revision'} or type(value['revision']) is not int or value['revision']<0: raise ValueError()
        domains=validate_domains(value['domains'])
        return {'domains':domains,'revision':value['revision']}
    except (ValueError,TypeError,KeyError): return {'domains':[],'revision':0}


def validate_domains(domains):
    if not isinstance(domains,list): raise ValueError('Enter a list of exact public hostnames.')
    result=WebPolicy(allow=domains).allow
    for host in result:
        if host.startswith('.') or host.endswith('.local') or host.endswith('.localhost'): raise ValueError('Only exact public hostnames are supported.')
        try: ipaddress.ip_address(host)
        except ValueError: continue
        raise ValueError('IP addresses are not supported; enter a hostname.')
    return result


def target(url):
    if not isinstance(url,str) or len(url)>2048 or any(ord(c)<33 or ord(c)==127 for c in url): raise ToolError('Invalid browser URL.')
    try:
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.port not in (None,443): raise ValueError()
        host=canonical_host(parsed.hostname)
        if validate_domains([host])!=[host]: raise ValueError()
        return host
    except (ValueError,TypeError): raise ToolError('Browser network URLs must use HTTPS on port 443, without credentials, with an exact public hostname.') from None


class Broker:
    def __init__(self,db): self.db=db;self.server=None;self.tasks=set()

    def permitted(self,host):
        from . import computer
        session=computer._session
        if not enabled() or not computer.desktop_enabled() or not session or session.closed.is_set(): return False
        try:
            with self.db() as c:
                p=policy(c);grant=computer.permission(c,session.context.bot_id)
                row=c.execute('SELECT status,bot_id FROM runs WHERE id=?',(session.context.run_id,)).fetchone()
                paused=c.execute("SELECT value FROM config WHERE key='global_pause'").fetchone()
                return bool(host in p['domains'] and session.domains.get(host)==p['revision'] and grant['allowed'] and grant['revision']==session.revision and row and row['bot_id']==session.context.bot_id and row['status'] in ('running','waiting_approval') and not (paused and paused['value']=='1') and session.context.policy_for(c,'computer_shell','write')!='deny')
        except Exception: return False

    async def start(self):
        if not enabled(): return
        os.makedirs(os.path.dirname(SOCKET),mode=0o700,exist_ok=True)
        try:
            info=os.lstat(SOCKET)
            if not stat.S_ISSOCK(info.st_mode): raise RuntimeError('Browser proxy path is not a socket.')
            os.unlink(SOCKET)
        except FileNotFoundError: pass
        self.server=await asyncio.start_unix_server(self.handle,SOCKET,limit=8193)
        os.chmod(SOCKET,0o600)

    def revoke(self):
        for task in list(self.tasks): task.cancel()

    async def close(self):
        self.revoke()
        if self.tasks: await asyncio.gather(*list(self.tasks),return_exceptions=True)
        if self.server:
            self.server.close();await self.server.wait_closed()
            try: os.unlink(SOCKET)
            except FileNotFoundError: pass

    async def handle(self,reader,writer):
        task=asyncio.current_task();remote=None
        if len(self.tasks)>=MAX_CONNECTIONS:
            writer.close();return
        self.tasks.add(task)
        try:
            head=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),5)
            if len(head)>8192: raise ValueError()
            line=head.split(b'\r\n',1)[0].decode('ascii')
            match=re.fullmatch(r'CONNECT ([a-zA-Z0-9.-]+):443 HTTP/1\.[01]',line)
            if not match: raise ValueError()
            host=canonical_host(match.group(1))
            if validate_domains([host])!=[host] or not self.permitted(host): raise ValueError()
            addresses=await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host,443,type=socket.SOCK_STREAM),5)
            ips=list(dict.fromkeys(item[4][0] for item in addresses))
            if not ips or any(not public_address(ipaddress.ip_address(ip)) for ip in ips): raise ValueError()
            if not self.permitted(host): raise ValueError()
            # Literal address pins DNS. Chromium checks the TLS certificate for
            # the original host after CONNECT; no TLS interception is used.
            rr,remote=await asyncio.wait_for(asyncio.open_connection(ips[0],443),10)
            if not self.permitted(host): raise ValueError()
            writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n');await writer.drain()
            async def relay(src,dst):
                total=0
                while True:
                    data=await src.read(32768)
                    if not data: return
                    total+=len(data)
                    if total>MAX_BYTES: return
                    dst.write(data);await dst.drain()
            async with asyncio.timeout(90):
                await asyncio.gather(relay(reader,remote),relay(rr,writer))
        except (OSError,ValueError,TimeoutError,asyncio.IncompleteReadError,asyncio.LimitOverrunError,ToolError):
            try: writer.write(b'HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');await writer.drain()
            except OSError: pass
        finally:
            if remote: remote.close()
            writer.close();self.tasks.discard(task)


broker=None

def revoke():
    if broker: broker.revoke()
