# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Theme catalogue and validated user-pack discovery."""
import json
from pathlib import Path

from iarch.cli.theme_pack_validate import PackError, validate_pack
from iarch.lib import configstore

ROOT = Path(__file__).resolve().parents[2]


def user_packs_dir(env=None):
    return configstore.config_dir(env) / 'themes'


def catalogue(env=None):
    records = json.loads((ROOT / 'data/design/themes.json').read_text(encoding='utf-8'))['themes']
    result = [dict(x) for x in records if x['status'] != 'reference']
    known = {x['id'] for x in records}
    directory = user_packs_dir(env)
    if directory.is_dir():
        for path in sorted(directory.iterdir()):
            if not path.is_dir() or path.is_symlink():
                continue
            try:
                pack = validate_pack(path)['theme']
            except PackError:
                continue
            if pack['id'] in known:
                continue
            result.append({'id': pack['id'], 'name': pack['name'], 'group': 'dynamic',
                           'engine': 'ishell', 'status': 'imported', 'source_screenshot': None})
    return {'classic': [x for x in result if x['group'] == 'classic'],
            'dynamic': [x for x in result if x['group'] == 'dynamic']}


def find_dynamic(pack_id, env=None):
    # A pack id is a single directory name, never a path.
    import re
    if not re.fullmatch(r'[a-z][a-z0-9]*(-[a-z0-9]+)*', pack_id):
        raise PackError('invalid pack id')
    if pack_id == 'dynamic-reference':
        raise PackError('reference pack is not offered for application or export')
    for path in (user_packs_dir(env) / pack_id, ROOT / 'data/themes' / pack_id):
        if path.exists():
            validate_pack(path)
            return path
    raise PackError(f'no installed dynamic pack: {pack_id}')
