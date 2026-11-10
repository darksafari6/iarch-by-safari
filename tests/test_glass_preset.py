"""Checks the staging preset without running a compositor or real services."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('glass_preset', ROOT / 'tools/glass_preset.py')
glass = importlib.util.module_from_spec(spec)
spec.loader.exec_module(glass)


class GlassPreset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stage = Path(self.tmp.name)
        # The v4 preset edits the legacy settings.json, which now lives in legacy/config/.
        (self.stage / 'noctalia').mkdir()
        shutil.copy(ROOT / 'legacy/config/noctalia/settings.json', self.stage / 'noctalia/settings.json')
        (self.stage / 'hypr').mkdir()
        (self.stage / 'hypr/windowrules.conf').write_text('# original\n')
        self.file = self.stage / 'noctalia/settings.json'

    def test_preset_preserves_widgets_and_other_settings(self):
        before = json.loads(self.file.read_text())
        glass.apply(self.stage)
        result = json.loads(self.file.read_text())
        for section in ('left', 'center'):
            self.assertEqual(before['bar']['widgets'][section], result['bar']['widgets'][section])
        ids = [x['id'] for x in result['bar']['widgets']['right']]
        self.assertEqual([x for x in ids if x not in ('Network', 'Bluetooth')],
                         [x['id'] for x in before['bar']['widgets']['right']])
        self.assertEqual(ids.count('Network'), 1)
        self.assertEqual(ids.count('Bluetooth'), 1)
        self.assertEqual(result['colorSchemes'], before['colorSchemes'])
        self.assertEqual(result['appLauncher'], before['appLauncher'])
        self.assertFalse(result['notifications']['sounds']['enabled'])
        self.assertTrue(next(c['enabled'] for c in result['controlCenter']['cards'] if c['id'] == 'brightness-card'))
        sound = self.stage / 'quickshell/noctalia-shell/Assets/Sounds/minimalinux-twinkle.wav'
        with wave.open(str(sound)) as wav:
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getnframes() / wav.getframerate(), 0.08)
        original = self.file.read_text()
        glass.apply(self.stage)
        self.assertEqual(original, self.file.read_text())
        self.assertEqual((self.stage / 'hypr/windowrules.conf').read_text().count('layerrule ='), 1)

    def test_unknown_settings_version_fails_before_writing(self):
        settings = json.loads(self.file.read_text())
        settings['settingsVersion'] = 99
        self.file.write_text(json.dumps(settings))
        original = self.file.read_text()
        with self.assertRaises(ValueError):
            glass.apply(self.stage)
        self.assertEqual(self.file.read_text(), original)
        self.assertFalse((self.stage / 'quickshell').exists())
        self.assertEqual((self.stage / 'hypr/windowrules.conf').read_text(), '# original\n')

    def test_custom_cards_are_not_discarded(self):
        settings = json.loads(self.file.read_text())
        settings['controlCenter'] = {'cards': [{'id': 'custom-card', 'enabled': False}]}
        self.file.write_text(json.dumps(settings))
        glass.apply(self.stage)
        cards = json.loads(self.file.read_text())['controlCenter']['cards']
        self.assertEqual(cards[0], {'id': 'custom-card', 'enabled': False})
        self.assertEqual(cards[1], {'id': 'brightness-card', 'enabled': True})


if __name__ == '__main__':
    unittest.main()
