# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Transactional apply uses a fake shell and compositor, never the real session."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from iarch.cli import theme_pack_apply, theme_records
from iarch.lib.runner import Answer

ROOT = Path(__file__).resolve().parents[1]


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pack = self.root / 'example-pack'
        shutil.copytree(ROOT / 'data/themes/dynamic-reference', self.pack)
        for p in self.pack.glob('*.json'):
            data = json.loads(p.read_text())
            data['id'] = 'example-pack'
            p.write_text(json.dumps(data))
        self.env = {'HOME': str(self.root), 'IARCH_CONFIG_DIR': str(self.root / 'config'),
                    'IARCH_STATE_DIR': str(self.root / 'state')}
        self.output = self.root / 'output.conf'
        self.output.write_text('old bytes\n')
        self.output.chmod(0o640)
        self.calls = []
        self.fail_ipc = False
        self.new_errors = False
        self.error_reads = 0

    def render(self, docs):
        return [('preserving', self.output, 'new bytes\n')]

    def run_command(self, command, timeout):
        self.calls.append(tuple(command))
        if command[:2] == ('hyprctl', 'configerrors'):
            self.error_reads += 1
            text = 'old warning\n' + ('new problem\n' if self.new_errors and self.error_reads > 1 else '')
            return Answer(tuple(command), 0, stdout=text)
        if command[0] == 'quickshell' and self.fail_ipc:
            return Answer(tuple(command), 1)
        return Answer(tuple(command), 0)

    def test_success(self):
        result = theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        self.assertEqual(result['verdict'], 'applied')
        self.assertEqual(self.output.read_text(), 'new bytes\n')
        self.assertEqual(theme_records.read_selection(self.env)['engine'], 'dynamic')

    def test_shell_failure_restores_files_and_record(self):
        self.fail_ipc = True
        with self.assertRaises(theme_pack_apply.ApplyError):
            theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        self.assertEqual(self.output.read_text(), 'old bytes\n')
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o640)
        self.assertFalse(theme_records.selection_path(self.env).exists())
        self.assertIn(('hyprctl', 'reload'), self.calls)

    def test_new_compositor_errors_roll_back(self):
        self.new_errors = True
        with self.assertRaisesRegex(theme_pack_apply.ApplyError, 'new problem'):
            theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        self.assertEqual(self.output.read_text(), 'old bytes\n')
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o640)
        self.assertFalse(theme_records.selection_path(self.env).exists())

    def test_validation_failure_never_writes(self):
        (self.pack / 'palette.json').write_text('{}')
        with self.assertRaises(ValueError):
            theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        self.assertEqual(self.output.read_text(), 'old bytes\n')
        self.assertEqual(self.calls, [])

    def test_unavailable_baseline_refuses_before_writes(self):
        with self.assertRaises(theme_pack_apply.ApplyError):
            theme_pack_apply.apply(self.pack, self.render, env=self.env, run=lambda *a: None)
        self.assertEqual(self.output.read_text(), 'old bytes\n')

    def test_reference_cannot_apply(self):
        with self.assertRaisesRegex(theme_pack_apply.ApplyError, 'reference'):
            theme_pack_apply.apply(ROOT / 'data/themes/dynamic-reference', self.render, env=self.env, run=self.run_command)


if __name__ == '__main__':
    unittest.main()
