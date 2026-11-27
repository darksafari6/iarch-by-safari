#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Play a validated dynamic pack event with bounded execution and no shell."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.cli import shell_runtime, theme_packs  # noqa: E402
from iarch.lib import runner  # noqa: E402

EVENTS = frozenset(('notification', 'volume', 'switch'))


def play(pack_id, event, *, env=None, run=runner.run, lookup=None):
    if event not in EVENTS:
        raise ValueError('unknown sound event')
    lookup = lookup or (lambda value: theme_packs.find_dynamic(value, env))
    path = Path(lookup(pack_id))
    runtime = shell_runtime.ThemeRuntime(env, pack_lookup=lambda _: path)
    docs = runtime.load(pack_id)
    sound = docs['sounds']['events'][event]
    overrides = docs['user_overrides']
    if not sound['enabled'] or overrides['sounds_enabled'] is False:
        return {'played': False, 'reason': 'disabled'}
    volume = sound['volume'] if overrides['volume'] is None else overrides['volume']
    file = str(path / sound['file'])
    # No shell; only try the alternate player if the first is absent. A playback
    # error must not cause two simultaneous players or be misreported as success.
    result = run(('pw-play', '--volume', str(volume), file), 10.0, env=env)
    if result is None:
        result = run(('paplay', '--volume=' + str(round(volume * 65536)), file), 10.0, env=env)
    if result is None:
        raise ValueError('no sound player available')
    if result.timed_out or not result.ok:
        raise ValueError('sound player failed or timed out')
    return {'played': True, 'reason': ''}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pack_id')
    parser.add_argument('event', choices=sorted(EVENTS))
    args = parser.parse_args(argv)
    try:
        print(json.dumps(play(args.pack_id, args.event), separators=(',', ':')))
        return 0
    except (ValueError, OSError, ImportError) as exc:
        print(f'shell sound: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
