#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Query or explicitly request the local night-light setting; never starts a daemon."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.lib import runner  # noqa: E402


def command(args, run=runner.run):
    response = run(('hyprctl', 'hyprsunset', *args), 5.0)
    if response is None or response.timed_out or not response.ok:
        raise ValueError('night-light service unavailable')
    text = response.stdout.strip()
    if len(text) > 128:
        raise ValueError('invalid night-light response')
    return text


def operate(action, temperature=None, run=runner.run):
    if action == 'set':
        if type(temperature) is not int or not 1000 <= temperature <= 20000:
            raise ValueError('temperature must be an integer from 1000 to 20000')
        if command(('temperature', str(temperature)), run) != 'ok':
            raise ValueError('night-light request rejected')
    elif action == 'disable':
        if command(('identity',), run) != 'ok':
            raise ValueError('night-light request rejected')
    elif action != 'read':
        raise ValueError('invalid night-light action')
    identity = command(('identity', 'get'), run)
    temp = command(('temperature',), run)
    if identity not in ('true', 'false') or not re.fullmatch(r'[0-9]{1,5}', temp) or not 1000 <= int(temp) <= 20000:
        raise ValueError('invalid night-light state')
    return {'enabled': identity == 'false', 'temperature': int(temp)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('read', 'set', 'disable'))
    parser.add_argument('temperature', type=int, nargs='?')
    args = parser.parse_args(argv)
    if (args.action == 'set') != (args.temperature is not None):
        parser.error('temperature is required only for set')
    try:
        print(json.dumps(operate(args.action, args.temperature), separators=(',', ':')))
        return 0
    except (OSError, ValueError) as exc:
        print(f'night light: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
