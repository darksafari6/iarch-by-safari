# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Validate an untrusted dynamic theme directory without executing its contents.

Validation is read-only. Wallpaper recipes are validated but not rendered here.
Archive extraction has additional requirements and must not rely on this directory
validator to make unsafe extraction safe.
"""
import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
FILES = ('theme', 'palette', 'layout', 'motion', 'sounds', 'hypr', 'apps')
MAX_TOTAL = 8 * 1024 * 1024
MAX_FILE = 2 * 1024 * 1024
COLOR = re.compile(r'#[0-9a-fA-F]{3,8}\b')


class PackError(ValueError):
    """A pack is invalid or unsafe to consume."""


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackError(f'duplicate key: {key}')
        result[key] = value
    return result


def _load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique,
                          parse_constant=lambda value: (_ for _ in ()).throw(PackError(f'invalid number: {value}')))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackError(f'{path}: {exc}') from exc


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _safe_string(s, name):
    # Reject filesystem escape spellings, including Windows paths on Unix.
    if '\x00' in s or s.startswith(('/', '~', '\\')) or re.match(r'^[A-Za-z]:[\\/]', s):
        raise PackError(f'{name}: absolute path or unsafe string')
    if '..' in re.split(r'[/\\]', s):
        raise PackError(f'{name}: parent traversal')
    if name != 'palette' and COLOR.search(s):
        raise PackError(f'{name}: colour literal outside palette.json')


def _inventory(path):
    if path.is_symlink() or not path.is_dir():
        raise PackError('pack root must be a real directory')
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            item = Path(root) / name
            info = item.lstat()
            rel = item.relative_to(path).as_posix()
            if stat.S_ISLNK(info.st_mode):
                raise PackError(f'{rel}: symlink forbidden')
            if stat.S_ISDIR(info.st_mode):
                if rel not in ('sounds', 'preview', 'wallpapers'):
                    raise PackError(f'{rel}: unknown directory')
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o111:
                raise PackError(f'{rel}: non-regular or executable file')
            if info.st_nlink != 1:
                raise PackError(f'{rel}: hard link forbidden')
            allowed = rel in {f'{n}.json' for n in FILES}
            allowed |= bool(re.fullmatch(r'sounds/[a-zA-Z0-9._-]+\.(ogg|wav)', rel))
            allowed |= bool(re.fullmatch(r'preview/[a-zA-Z0-9._-]+\.png', rel))
            allowed |= bool(re.fullmatch(r'wallpapers/[a-zA-Z0-9._-]+\.json', rel))
            if not allowed:
                raise PackError(f'{rel}: unknown file')
            if info.st_size > MAX_FILE:
                raise PackError(f'{rel}: file exceeds size limit')
            total += info.st_size
            if total > MAX_TOTAL:
                raise PackError('pack exceeds unpacked size limit')


def validate_pack(path, *, require_directory_id=True):
    """Return validated documents; raise PackError for malformed or unsafe input."""
    try:
        from jsonschema import Draft7Validator
    except ImportError as exc:
        raise PackError('jsonschema is required for pack validation') from exc
    path = Path(path)
    _inventory(path)
    docs = {}
    for name in FILES:
        doc = _load(path / f'{name}.json')
        schema_name = 'theme-pack' + (f'-{name}' if name != 'theme' else '')
        schema = _load(ROOT / 'data' / 'schemas' / f'{schema_name}.schema.json')
        errors = sorted(Draft7Validator(schema).iter_errors(doc), key=lambda e: list(map(str, e.absolute_path)))
        if errors:
            raise PackError(f'{name}.json: {errors[0].message}')
        for s in _strings(doc):
            _safe_string(s, name)
        docs[name] = doc
    theme = docs['theme']
    if require_directory_id and path.name != theme['id']:
        raise PackError('manifest id does not match directory name')
    if any(doc['id'] != theme['id'] for doc in docs.values()):
        raise PackError('document ids do not match manifest')
    if docs['palette']['mode'] != theme['mode']:
        raise PackError('palette mode does not match manifest')
    classic = _load(ROOT / 'data/themes/ids.json')
    if theme['id'] in {x['id'] for x in classic['themes']}:
        raise PackError('id collides with a Classic theme')
    licenses = _load(ROOT / 'data/licenses.json')
    if set(theme['credits']) - {x['id'] for x in licenses['components']}:
        raise PackError('unknown credit id')
    font = _load(ROOT / 'data/design/tokens.json')['font']
    families = {font[k] for k in ('ui', 'ui_display', 'mono', 'emoji')} | {f['family'] for f in font['fallback']}
    if set(theme['fonts'].values()) - families:
        raise PackError('unknown font family')
    surfaces = docs['layout']['surfaces']
    if set(theme['variants']) != {f"{k}:{v['variant']}" for k, v in surfaces.items()}:
        raise PackError('manifest variants do not match layout')
    sizes = docs['layout']['sizes']
    for name, surface in surfaces.items():
        if surface['size'] not in sizes:
            raise PackError(f'{name}: unknown size token')
    hypr = docs['hypr']
    for token in (hypr['gaps_in'], hypr['gaps_out'], hypr['border_width'], hypr['blur']['size'], hypr['shadow']['range'], docs['apps']['cursor']['size']):
        if token not in sizes:
            raise PackError(f'unknown size token: {token}')
    if hypr['rounding'] not in theme['shape']['radius']:
        raise PackError('unknown radius token')
    colors = docs['palette']['colors']
    apps = docs['apps']
    for token in (hypr['active_border'], hypr['inactive_border'], hypr['shadow']['color'], apps['gtk']['accent'], apps['kitty']['foreground'], apps['kitty']['background'], apps['kitty']['cursor'], apps['fish']['command'], apps['fish']['error'], apps['starship']['accent']):
        if token not in colors:
            raise PackError(f'unknown colour token: {token}')
    recipe_schema = _load(ROOT / 'data/schemas/theme-pack-wallpaper.schema.json')
    for recipe_path in sorted((path / 'wallpapers').glob('*.json')):
        recipe = _load(recipe_path)
        errors = list(Draft7Validator(recipe_schema).iter_errors(recipe))
        if errors:
            raise PackError(f'{recipe_path.name}: {errors[0].message}')
        for value in _strings(recipe):
            _safe_string(value, 'wallpapers')
        if recipe['id'] != theme['id'] or recipe['size'] not in sizes or set(recipe['colors']) - colors.keys():
            raise PackError(f'{recipe_path.name}: invalid wallpaper references')
    for event in docs['sounds']['events'].values():
        if event['enabled'] and not (path / PurePosixPath(event['file'])).is_file():
            raise PackError(f"missing sound: {event['file']}")
    return docs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args(argv)
    try:
        docs = validate_pack(args.directory)
    except PackError as exc:
        print(f'invalid pack: {exc}', file=sys.stderr)
        return 1
    print(f"valid pack: {docs['theme']['id']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
