# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Keep the reserved dynamic shell tree small and its boundaries explicit."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / 'iarch/shell'


class ShellLayout(unittest.TestCase):
    def test_folders_and_readmes(self):
        for name in ('', 'runtime', 'services', 'components', 'surfaces',
                     'surfaces/bar', 'surfaces/overview', 'surfaces/sidebar-right',
                     'surfaces/sidebar-left', 'surfaces/dock', 'surfaces/osk', 'tests'):
            with self.subTest(name=name):
                text = (SHELL / name / 'README.md').read_text()
                self.assertGreaterEqual(len(text.splitlines()), 10)
                for heading in ('## Purpose', '## Inputs', '## Outputs'):
                    self.assertIn(heading, text)
        for name in ('assets/sounds', 'docs/themes'):
            self.assertTrue((ROOT / name / 'README.md').is_file())

    def test_qml_boundaries(self):
        for path in SHELL.rglob('*.qml'):
            with self.subTest(path=path):
                lines = path.read_text().splitlines()
                self.assertLess(len(lines), 150 if path.name == 'shell.qml' else 400)
                self.assertTrue(lines[0].startswith('// Copyright (C) 2026 Safari'))
                if path.name not in ('shell.qml', 'ShellCore.qml', 'PreviewShell.qml', 'GalleryShell.qml') and 'services' not in path.relative_to(SHELL).parts:
                    self.assertNotRegex('\n'.join(lines), r'(?m)^\s*import\s+Quickshell')
                if path.relative_to(SHELL).as_posix() != 'runtime/Theme.qml':
                    self.assertNotRegex('\n'.join(lines), r'#[0-9a-fA-F]{6}\b')


if __name__ == '__main__':
    unittest.main()
