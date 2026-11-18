# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Theme selection migration and overrides are isolated from pack data."""
import json
import tempfile
import unittest
from pathlib import Path
from iarch.cli import theme_records


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {'HOME': self.tmp.name, 'IARCH_CONFIG_DIR': self.tmp.name}

    def test_legacy_migration(self):
        path = theme_records.selection_path(self.env)
        path.write_text('{"id":"greenhouse"}')
        record = theme_records.read_selection(self.env)
        self.assertEqual(record, {'schema_version': 1, 'id': 'greenhouse', 'engine': 'classic', 'overrides': {}})
        theme_records.write_selection(record, self.env)
        self.assertEqual(json.loads(path.read_text()), record)

    def test_overrides_validation(self):
        data = theme_records.read_overrides(self.env)
        data['volume'] = 0.7
        theme_records.write_overrides(data, self.env)
        self.assertEqual(theme_records.read_overrides(self.env)['volume'], 0.7)
        data['volume'] = 2
        with self.assertRaises(ValueError):
            theme_records.write_overrides(data, self.env)


if __name__ == '__main__':
    unittest.main()
