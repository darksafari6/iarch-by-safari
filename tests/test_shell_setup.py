# Copyright (C) 2026 Safari — GPL-3.0-or-later
import tempfile
import unittest
from pathlib import Path
from iarch.cli.shell_setup import install


class SetupTests(unittest.TestCase):
    def test_opt_in_link_idempotent_and_no_session_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'; source.mkdir(); (source / 'shell.qml').write_text('// skeleton')
            env = {'HOME': temp}
            path = install(env, source)
            self.assertTrue(path.is_symlink())
            self.assertEqual(path.resolve(), source)
            self.assertEqual(install(env, source), path)
            self.assertFalse((root / '.config/systemd').exists())

    def test_repository_assets_resolve_through_development_config_link(self):
        from iarch.cli.shell_setup import ROOT
        with tempfile.TemporaryDirectory() as temp:
            link = install({'HOME': temp})
            self.assertEqual((link / 'assets/fonts/ui/regular.ttf').resolve(),
                             (ROOT / 'assets/fonts/ui/regular.ttf').resolve())
            self.assertEqual((link / 'assets/icons/shell/wifi.svg').resolve(),
                             (ROOT / 'assets/icons/shell/wifi.svg').resolve())

    def test_refuses_foreign_files_links_and_parent_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'source'; source.mkdir(); (source / 'shell.qml').write_text('// skeleton')
            config = root / 'config'; parent = config / 'quickshell'; parent.mkdir(parents=True)
            env = {'HOME': temp, 'XDG_CONFIG_HOME': str(config)}
            target = parent / 'iarch'; target.mkdir()
            with self.assertRaises(ValueError): install(env, source)
            target.rmdir(); foreign = root / 'foreign'; foreign.mkdir(); target.symlink_to(foreign)
            with self.assertRaises(ValueError): install(env, source)
            self.assertTrue(target.is_symlink())
            target.unlink(); parent.rmdir(); parent.symlink_to(foreign)
            with self.assertRaises(ValueError): install(env, source)
            with self.assertRaises(ValueError): install({'HOME': temp, 'XDG_CONFIG_HOME': 'relative'}, source)


if __name__ == '__main__': unittest.main()
