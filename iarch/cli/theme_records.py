# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Read and write the theme selection and user overrides without changing packs."""
import fcntl
import json
import os
import stat
from contextlib import contextmanager
from pathlib import Path

from iarch.lib import configstore

ROOT = Path(__file__).resolve().parents[2]


def selection_path(env=None):
    return configstore.config_dir(env) / 'theme.json'


def overrides_path(env=None):
    return configstore.config_dir(env) / 'theme-overrides.json'


def read_selection(env=None):
    path = selection_path(env)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        data = {'id': 'forest-night'}
    if not isinstance(data, dict) or not isinstance(data.get('id'), str):
        raise ValueError('invalid theme selection')
    version = data.get('schema_version', 1)
    engine = data.get('engine', 'classic')
    overrides = data.get('overrides', {})
    if version != 1 or engine not in ('classic', 'dynamic') or not isinstance(overrides, dict):
        raise ValueError('unsupported theme selection')
    return {'schema_version': 1, 'id': data['id'], 'engine': engine, 'overrides': overrides}


def write_selection(record, env=None):
    if not isinstance(record, dict) or set(record) != {'schema_version', 'id', 'engine', 'overrides'}:
        raise ValueError('invalid selection keys')
    if record['schema_version'] != 1 or record['engine'] not in ('classic', 'dynamic') or not isinstance(record['id'], str) or not isinstance(record['overrides'], dict):
        raise ValueError('invalid selection values')
    configstore.atomic_write(selection_path(env), json.dumps(record, indent=2) + '\n', validate_json=True)


def read_overrides(env=None):
    path = overrides_path(env)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        data = json.loads((ROOT / 'data/theme-overrides.default.json').read_text(encoding='utf-8'))
    validate_overrides(data)
    return data


def validate_overrides(data):
    from jsonschema import Draft7Validator
    schema = json.loads((ROOT / 'data/schemas/theme-overrides.schema.json').read_text(encoding='utf-8'))
    errors = list(Draft7Validator(schema).iter_errors(data))
    if errors:
        raise ValueError('invalid overrides: ' + errors[0].message)


@contextmanager
def _overrides_lock(env=None):
    """Serialize cooperating read-modify-write operations in the private state dir."""
    directory = configstore.state_dir(env)
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(directory / '.theme-overrides.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'r+') as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise ValueError('override lock is not a regular file')
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _write_overrides_locked(data, env):
    validate_overrides(data)
    path = overrides_path(env)
    if path.is_symlink():
        raise ValueError('refusing a symlink override file')
    # Preserve malformed existing records, rather than replacing them with a
    # seemingly valid update. Also avoid backups and writes for an unchanged file.
    if path.exists():
        previous = read_overrides(env)
        if previous == data:
            return False
        configstore.backup_of(path, env)
    configstore.atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + '\n', validate_json=True)
    return True


def write_overrides(data, env=None):
    with _overrides_lock(env):
        _write_overrides_locked(data, env)


def set_quality(quality, env=None):
    """Atomically update just the quality preference, preserving other overrides."""
    if quality is not None and quality not in ('ultra', 'high', 'balanced', 'low'):
        raise ValueError('invalid shell quality')
    with _overrides_lock(env):
        if overrides_path(env).is_symlink():
            raise ValueError('refusing a symlink override file')
        data = read_overrides(env)
        data['quality'] = quality
        return _write_overrides_locked(data, env)
