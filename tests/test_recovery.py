#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery', REPO / 'tools/recover_session.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)

class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / '.config'
        self.config.mkdir()
        self.original = self.config / 'minimalinux'
        self.original.mkdir()
        (self.original / 'custom').write_text('current')
        self.backup = self.config / 'minimalinux.backup.20260101.example'
        self.backup.mkdir()
        (self.backup / 'custom').write_text('backup')

    def test_restore_preserves_both(self):
        previous = recovery.restore(self.config, self.backup)
        self.assertEqual((self.original / 'custom').read_text(), 'backup')
        self.assertEqual((previous / 'custom').read_text(), 'current')
        self.assertEqual((self.backup / 'custom').read_text(), 'backup')

    def test_rejects_outside_and_symlink(self):
        link = self.config / 'minimalinux.backup.link'
        link.symlink_to(self.backup)
        for candidate in (self.config.parent, link):
            with self.assertRaises(ValueError):
                recovery.restore(self.config, candidate)
        self.assertEqual((self.original / 'custom').read_text(), 'current')

    def test_copy_failure_leaves_current_untouched(self):
        with patch.object(recovery.shutil, 'copytree', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                recovery.restore(self.config, self.backup)
        self.assertEqual((self.original / 'custom').read_text(), 'current')
        self.assertFalse(list(self.config.glob('.minimalinux-restore.*')))

    def test_replace_failure_restores_current(self):
        rename = recovery.os.rename
        def fail_stage(src, dst):
            if Path(src).name.startswith('.minimalinux-restore.'):
                raise OSError('simulated failure')
            return rename(src, dst)
        with patch.object(recovery.os, 'rename', side_effect=fail_stage):
            with self.assertRaises(OSError):
                recovery.restore(self.config, self.backup)
        self.assertEqual((self.original / 'custom').read_text(), 'current')
        self.assertEqual((self.backup / 'custom').read_text(), 'backup')

if __name__ == '__main__':
    unittest.main()
