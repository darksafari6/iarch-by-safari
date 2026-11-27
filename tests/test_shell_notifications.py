# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Notification persistence uses bounded stdin and private files."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class NotificationTests(unittest.TestCase):
    def test_cli_history_private_and_refuses_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, HOME=temp, IARCH_STATE_DIR=str(Path(temp) / 'state'))
            command = [sys.executable, str(ROOT / 'iarch/cli/shell_notifications.py')]
            item = {'app': 'app', 'summary': 'hello', 'body': '', 'urgency': 'normal',
                    'timestamp': 1, 'image': '', 'actions': []}
            result = subprocess.run(command + ['append'], input=json.dumps(item), env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            path = Path(temp) / 'state/notifications.json'
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(result.stdout), {'ok': True, 'count': 1})
            read = subprocess.run(command + ['read'], env=env, text=True, capture_output=True)
            self.assertEqual(json.loads(read.stdout)['items'][0]['summary'], 'hello')
            path.write_text('{broken')
            result = subprocess.run(command + ['append'], input=json.dumps(item), env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_text(), '{broken')
            result = subprocess.run(command + ['append'], input='x' * 32769, env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_text(), '{broken')

    def test_ownership_probe_compares_actual_bus_pid(self):
        from unittest.mock import patch
        from io import StringIO
        from contextlib import redirect_stdout
        from iarch.cli import shell_notifications
        from iarch.lib.dbus_probe import BusOwner
        with patch.object(shell_notifications.dbus_probe, 'notification_server', return_value=BusOwner('name', ':1.9', 42, True)):
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(shell_notifications.main(['owner', '--pid', '42']), 0)
            self.assertTrue(json.loads(output.getvalue())['available'])
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(shell_notifications.main(['owner', '--pid', '43']), 0)
            self.assertFalse(json.loads(output.getvalue())['available'])

    def test_grouping_is_bounded_and_preserves_arrival_order(self):
        import shutil
        node = shutil.which('node')
        if not node:
            self.skipTest('Node unavailable')
        module = ROOT / 'iarch/shell/services/notification_groups.js'
        code = """const assert=require('assert'), g=require(process.argv[1]);
let a={appName:'a'}, b={appName:'b'}, c={appName:'a'};
let groups=g.group([a,b,c]); assert.equal(groups.length,2);
assert.deepEqual(groups[0].items,[a,c]); assert.deepEqual(groups[1].items,[b]);
assert.deepEqual(g.group(new Array(201).fill(a)),[]);
"""
        result = subprocess.run([node, '-e', code, str(module)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_server_is_opt_in_and_does_not_advertise_unimplemented_ui(self):
        shell = (ROOT / 'iarch/shell/ShellCore.qml').read_text()
        server = (ROOT / 'iarch/shell/services/Notifications.qml').read_text()
        self.assertIn('IARCH_ENABLE_NOTIFICATIONS', shell)
        self.assertIn('!shell.preview', shell)
        self.assertIn('property bool actionsVisible: false', server)
        self.assertIn('actionsSupported: root.actionsVisible', server)
        self.assertIn('property bool imagesVisible: false', server)
        self.assertIn('imageSupported: root.imagesVisible', server)
        self.assertIn('notification.transient', server)


if __name__ == '__main__':
    unittest.main()
