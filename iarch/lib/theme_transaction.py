# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Durable, lock-serialized step runner for theme operations.

Inputs: named steps with JSON payloads and do/verify/idempotent undo handlers.
Outputs: a private journal recording every attempted step and its compensation.
Recovery requires the caller to supply the same allowlisted handler registry.
This module does not itself switch engines or render or restore any files.
"""
import json
import os
import re
import stat
import uuid
from pathlib import Path

from iarch.lib import configstore, session_lock

ID_PATTERN = re.compile(r'^[0-9a-f]{32}$')
NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')
MAX_JOURNAL_BYTES = 4 * 1024 * 1024


class TransactionError(RuntimeError):
    """The operation failed; journal_path identifies the recovery record."""
    def __init__(self, message, journal_path=None):
        super().__init__(message)
        self.journal_path = journal_path


def _directory(env):
    directory = configstore.state_dir(env) / 'transactions'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        raise TransactionError('transaction directory must be private and owned by the user')
    return directory


def _path(env, transaction_id):
    if not isinstance(transaction_id, str) or not ID_PATTERN.fullmatch(transaction_id):
        raise TransactionError('invalid transaction id')
    return _directory(env) / (transaction_id + '.json')


def _write(path, journal):
    text = json.dumps(journal, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    if len(text.encode('utf-8')) > MAX_JOURNAL_BYTES:
        raise TransactionError('transaction journal exceeds size limit', path)
    configstore.atomic_write(path, text, validate_json=True)


def _read(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JOURNAL_BYTES:
            raise ValueError('invalid journal file')
        value = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(value, dict) or value.get('schema_version') != 1
                or value.get('id') != path.stem or value.get('state') not in
                ('active', 'undoing', 'recovery_needed', 'committed', 'rolled_back')
                or not isinstance(value.get('steps'), list)):
            raise ValueError('invalid journal structure')
        for step in value['steps']:
            if (not isinstance(step, dict) or set(step) != {'name', 'payload', 'state'}
                    or not isinstance(step['name'], str) or not NAME_PATTERN.fullmatch(step['name'])
                    or step['state'] not in ('pending', 'running', 'done', 'undoing', 'undone')):
                raise ValueError('invalid journal step')
        return value
    except (OSError, ValueError, TypeError) as exc:
        raise TransactionError(f'cannot read transaction journal: {exc}', path) from exc


def _compensate(path, journal, handlers):
    journal['state'] = 'undoing'
    _write(path, journal)
    for step in reversed(journal['steps']):
        if step['state'] not in ('running', 'done', 'undoing'):
            continue
        handler = handlers.get(step['name'])
        if handler is None:
            journal['state'] = 'recovery_needed'
            _write(path, journal)
            raise TransactionError('missing recovery handler: ' + step['name'], path)
        step['state'] = 'undoing'
        _write(path, journal)
        try:
            handler.undo(step['payload'])
        except Exception as exc:
            journal['state'] = 'recovery_needed'
            _write(path, journal)
            raise TransactionError(f'undo of {step["name"]} failed: {exc}', path) from exc
        step['state'] = 'undone'
        _write(path, journal)
    journal['state'] = 'rolled_back'
    _write(path, journal)
    return journal


def execute(steps, handlers, *, env=None):
    """Execute steps, verifying each; on error undo every attempted step in reverse."""
    with session_lock.session_lock(env):
        directory = _directory(env)
        for existing in directory.glob('*.json'):
            record = _read(existing)
            if record['state'] not in ('committed', 'rolled_back'):
                raise TransactionError('unfinished theme transaction; recover it first', existing)
        entries = []
        for name, payload in steps:
            if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name) or name not in handlers:
                raise TransactionError('unrecognized transaction step')
            # Ensure data can be journalled before performing any operation.
            json.dumps(payload, allow_nan=False)
            entries.append({'name': name, 'payload': payload, 'state': 'pending'})
        if not entries:
            raise TransactionError('transaction has no steps')
        transaction_id = uuid.uuid4().hex
        path = _path(env, transaction_id)
        journal = {'schema_version': 1, 'id': transaction_id, 'state': 'active', 'steps': entries}
        _write(path, journal)
        try:
            for step in entries:
                step['state'] = 'running'
                _write(path, journal)
                handler = handlers[step['name']]
                handler.do(step['payload'])
                if not handler.verify(step['payload']):
                    raise RuntimeError('verification failed: ' + step['name'])
                step['state'] = 'done'
                _write(path, journal)
            journal['state'] = 'committed'
            _write(path, journal)
            return journal
        except Exception as exc:
            try:
                _compensate(path, journal, handlers)
            except Exception as undo_error:
                raise TransactionError(f'{exc}; recovery incomplete: {undo_error}', path) from exc
            raise TransactionError(str(exc), path) from exc


def recover(transaction_id, handlers, *, env=None):
    """Idempotently undo an interrupted journal; never redo forward operations."""
    with session_lock.session_lock(env):
        path = _path(env, transaction_id)
        journal = _read(path)
        if journal['state'] in ('committed', 'rolled_back'):
            return journal
        return _compensate(path, journal, handlers)
