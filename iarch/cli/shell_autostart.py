#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Generate an opt-in user unit that delegates to the guarded engine switch.

Writing a unit does not enable it, start a shell, or install a shell entry point.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.lib import configstore  # noqa: E402

BODY = '''[Unit]
Description=iArch by Safari dynamic shell (opt-in)
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=oneshot
ExecStart=%h/.local/bin/iarch-shell start

[Install]
WantedBy=graphical-session.target
'''
MARKER = configstore.header_for(Path('iarch-shell.service'))


def unit_path(env=None):
    env = os.environ if env is None else env
    value = env.get('XDG_CONFIG_HOME')
    root = Path(value) if value else configstore.home_dir(env) / '.config'
    if not root.is_absolute():
        raise ValueError('XDG_CONFIG_HOME must be absolute')
    target = root / 'systemd/user/iarch-shell.service'
    if not target.parent.resolve().is_relative_to(root.resolve()):
        raise ValueError('unit parent escapes the configuration directory')
    return target


def install(env=None):
    path = unit_path(env)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('refusing a symlink or non-file unit')
    expected = MARKER + '\n' + BODY + '\n'
    if path.exists():
        old = path.read_text(encoding='utf-8')
        if not old.startswith(MARKER + '\n'):
            raise ValueError('refusing to overwrite a foreign unit')
        if old == expected:
            return path
    configstore.write_generated(path, BODY, env)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='write the unit, without enabling or starting it')
    args = parser.parse_args(argv)
    try:
        if args.write:
            print(f'wrote {install()}; not enabled or started')
        else:
            print(MARKER + '\n' + BODY, end='')
        return 0
    except (ValueError, OSError, configstore.ConfigError) as exc:
        print(f'shell autostart: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
