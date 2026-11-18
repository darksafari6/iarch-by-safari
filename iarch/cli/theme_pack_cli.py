# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Pack-oriented iarch-theme commands. Classic commands remain in theme.py."""
import argparse
import json
import sys

from iarch.cli import theme_pack_archive, theme_pack_preview, theme_packs, theme_records
from iarch.cli.theme_pack_validate import PackError, validate_pack


def main(argv=None):
    parser = argparse.ArgumentParser(prog='iarch-theme')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list').add_argument('--json', action='store_true')
    sub.add_parser('current').add_argument('--json', action='store_true')
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
        elif args.command == 'validate':
            doc = validate_pack(args.path)
            print(f"valid pack: {doc['theme']['id']}")
        elif args.command == 'export':
            print(theme_pack_archive.export_pack(theme_packs.find_dynamic(args.id), args.file))
        elif args.command == 'preview':
            print(theme_pack_preview.render_preview(theme_packs.find_dynamic(args.id)))
        elif args.command == 'import':
            print(theme_pack_archive.import_pack(args.file, theme_packs.user_packs_dir(),
                                                  force=args.force, reserved_ids={'dynamic-reference'}))
        return 0
    except (PackError, ValueError, OSError, ImportError) as exc:
        print(f'iarch-theme: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
