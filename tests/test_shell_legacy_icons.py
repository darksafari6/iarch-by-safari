# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Remove only the generated obsolete false value; preserve user config."""
import os
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

from iarch.cli import shell_legacy_icons as migration

ROOT = Path(__file__).resolve().parents[1]


class LegacyIconTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = {'HOME': str(self.home), 'IARCH_STATE_DIR': str(self.home / 'state'),
                    'XDG_CONFIG_HOME': str(self.home / 'conf')}
        self.path = migration.config_path(self.env)
        self.path.parent.mkdir(parents=True)

    def test_dry_run_then_preserves_other_values_comments_and_backup(self):
        original = '# custom\n[shell]\napp_icon_colorize = false # my note\nfont_family = "Example"\n[shell.launcher]\ncolorize_icons = true\n'
        self.path.write_text(original)
        self.assertTrue(migration.migrate(self.path, env=self.env))
        self.assertEqual(self.path.read_text(), original)
        self.assertTrue(migration.migrate(self.path, write=True, env=self.env))
        updated = self.path.read_text()
        self.assertIn('# my note', updated)
        self.assertNotIn('app_icon_colorize', updated)
        self.assertEqual(tomllib.loads(updated)['shell']['launcher']['colorize_icons'], True)
        self.assertEqual(tomllib.loads(updated)['shell']['font_family'], 'Example')
        backups = list((self.home / 'state/backups').glob('*.bak'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), original)
        self.assertFalse(migration.migrate(self.path, write=True, env=self.env))
        self.assertEqual(len(list((self.home / 'state/backups').glob('*.bak'))), 1)

    def test_true_invalid_and_unusual_forms_are_not_changed(self):
        for text in ('[shell]\napp_icon_colorize = true\n',
                     '[shell]\napp_icon_colorize = "false"\n',
                     'shell.app_icon_colorize = false\n',
                     '[shell]\napp_icon_colorize = false\napp_icon_colorize = false\n'):
            self.path.write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                migration.migrate(self.path, write=True, env=self.env)
            self.assertEqual(self.path.read_text(), text)
        self.assertFalse((self.home / 'state/backups').exists())

    def test_refuses_symlink_missing_and_relative_xdg(self):
        target = self.home / 'target'; target.write_text('[shell]\napp_icon_colorize = false\n')
        self.path.symlink_to(target)
        with self.assertRaises(ValueError): migration.migrate(self.path, write=True, env=self.env)
        self.assertEqual(target.read_text(), '[shell]\napp_icon_colorize = false\n')
        self.path.unlink()
        with self.assertRaises(FileNotFoundError): migration.migrate(self.path, write=True, env=self.env)
        with self.assertRaises(ValueError): migration.config_path({'HOME': str(self.home), 'XDG_CONFIG_HOME': 'relative'})

    def test_multiline_content_cannot_be_mistaken_for_a_setting(self):
        text = '[shell]\nmessage = """\napp_icon_colorize = false\n"""\napp_icon_colorize = false\n'
        self.path.write_text(text)
        with self.assertRaises(ValueError): migration.migrate(self.path, write=True, env=self.env)
        self.assertEqual(self.path.read_text(), text)

    def test_launcher_requires_write_to_change_file(self):
        original = '[shell]\napp_icon_colorize = false\n'
        self.path.write_text(original)
        env = dict(os.environ, **self.env)
        cmd = [str(ROOT / 'scripts/iarch-shell.sh'), 'fix-legacy-icons']
        dry = subprocess.run(cmd, env=env, capture_output=True, text=True)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertEqual(self.path.read_text(), original)
        applied = subprocess.run(cmd + ['--write'], env=env, capture_output=True, text=True)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertNotIn('app_icon_colorize', self.path.read_text())


if __name__ == '__main__': unittest.main()
