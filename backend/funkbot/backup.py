"""Bounded workspace archives and non-destructive staged restore.

Archive bytes are sensitive: they include the key that decrypts saved gateways.
Never extract arbitrary ZIP paths or overwrite a live installation.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from cryptography.fernet import Fernet, InvalidToken

MAX_TOTAL = 256 * 1024 * 1024
MAX_FILES = 5000
MAX_MANIFEST = 1024 * 1024
FIXED = {'funk.db', 'vault.key', 'session.key', 'banner.png'}
TREES = {'vault', 'workspaces'}


class BackupError(ValueError):
    pass


def valid_path(name):
    if not name or '\\' in name or '\x00' in name or name.startswith('/'):
        return False
    parts = name.split('/')
    if any(not part or part in ('.', '..') or len(part) > 255 or ':' in part or any(ord(char)<32 for char in part) for part in parts):
        return False
    return (len(parts) == 1 and name in FIXED) or (len(parts) > 1 and parts[0] in TREES)


def _files(data):
    for name in sorted(FIXED - {'funk.db'}):
        path = data / name
        if path.is_symlink(): raise BackupError('A workspace file is a symbolic link.')
        if path.exists(): yield name, path
        elif name in {'vault.key', 'session.key'}: raise BackupError('Workspace key is missing.')
    for rootname in sorted(TREES):
        root = data / rootname
        if root.is_symlink(): raise BackupError('A workspace directory is a symbolic link.')
        if not root.exists(): continue
        if not root.is_dir(): raise BackupError('Invalid workspace directory.')
        for folder, dirs, files in os.walk(root, followlinks=False):
            dirs.sort(); files.sort()
            for name in dirs:
                if (Path(folder) / name).is_symlink(): raise BackupError('A workspace directory is a symbolic link.')
            for name in files:
                path = Path(folder) / name
                relative = path.relative_to(data).as_posix()
                if not valid_path(relative) or path.is_symlink(): raise BackupError('Unsafe workspace file.')
                yield relative, path


def create(data: Path, database: Path, output):
    """Use SQLite's online backup API; do not copy WAL or live DB bytes."""
    with tempfile.TemporaryDirectory(prefix='funk-backup-') as temp:
        snapshot = Path(temp) / 'funk.db'
        with sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True) as source, sqlite3.connect(snapshot) as dest:
            source.backup(dest)
        entries = [('funk.db', snapshot), *_files(data)]
        if len(entries) > MAX_FILES: raise BackupError('Workspace contains too many files.')
        metadata = {}; total = 0
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
            for name, path in entries:
                # The owner must stop concurrent workspace changes before exporting.
                if path.is_symlink(): raise BackupError('A workspace file is a symbolic link.')
                info = path.stat()
                if not stat.S_ISREG(info.st_mode): raise BackupError('Workspace contains a non-regular file.')
                total += info.st_size
                if total > MAX_TOTAL: raise BackupError('Workspace exceeds the backup size limit.')
                digest=hashlib.sha256();written=0
                flags=os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os,'O_NONBLOCK',0)
                with os.fdopen(os.open(path,flags),'rb') as source, archive.open(name,'w') as target:
                    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode): raise BackupError('Workspace contains a non-regular file.')
                    while chunk := source.read(1024*1024):
                        written += len(chunk)
                        if total - info.st_size + written > MAX_TOTAL: raise BackupError('Workspace exceeds the backup size limit.')
                        digest.update(chunk);target.write(chunk)
                total += written-info.st_size
                metadata[name]={'size':written,'sha256':digest.hexdigest()}
            manifest=json.dumps({'format':'funkbot-workspace','version':1,'files':metadata},sort_keys=True,separators=(',',':')).encode()
            if len(manifest)>MAX_MANIFEST: raise BackupError('Backup manifest is too large.')
            archive.writestr('manifest.json',manifest)


def restore(archive_path: Path, data: Path, expected_revision: str):
    """Validate and extract to a new private directory; never replace live data."""
    parent=data / 'restores'
    if parent.is_symlink(): raise BackupError('Unsafe restore directory.')
    parent.mkdir(mode=0o700, exist_ok=True)
    if not parent.is_dir(): raise BackupError('Unsafe restore directory.')
    if sum(1 for _ in parent.iterdir()) >= 3: raise BackupError('At most three restores may be staged; remove an older stage first.')
    stage=parent / str(uuid.uuid4());stage.mkdir(mode=0o700)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members=archive.infolist();names=[entry.filename for entry in members]
            if len(members)>MAX_FILES+1 or len(set(names))!=len(names) or 'manifest.json' not in names: raise BackupError('Invalid backup entries.')
            manifest_info=archive.getinfo('manifest.json')
            if manifest_info.file_size>MAX_MANIFEST: raise BackupError('Backup manifest is too large.')
            if any(entry.compress_type!=zipfile.ZIP_STORED or entry.flag_bits & 1 or entry.is_dir() or (entry.external_attr >> 16 and stat.S_ISLNK(entry.external_attr >> 16)) for entry in members): raise BackupError('Unsupported backup entry.')
            manifest=json.loads(archive.read(manifest_info))
            if not isinstance(manifest,dict) or manifest.get('format')!='funkbot-workspace' or manifest.get('version')!=1 or not isinstance(manifest.get('files'),dict): raise BackupError('Invalid backup manifest.')
            files=manifest['files']
            if set(names) != set(files)|{'manifest.json'} or not {'funk.db','vault.key','session.key'} <= set(files): raise BackupError('Backup is incomplete.')
            total=0
            for entry in members:
                if entry.filename=='manifest.json': continue
                if not valid_path(entry.filename): raise BackupError('Unsafe backup path.')
                spec=files[entry.filename]
                if not isinstance(spec,dict) or type(spec.get('size')) is not int or spec['size']!=entry.file_size or not isinstance(spec.get('sha256'),str): raise BackupError('Invalid backup file metadata.')
                total+=entry.file_size
                if total>MAX_TOTAL: raise BackupError('Backup exceeds the size limit.')
                target=stage.joinpath(*PurePosixPath(entry.filename).parts);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                digest=hashlib.sha256();count=0
                with archive.open(entry) as source, target.open('xb') as out:
                    os.chmod(target,0o600)
                    while chunk := source.read(1024*1024):
                        count+=len(chunk)
                        if count>entry.file_size: raise BackupError('Invalid backup file size.')
                        digest.update(chunk);out.write(chunk)
                if count!=entry.file_size or digest.hexdigest()!=spec['sha256']: raise BackupError('Backup checksum failed.')
        key=Fernet((stage/'vault.key').read_bytes().strip())
        if not (stage/'session.key').read_text().strip(): raise BackupError('Invalid session key.')
        with sqlite3.connect((stage/'funk.db').resolve().as_uri()+'?mode=ro',uri=True) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchone(): raise BackupError('Backup database is invalid.')
            revisions=db.execute('SELECT version_num FROM alembic_version').fetchall()
            if revisions != [(expected_revision,)]: raise BackupError('Backup version does not match this Funk Bot version.')
            row=db.execute("SELECT value FROM config WHERE key='gateways'").fetchone()
            gateways=json.loads(row[0]) if row else {}
            if not isinstance(gateways,dict) or any(not isinstance(g,dict) for g in gateways.values()): raise BackupError('Invalid gateway configuration.')
            for gateway in gateways.values():
                if gateway.get('key'): key.decrypt(gateway['key'].encode())
        return stage
    except (BackupError, OSError, ValueError, KeyError, TypeError, sqlite3.Error, zipfile.BadZipFile, InvalidToken) as exc:
        shutil.rmtree(stage,ignore_errors=True)
        if isinstance(exc,BackupError): raise
        raise BackupError('Invalid or damaged workspace backup.') from exc
