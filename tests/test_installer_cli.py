#!/usr/bin/env python3
"""Safe end-to-end tests: all system operations are mocked."""
import json
import os
import pty
import select
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class InstallerCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.home, self.bin, self.system = root / 'home', root / 'bin', root / 'system'
        for directory in (self.home, self.bin, self.system):
            directory.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), MOCK_ROOT=str(self.system),
                        PATH=str(self.bin) + os.pathsep + os.environ['PATH'], TERM='xterm-256color', NO_COLOR='1')
        self.mock('sudo', '''#!/usr/bin/env bash
set -euo pipefail
if [[ $1 == install ]]; then
 mkdir -p "$MOCK_ROOT$(dirname "$4")"; cp "$3" "$MOCK_ROOT$4"
else echo "Unexpected sudo: $*" >&2; exit 1; fi
''')
        self.mock('curl', '#!/bin/sh\nexit 0\n')
        self.mock('git', '''#!/usr/bin/env bash
set -euo pipefail
if [[ $1 == -C && $3 == rev-parse ]]; then
 echo "${MOCK_NOCTALIA_REV:-55e9b3735d78aef8fdab49d3d3d7d31d81628b49}"
 exit 0
fi
[[ $1 == -c && $3 == clone ]]
target=${@: -1}; mkdir -p "$target/.git"; touch "$target/shell.qml"
''')

    def mock(self, name, script):
        path = self.bin / name
        path.write_text(script)
        path.chmod(0o755)

    def run_installer(self, *args, input=''):
        return subprocess.run([str(REPO / 'legacy/install-v4-session.sh'), *args], input=input, text=True,
                              capture_output=True, env=self.env, timeout=20)

    def test_automation_flags_verbose_theme_and_welcome(self):
        result = self.run_installer('--skip-packages', '--yes', '--verbose', '--theme', 'catppuccin', '--no-welcome')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('[command]', result.stdout)
        self.assertNotIn('\x1b[', result.stdout)
        logs = list((self.home / '.local/state/minimalinux/logs').glob('install.*.log'))
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].stat().st_mode & 0o777, 0o600)
        self.assertIn('SUCCESS', logs[0].read_text())
        config = self.home / '.config/minimalinux'
        settings = json.loads((config / 'noctalia/settings.json').read_text())
        self.assertEqual(settings['colorSchemes']['predefinedScheme'], 'Catppuccin')
        self.assertEqual(settings['wallpaper']['solidColor'], '#1e1e2e')
        self.assertIn('background #1e1e2e', (config / 'kitty/minima-colors.conf').read_text())
        self.assertNotIn('\nexec-once = python3 "$HOME/.config/minimalinux/minimalinux/center.py" --welcome-once', (config / 'hypr/startup.conf').read_text())
        self.assertTrue((self.system / 'usr/share/wayland-sessions/minimalinux.desktop').exists())

    def test_nord_theme_can_be_installed_without_packages(self):
        result = self.run_installer('--skip-packages', '--yes', '--theme', 'nord')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        config = self.home / '.config/minimalinux'
        settings = json.loads((config / 'noctalia/settings.json').read_text())
        self.assertEqual(settings['colorSchemes']['predefinedScheme'], 'Nord')
        self.assertEqual(settings['wallpaper']['solidColor'], '#2e3440')

    def test_glass_reinstall_backup_and_version_guard(self):
        config = self.home / '.config/minimalinux'
        config.mkdir(parents=True)
        (config / 'custom').write_text('keep me')
        self.env['MOCK_NOCTALIA_REV'] = 'unsupported'
        result = self.run_installer('--skip-packages', '--yes', '--glass')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires the audited Noctalia', result.stderr)
        self.assertEqual((config / 'custom').read_text(), 'keep me')
        self.assertEqual(list(config.parent.glob('minimalinux.backup.*')), [])
        self.assertEqual(list(config.parent.glob('.minimalinux-install.*')), [])
        del self.env['MOCK_NOCTALIA_REV']
        result = self.run_installer('--skip-packages', '--yes', '--glass', '--theme', 'nord')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        backups = list(config.parent.glob('minimalinux.backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'custom').read_text(), 'keep me')
        settings = json.loads((config / 'noctalia/settings.json').read_text())
        self.assertEqual(settings['colorSchemes']['predefinedScheme'], 'Nord')
        self.assertEqual(settings['bar']['backgroundOpacity'], 0.82)
        self.assertFalse(settings['notifications']['sounds']['enabled'])
        self.assertTrue((config / 'quickshell/noctalia-shell/Assets/Sounds/minimalinux-twinkle.wav').is_file())
        self.assertIn('match:namespace ^noctalia-', (config / 'hypr/windowrules.conf').read_text())

    def test_invalid_options_and_cancel_do_not_write(self):
        for args in [('--skip-packages', '--apps', 'firefox', '--yes'),
                     ('--theme', 'invalid'), ('--theme',), ('--apps', 'bad')]:
            result = self.run_installer(*args)
            self.assertNotEqual(result.returncode, 0, (args, result.stdout))
            self.assertFalse((self.home / '.config/minimalinux').exists())
        result = self.run_installer('--skip-packages', input='n\n')
        self.assertEqual(result.returncode, 0)
        self.assertIn('Cancelled', result.stdout)
        self.assertFalse((self.home / '.config/minimalinux').exists())
        result = self.run_installer('--skip-packages')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / '.config/minimalinux').exists())

    def test_registration_failure_keeps_existing_configuration(self):
        config = self.home / '.config/minimalinux'
        config.mkdir(parents=True)
        (config / 'custom').write_text('keep this')
        self.mock('sudo', '#!/usr/bin/env bash\necho denied >&2\nexit 13\n')
        result = self.run_installer('--skip-packages', '--yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((config / 'custom').read_text(), 'keep this')
        self.assertIn('Some managed system launchers may already', result.stderr)
        logs = list((self.home / '.local/state/minimalinux/logs').glob('install.*.log'))
        self.assertEqual(len(logs), 1)
        self.assertIn('FAIL exit=13', logs[0].read_text())
        self.assertEqual(list((self.home / '.config').glob('.minimalinux-install.*')), [])

    def test_tty_color_and_cancellation(self):
        env = self.env.copy()
        env.pop('NO_COLOR', None)
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen([str(REPO / 'legacy/install-v4-session.sh'), '--skip-packages', '--theme', 'tokyo', '--no-welcome'],
                                       stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True)
            os.close(slave)
            slave = -1
            os.write(master, b'n\n')
            chunks = []
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.2)
                if ready:
                    try:
                        data = os.read(master, 65536)
                    except OSError:
                        break
                    if not data:
                        break
                    chunks.append(data)
                if process.poll() is not None and not ready:
                    break
            try:
                code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                self.fail('Interactive installer did not finish')
            output = b''.join(chunks).decode(errors='replace')
            self.assertEqual(code, 0, output)
            self.assertIn('\x1b[', output)
            self.assertIn('Cancelled.', output)
            self.assertFalse((self.home / '.config/minimalinux').exists())
        finally:
            os.close(master)
            if slave >= 0:
                os.close(slave)

    def test_interactive_menu_reprompts_and_applies_choices(self):
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen([str(REPO / 'legacy/install-v4-session.sh')], stdin=slave, stdout=slave,
                                       stderr=slave, env=self.env, close_fds=True)
            os.close(slave)
            slave = -1
            os.write(master, b'2\n9\n4\nn\ny\n')
            chunks = []
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.2)
                if ready:
                    try:
                        data = os.read(master, 65536)
                    except OSError:
                        break
                    if not data:
                        break
                    chunks.append(data)
                if process.poll() is not None and not ready:
                    break
            try:
                code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                self.fail('Interactive installer did not finish')
            output = b''.join(chunks).decode(errors='replace')
            self.assertEqual(code, 0, output)
            self.assertIn('Choose 1, 2, 3, 4, or 5', output)
            self.assertIn('Theme: Light', output)
            self.assertIn('First-login welcome screen: disabled', output)
            self.assertNotIn('\x1b[', output)
            config = self.home / '.config/minimalinux'
            self.assertFalse(json.loads((config / 'noctalia/settings.json').read_text())['colorSchemes']['darkMode'])
        finally:
            os.close(master)
            if slave >= 0:
                os.close(slave)


if __name__ == '__main__':
    unittest.main()
