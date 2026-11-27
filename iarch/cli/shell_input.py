#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Explicit, temporary Hyprland input requests; never guesses a device."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.lib import runner  # noqa: E402

# Restrict names to avoid generating arbitrary Lua, including control characters.
NAME = re.compile(r'^[a-zA-Z0-9_.:-]{1,160}$')


def ask(args, run):
    response = run(('hyprctl', *args), 5.0)
    if response is None or response.timed_out or not response.ok:
        raise ValueError('compositor unavailable')
    return response.stdout.strip()


def pointer_names(run=runner.run):
    text = ask(('-j', 'devices'), run)
    if len(text) > 1048576:
        raise ValueError('device response too large')
    try:
        data = json.loads(text)
        mice = data['mice']
        if not isinstance(mice, list) or len(mice) > 256:
            raise ValueError('invalid pointer list')
        return sorted({item['name'] for item in mice if isinstance(item, dict) and isinstance(item.get('name'), str) and NAME.fullmatch(item['name'])})
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('invalid device response') from exc


def request(action, enabled=None, name=None, run=runner.run):
    if action == 'list':
        return {'pointers': pointer_names(run)}
    if type(enabled) is not bool:
        raise ValueError('enabled must be boolean')
    value = 'true' if enabled else 'false'
    if action == 'device':
        if not isinstance(name, str) or not NAME.fullmatch(name) or name not in pointer_names(run):
            raise ValueError('choose an existing explicitly identified pointer')
        # The restricted name contains no Lua quoting characters.
        code = f'hl.device({{name = "{name}", enabled = {value}}})'
    elif action == 'raw':
        if name is not None:
            raise ValueError('raw mode is global')
        code = f'hl.config({{input = {{force_no_accel = {value}}}}})'
    else:
        raise ValueError('unknown input action')
    if ask(('eval', code), run) != 'ok':
        raise ValueError('compositor rejected input request')
    # hl.device schedules a refresh and has no readback here; do not claim it
    # has already taken effect. Reload or session restart may reset this change.
    return {'requested': True, 'verified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('list')
    for action in ('device', 'raw'):
        p = sub.add_parser(action)
        p.add_argument('state', choices=('on', 'off'))
        if action == 'device': p.add_argument('name')
    args = parser.parse_args(argv)
    try:
        result = request(args.action, None if args.action == 'list' else args.state == 'on', getattr(args, 'name', None))
        print(json.dumps(result, separators=(',', ':')))
        return 0
    except (ValueError, OSError) as exc:
        print(f'input: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
