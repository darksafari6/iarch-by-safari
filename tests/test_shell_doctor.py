# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Read-only diagnostics distinguish unavailable IPC and invalid packs."""
import tempfile
import unittest
from pathlib import Path
from iarch.cli import iarch_doctor, theme_records
from iarch.lib.runner import Answer


class ShellDoctorTests(unittest.TestCase):
    def test_missing_tools_and_no_dynamic_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {'HOME': directory, 'IARCH_CONFIG_DIR': str(Path(directory) / 'config'), 'PATH': directory}
            report = iarch_doctor.shell_diagnostics(env)
            self.assertFalse(any(report['tools'].values()))
            self.assertEqual(report['pack']['status'], 'not-selected')
            self.assertEqual(report['ipc']['status'], 'not-checked')
            self.assertTrue(all(report['font_assets'].values()))

    def test_invalid_pack_and_reachable_ipc_are_separate_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {'HOME': directory, 'IARCH_CONFIG_DIR': str(Path(directory) / 'config'), 'PATH': directory}
            theme_records.write_selection({'schema_version': 1, 'id': 'missing', 'engine': 'dynamic', 'overrides': {}}, env)
            calls = []
            def run(command, timeout):
                calls.append(command)
                return Answer(tuple(command), 0, stdout='true')
            report = iarch_doctor.shell_diagnostics(env, True, run)
            self.assertEqual(report['pack']['status'], 'invalid-or-unavailable')
            self.assertEqual(report['ipc']['status'], 'reachable')
            self.assertEqual(calls[0][-2:], ('iarch.theme', 'ping'))
            report = iarch_doctor.shell_diagnostics(env, True, lambda *args: None)
            self.assertEqual(report['ipc']['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
