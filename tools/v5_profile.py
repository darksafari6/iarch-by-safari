#!/usr/bin/env python3
"""Stage the minimaOS Noctalia v5 profile or restore an explicit backup.

This changes Noctalia configuration only. Run outside the active shell session.
"""
import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parents[1] / '.config/noctalia'


def config_home():
    value = os.environ.get('NOCTALIA_CONFIG_HOME') or os.environ.get('XDG_CONFIG_HOME')
    root = Path(value) if value else Path.home() / '.config'
    if not root.is_absolute():
        raise ValueError('Noctalia config home must be an absolute path')
    return root


def real_dir(path):
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f'Expected a real directory (not a symlink): {path}')


def checked_noctalia():
    binary = shutil.which('noctalia')
    if not binary:
        raise ValueError('Noctalia v5 binary not found; no changes made')
    version = subprocess.run([binary, '--version'], text=True, capture_output=True, timeout=10, check=True).stdout
    # Schema and CLI were inspected against v5.4.1; fail closed on other releases.
    if not re.match(r'^noctalia v?5\.4\.1(?:\s|$)', version.strip()):
        raise ValueError(f'Noctalia v5.4.1 required, got {version.strip()!r}')
    return binary


def swap(config_dir, stage):
    """Replace the active directory, keeping it as a uniquely named backup."""
    target = config_dir / 'noctalia'
    if target.is_symlink():
        raise ValueError('Refusing to replace a symlinked Noctalia directory')
    backup = None
    if target.exists():
        real_dir(target)
        prefix = 'noctalia.backup.' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.'
        backup = Path(tempfile.mkdtemp(prefix=prefix, dir=config_dir))
        backup.rmdir()
        os.rename(target, backup)
    try:
        os.rename(stage, target)
    except OSError:
        if backup is not None:
            try:
                os.rename(backup, target)
            except OSError as exc:
                raise RuntimeError(f'Could not restore the original directory; recover it from {backup}') from exc
        raise
    return backup


def apply(config_dir, binary):
    real_dir(config_dir)
    target = config_dir / 'noctalia'
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError('Noctalia config must be a real directory, not a symlink or file')
    stage = Path(tempfile.mkdtemp(prefix='.noctalia-stage.', dir=config_dir))
    try:
        if target.exists():
            shutil.copytree(target, stage, symlinks=True, dirs_exist_ok=True)
        # Never follow symlinks or overwrite directories at the two managed paths.
        palette_dir = stage / 'palettes'
        if palette_dir.is_symlink() or (palette_dir.exists() and not palette_dir.is_dir()):
            raise ValueError('Refusing a symlink or non-directory palettes path')
        palette_dir.mkdir(exist_ok=True)
        for relative in ('config.toml', 'palettes/minimaOS.json'):
            dest = stage / relative
            if dest.is_symlink() or (dest.exists() and not dest.is_file()):
                raise ValueError(f'Refusing unsafe destination: {relative}')
            # Remove only the disposable stage's copied file, not the original.
            if dest.exists():
                dest.unlink()
            shutil.copy2(SOURCE / relative, dest)
        result = subprocess.run([binary, 'config', 'validate', str(stage)], text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise ValueError('Noctalia rejected the staged configuration: ' + (result.stderr + result.stdout).strip())
        # The validator may return success with warnings; do not hide them.
        if (result.stdout + result.stderr).strip():
            print('Noctalia validation output:\n' + (result.stdout + result.stderr).strip(), file=sys.stderr)
        return swap(config_dir, stage)
    finally:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)


def restore(config_dir, backup):
    real_dir(config_dir)
    if backup.parent.resolve() != config_dir.resolve() or not backup.name.startswith('noctalia.backup.'):
        raise ValueError('Select a direct noctalia.backup.* directory under the config home')
    real_dir(backup)
    stage = Path(tempfile.mkdtemp(prefix='.noctalia-restore.', dir=config_dir))
    try:
        shutil.copytree(backup, stage, symlinks=True, dirs_exist_ok=True)
        return swap(config_dir, stage)
    finally:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--apply', action='store_true')
    group.add_argument('--restore', metavar='BACKUP')
    args = parser.parse_args()
    if os.geteuid() == 0:
        print('Run as the desktop user, not root.', file=sys.stderr)
        return 1
    try:
        config_dir = config_home()
        print('Config home:', config_dir)
        print('The existing Noctalia directory will be backed up; other directories and GUI state are not changed.')
        print('Run from outside the active Noctalia session. The profile replaces config.toml and minimaOS.json.')
        if input('Continue? [y/N] ').lower() not in ('y', 'yes'):
            print('Cancelled; nothing changed.')
            return 0
        if args.apply:
            backup = apply(config_dir, checked_noctalia())
        else:
            backup = restore(config_dir, Path(args.restore))
        print('Complete. Previous directory backup:', backup or '(none)')
        if args.restore:
            print('The selected backup was copied and remains intact.')
        print('Log in again; GUI-managed state overrides may still take precedence.')
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, EOFError) as exc:
        print('Noctalia profile operation failed:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
