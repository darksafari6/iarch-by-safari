# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Small validated local stores for future shell todo and stopwatch adapters.

Corrupt existing files are refused, not overwritten. All reads and writes are
local; callers decide when to poll or expose data to a surface.
"""
import json
import os
import tempfile
import time
from pathlib import Path

from iarch.lib import configstore

MAX_BYTES = 1024 * 1024
MAX_TODOS = 1000
MAX_TEXT = 1000


class StoreError(ValueError):
    """A store is corrupt, too large or invalid."""


def _read(path, default):
    path = Path(path)
    if path.is_symlink():
        raise StoreError('store is a symlink')
    try:
        if path.stat().st_size > MAX_BYTES:
            raise StoreError('store is too large')
        value = json.loads(path.read_text(encoding='utf-8'),
                           parse_constant=lambda x: (_ for _ in ()).throw(StoreError('invalid number')))
    except FileNotFoundError:
        return default
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StoreError(f'cannot read store: {exc}') from exc
    return value


def _write(path, value):
    # Todo and timer data may contain personal information too.
    _write_private(path, value)


def _todos(value):
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'items'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1):
        raise StoreError('invalid todo store')
    items = value['items']
    if not isinstance(items, list) or len(items) > MAX_TODOS:
        raise StoreError('invalid todo list')
    ids = set()
    for item in items:
        if (not isinstance(item, dict) or set(item) != {'id', 'text', 'done'}
                or not isinstance(item['id'], str) or not item['id'] or len(item['id']) > 80
                or not isinstance(item['text'], str) or not 0 < len(item['text']) <= MAX_TEXT
                or not isinstance(item['done'], bool) or item['id'] in ids):
            raise StoreError('invalid todo item')
        ids.add(item['id'])
    return value


def read_todos(path):
    return _todos(_read(path, {'schema_version': 1, 'items': []}))


def write_todos(path, value):
    # Never destroy an unreadable or invalid existing store while saving.
    read_todos(path)
    _write(path, _todos(value))


def _stopwatch(value):
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'elapsed', 'started_at'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1):
        raise StoreError('invalid stopwatch store')
    for key in ('elapsed', 'started_at'):
        n = value[key]
        if n is None and key == 'started_at':
            continue
        if isinstance(n, bool) or not isinstance(n, (int, float)) or not 0 <= n < 10**12:
            raise StoreError(f'invalid stopwatch {key}')
    return value


def read_stopwatch(path):
    return _stopwatch(_read(path, {'schema_version': 1, 'elapsed': 0, 'started_at': None}))


def stopwatch_elapsed(value, now=None):
    value = _stopwatch(value)
    now = time.time() if now is None else now
    return value['elapsed'] + (max(0, now - value['started_at']) if value['started_at'] is not None else 0)


def set_stopwatch(path, action, now=None):
    now = time.time() if now is None else now
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not 0 <= now < 10**12:
        raise StoreError('invalid clock')
    value = read_stopwatch(path)
    if action == 'start':
        if value['started_at'] is None:
            value['started_at'] = now
    elif action == 'pause':
        value['elapsed'] = stopwatch_elapsed(value, now)
        value['started_at'] = None
    elif action == 'reset':
        value.update(elapsed=0, started_at=None)
    else:
        raise StoreError('unknown stopwatch action')
    _write(path, _stopwatch(value))
    return value


def _timer(value):
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'remaining', 'deadline'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1):
        raise StoreError('invalid timer store')
    for key in ('remaining', 'deadline'):
        number = value[key]
        if key == 'deadline' and number is None:
            continue
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not 0 <= number < 10**12:
            raise StoreError(f'invalid timer {key}')
    return value


def read_timer(path):
    return _timer(_read(path, {'schema_version': 1, 'remaining': 0, 'deadline': None}))


def timer_remaining(value, now=None):
    value = _timer(value)
    now = time.time() if now is None else now
    return max(0, value['deadline'] - now) if value['deadline'] is not None else value['remaining']


def set_timer(path, action, *, seconds=None, now=None):
    now = time.time() if now is None else now
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not 0 <= now < 10**12:
        raise StoreError('invalid clock')
    value = read_timer(path)
    if action == 'set':
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 <= seconds < 10**9:
            raise StoreError('invalid timer duration')
        value.update(remaining=seconds, deadline=None)
    elif action == 'start':
        if value['deadline'] is None and value['remaining'] > 0:
            value['deadline'] = now + value['remaining']
    elif action == 'pause':
        value.update(remaining=timer_remaining(value, now), deadline=None)
    elif action == 'reset':
        value.update(remaining=0, deadline=None)
    else:
        raise StoreError('unknown timer action')
    _write(path, _timer(value))
    return value

# Notification content is local data. Images and action identifiers are stored
# as text only: callers must not execute or fetch them without separate checks.
MAX_NOTIFICATIONS = 200


def _notifications(value):
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'items'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or not isinstance(value['items'], list) or len(value['items']) > MAX_NOTIFICATIONS):
        raise StoreError('invalid notification history')
    for item in value['items']:
        if not isinstance(item, dict) or set(item) != {'app', 'summary', 'body', 'urgency', 'timestamp', 'image', 'actions'}:
            raise StoreError('invalid notification')
        for field, maximum in (('app', 200), ('summary', 1000), ('body', 4000), ('image', 2048)):
            if not isinstance(item[field], str) or len(item[field]) > maximum:
                raise StoreError(f'invalid notification {field}')
        if item['urgency'] not in ('low', 'normal', 'critical'):
            raise StoreError('invalid notification urgency')
        timestamp = item['timestamp']
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not 0 <= timestamp < 10**12:
            raise StoreError('invalid notification timestamp')
        actions = item['actions']
        if (not isinstance(actions, list) or len(actions) > 20
                or not all(isinstance(action, dict) and set(action) == {'id', 'label'}
                           and all(isinstance(action[k], str) and 0 < len(action[k]) <= 200
                                   for k in ('id', 'label')) for action in actions)):
            raise StoreError('invalid notification actions')
    return value


def read_notifications(path):
    return _notifications(_read(path, {'schema_version': 1, 'items': []}))


def _write_private(path, value):
    """Atomically replace private history with mode 0600, including new files."""
    path = Path(path)
    if path.is_symlink():
        raise StoreError('store is a symlink')
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise StoreError('store would be too large')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                         prefix='.notifications.', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink():
            raise StoreError('store is a symlink')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def append_notification(path, item):
    """Append a validated record, retaining at most the most recent 200."""
    history = read_notifications(path)
    _notifications({'schema_version': 1, 'items': [item]})
    history['items'] = (history['items'] + [item])[-MAX_NOTIFICATIONS:]
    # Large messages may hit the byte ceiling before the item ceiling.
    while len(history['items']) > 1 and len((json.dumps(history, ensure_ascii=False, indent=2) + '\n').encode('utf-8')) > MAX_BYTES:
        history['items'].pop(0)
    _write_private(path, history)
    return history
