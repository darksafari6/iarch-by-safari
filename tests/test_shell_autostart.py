# Copyright (C) 2026 Safari — GPL-3.0-or-later
import tempfile
import unittest
from pathlib import Path
from iarch.cli import shell_autostart


class AutoStartTests(unittest.TestCase):
    def test_unit_is_opt_in_idempotent_and_backs_up(self):
        with tempfile.TemporaryDirectory() as temp:
            env = {'HOME': temp, 'IARCH_STATE_DIR': temp + '/state'}
            path = shell_autostart.install(env)
            self.assertTrue(path.read_text().startswith(shell_autostart.MARKER))
            self.assertIn('ExecStart=%h/.local/bin/iarch-shell start', path.read_text())
            self.assertFalse((path.parent / 'graphical-session.target.wants').exists())
            shell_autostart.install(env)
            self.assertFalse((Path(temp) / 'state/backups').exists())
            path.write_text(shell_autostart.MARKER + '\n# old generated unit\n')
            shell_autostart.install(env)
            self.assertEqual(len(list((Path(temp) / 'state/backups').glob('*.bak'))), 1)

    def test_foreign_symlink_and_escaping_parent_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            env = {'HOME': temp}
            path = shell_autostart.unit_path(env)
            path.parent.mkdir(parents=True)
            path.write_text('foreign')
            with self.assertRaises(ValueError): shell_autostart.install(env)
            self.assertEqual(path.read_text(), 'foreign')
            path.unlink()
            target = Path(temp) / 'target'; target.write_text('keep')
            path.symlink_to(target)
            with self.assertRaises(ValueError): shell_autostart.install(env)
            self.assertEqual(target.read_text(), 'keep')
            with self.assertRaises(ValueError): shell_autostart.unit_path({'HOME': temp, 'XDG_CONFIG_HOME': 'relative'})


if __name__ == '__main__': unittest.main()
