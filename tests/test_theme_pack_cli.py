# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Exercise public dynamic pack commands without a live compositor."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from iarch.cli import theme_pack_archive, theme_pack_cli

ROOT = Path(__file__).resolve().parents[1]


class PackCliTests(unittest.TestCase):
    def test_list_json(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(theme_pack_cli.main(['list', '--json']), 0)
        self.assertEqual(set(json.loads(output.getvalue())), {'classic', 'dynamic'})

    def test_validate_reference(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(theme_pack_cli.main(['validate', str(ROOT / 'data/themes/dynamic-reference')]), 0)

    def test_import_refuses_reserved_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'pack.tar.gz'
            theme_pack_archive.export_pack(ROOT / 'data/themes/dynamic-reference', archive)
            with patch.dict(os.environ, {'IARCH_CONFIG_DIR': str(Path(temp) / 'config')}):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(theme_pack_cli.main(['import', str(archive)]), 1)
                self.assertFalse((Path(temp) / 'config/themes/dynamic-reference').exists())


if __name__ == '__main__':
    unittest.main()
