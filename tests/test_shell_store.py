# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Local store validation, corruption preservation and restart semantics."""
import tempfile
import unittest
from pathlib import Path
from iarch.lib import shell_store as store


class ShellStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_todos_round_trip_and_duplicate_refusal(self):
        path = self.root / 'todo.json'
        doc = {'schema_version': 1, 'items': [{'id': 'a', 'text': 'Task', 'done': False}]}
        store.write_todos(path, doc)
        self.assertEqual(store.read_todos(path), doc)
        doc['items'].append(dict(doc['items'][0]))
        with self.assertRaises(store.StoreError):
            store.write_todos(path, doc)
        self.assertEqual(len(store.read_todos(path)['items']), 1)

    def test_corruption_is_not_overwritten(self):
        path = self.root / 'todo.json'
        path.write_text('{broken')
        with self.assertRaises(store.StoreError):
            store.write_todos(path, {'schema_version': 1, 'items': []})
        self.assertEqual(path.read_text(), '{broken')

    def test_stopwatch_survives_restart_and_clock_reversal(self):
        path = self.root / 'watch.json'
        store.set_stopwatch(path, 'start', now=100)
        self.assertEqual(store.stopwatch_elapsed(store.read_stopwatch(path), now=125), 25)
        paused = store.set_stopwatch(path, 'pause', now=130)
        self.assertEqual(store.stopwatch_elapsed(paused, now=1000), 30)
        store.set_stopwatch(path, 'start', now=500)
        self.assertEqual(store.stopwatch_elapsed(store.read_stopwatch(path), now=490), 30)
        self.assertEqual(store.set_stopwatch(path, 'reset', now=600)['elapsed'], 0)

    def test_timer_persists_and_cannot_go_negative(self):
        path = self.root / 'timer.json'
        store.set_timer(path, 'set', seconds=60, now=100)
        store.set_timer(path, 'start', now=100)
        self.assertEqual(store.timer_remaining(store.read_timer(path), now=125), 35)
        paused = store.set_timer(path, 'pause', now=130)
        self.assertEqual(store.timer_remaining(paused, now=999), 30)
        store.set_timer(path, 'start', now=200)
        self.assertEqual(store.timer_remaining(store.read_timer(path), now=300), 0)
        self.assertEqual(store.set_timer(path, 'reset', now=300)['remaining'], 0)
        with self.assertRaises(store.StoreError):
            store.set_timer(path, 'set', seconds=-1, now=300)

    def test_notification_history_rotation_and_invalid_preservation(self):
        path = self.root / 'notifications.json'
        item = {'app': 'app', 'summary': 'summary', 'body': '', 'urgency': 'normal',
                'timestamp': 1, 'image': '', 'actions': [{'id': 'open', 'label': 'Open'}]}
        # Seed at capacity without repeatedly writing files.
        store._write(path, {'schema_version': 1, 'items': [dict(item, timestamp=n)
                                                           for n in range(store.MAX_NOTIFICATIONS)]})
        result = store.append_notification(path, dict(item, timestamp=999))
        self.assertEqual(len(result['items']), store.MAX_NOTIFICATIONS)
        self.assertEqual(result['items'][0]['timestamp'], 1)
        self.assertEqual(result['items'][-1]['timestamp'], 999)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        before = path.read_bytes()
        with self.assertRaises(store.StoreError):
            store.append_notification(path, dict(item, urgency='unknown'))
        self.assertEqual(path.read_bytes(), before)
        path.write_text('{broken')
        with self.assertRaises(store.StoreError):
            store.append_notification(path, item)
        self.assertEqual(path.read_text(), '{broken')

    def test_notification_rotation_respects_byte_limit(self):
        path = self.root / 'notifications.json'
        item = {'app': 'app', 'summary': 's' * 1000, 'body': 'b' * 4000,
                'urgency': 'normal', 'timestamp': 1, 'image': '',
                'actions': [{'id': str(i), 'label': 'a' * 200} for i in range(20)]}
        doc = {'schema_version': 1, 'items': [dict(item, timestamp=n) for n in range(100)]}
        while len(__import__('json').dumps(doc, indent=2).encode()) >= store.MAX_BYTES - 16000:
            doc['items'].pop()
        store._write_private(path, doc)
        original_count = len(doc['items'])
        result = store.append_notification(path, dict(item, timestamp=999))
        self.assertLessEqual(path.stat().st_size, store.MAX_BYTES)
        self.assertEqual(result['items'][-1]['timestamp'], 999)
        self.assertLessEqual(len(result['items']), original_count + 1)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_schema_version_requires_integer_not_boolean(self):
        for reader, doc in (
            (store.read_todos, {'schema_version': True, 'items': []}),
            (store.read_timer, {'schema_version': True, 'remaining': 0, 'deadline': None}),
            (store.read_stopwatch, {'schema_version': True, 'elapsed': 0, 'started_at': None}),
        ):
            path = self.root / 'invalid.json'
            path.write_text(__import__('json').dumps(doc))
            with self.subTest(reader=reader.__name__), self.assertRaises(store.StoreError):
                reader(path)

    def test_symlink_is_refused(self):
        target = self.root / 'target'
        target.write_text('keep')
        path = self.root / 'todo.json'
        path.symlink_to(target)
        with self.assertRaises(store.StoreError):
            store.write_todos(path, {'schema_version': 1, 'items': []})
        self.assertEqual(target.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
