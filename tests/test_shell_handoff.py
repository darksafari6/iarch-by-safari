# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Fault-injected handoff tests; no real shell or D-Bus is touched."""
import tempfile
import unittest
from pathlib import Path

from iarch.cli import engine_state, shell_handoff as handoff, theme_engine


class FakeSession:
    def __init__(self):
        self.running = {'classic': [11], 'dynamic': []}
        self.owner = handoff.Owner(True, 11, ':1.1')
        self.now = 0.0
        self.no_claim = False
        self.foreign_after_stop = False

    def get(self): return self.owner
    def pids(self, name): return list(self.running[name])
    def stop(self, name):
        self.running[name] = []
        self.owner = handoff.Owner(True, 99, ':1.99') if self.foreign_after_stop else handoff.Owner(True)
        return True
    def start(self, name):
        pid = 11 if name == 'classic' else 22
        self.running[name] = [pid]
        if not self.no_claim or name == 'classic':
            self.owner = handoff.Owner(True, pid, ':1.' + str(pid))
        return True
    def clock(self): return self.now
    def sleep(self, value): self.now += value


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.env = {'HOME': str(root), 'IARCH_STATE_DIR': str(root / 'state'),
                    'IARCH_CONFIG_DIR': str(root / 'config')}
        self.fake = FakeSession()

    def args(self):
        return dict(env=self.env, probe=self.fake, control=self.fake,
                    clock=self.fake.clock, sleep=self.fake.sleep)

    def test_success_records_verified_owner(self):
        state = handoff.handoff('classic', 'dynamic', **self.args())
        self.assertEqual('VERIFIED', state['phase'])
        self.assertEqual([22], self.fake.pids('dynamic'))
        self.assertEqual([], self.fake.pids('classic'))
        self.assertEqual(22, self.fake.owner.pid)
        self.assertEqual('dynamic', engine_state.selected_id(self.env))

    def test_timeout_restores_old_engine_and_owner(self):
        self.fake.no_claim = True
        with self.assertRaises(handoff.HandoffError) as caught:
            handoff.handoff('classic', 'dynamic', **self.args())
        self.assertEqual('FAILED_SAFE', caught.exception.state['phase'])
        self.assertEqual([11], self.fake.pids('classic'))
        self.assertEqual([], self.fake.pids('dynamic'))
        self.assertEqual(11, self.fake.owner.pid)
        self.assertGreaterEqual(self.fake.now, handoff.CLAIM_SECONDS)

    def test_foreign_claim_is_never_killed_and_recovery_is_open(self):
        self.fake.foreign_after_stop = True
        with self.assertRaises(handoff.HandoffError) as caught:
            handoff.handoff('classic', 'dynamic', **self.args())
        self.assertEqual('ROLLING_BACK', caught.exception.state['phase'])
        self.assertEqual(99, self.fake.owner.pid)
        self.assertEqual([], self.fake.pids('dynamic'))

    def test_unreadable_journal_is_not_overwritten(self):
        path = theme_engine.switch_record_path(self.env)
        path.parent.mkdir(parents=True)
        path.write_text('broken')
        with self.assertRaises(handoff.HandoffError):
            handoff.handoff('classic', 'dynamic', **self.args())
        self.assertEqual('broken', path.read_text())
        self.assertEqual([11], self.fake.pids('classic'))

    def test_recover_after_interruption_during_each_mutating_phase(self):
        for phase in ('STOPPING_OLD', 'WAITING_RELEASE', 'STARTING_NEW', 'WAITING_CLAIM', 'ROLLING_BACK'):
            with self.subTest(phase=phase):
                self.fake = FakeSession()
                self.fake.running = {'classic': [], 'dynamic': [22]}
                self.fake.owner = handoff.Owner(True, 22, ':1.22')
                state = {'schema_version': 2, 'phase': phase, 'previous_engine': 'classic',
                         'target_engine': 'dynamic', 'previous_record': {'previous': None}}
                engine_state.write_json(theme_engine.switch_record_path(self.env), state)
                result = handoff.recover(**self.args())
                self.assertEqual('RESTORED', result['phase'])
                self.assertEqual([11], self.fake.pids('classic'))
                self.assertEqual([], self.fake.pids('dynamic'))
                self.assertEqual(11, self.fake.owner.pid)
                self.assertEqual('RESTORED', handoff.recover(**self.args())['phase'])


if __name__ == '__main__': unittest.main()
