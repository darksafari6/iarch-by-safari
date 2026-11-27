#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Reject literal hex colours in QML outside the shared Theme defaults."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / 'iarch/shell'
HEX_COLOR = re.compile(r'#[0-9a-fA-F]{3,8}(?![0-9a-fA-F])')


def findings(root=SHELL):
    result = []
    for path in sorted(Path(root).rglob('*.qml')):
        if path.relative_to(root).as_posix() == 'runtime/Theme.qml':
            continue
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if HEX_COLOR.search(line):
                result.append((path, number))
    return result


def main():
    issues = findings()
    for path, line in issues:
        print(f'{path}:{line}: literal colour belongs in Theme defaults', file=sys.stderr)
    print(f'QML colour lint: {len(issues)} finding(s)')
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
