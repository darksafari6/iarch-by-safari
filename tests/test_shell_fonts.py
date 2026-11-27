# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Vendored font payloads, license presence and loader drift checks."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTS = {
    'display': ('fc7287273e66929776e2ba54f144fe699080bec29f61bf649d70d871468aeade', 'font-display'),
    'mono': ('48715a42ec242c21e9f02692891e147d022299a52e48d5e413e1a942193ffeda', 'font-mono-vendored'),
    'rounded': ('bb55a5ca5c2042335b3991af27c4d0705d0ef41cac6164ac737fd8f2a1e85207', 'font-rounded'),
    'ui': ('29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031', 'font-ui'),
}


class FontAssetsTests(unittest.TestCase):
    def test_assets_license_notices_and_loaders(self):
        components = {entry['id']: entry for entry in json.loads((ROOT / 'data/licenses.json').read_text())['components']}
        theme = (ROOT / 'iarch/shell/runtime/Theme.qml').read_text()
        for folder, (digest, notice_id) in FONTS.items():
            with self.subTest(font=folder):
                path = ROOT / 'assets/fonts' / folder / 'regular.ttf'
                data = path.read_bytes()
                self.assertEqual(data[:4], b'\x00\x01\x00\x00')
                self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
                self.assertIn('SIL OPEN FONT LICENSE Version 1.1',
                              (path.parent / 'OFL.txt').read_text())
                self.assertEqual(components[notice_id]['license'], 'OFL-1.1')
                self.assertIn('assets/fonts/' + folder + '/regular.ttf', components[notice_id]['used_by'])
                self.assertIn('assets/fonts/' + folder + '/regular.ttf', theme)


if __name__ == '__main__':
    unittest.main()
