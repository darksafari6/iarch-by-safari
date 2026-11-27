# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The preview launcher never starts the unfinished session shell."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/iarch-shell.sh'


class GalleryLauncherTests(unittest.TestCase):
    def test_preview_arguments_and_session_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            stub = Path(temporary) / 'quickshell'
            stub.write_text('#!/bin/sh\nprintf "%s\\n" "$IARCH_SHELL_ROOT" "$@"\n')
            stub.chmod(0o755)
            env = dict(os.environ, PATH=temporary + os.pathsep + os.environ.get('PATH', ''))
            result = subprocess.run([str(SCRIPT), 'gallery'], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), [str(ROOT), '--path',
                             str(ROOT / 'iarch/shell/GalleryShell.qml'), '--no-duplicate'])
            # Preview is an explicit, separate configuration, never a switch.
            preview = subprocess.run([str(SCRIPT), 'preview'], env=env, capture_output=True, text=True)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertEqual(preview.stdout.splitlines(), [str(ROOT), '--path',
                             str(ROOT / 'iarch/shell/PreviewShell.qml'), '--no-duplicate'])
            # Stub Python to prove start delegates to the guarded switch with
            # the correct root; the real switch refuses the skeleton separately.
            python = Path(temporary) / 'python3'
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$IARCH_SHELL_ROOT" "$@"\n')
            python.chmod(0o755)
            start = subprocess.run([str(SCRIPT), 'start'], env=env, capture_output=True, text=True)
            self.assertEqual(start.returncode, 0, start.stderr)
            self.assertEqual(start.stdout.splitlines(), [str(ROOT), str(ROOT / 'iarch/cli/iarch_shell_switch.py'), 'to', 'dynamic'])

    def test_preview_disables_inherited_notification_opt_in(self):
        with tempfile.TemporaryDirectory() as temporary:
            stub = Path(temporary) / 'quickshell'
            stub.write_text('#!/bin/sh\nprintf "%s\\n" "${IARCH_ENABLE_NOTIFICATIONS-unset}"\n')
            stub.chmod(0o755)
            env = dict(os.environ, PATH=temporary + os.pathsep + os.environ.get('PATH', ''),
                       IARCH_ENABLE_NOTIFICATIONS='1')
            preview = subprocess.run([str(SCRIPT), 'preview'], env=env, capture_output=True, text=True)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertEqual(preview.stdout.strip(), 'unset')
            core = (ROOT / 'iarch/shell/ShellCore.qml').read_text()
            window = (ROOT / 'iarch/shell/services/SurfaceWindow.qml').read_text()
            startup = (ROOT / 'iarch/shell/services/StartupTheme.qml').read_text()
            self.assertIn('!shell.preview &&', core)
            self.assertIn('exclusiveZone: !preview && bar', window)
            self.assertIn('--reference-preview', startup)
            self.assertIn('ShellCore { preview: true }', (ROOT / 'iarch/shell/PreviewShell.qml').read_text())


if __name__ == '__main__':
    unittest.main()
