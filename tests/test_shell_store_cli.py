# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The shell store helper is private, serialized and rejects invalid requests."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StoreCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, HOME=str(self.root), IARCH_STATE_DIR=str(self.root / 'state'))

    def call(self, kind, value):
        return subprocess.run([sys.executable, str(ROOT / 'iarch/cli/shell_store_cli.py'), kind],
                              input=json.dumps(value), text=True, capture_output=True, env=self.env)

    def test_todo_roundtrip_private_and_invalid_preserved(self):
        result = self.call('todo', {'action': 'add', 'text': 'Do something'})
        self.assertEqual(result.returncode, 0, result.stderr)
        item = json.loads(result.stdout)['items'][0]
        path = self.root / 'state/todo.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        result = self.call('todo', {'action': 'toggle', 'id': item['id'], 'done': True})
        self.assertTrue(json.loads(result.stdout)['items'][0]['done'])
        before = path.read_bytes()
        self.assertNotEqual(self.call('todo', {'action': 'toggle', 'id': item['id'], 'done': 'yes'}).returncode, 0)
        self.assertEqual(path.read_bytes(), before)
        result = self.call('todo', {'action': 'delete', 'id': item['id']})
        self.assertEqual(json.loads(result.stdout)['items'], [])

    def test_timer_stopwatch_and_corrupt_file_refusal(self):
        self.assertEqual(self.call('timer', {'action': 'set', 'seconds': 60}).returncode, 0)
        self.assertIsNotNone(json.loads(self.call('timer', {'action': 'start'}).stdout)['deadline'])
        self.assertIsNotNone(json.loads(self.call('stopwatch', {'action': 'start'}).stdout)['started_at'])
        path = self.root / 'state/timer.json'
        path.write_text('{broken')
        self.assertNotEqual(self.call('timer', {'action': 'reset'}).returncode, 0)
        self.assertEqual(path.read_text(), '{broken')

    def test_explicit_recovery_preserves_corrupt_files_and_refuses_valid_or_missing(self):
        state = self.root / 'state'
        state.mkdir()
        for kind in ('todo', 'timer', 'stopwatch'):
            path = state / (kind + '.json')
            self.assertNotEqual(self.call(kind, {'action': 'recover'}).returncode, 0)
            corrupt = b'{broken\xff'
            path.write_bytes(corrupt)
            result = self.call(kind, {'action': 'recover'})
            self.assertEqual(result.returncode, 0, result.stderr)
            result = json.loads(result.stdout)
            backup = Path(result['backup'])
            self.assertEqual(backup.parent, state)
            self.assertEqual(backup.read_bytes(), corrupt)
            self.assertEqual(json.loads(path.read_text()), result['data'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotEqual(self.call(kind, {'action': 'recover'}).returncode, 0)
            self.assertEqual(backup.read_bytes(), corrupt)

    def test_recovery_refuses_symlinks_and_bad_request(self):
        state = self.root / 'state'
        state.mkdir()
        target = self.root / 'target'
        target.write_text('{broken')
        (state / 'todo.json').symlink_to(target)
        self.assertNotEqual(self.call('todo', {'action': 'recover'}).returncode, 0)
        self.assertNotEqual(self.call('todo', {'action': 'recover', 'extra': 1}).returncode, 0)
        self.assertEqual(target.read_text(), '{broken')
        self.assertEqual(list(state.glob('*.corrupt-*')), [])

    def test_lock_symlink_is_refused(self):
        state = self.root / 'state'
        state.mkdir()
        target = self.root / 'target'
        target.write_text('untouched')
        (state / '.shell-stores.lock').symlink_to(target)
        self.assertNotEqual(self.call('todo', {'action': 'read'}).returncode, 0)
        self.assertEqual(target.read_text(), 'untouched')


if __name__ == '__main__':
    unittest.main()
