# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Dynamic render is pure and resolves colours and sizes from the pack."""
import tempfile
import unittest
from pathlib import Path
from iarch.cli import theme_pack_render, theme_pack_validate

ROOT = Path(__file__).resolve().parents[1]


class PackRenderTests(unittest.TestCase):
    def test_render_uses_pack_tokens_and_never_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            env = {'HOME': temp}
            pack = theme_pack_validate.validate_pack(ROOT / 'data/themes/dynamic-reference')
            pack['palette']['colors']['accent'] = '#123456'
            result = theme_pack_render.actions(pack, env)
            bodies = {path.name: body for _, path, body in result}
            self.assertIn('#123456', bodies['theme.conf'])
            self.assertIn('gaps_in = 4', bodies['theme.lua'])
            self.assertFalse((Path(temp) / '.config').exists())

    def test_window_rule_is_escaped_data(self):
        with tempfile.TemporaryDirectory() as temp:
            pack = theme_pack_validate.validate_pack(ROOT / 'data/themes/dynamic-reference')
            pack['hypr']['window_rules'] = [{'class': 'demo"}); error("bad', 'effect': 'float', 'enabled': True}]
            lua = next(body for _, path, body in theme_pack_render.actions(pack, {'HOME': temp}) if path.name == 'theme.lua')
            self.assertIn('demo\\"}); error(\\"bad', lua)
            self.assertIn('float = true', lua)

    def test_bad_compositor_size_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            pack = theme_pack_validate.validate_pack(ROOT / 'data/themes/dynamic-reference')
            pack['layout']['sizes']['small'] = 100
            with self.assertRaisesRegex(ValueError, 'border_size'):
                theme_pack_render.actions(pack, {'HOME': temp})


if __name__ == '__main__':
    unittest.main()
