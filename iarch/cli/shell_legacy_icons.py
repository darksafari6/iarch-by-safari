#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Safely remove the obsolete, disabled global icon-colorization setting.

The generated v5.4.1 configuration used the old global key with value false.
Both that release and the later component-specific settings default to false.
A true value is deliberately not migrated here: blindly deleting it could change
user preferences. No service is restarted or reloaded.
"""
import argparse
import copy
import os
import re
import stat
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.lib import configstore  # noqa: E402

MAX_BYTES = 5 * 1024 * 1024
SECTION = re.compile(r'^\s*\[\s*(?:shell|"shell"|\'shell\')\s*\]\s*(?:#.*)?$')
HEADER = re.compile(r'^\s*\[')
LEGACY_FALSE = re.compile(r'^(?P<indent>[ \t]*)app_icon_colorize[ \t]*=[ \t]*false[ \t]*(?P<comment>\#.*)?(?P<eol>\r?\n)?$')


def config_path(env=None):
    env = os.environ if env is None else env
    raw = env.get('XDG_CONFIG_HOME')
    base = Path(raw) if raw else configstore.home_dir(env) / '.config'
    if not base.is_absolute():
        raise ValueError('XDG_CONFIG_HOME must be absolute')
    return base / 'noctalia' / 'config.toml'


def remove_disabled_key(text):
    """Return a minimally edited document and whether it changed.

    Parse before and after and compare every other value; unexpected formatting,
    multiline strings, or a true legacy value are refused rather than guessed.
    """
    document = tomllib.loads(text)
    shell = document.get('shell', {})
    if not isinstance(shell, dict):
        raise ValueError('shell setting is not a table')
    if 'app_icon_colorize' not in shell:
        return text, False
    if shell['app_icon_colorize'] is not False:
        raise ValueError('legacy icon colorization is enabled or invalid; migrate its component settings manually')
    in_shell, matches = False, []
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if SECTION.match(line):
            in_shell = True
        elif HEADER.match(line):
            in_shell = False
        elif in_shell:
            match = LEGACY_FALSE.fullmatch(line)
            if match:
                matches.append((index, match))
    if len(matches) != 1:
        raise ValueError('legacy setting has an unsupported format; no changes made')
    index, match = matches[0]
    comment = match.group('comment')
    lines[index] = (match.group('indent') + comment + (match.group('eol') or '') if comment else '')
    updated = ''.join(lines)
    expected = copy.deepcopy(document)
    del expected['shell']['app_icon_colorize']
    if tomllib.loads(updated) != expected:
        raise ValueError('cannot prove other configuration is unchanged')
    return updated, True


def migrate(path, *, write=False, env=None):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('configuration path must be absolute')
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
        raise ValueError('configuration must be a regular file no larger than 5 MiB')
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError('configuration is too large')
    text = raw.decode('utf-8')
    updated, changed = remove_disabled_key(text)
    if changed and write:
        backup = configstore.backup_of(path, env)
        if backup is None:
            raise ValueError('could not back up configuration')
        if path.is_symlink() or path.read_bytes() != raw:
            raise ValueError('configuration changed during migration; backup preserved')
        configstore.atomic_write(path, updated, validate_json=False)
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='back up and update the existing config')
    parser.add_argument('--config', type=Path, help='absolute config.toml path (default: XDG config path)')
    args = parser.parse_args(argv)
    try:
        path = args.config if args.config is not None else config_path()
        changed = migrate(path, write=args.write)
        if not changed:
            print('No obsolete icon-colorization setting found; no changes made.')
        elif args.write:
            print(f'Updated {path}; a backup was kept. Reload the shell if the warning remains.')
        else:
            print(f'Found the disabled legacy setting in {path}; rerun with --write to back up and remove it.')
        return 0
    except (ValueError, OSError, UnicodeError, configstore.ConfigError) as exc:
        print(f'icon setting migration: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
