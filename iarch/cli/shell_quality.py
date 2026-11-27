#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Read or save the dynamic shell's preferred quality without changing a pack."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.cli import theme_engine, theme_records  # noqa: E402
from iarch.lib import configstore  # noqa: E402


def current(env=None):
    return theme_records.read_overrides(env).get('quality') or 'balanced'


def set_preference(level, env=None, run=None, reload=True):
    if level not in ('ultra', 'high', 'balanced', 'low', 'default'):
        raise ValueError('invalid shell quality')
    changed = theme_records.set_quality(None if level == 'default' else level, env)
    result = {'quality': 'balanced' if level == 'default' else level,
              'changed': changed, 'reload': 'not-requested'}
    if reload:
        answer = theme_engine.ipc_call(theme_engine.IPC_TARGET_THEME, 'reload', run=run)
        result['reload'] = ('queued' if answer is not None and not answer.timed_out
                            and answer.ok and answer.stdout.strip().lower() == 'true'
                            else 'unavailable-or-rejected')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('level', nargs='?', choices=('ultra', 'high', 'balanced', 'low', 'default'))
    parser.add_argument('--no-reload', action='store_true', help='save without asking a running shell to reload')
    args = parser.parse_args(argv)
    try:
        if args.level is None:
            if args.no_reload:
                parser.error('--no-reload requires a level')
            print(current())
        else:
            result = set_preference(args.level, reload=not args.no_reload)
            print(f"quality preference: {result['quality']} ({'saved' if result['changed'] else 'unchanged'})")
            if result['reload'] == 'queued':
                print('theme reload queued; live application has not been verified')
            elif result['reload'] == 'unavailable-or-rejected':
                print('shell reload unavailable or rejected; preference is saved for the next theme load', file=sys.stderr)
        return 0
    except (ValueError, OSError, ImportError, configstore.ConfigError) as exc:
        print(f'shell quality: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
