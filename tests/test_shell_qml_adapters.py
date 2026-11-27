# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Exercise QML logic with test doubles, never claim a real Quickshell session."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AdapterHarnessTests(unittest.TestCase):
    def test_adapter_state_and_failures_with_mock_io(self):
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QSG_RHI_BACKEND='software')
        probe = subprocess.run(['python3', '-c', 'from PySide6.QtGui import QGuiApplication'],
                               capture_output=True, text=True, env=env, timeout=20)
        if probe.returncode:
            self.skipTest('PySide6 or native Qt runtime libraries unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            env.update(HOME=temporary, IARCH_CONFIG_DIR=str(Path(temporary) / 'config'))
            projection = subprocess.run(['python3', str(ROOT / 'iarch/cli/shell_projection.py'), '--reference-preview'],
                                        capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(projection.returncode, 0, projection.stderr)
            script = '''
import sys
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine, QQmlComponent
app = QGuiApplication([])
engine = QQmlEngine()
engine.addImportPath(sys.argv[1])
component = QQmlComponent(engine, QUrl.fromLocalFile(sys.argv[2]))
obj = component.create()
if obj is None:
    raise RuntimeError(str(component.errors()))
result = obj.exercise(sys.argv[3])
if result != 'ok':
    raise RuntimeError(result)
'''
            for harness in ('AdapterHarness.qml', 'CoreHarness.qml'):
                with self.subTest(harness=harness):
                    result = subprocess.run(['python3', '-c', script, str(ROOT / 'tests/qml/stubs'),
                                             str(ROOT / 'tests/qml' / harness), projection.stdout],
                                            capture_output=True, text=True, env=env, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    for warning in ('TypeError:', 'ReferenceError:', 'Cannot assign'):
                        self.assertNotIn(warning, result.stderr)


if __name__ == '__main__': unittest.main()
