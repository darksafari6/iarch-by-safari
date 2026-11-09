#!/usr/bin/env python3
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('minimalinux_backend', REPO / '.config/minimalinux/backend.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class CustomizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'minimalinux'
        self.original_root = backend.ROOT
        backend.ROOT = self.root
        self.addCleanup(setattr, backend, 'ROOT', self.original_root)
        (self.root / 'noctalia').mkdir(parents=True)
        (self.root / 'hypr').mkdir()
        (self.root / 'hypr/hyprland.conf').write_text('# test')
        (self.root / 'kitty').mkdir()
        (self.root / 'kitty/kitty.conf').write_text('# test')
        (self.root / 'noctalia/settings.json').write_text(json.dumps({'settingsVersion': 49, 'general': {'avatarImage': '/my/avatar'}, 'bar': {'position': 'bottom'}}))

    def settings(self):
        return json.loads((self.root / 'noctalia/settings.json').read_text())

    def test_theme_updates_isolated_settings_and_preserves_other_settings(self):
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': '/other/session'}, clear=False), patch.object(backend.subprocess, 'run') as run:
            backend.theme('Catppuccin', 'Papirus-Dark', 'Noto Sans 11')
        run.assert_not_called()
        settings = self.settings()
        self.assertEqual(settings['bar']['position'], 'bottom')
        self.assertEqual(settings['general']['avatarImage'], '/my/avatar')
        self.assertEqual(settings['colorSchemes']['predefinedScheme'], 'Catppuccin')
        self.assertIn('gtk-theme-name = adw-gtk3-dark', (self.root / 'gtk-3.0/settings.ini').read_text())
        self.assertIn('89b4fa', (self.root / 'hypr/themes/colors.conf').read_text())
        self.assertIn('background #1e1e2e', (self.root / 'kitty/minima-colors.conf').read_text())

    def test_light_theme_and_profiles(self):
        backend.theme('Light', 'Papirus', 'Noto Sans 10')
        self.assertFalse(self.settings()['colorSchemes']['darkMode'])
        self.assertIn('gtk-theme-name = adw-gtk3\n', (self.root / 'gtk-3.0/settings.ini').read_text())
        backend.terminal_profile('Monospace', 14, 'Minimal')
        self.assertIn('font_size 14', (self.root / 'kitty/minima-profile.conf').read_text())
        self.assertIn('starship-minimal.toml', (self.root / 'fish/conf.d/minimalinux-prompt.fish').read_text())
        for theme in backend.THEMES:
            backend.kitty_colors(theme)
            self.assertIn('color15 ', (self.root / 'kitty/minima-colors.conf').read_text())
        with self.assertRaises(ValueError):
            backend.terminal_profile('x', 99, 'Detailed')
        with self.assertRaises(ValueError):
            backend.theme('Bad', 'Papirus', 'Noto Sans 10')

    def test_theme_failure_restores_existing_files(self):
        gtk = self.root / 'gtk-3.0/settings.ini'
        gtk.parent.mkdir(parents=True)
        gtk.write_text('[Settings]\ngtk-font-name=MyFont 12\n')
        gtk.chmod(0o640)
        original = (self.root / 'noctalia/settings.json').read_bytes()
        real_write = backend.write
        def failing_write(path, text):
            if Path(path).name == 'minima-colors.conf':
                raise OSError('simulated write failure')
            return real_write(path, text)
        with patch.object(backend, 'write', side_effect=failing_write):
            with self.assertRaisesRegex(RuntimeError, 'rolled back'):
                backend.theme('Nord', 'Papirus', 'Noto Sans 10')
        self.assertEqual(gtk.read_text(), '[Settings]\ngtk-font-name=MyFont 12\n')
        self.assertEqual(gtk.stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.root / 'noctalia/settings.json').read_bytes(), original)
        self.assertFalse((self.root / 'hypr/themes/colors.conf').exists())
        backups = list((self.root / 'minimalinux/theme-backups').glob('*/manifest.json'))
        self.assertEqual(len(backups), 1)

    def test_theme_refuses_symlinked_config(self):
        gtk = self.root / 'gtk-3.0'
        gtk.mkdir()
        outside = Path(self.tmp.name) / 'outside'
        outside.write_text('keep')
        (gtk / 'settings.ini').symlink_to(outside)
        with self.assertRaises(ValueError):
            backend.theme('Nord', 'Papirus', 'Noto Sans 10')
        self.assertEqual(outside.read_text(), 'keep')

    def test_missing_theme_components_are_reported(self):
        (self.root / 'noctalia/settings.json').unlink()
        (self.root / 'kitty/kitty.conf').unlink()
        (self.root / 'hypr/hyprland.conf').unlink()
        warnings = backend.theme('Nord', 'Papirus', 'Noto Sans 10')
        self.assertEqual(len(warnings), 3)
        self.assertTrue((self.root / 'gtk-3.0/settings.ini').exists())
        self.assertFalse((self.root / 'noctalia/settings.json').exists())
        self.assertFalse((self.root / 'kitty/minima-colors.conf').exists())

    def test_invalid_settings_not_overwritten(self):
        path = self.root / 'noctalia/settings.json'
        path.write_text('{ broken')
        with self.assertRaises(ValueError):
            backend.settings_update({'bar': {'position': 'top'}})
        self.assertEqual(path.read_text(), '{ broken')

    def test_shortcuts_read_deployed_file(self):
        (self.root / 'hypr/keybinds.conf').write_text('bind = SUPER, RETURN, exec, kitty #"Terminal"\nbindm = SUPER, mouse:272, movewindow #"Move Window"\n')
        self.assertEqual(backend.shortcuts(), [('SUPER + RETURN', 'Terminal'), ('SUPER + mouse:272', 'Move Window')])

    def test_ipc_is_restricted_to_session_and_uses_argument_array(self):
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': '/other'}, clear=False), self.assertRaises(RuntimeError):
            backend.ipc('wallpaper', 'set', '/tmp/picture with spaces.png', 'all')
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.root)}, clear=False), patch.object(backend.shutil, 'which', return_value='/usr/bin/qs'), patch.object(backend.subprocess, 'run') as run:
            run.return_value.returncode = 0
            backend.ipc('wallpaper', 'set', '/tmp/picture with spaces.png', 'all')
            self.assertEqual(run.call_args.args[0][-2:], ['/tmp/picture with spaces.png', 'all'])

    def test_optional_packages_allowlist(self):
        with patch.object(backend.shutil, 'which', return_value='/usr/bin/kitty'), patch.object(backend.subprocess, 'Popen') as popen:
            backend.install_optional(['Firefox browser', 'Audio controls'])
            self.assertEqual(popen.call_args.args[0][-2:], ['firefox', 'pavucontrol'])
            with self.assertRaises(ValueError):
                backend.install_optional(['firefox; bad'])

if __name__ == '__main__':
    unittest.main()
