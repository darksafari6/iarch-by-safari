#!/usr/bin/env python3
"""List or safely restore an isolated minimaLinux session backup."""
import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile
from datetime import datetime


def list_backups(config_dir):
    if not config_dir.is_dir():
        return []
    return sorted(config_dir.glob('minimalinux.backup.*'), key=lambda p: p.name, reverse=True)


def restore(config_dir, backup):
    """Copy an explicit backup, preserving it and moving the current config aside."""
    config_dir = Path(config_dir)
    backup = Path(backup)
    if backup.parent.resolve() != config_dir.resolve() or not backup.name.startswith('minimalinux.backup.'):
        raise ValueError('Backup must be a direct minimalinux.backup.* entry in ~/.config.')
    if backup.is_symlink() or not backup.is_dir():
        raise ValueError('Backup must be a real directory, not a symlink. Inspect it manually.')
    target = config_dir / 'minimalinux'
    stage = Path(tempfile.mkdtemp(prefix='.minimalinux-restore.', dir=config_dir))
    previous = None
    try:
        shutil.copytree(backup, stage, symlinks=True, dirs_exist_ok=True, copy_function=shutil.copy2)
        if target.exists() or target.is_symlink():
            previous = Path(tempfile.mkdtemp(prefix='minimalinux.backup.pre-restore.' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.', dir=config_dir))
            previous.rmdir()
            os.rename(target, previous)
        try:
            os.rename(stage, target)
        except OSError as exc:
            if previous is not None:
                try:
                    os.rename(previous, target)
                    previous = None
                except OSError as recovery_error:
                    raise RuntimeError(f'Could not restore current config; recover it from {previous}: {recovery_error}') from exc
            raise
        return previous
    finally:
        if stage.is_dir() and not stage.is_symlink():
            # Only the freshly-created staging directory is removed.
            shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', metavar='BACKUP', help='Copy a specific backup into place after confirmation')
    args = parser.parse_args()
    if os.geteuid() == 0:
        print('Run as the user whose session is being recovered, not root.', file=sys.stderr)
        return 1
    config_dir = Path.home() / '.config'
    if not args.restore:
        backups = list_backups(config_dir)
        print('Session backups (nothing changed):')
        for path in backups:
            print(' ', path, '(symlink: manual recovery only)' if path.is_symlink() else '')
        if not backups:
            print('  None found.')
        print('To restore one: python3 tools/recover_session.py --restore /path/to/minimalinux.backup.NAME')
        return 0
    print('The selected backup will be copied. The current session config, if any, will be moved to a new backup.')
    print('Backup:', args.restore)
    try:
        answer = input('Continue? [y/N] ')
    except EOFError:
        print('Cancelled.')
        return 1
    if answer.lower() not in ('y', 'yes'):
        print('Cancelled.')
        return 0
    try:
        previous = restore(config_dir, args.restore)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Recovery failed: {exc}', file=sys.stderr)
        return 1
    print('Restored the selected backup without deleting it.')
    if previous:
        print('The previous session config is preserved at:', previous)
    print('Log out and back in to use the restored session.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
