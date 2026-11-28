# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Serialize cooperating shell switches and theme transactions.

Input: an optional iArch environment mapping. Output: an exclusive, reentrant
process/thread lock on the private state directory's shell-switch.lock. The
lock is advisory and cannot constrain unrelated programs or direct file edits.
"""
import fcntl
import os
import stat
import threading
from contextlib import contextmanager

from iarch.lib import configstore

_mutex = threading.RLock()
_local = threading.local()


@contextmanager
def session_lock(env=None):
    directory = configstore.state_dir(env)
    path = directory / 'shell-switch.lock'
    with _mutex:
        active = getattr(_local, 'path', None)
        if active is not None:
            if active != path:
                raise ValueError('cannot nest locks for different iArch state directories')
            yield
            return
        directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'r+') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('session lock must be an unlinked regular file')
            fcntl.flock(stream, fcntl.LOCK_EX)
            _local.path = path
            try:
                yield
            finally:
                _local.path = None
                fcntl.flock(stream, fcntl.LOCK_UN)
