# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Quality persistence is validated, backed up and never implies a live ack."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from iarch.cli import shell_quality, theme_records
from iarch.lib.runner import Answer

ROOT = Path(__file__).resolve().parents[1]


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {'HOME': str(self.root), 'IARCH_CONFIG_DIR': str(self.root / 'config'),
                    'IARCH_STATE_DIR': str(self.root / 'state')}

    def test_change_preserves_overrides_and_backs_up_previous_bytes(self):
        original = theme_records.read_overrides(self.env)
        original['accent'] = '#112233'
        theme_records.write_overrides(original, self.env)
        path = theme_records.overrides_path(self.env)
        before = path.read_bytes()
        calls = []
        def run(command, timeout):
            calls.append(command)
            return Answer(tuple(command), 0, stdout='true')
        result = shell_quality.set_preference('high', self.env, run=run)
        self.assertEqual(result, {'quality': 'high', 'changed': True, 'reload': 'queued'})
        self.assertEqual(calls[0][-2:], ('iarch.theme', 'reload'))
        self.assertEqual(theme_records.read_overrides(self.env)['accent'], '#112233')
        self.assertEqual(shell_quality.current(self.env), 'high')
        backups = list((self.root / 'state/backups').glob('*.bak'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)
        result = shell_quality.set_preference('high', self.env, reload=False)
        self.assertFalse(result['changed'])
        self.assertEqual(len(list((self.root / 'state/backups').glob('*.bak'))), 1)
        shell_quality.set_preference('default', self.env, reload=False)
        self.assertIsNone(theme_records.read_overrides(self.env)['quality'])
        self.assertEqual(shell_quality.current(self.env), 'balanced')

    def test_errors_keep_existing_file_and_failed_reload_is_not_success(self):
        path = theme_records.overrides_path(self.env)
        path.parent.mkdir(parents=True)
        path.write_text('{broken')
        with self.assertRaises(ValueError): shell_quality.set_preference('low', self.env)
        self.assertEqual(path.read_text(), '{broken')
        with self.assertRaises(ValueError): shell_quality.set_preference('invented', self.env)
        path.unlink()
        result = shell_quality.set_preference('low', self.env, run=lambda *args: None)
        self.assertEqual(result['reload'], 'unavailable-or-rejected')
        self.assertEqual(shell_quality.current(self.env), 'low')
        result = shell_quality.set_preference('low', self.env,
                       run=lambda command, timeout: Answer(tuple(command), 0, stdout='false'))
        self.assertEqual(result['reload'], 'unavailable-or-rejected')

    def test_symlinked_override_or_lock_is_not_followed(self):
        target = self.root / 'target'; target.write_text('untouched')
        path = theme_records.overrides_path(self.env); path.parent.mkdir(parents=True)
        path.symlink_to(target)
        with self.assertRaises(ValueError): shell_quality.set_preference('low', self.env)
        self.assertEqual(target.read_text(), 'untouched')
        path.unlink()
        lock = self.root / 'state/.theme-overrides.lock'
        lock.unlink(); lock.symlink_to(target)
        with self.assertRaises(OSError): shell_quality.set_preference('low', self.env)
        self.assertEqual(target.read_text(), 'untouched')

    def test_launcher_saves_without_reload_and_reads_back(self):
        env = dict(os.environ, **self.env)
        command = [str(ROOT / 'scripts/iarch-shell.sh'), 'quality']
        result = subprocess.run(command + ['ultra', '--no-reload'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ultra (saved)', result.stdout)
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'ultra')
        data = json.loads(theme_records.overrides_path(self.env).read_text())
        self.assertEqual(data['quality'], 'ultra')
        result = subprocess.run(command + ['bad'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(theme_records.overrides_path(self.env).read_text()), data)


if __name__ == '__main__': unittest.main()
