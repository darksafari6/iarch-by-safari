# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Part T1 acceptance: documents, format, catalogue, transaction and engine rule."""
import json
import tempfile
import unittest
from pathlib import Path

from iarch.cli import gen_theme_status, theme_engine, theme_pack_apply, theme_pack_render, theme_pack_validate, theme_packs
from iarch.lib.runner import Answer

ROOT = Path(__file__).resolve().parents[1]


class PartT1Acceptance(unittest.TestCase):
    def test_documents_and_status(self):
        for name in ('THEMES-ARCHITECTURE.md', 'THEMES-ASSETS.md', 'THEMES-MILESTONES.md'):
            self.assertTrue((ROOT / 'docs' / name).is_file())
        self.assertEqual(gen_theme_status.OUTPUT.read_text(), gen_theme_status.render())

    def test_reference_and_groups(self):
        self.assertEqual(theme_pack_validate.validate_pack(ROOT / 'data/themes/dynamic-reference')['theme']['engine'], 'ishell')
        groups = theme_packs.catalogue({'HOME': '/nonexistent', 'IARCH_CONFIG_DIR': '/nonexistent'})
        self.assertEqual(set(groups), {'classic', 'dynamic'})
        self.assertTrue(groups['classic'] and groups['dynamic'])
        self.assertNotIn('dynamic-reference', [v['id'] for v in groups['dynamic']])

    def test_engine_default_and_one_shell_rule(self):
        self.assertEqual(theme_engine.DEFAULT_ENGINE_ID, 'classic')
        self.assertEqual(theme_engine.by_pack_engine('ishell').id, 'dynamic')
        self.assertTrue(callable(theme_engine.one_shell_violations))

    def test_transaction_rolls_back_if_shell_does_not_answer(self):
        with tempfile.TemporaryDirectory() as temp:
            import shutil
            root = Path(temp)
            pack = root / 'demo-pack'
            shutil.copytree(ROOT / 'data/themes/dynamic-reference', pack)
            for path in pack.rglob('*.json'):
                data = json.loads(path.read_text())
                data['id'] = 'demo-pack'
                path.write_text(json.dumps(data))
            env = {'HOME': temp, 'IARCH_CONFIG_DIR': str(root / '.config/iarch'),
                   'IARCH_STATE_DIR': str(root / '.local/state/iarch')}
            def fake(command, timeout):
                if command[0] == 'quickshell':
                    return Answer(tuple(command), 1)
                return Answer(tuple(command), 0)
            with self.assertRaises(theme_pack_apply.ApplyError):
                theme_pack_apply.apply(pack, lambda docs: theme_pack_render.actions(docs, env), env=env, run=fake)
            self.assertFalse((root / '.config/iarch/theme.json').exists())
            self.assertFalse((root / '.config/hypr/generated/theme.lua').exists())


if __name__ == '__main__':
    unittest.main()
