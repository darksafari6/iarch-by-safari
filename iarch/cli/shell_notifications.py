#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Read or append bounded private notification history using JSON over stdin."""
import argparse
import fcntl
import os
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.lib import configstore, dbus_probe, shell_store  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('read', 'append', 'owner'))
    parser.add_argument('--pid', type=int)
    args = parser.parse_args(argv)
    try:
        if args.action == 'owner':
            if args.pid is None or args.pid <= 1:
                raise ValueError('valid shell process id required')
            owner = dbus_probe.notification_server()
            result = {'available': owner.searched and owner.pid == args.pid,
                      'error': '' if owner.searched and owner.pid == args.pid else (owner.note or 'notification bus is owned by another process')}
            print(json.dumps(result, ensure_ascii=True, separators=(',', ':')))
            return 0
        if args.pid is not None:
            raise ValueError('--pid is only valid for owner')
        path = configstore.state_dir() / 'notifications.json'
        item = None
        if args.action == 'append':
            raw = sys.stdin.buffer.read(32769)
            if len(raw) > 32768:
                raise ValueError('notification request too large')
            item = json.loads(raw.decode('utf-8'), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('invalid number')))
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path.parent / '.shell-stores.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.action == 'read':
                result = shell_store.read_notifications(path)
            else:
                history = shell_store.append_notification(path, item)
                result = {'ok': True, 'count': len(history['items'])}
        print(json.dumps(result, ensure_ascii=True, separators=(',', ':')))
        return 0
    except (ValueError, OSError, UnicodeError) as exc:
        print(f'notification history: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
