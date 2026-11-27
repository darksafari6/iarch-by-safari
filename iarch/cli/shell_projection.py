#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Produce a bounded, validated shell projection without changing the session.

This helper is a building block, not a running shell or an IPC handler. It uses
exactly the pack and overrides validators used by the command line runtime.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iarch.cli import shell_runtime, theme_records, theme_packs  # noqa: E402


def build(pack_id=None, env=None, quality=None, reduce_motion=False):
    if pack_id is None:
        selection = theme_records.read_selection(env)
        if selection['engine'] != 'dynamic':
            raise shell_runtime.RuntimeError('selected theme is not dynamic')
        pack_id = selection['id']
    runtime = shell_runtime.ThemeRuntime(env)
    runtime.load(pack_id)
    return {'schema_version': 1, 'theme': runtime.projection(quality, reduce_motion),
            'surfaces': runtime.snapshot['layout']['surfaces']}


def reference_preview():
    """The bundled test pack is preview-only, never an applicable session pack."""
    path = theme_packs.ROOT / 'data/themes/dynamic-reference'
    runtime = shell_runtime.ThemeRuntime(pack_lookup=lambda _: path, reference_preview=True)
    runtime.load('dynamic-reference')
    return {'schema_version': 1, 'theme': runtime.projection(),
            'surfaces': runtime.snapshot['layout']['surfaces']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('id', nargs='?', help='pack ID; omit to use the selected dynamic pack')
    parser.add_argument('--quality', choices=('ultra', 'high', 'balanced', 'low'), default=None,
                        help='override the saved quality for this projection')
    parser.add_argument('--reduce-motion', action='store_true')
    parser.add_argument('--reference-preview', action='store_true', help='preview the bundled test pack; never select or apply it')
    parser.add_argument('--list', action='store_true', help='list currently installed, validated dynamic pack IDs')
    args = parser.parse_args(argv)
    try:
        if args.list:
            if args.id or args.reference_preview or args.reduce_motion or args.quality is not None:
                parser.error('--list cannot be combined with projection options')
            result = [entry['id'] for entry in theme_packs.catalogue()['dynamic']
                      if entry['status'] in ('imported', 'shipped')][:256]
        elif args.reference_preview:
            if args.id or args.reduce_motion or args.quality is not None:
                parser.error('--reference-preview cannot be combined with projection options')
            result = reference_preview()
        else:
            result = build(args.id, quality=args.quality, reduce_motion=args.reduce_motion)
    except (ValueError, OSError, ImportError) as exc:
        print(f'shell projection: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
