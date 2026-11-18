# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Pack-oriented iarch-theme commands. Classic commands remain in theme.py."""
import argparse
import json
import sys

from pathlib import Path

from iarch.cli import (session_theme, theme_pack_apply, theme_pack_archive, theme_pack_preview,
                       theme_pack_render, theme_packs, theme_records)
from iarch.lib import runner
from iarch.cli.theme_pack_validate import PackError, validate_pack


def _play_switch(docs, pack_path):
    event = docs['sounds']['events']['switch']
    overrides = theme_records.read_overrides()
    enabled = event['enabled'] if overrides['sounds_enabled'] is None else overrides['sounds_enabled']
    if not enabled or not event['enabled']:
        return
    volume = event['volume'] if overrides['volume'] is None else overrides['volume']
    answer = runner.run(('paplay', '--volume=' + str(round(volume * 65536)),
                         str(pack_path / event['file'])), 10.0)
    if answer is None or answer.timed_out or not answer.ok:
        raise RuntimeError('switch sound could not be played')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='iarch-theme')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list').add_argument('--json', action='store_true')
    sub.add_parser('current').add_argument('--json', action='store_true')
    p = sub.add_parser('apply')
    p.add_argument('id')
    p.add_argument('--no-transition', action='store_true')
    sub.add_parser('rollback')
    p = sub.add_parser('validate')
    p.add_argument('path')
    p = sub.add_parser('export')
    p.add_argument('id')
    p.add_argument('file')
    p = sub.add_parser('preview')
    p.add_argument('id')
    p = sub.add_parser('import')
    p.add_argument('file')
    p.add_argument('--force', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            groups = theme_packs.catalogue()
            if args.json:
                print(json.dumps(groups, indent=2))
            else:
                for group, entries in groups.items():
                    print(group.title() + ':')
                    for item in entries:
                        print(f"  {item['id']}: {item['name']} ({item['status']})")
        elif args.command == 'current':
            record = theme_records.read_selection()
            print(json.dumps(record, indent=2) if args.json else record['id'])
        elif args.command == 'apply':
            path = theme_packs.find_dynamic(args.id)
            report = theme_pack_apply.apply(path, theme_pack_render.actions, play_sound=_play_switch,
                                            no_transition=args.no_transition)
            print(json.dumps(report, indent=2))
        elif args.command == 'rollback':
            print(json.dumps(theme_pack_apply.rollback(), indent=2))
        elif args.command == 'validate':
            path = Path(args.path)
            if path.is_dir():
                doc = validate_pack(path)
                print(f"valid pack: {doc['theme']['id']}")
            else:
                from jsonschema import Draft7Validator
                data = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data, dict) and 'meta' in data:
                    session_theme.validate_pack(data, data['meta'].get('id'), path)
                else:
                    schema = json.loads((theme_packs.ROOT / 'data/schemas/preset.schema.json').read_text(encoding='utf-8'))
                    errors = list(Draft7Validator(schema).iter_errors(data))
                    if errors:
                        raise ValueError(errors[0].message)
                print(f'valid theme: {path}')
        elif args.command == 'export':
            print(theme_pack_archive.export_pack(theme_packs.find_dynamic(args.id), args.file))
        elif args.command == 'preview':
            print(theme_pack_preview.render_preview(theme_packs.find_dynamic(args.id)))
        elif args.command == 'import':
            print(theme_pack_archive.import_pack(args.file, theme_packs.user_packs_dir(),
                                                  force=args.force, reserved_ids={'dynamic-reference'}))
        return 0
    except (theme_pack_apply.ApplyError, session_theme.SessionThemeError, PackError, ValueError, OSError, ImportError) as exc:
        print(f'iarch-theme: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
