# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Safe, bounded import and export of dynamic theme-pack archives.

Archives contain one top-level pack directory. Members are checked before any
are written, and extraction never uses tarfile.extract or follows links.
"""
import os
import re
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from iarch.cli.theme_pack_validate import MAX_FILE, MAX_TOTAL, PackError, validate_pack

MAX_ARCHIVE = 2 * 1024 * 1024
MAX_MEMBERS = 256
PACK_ID = re.compile(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$')


def export_pack(source, destination):
    source, destination = Path(source), Path(destination)
    docs = validate_pack(source)
    if destination.exists():
        raise PackError('destination already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as f:
            tmp = Path(f.name)
        with tarfile.open(tmp, 'w:gz') as archive:
            archive.add(source, arcname=docs['theme']['id'], recursive=True)
        if tmp.stat().st_size > MAX_ARCHIVE:
            raise PackError('archive exceeds compressed size limit')
        # Avoid overwriting a destination created concurrently.
        os.link(tmp, destination)
    except (OSError, tarfile.TarError) as exc:
        raise PackError(f'export failed: {exc}') from exc
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return destination


def import_pack(archive_path, destination, *, force=False):
    archive_path, destination = Path(archive_path), Path(destination)
    try:
        if archive_path.stat().st_size > MAX_ARCHIVE:
            raise PackError('archive exceeds compressed size limit')
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.iarch-import-', dir=destination) as temp:
            temp = Path(temp)
            with tarfile.open(archive_path, 'r:gz') as archive:
                members = archive.getmembers()
                if not members or len(members) > MAX_MEMBERS:
                    raise PackError('invalid archive member count')
                seen, root, total = set(), None, 0
                for member in members:
                    raw = member.name
                    parts = PurePosixPath(raw).parts
                    if (not parts or raw.startswith('/') or '\\' in raw or
                            any(p in ('.', '..') for p in raw.split('/')) or
                            not PACK_ID.fullmatch(parts[0])):
                        raise PackError(f'unsafe archive path: {raw}')
                    if root is None:
                        root = parts[0]
                    if parts[0] != root or raw in seen:
                        raise PackError('multiple roots or duplicate archive entry')
                    seen.add(raw)
                    if not (member.isdir() or member.isfile()) or member.mode & 0o111 and member.isfile():
                        raise PackError(f'unsafe archive member: {raw}')
                    if member.size > MAX_FILE:
                        raise PackError('archive member exceeds size limit')
                    total += member.size
                    if total > MAX_TOTAL:
                        raise PackError('archive exceeds unpacked size limit')
                for member in members:
                    target = temp.joinpath(*PurePosixPath(member.name).parts)
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        stream = archive.extractfile(member)
                        if stream is None:
                            raise PackError('unreadable archive member')
                        with stream, target.open('xb') as out:
                            shutil.copyfileobj(stream, out)
            source = temp / root
            validate_pack(source)
            target = destination / root
            if target.exists() or target.is_symlink():
                if not force:
                    raise PackError('pack already exists; use force to replace it')
                if target.is_symlink() or not target.is_dir():
                    raise PackError('destination is not a real directory')
                # Rename the old pack aside before replacement and restore on failure.
                backup = temp / '.previous'
                target.rename(backup)
                try:
                    source.rename(target)
                except OSError:
                    backup.rename(target)
                    raise
            else:
                source.rename(target)
            return target
    except (OSError, tarfile.TarError, EOFError) as exc:
        raise PackError(f'import failed: {exc}') from exc
