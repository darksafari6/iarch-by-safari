#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Bounded JSON-in/JSON-out launcher calculation and search helper.

This helper does not enumerate, launch, or interpret application commands.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.lib.launcher_math import calculate, convert  # noqa: E402
from iarch.lib.launcher_search import rank  # noqa: E402


def respond(request):
    if not isinstance(request, dict):
        raise ValueError('request must be an object')
    action = request.get('action')
    if action == 'calculate' and set(request) == {'action', 'expression'}:
        return {'result': str(calculate(request['expression']))}
    if action == 'convert' and set(request) == {'action', 'expression', 'from', 'to'}:
        return {'result': str(convert(request['expression'], request['from'], request['to']))}
    if action == 'search' and set(request) <= {'action', 'query', 'entries', 'frequency', 'limit'} and 'query' in request and 'entries' in request:
        return {'results': rank(request['query'], request['entries'], request.get('frequency'), request.get('limit', 30))}
    raise ValueError('invalid request')


def main():
    try:
        data = sys.stdin.buffer.read(1048577)
        if len(data) > 1048576:
            raise ValueError('request too large')
        request = json.loads(data.decode('utf-8'), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid number')))
        print(json.dumps(respond(request), ensure_ascii=True, separators=(',', ':')))
        return 0
    except (ValueError, UnicodeError, RecursionError) as exc:
        print('launcher: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
