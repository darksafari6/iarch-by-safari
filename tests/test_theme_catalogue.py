# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The status document and theme list derive from one catalogue."""
import unittest
from iarch.cli import gen_theme_status, theme_packs


class CatalogueTests(unittest.TestCase):
    def test_status_is_current(self):
        self.assertEqual(gen_theme_status.OUTPUT.read_text(), gen_theme_status.render())

    def test_groups_hide_reference(self):
        groups = theme_packs.catalogue({'HOME': '/nonexistent', 'IARCH_CONFIG_DIR': '/nonexistent'})
        self.assertEqual(len(groups['classic']), 6)
        self.assertEqual(len(groups['dynamic']), 6)
        self.assertNotIn('dynamic-reference', {x['id'] for x in groups['dynamic']})


if __name__ == '__main__':
    unittest.main()
