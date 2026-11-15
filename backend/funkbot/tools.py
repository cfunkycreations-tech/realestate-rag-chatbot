"""Typed tool primitives. Calling a write tool still requires an approval layer.

Web requests connect to a validated DNS result directly, not via a proxy or a
second DNS lookup. Redirects and compressed responses are intentionally not
followed/decoded, keeping the public-network and size boundaries explicit.
"""
import asyncio
import ipaddress
import os
import re
import socket
import ssl
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit

import h11
from pydantic import BaseModel, ConfigDict, Field

MAX_FETCH_BYTES = 256 * 1024
FETCH_TIMEOUT = 10


class ToolError(ValueError):
    pass


class WebFetchArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str = Field(min_length=1, max_length=2048)


class NotesArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filename: str = Field(min_length=5, max_length=85)
    content: str = Field(max_length=16000)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    risk: Literal['read', 'write']
    args: type[BaseModel]
    description: str


REGISTRY = {
    'web_fetch': ToolSpec('web_fetch', 'read', WebFetchArgs, 'Fetch text from an explicitly allowed public website.'),
    'write_note': ToolSpec('write_note', 'write', NotesArgs, 'Create a text note in this Bot’s workspace.'),
}


def canonical_host(host):
    try:
        value = host.rstrip('.').encode('idna').decode('ascii').lower()
        if not value or len(value) > 253:
            raise ValueError()
        return value
    except (UnicodeError, ValueError) as exc:
        raise ToolError('Invalid hostname.') from exc


def host_matches(host, pattern):
    suffix = pattern.startswith('.')
    domain = canonical_host(pattern[1:] if suffix else pattern)
    return host == domain or (suffix and host.endswith('.' + domain))


def validate_target(url, allow, deny):
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in url):
        raise ToolError('URL contains invalid characters.')
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ToolError('Use an HTTP(S) URL without credentials.')
        host, port = canonical_host(parsed.hostname), parsed.port or (443 if parsed.scheme == 'https' else 80)
        if not 1 <= port <= 65535:
            raise ToolError('Invalid port.')
    except ValueError as exc:
        raise ToolError('Invalid URL.') from exc
    if host == 'localhost' or host.endswith('.localhost') or host.endswith('.local'):
        raise ToolError('Private and non-public addresses are blocked.')
    if any(host_matches(host, item) for item in deny) or not any(host_matches(host, item) for item in allow):
        raise ToolError('This website is not allowed by the web fetch policy.')
    try:
        address = ipaddress.ip_address(host)
        if not public_address(address): raise ToolError('Private and non-public addresses are blocked.')
    except ValueError as exc:
        if isinstance(exc, ToolError): raise
    path = quote(parsed.path or '/', safe="/%:@!$&'()*+,;=-._~")
    if parsed.query: path += '?' + quote(parsed.query, safe="/%:@!$&'()*+,;=?-._~")
    return parsed.scheme, host, port, path


def public_address(address):
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not (address.is_multicast or address.is_unspecified or address.is_loopback or address.is_link_local or address.is_private or address.is_reserved)


async def _fetch(url, allow, deny):
    scheme, host, port, path = validate_target(url, allow, deny)
    loop = asyncio.get_running_loop()
    try:
        resolved = await loop.getaddrinfo(host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ToolError('Could not resolve this website.') from exc
    addresses = list(dict.fromkeys(item[4][0] for item in resolved))
    if not addresses:
        raise ToolError('Could not resolve this website.')
    try:
        if any(not public_address(ipaddress.ip_address(address)) for address in addresses):
            raise ToolError('Private and non-public addresses are blocked.')
    except ValueError as exc:
        if isinstance(exc, ToolError): raise
        raise ToolError('Could not validate website addresses.') from exc
    # Pass a literal validated address to the socket; never re-resolve a host
    # after checking it. TLS certificate validation still uses the original host.
    tls = ssl.create_default_context() if scheme == 'https' else None
    try:
        reader, writer = await asyncio.open_connection(addresses[0],port,ssl=tls,server_hostname=host if tls else None)
        try:
            conn=h11.Connection(h11.CLIENT, max_incomplete_event_size=16*1024)
            authority=f'[{host}]' if ':' in host else host
            if port != (443 if scheme=='https' else 80): authority += f':{port}'
            writer.write(conn.send(h11.Request(method='GET',target=path,headers=[('Host',authority),('User-Agent','FunkBot/1.0'),('Accept','text/plain,text/html,application/json;q=0.9,*/*;q=0.1'),('Accept-Encoding','identity'),('Connection','close')])))
            writer.write(conn.send(h11.EndOfMessage()))
            await writer.drain()
            body=bytearray(); status=None; content_type=''; encoding=''
            while True:
                event=conn.next_event()
                if event is h11.NEED_DATA:
                    data=await reader.read(8192)
                    conn.receive_data(data)
                    continue
                if isinstance(event,h11.InformationalResponse): continue
                if isinstance(event,h11.Response):
                    status=event.status_code
                    headers={k.decode('ascii').lower():v.decode('latin1') for k,v in event.headers}
                    content_type=headers.get('content-type','')
                    encoding=headers.get('content-encoding','').strip().lower()
                    if status < 200 or status >= 300:
                        raise ToolError('Website returned a non-success status; redirects are not followed.')
                    if encoding not in ('','identity'):
                        raise ToolError('Compressed responses are not supported.')
                    try:
                        if int(headers.get('content-length','0')) > MAX_FETCH_BYTES:
                            raise ToolError('Website response is too large.')
                    except ValueError as exc:
                        if isinstance(exc,ToolError): raise
                        raise ToolError('Invalid response length.') from exc
                elif isinstance(event,h11.Data):
                    body.extend(event.data)
                    if len(body)>MAX_FETCH_BYTES: raise ToolError('Website response is too large.')
                elif isinstance(event,h11.EndOfMessage):
                    if status is None: raise ToolError('Website returned an invalid response.')
                    return {'url':url,'status':status,'content_type':content_type[:200],'text':body.decode('utf-8','replace')}
                elif isinstance(event,h11.ConnectionClosed):
                    raise ToolError('Website closed the connection unexpectedly.')
        finally:
            writer.close()
            try: await asyncio.wait_for(writer.wait_closed(), timeout=1)
            except (OSError, asyncio.TimeoutError): pass
    except (OSError, h11.RemoteProtocolError, h11.LocalProtocolError, UnicodeError) as exc:
        raise ToolError('Could not safely fetch this website.') from exc


async def web_fetch(args: WebFetchArgs, allow: list[str], deny: list[str]):
    try:
        return await asyncio.wait_for(_fetch(args.url,allow,deny), timeout=FETCH_TIMEOUT)
    except asyncio.TimeoutError as exc:
        raise ToolError('Website request timed out.') from exc


def write_note(data_dir: Path, bot_id: str, args: NotesArgs):
    """Create only a new file, through non-symlink directory descriptors."""
    try:
        if str(uuid.UUID(bot_id)) != bot_id: raise ValueError()
    except ValueError as exc:
        raise ToolError('Invalid Bot workspace.') from exc
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\.txt',args.filename):
        raise ToolError('Use a simple .txt filename without folders.')
    if not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_DIRECTORY') or os.open not in os.supports_dir_fd:
        raise ToolError('Secure workspace writes are not supported on this platform; use Docker.')
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    root_fd=workspace_fd=bot_fd=None
    try:
        root_fd=os.open(data_dir,flags)
        try: os.mkdir('workspaces',0o700,dir_fd=root_fd)
        except FileExistsError: pass
        workspace_fd=os.open('workspaces',flags,dir_fd=root_fd)
        try: os.mkdir(bot_id,0o700,dir_fd=workspace_fd)
        except FileExistsError: pass
        bot_fd=os.open(bot_id,flags,dir_fd=workspace_fd)
        fd=os.open(args.filename,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=bot_fd)
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as file:
            file.write(args.content)
        return {'filename':args.filename,'bytes':len(args.content.encode('utf-8'))}
    except FileExistsError as exc:
        raise ToolError('That note already exists; choose another filename.') from exc
    except OSError as exc:
        raise ToolError('Could not safely create the note in this workspace.') from exc
    finally:
        for fd in (bot_fd,workspace_fd,root_fd):
            if fd is not None: os.close(fd)
