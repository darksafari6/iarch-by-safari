"""Filesystem and CLI-mock tests; no desktop or real Noctalia is started."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('v5_profile', ROOT / 'tools/v5_profile.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class V5Profile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / 'config'
        self.config.mkdir()
        self.active = self.config / 'noctalia'
        self.active.mkdir()
        (self.active / 'config.toml').write_text('original')
        (self.active / 'personal').write_text('keep')
        self.bin = self.root / 'noctalia'
        self.bin.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo "noctalia v5.4.1"; else exit 0; fi\n')
        self.bin.chmod(0o755)

    def test_apply_and_restore_preserve_both_versions(self):
        backup = profile.apply(self.config, str(self.bin))
        self.assertEqual((backup / 'config.toml').read_text(), 'original')
        self.assertEqual((self.active / 'personal').read_text(), 'keep')
        self.assertIn('enable_notification_sounds = false', (self.active / 'config.toml').read_text())
        self.assertTrue((self.active / 'palettes/minimaOS.json').is_file())
        previous = profile.restore(self.config, backup)
        self.assertEqual((self.active / 'config.toml').read_text(), 'original')
        self.assertEqual((backup / 'config.toml').read_text(), 'original')
        self.assertIn('enable_notification_sounds = false', (previous / 'config.toml').read_text())

    def test_validation_failure_never_changes_current(self):
        self.bin.write_text('#!/bin/sh\necho invalid >&2\nexit 1\n')
        with self.assertRaises(ValueError):
            profile.apply(self.config, str(self.bin))
        self.assertEqual((self.active / 'config.toml').read_text(), 'original')
        self.assertEqual(list(self.config.glob('noctalia.backup.*')), [])
        self.assertEqual(list(self.config.glob('.noctalia-stage.*')), [])

    def test_symlink_paths_rejected_without_changing_target(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.active / 'palettes').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            profile.apply(self.config, str(self.bin))
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual((self.active / 'config.toml').read_text(), 'original')

    def test_wrong_version_and_untrusted_backup_rejected(self):
        with mock.patch('shutil.which', return_value=str(self.bin)):
            self.bin.write_text('#!/bin/sh\necho "noctalia v4.4.0"\n')
            with self.assertRaises(ValueError):
                profile.checked_noctalia()
        with self.assertRaises(ValueError):
            profile.restore(self.config, self.root / 'noctalia.backup.bad')
        self.assertEqual((self.active / 'config.toml').read_text(), 'original')

    def test_deploy_failure_restores_original(self):
        real_rename = os.rename
        def fail_stage(src, dest):
            if Path(src).name.startswith('.noctalia-stage.'):
                raise OSError('injected failure')
            return real_rename(src, dest)
        with mock.patch.object(profile.os, 'rename', side_effect=fail_stage):
            with self.assertRaises(OSError):
                profile.apply(self.config, str(self.bin))
        self.assertEqual((self.active / 'config.toml').read_text(), 'original')
        self.assertEqual(list(self.config.glob('.noctalia-stage.*')), [])


if __name__ == '__main__':
    unittest.main()
