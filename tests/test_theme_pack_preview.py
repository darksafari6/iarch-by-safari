# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Preview generation is deterministic and stays in the user cache."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from iarch.cli import theme_pack_preview

ROOT = Path(__file__).resolve().parents[1]


class PreviewTests(unittest.TestCase):
    def test_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack = root / 'example-pack'
            shutil.copytree(ROOT / 'data/themes/dynamic-reference', pack)
            for p in pack.rglob('*.json'):
                doc = json.loads(p.read_text())
                doc['id'] = 'example-pack'
                p.write_text(json.dumps(doc))
            env = {'HOME': tmp, 'XDG_CACHE_HOME': str(root / 'cache')}
            path = theme_pack_preview.render_preview(pack, env=env)
            self.assertEqual(path.parent, root / 'cache/iarch/theme-previews')
            first = path.read_bytes()
            self.assertTrue(first.startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertEqual(first, theme_pack_preview.render_preview(pack, env=env).read_bytes())


if __name__ == '__main__':
    unittest.main()
