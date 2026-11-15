"""Durable, non-destructive active-workspace pointer for one backend worker.

The root and its previous workspace are never replaced. A corrupt pointer fails
closed rather than creating a fresh installation or following arbitrary paths.
"""
import json
import os
import stat
import uuid
from pathlib import Path

POINTER = 'active-workspace.json'
MAX_DEPTH = 12


class PointerError(ValueError):
    pass


def resolve(root: Path, relative: str) -> Path:
    if not isinstance(relative, str): raise PointerError('Invalid workspace pointer.')
    if not relative: return root
    parts=relative.split('/')
    if len(parts)%2 or len(parts)>MAX_DEPTH*2: raise PointerError('Invalid workspace pointer.')
    current=root
    for i in range(0,len(parts),2):
        try:
            if parts[i]!='restores' or str(uuid.UUID(parts[i+1]))!=parts[i+1]: raise ValueError()
        except (ValueError,IndexError): raise PointerError('Invalid workspace pointer.')
        for name in parts[i:i+2]:
            current=current/name
            try: info=current.lstat()
            except OSError as exc: raise PointerError('Active workspace directory is missing.') from exc
            if not stat.S_ISDIR(info.st_mode): raise PointerError('Unsafe workspace directory.')
    return current


def read(root: Path):
    pointer=root/POINTER
    try:
        if pointer.is_symlink(): raise PointerError('Unsafe workspace pointer.')
        if not pointer.exists(): return {'active':'','previous':None}
        if not pointer.is_file() or pointer.stat().st_size>4096: raise PointerError('Invalid workspace pointer.')
        value=json.loads(pointer.read_text(encoding='utf-8'))
        if not isinstance(value,dict) or value.get('version')!=1 or not isinstance(value.get('active'),str) or (value.get('previous') is not None and not isinstance(value['previous'],str)): raise PointerError('Invalid workspace pointer.')
        resolve(root,value['active'])
        if value.get('previous') is not None: resolve(root,value['previous'])
        return {'active':value['active'],'previous':value.get('previous')}
    except (OSError,UnicodeError,ValueError) as exc:
        if isinstance(exc,PointerError): raise
        raise PointerError('Invalid workspace pointer.') from exc


def write(root: Path, active: str, previous: str):
    resolve(root,active);resolve(root,previous)
    payload=json.dumps({'version':1,'active':active,'previous':previous},separators=(',',':'))
    temporary=root/('.active-workspace-'+str(uuid.uuid4()))
    try:
        fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            stream.write(payload);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,root/POINTER)
        # Some filesystems/platforms do not permit directory fsync. The
        # atomic pointer is already committed; never report failure and leave
        # an old process serving after the pointer changed.
        if hasattr(os,'O_DIRECTORY'):
            try:
                fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
                try: os.fsync(fd)
                finally: os.close(fd)
            except OSError: pass
    finally:
        temporary.unlink(missing_ok=True)
