# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Fault-injected durable transaction runner tests with private temporary homes."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from iarch.lib import theme_transaction as tx


class Handler:
    def __init__(self, state, fail=None, crash=None):
        self.state, self.fail, self.crash = state, fail, crash
    def do(self, payload):
        self.state.append(payload)
        if self.crash == payload: raise SystemExit('simulated crash')
        if self.fail == payload: raise RuntimeError('injected failure')
    def verify(self, payload): return self.fail != 'verify-' + payload
    def undo(self, payload):
        if payload in self.state: self.state.remove(payload)


class ThemeTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.env = {'HOME': str(root), 'IARCH_STATE_DIR': str(root / 'state')}

    def test_success_is_verified_and_journalled(self):
        state = []
        journal = tx.execute([('change', 'a'), ('change', 'b')], {'change': Handler(state)}, env=self.env)
        self.assertEqual(['a', 'b'], state)
        self.assertEqual('committed', journal['state'])
        self.assertEqual('committed', tx.recover(journal['id'], {'change': Handler(state)}, env=self.env)['state'])
        self.assertEqual(['a', 'b'], state)

    def test_failure_and_verification_matrix_undo_in_reverse(self):
        for index, payload in enumerate(('a', 'b', 'c')):
            for failure in (payload, 'verify-' + payload):
                with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                    env = {'HOME': temp, 'IARCH_STATE_DIR': str(Path(temp) / 'state')}
                    state = []
                    handler = Handler(state, fail=failure)
                    with self.assertRaises(tx.TransactionError) as caught:
                        tx.execute([('change', p) for p in ('a', 'b', 'c')], {'change': handler}, env=env)
                    self.assertEqual([], state)
                    journal = json.loads(caught.exception.journal_path.read_text())
                    self.assertEqual('rolled_back', journal['state'])
                    self.assertEqual(['undone'] * (index + 1), [s['state'] for s in journal['steps'][:index + 1]])
                    self.assertEqual(['pending'] * (2 - index), [s['state'] for s in journal['steps'][index + 1:]])

    def test_crash_after_each_do_can_be_recovered_idempotently(self):
        for payload in ('a', 'b', 'c'):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp:
                env = {'HOME': temp, 'IARCH_STATE_DIR': str(Path(temp) / 'state')}
                state = []
                with self.assertRaises(SystemExit):
                    tx.execute([('change', p) for p in ('a', 'b', 'c')],
                               {'change': Handler(state, crash=payload)}, env=env)
                path, = (Path(env['IARCH_STATE_DIR']) / 'transactions').glob('*.json')
                with self.assertRaisesRegex(tx.TransactionError, 'unfinished'):
                    tx.execute([('change', 'other')], {'change': Handler(state)}, env=env)
                result = tx.recover(path.stem, {'change': Handler(state)}, env=env)
                self.assertEqual('rolled_back', result['state'])
                self.assertEqual([], state)
                self.assertEqual('rolled_back', tx.recover(path.stem, {'change': Handler(state)}, env=env)['state'])

    def test_refuses_untrusted_journal_and_symlink_directory(self):
        with self.assertRaises(tx.TransactionError): tx.recover('../bad', {}, env=self.env)
        state = Path(self.env['IARCH_STATE_DIR']); state.mkdir(exist_ok=True)
        (state / 'transactions').symlink_to(state, target_is_directory=True)
        with self.assertRaises(tx.TransactionError):
            tx.execute([('change', 'a')], {'change': Handler([])}, env=self.env)

    def test_oversize_journal_is_refused_before_the_first_step(self):
        state = []
        with self.assertRaisesRegex(tx.TransactionError, 'size limit'):
            tx.execute([('change', 'x' * tx.MAX_JOURNAL_BYTES)], {'change': Handler(state)}, env=self.env)
        self.assertEqual([], state)
        self.assertEqual([], list((Path(self.env['IARCH_STATE_DIR']) / 'transactions').glob('*.json')))

    def test_private_journal_and_directory_fsync_failure_precedes_mutation(self):
        state = []
        original = tx._sync_directory
        calls = []
        def sync(directory):
            calls.append(directory)
            if directory.name == 'transactions':
                raise OSError('directory sync failed')
            original(directory)
        with mock.patch.object(tx, '_sync_directory', side_effect=sync):
            with self.assertRaisesRegex(OSError, 'directory sync failed'):
                tx.execute([('change', 'a')], {'change': Handler(state)}, env=self.env)
        self.assertEqual([], state)
        path, = (Path(self.env['IARCH_STATE_DIR']) / 'transactions').glob('*.json')
        self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
        self.assertEqual('rolled_back', tx.recover(path.stem, {'change': Handler(state)}, env=self.env)['state'])

    def test_refuses_hardlinked_or_world_readable_journals(self):
        journal = tx.execute([('change', 'a')], {'change': Handler([])}, env=self.env)
        path = Path(self.env['IARCH_STATE_DIR']) / 'transactions' / (journal['id'] + '.json')
        path.chmod(0o644)
        with self.assertRaisesRegex(tx.TransactionError, 'private'):
            tx.recover(journal['id'], {'change': Handler([])}, env=self.env)
        path.chmod(0o600)
        link = path.with_suffix('.link')
        os.link(path, link)
        with self.assertRaisesRegex(tx.TransactionError, 'private'):
            tx.recover(journal['id'], {'change': Handler([])}, env=self.env)

    def test_real_process_death_during_do_and_undo_is_recoverable(self):
        script = '''
import os, sys
from pathlib import Path
from iarch.lib import theme_transaction as tx
root = Path(sys.argv[1]); phase = sys.argv[2]
env = {'HOME': str(root), 'IARCH_STATE_DIR': str(root / 'state')}
target = root / 'effect'
class Handler:
    def do(self, payload):
        target.write_text('changed')
        os._exit(71)
    def verify(self, payload): return True
    def undo(self, payload):
        target.unlink(missing_ok=True)
        if phase == 'crash-undo': os._exit(72)
handler = {'change': Handler()}
if phase == 'crash-do':
    tx.execute([('change', {})], handler, env=env)
else:
    path, = (root / 'state' / 'transactions').glob('*.json')
    assert tx.recover(path.stem, handler, env=env)['state'] == 'rolled_back'
'''
        root = Path(self.env['HOME'])
        def run(phase):
            return subprocess.run([sys.executable, '-c', script, str(root), phase],
                                  capture_output=True, text=True)
        first = run('crash-do')
        self.assertEqual(71, first.returncode, first.stderr)
        self.assertEqual('changed', (root / 'effect').read_text())
        second = run('crash-undo')
        self.assertEqual(72, second.returncode, second.stderr)
        self.assertFalse((root / 'effect').exists())
        third = run('recover')
        self.assertEqual(0, third.returncode, third.stderr)
        fourth = run('recover')
        self.assertEqual(0, fourth.returncode, fourth.stderr)

    def test_failed_undo_remains_recoverable(self):
        state = []
        class FailingUndo(Handler):
            def undo(self, payload): raise RuntimeError('cannot undo')
        with self.assertRaises(tx.TransactionError) as caught:
            tx.execute([('change', 'a')], {'change': FailingUndo(state, fail='a')}, env=self.env)
        path = caught.exception.journal_path
        self.assertEqual('recovery_needed', json.loads(path.read_text())['state'])
        self.assertEqual('rolled_back', tx.recover(path.stem, {'change': Handler(state)}, env=self.env)['state'])
        self.assertEqual([], state)


if __name__ == '__main__': unittest.main()
