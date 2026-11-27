# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The QML colour lint catches literals and allows the one defaults file."""
import tempfile
import unittest
from pathlib import Path
from tools import lint_no_hex_qml as lint


class QmlColourLintTests(unittest.TestCase):
    def test_violation_and_defaults_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / 'runtime'
            runtime.mkdir()
            (runtime / 'Theme.qml').write_text('color: "#abcdef"\n')
            other = root / 'surface.qml'
            other.write_text('color: "#abc"\n')
            self.assertEqual(lint.findings(root), [(other, 1)])
            other.write_text('color: theme.background\n')
            self.assertEqual(lint.findings(root), [])

    def test_repository_is_clean(self):
        self.assertEqual(lint.findings(), [])


if __name__ == '__main__':
    unittest.main()
