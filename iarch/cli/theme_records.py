# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Read and write the theme selection and user overrides without changing packs."""
import json
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


def write_overrides(data, env=None):
    validate_overrides(data)
    configstore.atomic_write(overrides_path(env), json.dumps(data, indent=2, ensure_ascii=False) + '\n', validate_json=True)
