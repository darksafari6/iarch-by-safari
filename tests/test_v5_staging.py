"""Test separation of Noctalia v5/Lua and legacy v4 installer payloads."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'lib/stage-v5-config.sh'


class V5Staging(unittest.TestCase):
    def test_payload_uses_lua_and_v5_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'stage'
            dest.mkdir()
            subprocess.run(['bash', str(SCRIPT), str(ROOT / '.config'), str(dest)], check=True)
            self.assertTrue((dest / 'hypr/hyprland.lua').is_file())
            self.assertTrue((dest / 'hypr/keybind.lua').is_file())
            self.assertTrue((dest / 'noctalia/config.toml').is_file())
            self.assertTrue((dest / 'noctalia/palettes/iarch-midnight.json').is_file())
            self.assertTrue((dest / 'kitty/minima-colors.conf').is_file())
            self.assertFalse((dest / 'hypr/hyprland.conf').exists())
            self.assertFalse((dest / 'hypr/startup.conf').exists())
            self.assertFalse((dest / 'noctalia/settings.json').exists())
            self.assertFalse((dest / 'noctalia/plugins.json').exists())
            self.assertFalse((dest / 'minimalinux').exists())
            self.assertFalse((dest / 'gtk-3.0').exists())

    def test_nonempty_or_missing_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / 'stage'
            dest.mkdir()
            (dest / 'keep').write_text('safe')
            for source in (ROOT / '.config', root / 'missing'):
                result = subprocess.run(['bash', str(SCRIPT), str(source), str(dest)], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((dest / 'keep').read_text(), 'safe')


if __name__ == '__main__':
    unittest.main()
