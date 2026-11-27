#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Opt in to a development shell config link without replacing user files.

This only links the checked-out configuration; it does not start or enable it.
The shell-switch readiness guard continues to apply.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.lib import configstore  # noqa: E402


def install(env=None, source=None):
    env = os.environ if env is None else env
    source = Path(source) if source is not None else ROOT / 'iarch/shell'
    if not source.is_absolute() or not source.is_dir() or not (source / 'shell.qml').is_file():
        raise ValueError('shell source is not a valid absolute directory')
    raw = env.get('XDG_CONFIG_HOME')
    config = Path(raw) if raw else configstore.home_dir(env) / '.config'
    if not config.is_absolute():
        raise ValueError('XDG_CONFIG_HOME must be absolute')
    parent = config / 'quickshell'
    if not parent.resolve().is_relative_to(config.resolve()):
        raise ValueError('shell config parent escapes the configuration directory')
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / 'iarch'
    if target.is_symlink():
        if target.resolve() == source.resolve(): return target
        raise ValueError('refusing to replace an existing shell config link')
    if target.exists():
        raise ValueError('refusing to replace an existing shell config')
    # symlink creation fails atomically if a competing writer created target.
    target.symlink_to(source, target_is_directory=True)
    return target


def main(argv=None):
    if argv is None: argv = sys.argv[1:]
    if argv:
        print('Usage: iarch-shell setup', file=sys.stderr)
        return 2
    try:
        path = install()
        print(f'linked {path}; not enabled or started (readiness guard still applies)')
        return 0
    except (ValueError, OSError, configstore.ConfigError) as exc:
        print(f'shell setup: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
