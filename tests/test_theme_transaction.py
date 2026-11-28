# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Fault-injected durable transaction runner tests with private temporary homes."""
import json
import tempfile
import unittest
from pathlib import Path

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
