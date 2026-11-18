# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Contract and rejection tests for dynamic pack version one."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from iarch.cli import theme_pack_validate as validator

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'data/themes/dynamic-reference'


class PackValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pack = Path(self.tmp.name) / 'dynamic-reference'
        shutil.copytree(REFERENCE, self.pack)

    def change(self, name, fn):
        path = self.pack / (name + '.json')
        data = json.loads(path.read_text())
        fn(data)
        path.write_text(json.dumps(data))

    def rejected(self):
        with self.assertRaises(validator.PackError):
            validator.validate_pack(self.pack)

    def test_reference(self):
        self.assertEqual(validator.validate_pack(self.pack)['theme']['id'], 'dynamic-reference')

    def test_unknown_key_in_each_document(self):
        for name in validator.FILES:
            with self.subTest(name=name):
                original = (self.pack / (name + '.json')).read_text()
                self.change(name, lambda d: d.update(unexpected=True))
                self.rejected()
                (self.pack / (name + '.json')).write_text(original)

    def test_unknown_colour_and_size_tokens(self):
        self.change('hypr', lambda d: d.update(active_border='invented'))
        self.rejected()
        shutil.copy(REFERENCE / 'hypr.json', self.pack / 'hypr.json')
        self.change('hypr', lambda d: d.update(gaps_in='invented'))
        self.rejected()

    def test_literal_colour_outside_palette(self):
        self.change('theme', lambda d: d.update(description='A colour #abcdef is not a token.'))
        self.rejected()

    def test_paths(self):
        for value in ('/etc/passwd', '../secret', 'C:\\secret'):
            with self.subTest(value=value):
                self.change('theme', lambda d: d['fonts'].update(ui=value))
                self.rejected()

    def test_symlink_and_executable_and_hardlink(self):
        link = self.pack / 'preview'
        link.symlink_to(REFERENCE, target_is_directory=True)
        self.rejected()
        link.unlink()
        p = self.pack / 'theme.json'
        p.chmod(0o755)
        self.rejected()
        p.chmod(0o644)
        os.link(p, self.pack / 'extra.json')
        self.rejected()

    def test_oversized(self):
        p = self.pack / 'preview'
        p.mkdir()
        with (p / 'preview.png').open('wb') as f:
            f.truncate(validator.MAX_FILE + 1)
        self.rejected()

    def test_id_mode_variants_credits(self):
        for name, fn in [('palette', lambda d: d.update(mode='light')),
                         ('layout', lambda d: d['surfaces']['bar'].update(variant='other')),
                         ('theme', lambda d: d.update(credits=['invented'])),
                         ('apps', lambda d: d.update(id='different'))]:
            with self.subTest(name=name):
                original = (self.pack / (name + '.json')).read_text()
                self.change(name, fn)
                self.rejected()
                (self.pack / (name + '.json')).write_text(original)

    def test_wallpaper_references_are_checked(self):
        path = self.pack / 'wallpapers/example.json'
        data = json.loads(path.read_text())
        data['colors'] = ['accent', 'unknown']
        path.write_text(json.dumps(data))
        self.rejected()

    def test_enabled_sound_must_exist(self):
        self.change('sounds', lambda d: d['events']['switch'].update(enabled=True))
        self.rejected()

    def test_duplicate_key(self):
        path = self.pack / 'theme.json'
        path.write_text(path.read_text().replace('"schema_version": 1,', '"schema_version": 1, "schema_version": 1,'))
        self.rejected()


if __name__ == '__main__':
    unittest.main()
