"""Ingest private, user-supplied PNG characters and draw them server-side."""
import hashlib
import io
import json
import secrets
import time
import unicodedata
import uuid
import warnings
import zipfile
from pathlib import Path, PurePosixPath

from PIL import Image, UnidentifiedImageError
from funkbot.redaction import redact_text

MAX_ARCHIVE = 20 * 1024 * 1024
MAX_UNPACKED = 64 * 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024
MAX_FILES = 500
MAX_PIXELS = 16_000_000
RARITY_WEIGHTS = {'common': 65, 'uncommon': 25, 'rare': 8, 'legendary': 2}


class VaultError(ValueError):
    pass


def normal_name(value):
    return unicodedata.normalize('NFKC', value).strip().casefold()


def inspect_png(data):
    if len(data) > MAX_IMAGE or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise VaultError('Not a supported PNG')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != 'PNG' or image.width < 1 or image.height < 1 or image.width * image.height > MAX_PIXELS:
                    raise VaultError('Invalid dimensions')
                metadata = {str(k).casefold(): str(v).strip() for k, v in image.info.items() if isinstance(v, str)}
                name = (metadata.get('funk:name') or metadata.get('charactername') or '').strip()
                if not name or len(name) > 120:
                    raise VaultError('Missing or invalid character name')
                role = (metadata.get('funk:titles') or metadata.get('characterrole') or '')[:160].split('|')[0]
                notes = (metadata.get('funk:personality') or metadata.get('notes') or '')[:2000]
                tags = [t.strip()[:60] for t in (metadata.get('funk:tags') or metadata.get('tags') or '').split(',') if t.strip()][:30]
                rarity = (metadata.get('funk:rarity') or 'common').casefold()
                if rarity not in RARITY_WEIGHTS:
                    rarity = 'common'
                # Re-encode to strip metadata and reject corrupt image data.
                image.load()
                output = io.BytesIO()
                image.convert('RGBA').save(output, format='PNG', optimize=True)
                if output.tell() > MAX_IMAGE:
                    raise VaultError('Image too large after conversion')
                return {'name':name, 'role':role, 'notes':notes, 'tags':tags, 'rarity':rarity, 'image':output.getvalue()}
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise VaultError('Invalid PNG') from exc


def import_zip(data, connection, directory: Path, redaction_keys: list[str] | None = None, collection: str = "", pack_id: str | None = None):
    if len(data) > MAX_ARCHIVE:
        raise VaultError('ZIP is too large (maximum 20 MB).')
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError) as exc:
        raise VaultError('Please choose a valid ZIP file.') from exc
    with archive:
        entries = [e for e in archive.infolist() if not e.is_dir()]
        if len(entries) > MAX_FILES or sum(e.file_size for e in entries) > MAX_UNPACKED:
            raise VaultError('ZIP exceeds the file or uncompressed-size limit.')
        # Paths are never extracted, but still reject traversal, absolute paths,
        # symlinks, encrypted entries and non-PNG files.
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        added = duplicate = invalid = 0
        created = []
        try:
            for entry in entries:
                path = PurePosixPath(entry.filename.replace('\\', '/'))
                mode = (entry.external_attr >> 16) & 0o170000
                if (path.is_absolute() or '..' in path.parts or mode == 0o120000 or entry.flag_bits & 1
                        or path.suffix.casefold() != '.png' or entry.file_size > MAX_IMAGE):
                    invalid += 1
                    continue
                try:
                    with archive.open(entry) as source:
                        raw = source.read(MAX_IMAGE + 1)
                    if len(raw) != entry.file_size or len(raw) > MAX_IMAGE:
                        raise VaultError('Invalid file size')
                    item = inspect_png(raw)
                    keys = redaction_keys or []
                    for field in ('name', 'role', 'notes'):
                        item[field] = redact_text(item[field], keys)
                    item['tags'] = [redact_text(tag, keys) for tag in item['tags']]
                    if collection and collection.casefold() not in {t.casefold() for t in item['tags']}:
                        item['tags'].append(redact_text(collection, keys))
                except (VaultError, OSError, RuntimeError, zipfile.BadZipFile, ValueError):
                    invalid += 1
                    continue
                digest = hashlib.sha256(raw).hexdigest()
                normalized = normal_name(item['name'])
                if connection.execute('SELECT 1 FROM characters WHERE content_hash=? OR normalized_name=?', (digest, normalized)).fetchone():
                    duplicate += 1
                    continue
                character_id = str(uuid.uuid4())
                target = directory / (character_id + '.png')
                with target.open('xb') as image_file:
                    image_file.write(item['image'])
                created.append(target)
                connection.execute('INSERT INTO characters VALUES (?,?,?,?,?,?,?,?,?,?)',
                                   (character_id,digest,item['name'],normalized,item['role'],json.dumps(item['tags']),item['notes'],item['rarity'],0,time.time()))
                if pack_id:
                    connection.execute('INSERT INTO pack_characters VALUES (?,?)', (character_id, pack_id))
                added += 1
        except BaseException:
            for target in created:
                target.unlink(missing_ok=True)
            raise
    return {'added':added, 'duplicates':duplicate, 'invalid':invalid}


def draw_character(connection, bot_id):
    counts = {row['rarity']:row['n'] for row in connection.execute(
        'SELECT rarity, COUNT(*) AS n FROM characters WHERE drawn=0 GROUP BY rarity').fetchall()}
    if not counts:
        count = connection.execute('SELECT COUNT(*) FROM characters').fetchone()[0]
        if not count:
            return None
        connection.execute('UPDATE characters SET drawn=0')
        counts = {row['rarity']:row['n'] for row in connection.execute(
            'SELECT rarity, COUNT(*) AS n FROM characters WHERE drawn=0 GROUP BY rarity').fetchall()}
    buckets = [(rarity, RARITY_WEIGHTS[rarity]) for rarity in RARITY_WEIGHTS if counts.get(rarity, 0)]
    pick = secrets.randbelow(sum(weight for _,weight in buckets))
    rarity = buckets[-1][0]
    for candidate, weight in buckets:
        if pick < weight:
            rarity = candidate
            break
        pick -= weight
    offset = secrets.randbelow(counts[rarity])
    character = connection.execute('SELECT id,name,role,tags,notes,rarity FROM characters WHERE drawn=0 AND rarity=? ORDER BY id LIMIT 1 OFFSET ?', (rarity,offset)).fetchone()
    connection.execute('UPDATE characters SET drawn=1 WHERE id=?',(character['id'],))
    connection.execute('INSERT INTO bot_characters VALUES (?,?,?)',(bot_id,character['id'],time.time()))
    return character_for_bot(character, bot_id)


def character_for_bot(row, bot_id):
    return {'name':row['name'], 'role':row['role'], 'tags':json.loads(row['tags']), 'notes':row['notes'],
            'rarity':row['rarity'], 'avatar_url':f'/api/bots/{bot_id}/avatar'}
