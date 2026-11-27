# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The icon whitelist, local assets, and upstream notices stay in sync."""
import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IconAssetTests(unittest.TestCase):
    def test_icons_are_local_whitelisted_and_licensed(self):
        directory = ROOT / 'assets/icons/shell'
        source = (ROOT / 'iarch/shell/components/Icon.qml').read_text()
        names = re.search(r'readonly property var names: \[(.*?)\]', source).group(1)
        expected = set(re.findall(r'"([a-z0-9-]+)"', names))
        self.assertTrue(expected)
        self.assertEqual(expected, {p.stem for p in directory.glob('*.svg')})
        for name in expected:
            root = ET.parse(directory / (name + '.svg')).getroot()
            self.assertEqual(root.tag, '{http://www.w3.org/2000/svg}svg')
            for element in root.iter():
                self.assertFalse(any(key.endswith('href') for key in element.attrib))
        license_text = (directory / 'LICENSE.txt').read_text()
        self.assertIn('ISC License', license_text)
        self.assertIn('The MIT License (MIT)', license_text)
        notices = json.loads((ROOT / 'data/licenses.json').read_text())['components']
        icon_notice = next(item for item in notices if item['id'] == 'shell-icon-assets')
        self.assertEqual(icon_notice['license'], 'ISC AND MIT')
        self.assertIn('assets/icons/shell/', icon_notice['used_by'])
        self.assertNotIn('http:', source)
        self.assertNotIn('https:', source)


if __name__ == '__main__':
    unittest.main()
