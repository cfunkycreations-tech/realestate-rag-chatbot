"""Strict, bounded, portable data-only computer workspace snapshots.

No tar/zip extraction: every path is validated and links and special files are
rejected. Collection uses no-follow directory descriptors so sandbox processes
cannot trick a privileged collector into following a link out of the workspace.
"""
import base64
import binascii
import os
import re
import stat

MAX_BYTES = 2 * 1024 * 1024
MAX_FILE = 512 * 1024
MAX_ENTRIES = 200
MAX_JSON = 3 * 1024 * 1024
NAME = re.compile(r'^[A-Za-z0-9_. -]{1,100}$')


class SnapshotError(ValueError): pass


def valid_path(path):
    if not isinstance(path,str) or len(path)>500: return False
    parts=path.split('/')
    return 1<=len(parts)<=8 and all(part not in ('.','..') and NAME.fullmatch(part) and not part.endswith(' ') for part in parts)


def validate(snapshot):
    if not isinstance(snapshot,dict) or set(snapshot)!={'dirs','files'} or not isinstance(snapshot['dirs'],list) or not isinstance(snapshot['files'],dict):
        raise SnapshotError('Invalid computer workspace snapshot.')
    dirs=snapshot['dirs'];files=snapshot['files']
    if len(dirs)+len(files)>MAX_ENTRIES: raise SnapshotError('Computer workspace has too many entries.')
    if any(not valid_path(p) for p in dirs) or len(set(dirs))!=len(dirs) or any(not valid_path(p) for p in files):
        raise SnapshotError('Computer workspace contains an unsupported path.')
    directory_set=set(dirs)
    if any(p in directory_set for p in files): raise SnapshotError('Workspace file and directory conflict.')
    for path in [*dirs,*files]:
        parts=path.split('/')
        if any('/'.join(parts[:i]) not in directory_set for i in range(1,len(parts))):
            raise SnapshotError('Workspace parent directory is missing.')
    total=0
    for entry in files.values():
        if not isinstance(entry,dict) or set(entry)!={'data','executable'} or type(entry['executable']) is not bool or not isinstance(entry['data'],str):
            raise SnapshotError('Invalid workspace file.')
        if len(entry['data'])>4*((MAX_FILE+2)//3): raise SnapshotError('Workspace file is too large.')
        try: data=base64.b64decode(entry['data'],validate=True)
        except (ValueError,binascii.Error): raise SnapshotError('Invalid workspace file encoding.') from None
        total+=len(data)
        if len(data)>MAX_FILE or total>MAX_BYTES: raise SnapshotError('Computer workspace exceeds its size limit.')
    return snapshot


def restore(snapshot,root):
    validate(snapshot)
    # Called as the unprivileged command UID into a new private tmpfs.
    for path in sorted(snapshot['dirs'],key=lambda p:(p.count('/'),p)):
        os.mkdir(os.path.join(root,path),0o700)
    for path,entry in snapshot['files'].items():
        with open(os.path.join(root,path),'xb') as out:
            out.write(base64.b64decode(entry['data'],validate=True))
        os.chmod(os.path.join(root,path),0o700 if entry['executable'] else 0o600)


def collect(root):
    snapshot={'dirs':[],'files':{}}; total=0
    dflags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    def walk(fd,prefix):
        nonlocal total
        for name in sorted(os.listdir(fd)):
            path=prefix+'/'+name if prefix else name
            if not valid_path(path) or len(snapshot['dirs'])+len(snapshot['files'])>=MAX_ENTRIES:
                raise SnapshotError('Workspace has too many entries or an unsupported path.')
            info=os.stat(name,dir_fd=fd,follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child=os.open(name,dflags,dir_fd=fd)
                try:
                    snapshot['dirs'].append(path);walk(child,path)
                finally: os.close(child)
            elif stat.S_ISREG(info.st_mode):
                if info.st_size>MAX_FILE: raise SnapshotError('Workspace file exceeds 512 KiB.')
                child=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
                try:
                    actual=os.fstat(child)
                    if not stat.S_ISREG(actual.st_mode): raise SnapshotError('Unsafe workspace entry.')
                    with os.fdopen(child,'rb',closefd=False) as f: data=f.read(MAX_FILE+1)
                finally: os.close(child)
                total+=len(data)
                if len(data)>MAX_FILE or total>MAX_BYTES: raise SnapshotError('Workspace exceeds its size limit.')
                snapshot['files'][path]={'data':base64.b64encode(data).decode('ascii'),'executable':bool(actual.st_mode & 0o111)}
            else: raise SnapshotError('Workspace links and special files cannot be saved.')
    fd=os.open(root,dflags)
    try: walk(fd,'')
    finally: os.close(fd)
    return validate(snapshot)
