#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Capture an explicitly requested screenshot into a private user-state folder."""
import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.lib import configstore, runner  # noqa: E402

REGION = re.compile(r'^-?\d{1,7},-?\d{1,7} [1-9]\d{0,5}x[1-9]\d{0,5}$')


def capture_directory(state_dir=None):
    base = Path(state_dir) if state_dir is not None else configstore.state_dir()
    base.mkdir(parents=True, exist_ok=True)
    directory = base / 'captures'
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('capture directory must be private and owned by the user')
    return directory


def capture(mode, *, state_dir=None, select=runner.run, run=subprocess.run):
    if mode not in ('screen', 'region'):
        raise ValueError('unknown capture mode')
    args = ['grim', '-t', 'png']
    if mode == 'region':
        selected = select(('slurp',), 120.0)
        if selected is None or selected.timed_out or not selected.ok:
            raise ValueError('region selection cancelled or unavailable')
        geometry = selected.stdout.strip()
        if not REGION.fullmatch(geometry):
            raise ValueError('invalid capture geometry')
        args += ['-g', geometry]
    args.append('-')  # write the screenshot to our already-open private file
    directory = capture_directory(state_dir)
    fd, name = tempfile.mkstemp(prefix='.capture-', suffix='.tmp', dir=directory)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as output:
            result = run(args, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.PIPE, timeout=30, check=False)
            output.flush()
            os.fsync(output.fileno())
        if result.returncode != 0 or temporary.stat().st_size < 8:
            raise ValueError('screenshot failed')
        with temporary.open('rb') as image:
            if image.read(8) != b'\x89PNG\r\n\x1a\n':
                raise ValueError('invalid screenshot output')
        final = directory / (temporary.name.removeprefix('.capture-').removesuffix('.tmp') + '.png')
        os.link(temporary, final, follow_symlinks=False)
        return {'path': str(final)}
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('screenshot tool unavailable or timed out') from exc
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('screen', 'region'))
    args = parser.parse_args(argv)
    try:
        print(json.dumps(capture(args.mode), separators=(',', ':')))
        return 0
    except (ValueError, OSError) as exc:
        print(f'screenshot: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
