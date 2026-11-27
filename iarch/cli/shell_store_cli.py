#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Serialized local todo/timer/stopwatch operations; JSON requests on stdin."""
import argparse
import fcntl
import json
import os
import stat
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.lib import configstore, shell_store  # noqa: E402


def recover_corrupt(kind, path):
    """Explicitly reset a corrupt regular store, preserving its bytes first.

    The caller holds the store lock. Valid, missing, unreadable and symlinked
    files are never reset. The backup is a hard link to the old inode; the new
    document is installed by the usual atomic replacement.
    """
    validators = {'todo': shell_store._todos, 'timer': shell_store._timer,
                  'stopwatch': shell_store._stopwatch}
    defaults = {'todo': {'schema_version': 1, 'items': []},
                'timer': {'schema_version': 1, 'remaining': 0, 'deadline': None},
                'stopwatch': {'schema_version': 1, 'elapsed': 0, 'started_at': None}}
    if kind not in validators:
        raise ValueError('invalid store')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        source = os.fstat(handle.fileno())
        if not stat.S_ISREG(source.st_mode):
            raise ValueError('store is not a regular file')
        raw = handle.read(shell_store.MAX_BYTES + 1)
        try:
            if len(raw) > shell_store.MAX_BYTES:
                raise shell_store.StoreError('store is too large')
            value = json.loads(raw.decode('utf-8'), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('invalid number')))
            validators[kind](value)
        except (ValueError, UnicodeError):
            pass
        else:
            raise ValueError('store is valid; recovery refused')
        backup = path.with_name(path.name + '.corrupt-' + uuid.uuid4().hex)
        os.link(path, backup, follow_symlinks=False)
        # Leave the backup in place even on failure: it may be the only copy
        # of the original if a non-cooperating process races the replacement.
        linked = backup.stat(follow_symlinks=False)
        current = path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(linked.st_mode) or (linked.st_dev, linked.st_ino) != (source.st_dev, source.st_ino)
                or (current.st_dev, current.st_ino) != (source.st_dev, source.st_ino)):
            raise ValueError('store changed during recovery')
        shell_store._write_private(path, defaults[kind])
    return {'data': defaults[kind], 'backup': str(backup)}


def operate(kind, request, root):
    if not isinstance(request, dict) or not isinstance(request.get('action'), str):
        raise ValueError('invalid request')
    action = request['action']
    path = root / (kind + '.json')
    if action == 'recover' and set(request) == {'action'}:
        return recover_corrupt(kind, path)
    if kind == 'todo':
        document = shell_store.read_todos(path)
        items = document['items']
        if action == 'read' and set(request) == {'action'}:
            return document
        if action == 'add' and set(request) == {'action', 'text'}:
            items.append({'id': uuid.uuid4().hex, 'text': request['text'], 'done': False})
        elif action in ('toggle', 'delete') and set(request) == ({'action', 'id', 'done'} if action == 'toggle' else {'action', 'id'}):
            selected = next((item for item in items if item['id'] == request['id']), None)
            if selected is None:
                raise ValueError('unknown todo item')
            if action == 'delete':
                items.remove(selected)
            else:
                selected['done'] = request['done']
        else:
            raise ValueError('invalid todo action')
        shell_store.write_todos(path, document)
        return document
    if kind == 'timer':
        if action == 'read' and set(request) == {'action'}:
            return shell_store.read_timer(path)
        expected = {'action', 'seconds'} if action == 'set' else {'action'}
        if set(request) != expected:
            raise ValueError('invalid timer request')
        return shell_store.set_timer(path, action, seconds=request.get('seconds'))
    if kind == 'stopwatch':
        if set(request) != {'action'}:
            raise ValueError('invalid stopwatch request')
        return shell_store.read_stopwatch(path) if action == 'read' else shell_store.set_stopwatch(path, action)
    raise ValueError('invalid store')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=('todo', 'timer', 'stopwatch'))
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384:
            raise ValueError('request too large')
        request = json.loads(raw.decode('utf-8'), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('invalid number')))
        root = configstore.state_dir()
        root.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(root / '.shell-stores.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = operate(args.kind, request, root)
        print(json.dumps(result, ensure_ascii=True, separators=(',', ':')))
        return 0
    except (ValueError, OSError, UnicodeError) as exc:
        print(f'shell store: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
