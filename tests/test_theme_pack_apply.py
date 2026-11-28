# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Transactional apply uses a fake shell and compositor, never the real session."""
import json
import shutil
import tempfile
import threading
import unittest
from unittest import mock
from pathlib import Path
from iarch.cli import theme_pack_apply, theme_pack_render, theme_records
from iarch.lib.runner import Answer

ROOT = Path(__file__).resolve().parents[1]


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pack = self.root / 'example-pack'
        shutil.copytree(ROOT / 'data/themes/dynamic-reference', self.pack)
        for p in self.pack.rglob('*.json'):
            data = json.loads(p.read_text())
            data['id'] = 'example-pack'
            p.write_text(json.dumps(data))
        self.env = {'HOME': str(self.root), 'IARCH_CONFIG_DIR': str(self.root / 'config'),
                    'IARCH_STATE_DIR': str(self.root / 'state')}
        self.output = self.root / '.config/output.conf'
        self.output.parent.mkdir()
        self.output.write_text('old bytes\n')
        self.output.chmod(0o640)
        self.calls = []
        self.fail_ipc = False
        self.new_errors = False
        self.error_reads = 0

    def render(self, docs):
        return [('preserving', self.output, 'new bytes\n')]

    def run_command(self, command, timeout):
        self.calls.append(tuple(command))
        if command[:2] == ('hyprctl', 'configerrors'):
            self.error_reads += 1
            text = 'old warning\n' + ('new problem\n' if self.new_errors and self.error_reads > 1 else '')
            return Answer(tuple(command), 0, stdout=text)
        if command[0] == 'quickshell':
            return Answer(tuple(command), 1 if self.fail_ipc else 0, stdout='' if self.fail_ipc else 'true')
        return Answer(tuple(command), 0)

    def test_two_phase_shell_acknowledges_only_after_commit(self):
        seen = []
        def run(command, timeout):
            seen.append(tuple(command))
            method = command[-2]
            reply = {'apply': 'pending:42', 'status': 'ready', 'commit': 'true'}.get(method, 'false')
            return Answer(tuple(command), 0, stdout=reply)
        self.assertTrue(theme_pack_apply._signal('example-pack', run))
        self.assertEqual([c[-2:] for c in seen], [('apply', 'example-pack'), ('status', '42'), ('commit', '42')])

    def test_two_phase_does_not_commit_failed_validation(self):
        seen = []
        def run(command, timeout):
            seen.append(tuple(command))
            return Answer(tuple(command), 0, stdout='pending:9' if command[-2] == 'apply' else 'failed')
        self.assertFalse(theme_pack_apply._signal('example-pack', run))
        self.assertEqual([c[-2] for c in seen], ['apply', 'status'])

    def test_two_phase_timeout_never_commits(self):
        seen = []
        def run(command, timeout):
            seen.append(tuple(command))
            return Answer(tuple(command), 0, stdout='pending:7' if command[-2] == 'apply' else 'pending')
        with mock.patch.object(theme_pack_apply.time, 'monotonic', side_effect=[0, 1, 6]), \
             mock.patch.object(theme_pack_apply.time, 'sleep'):
            self.assertFalse(theme_pack_apply._signal('example-pack', run))
        self.assertEqual([c[-2] for c in seen], ['apply', 'status'])

    def test_two_phase_rejects_malformed_token_and_failed_commit(self):
        def malformed(command, timeout):
            return Answer(tuple(command), 0, stdout='pending:../danger')
        self.assertFalse(theme_pack_apply._signal('example-pack', malformed))
        def denied(command, timeout):
            response = {'apply': 'pending:1', 'status': 'ready', 'commit': 'false'}
            return Answer(tuple(command), 0, stdout=response[command[-2]])
        self.assertFalse(theme_pack_apply._signal('example-pack', denied))

    def test_transaction_lock_serializes_apply_and_rollback(self):
        attempted = threading.Event()
        entered = threading.Event()
        errors = []
        def contender():
            attempted.set()
            try:
                with theme_pack_apply._transaction_lock(self.env):
                    entered.set()
            except Exception as exc:
                errors.append(exc)
        with theme_pack_apply._transaction_lock(self.env):
            thread = threading.Thread(target=contender)
            thread.start()
            self.assertTrue(attempted.wait(2))
            self.assertFalse(entered.wait(0.1))
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)
        self.assertTrue(entered.is_set())

    def test_shared_lock_is_reentrant_for_nested_switch_and_apply(self):
        from iarch.lib import session_lock
        with session_lock.session_lock(self.env):
            with theme_pack_apply._transaction_lock(self.env):
                self.assertTrue((Path(self.env['IARCH_STATE_DIR']) / 'shell-switch.lock').is_file())

    def test_transaction_lock_refuses_symlink(self):
        state = Path(self.env['IARCH_STATE_DIR'])
        state.mkdir()
        (state / 'shell-switch.lock').symlink_to(self.output)
        with self.assertRaises(OSError):
            theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        self.assertEqual(self.output.read_text(), 'old bytes\n')
        self.assertEqual([], self.calls)

    def test_success(self):
        result = theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        self.assertEqual(result['verdict'], 'applied')
        self.assertEqual(self.output.read_text(), 'new bytes\n')
        self.assertEqual(theme_records.read_selection(self.env)['engine'], 'dynamic')

    def test_selection_is_committed_only_after_shell_and_compositor_verify(self):
        observed = []
        def run(command, timeout):
            observed.append((tuple(command), theme_records.read_selection(self.env)['engine']))
            return self.run_command(command, timeout)
        theme_pack_apply.apply(self.pack, self.render, env=self.env, run=run)
        self.assertTrue(any(command[0] == 'quickshell' for command, _ in observed))
        self.assertTrue(any(command[:2] == ('hyprctl', 'reload') for command, _ in observed))
        self.assertTrue(all(engine == 'classic' for _, engine in observed))
        self.assertEqual('dynamic', theme_records.read_selection(self.env)['engine'])

    def test_no_transition_is_forwarded_to_shell(self):
        theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command, no_transition=True)
        self.assertTrue(any(c[-2:] == ('applyImmediate', 'example-pack') for c in self.calls))

    def test_full_renderer_applies_and_restores_with_fake_session(self):
        render = lambda docs: theme_pack_render.actions(docs, self.env)
        report = theme_pack_apply.apply(self.pack, render, env=self.env, run=self.run_command)
        self.assertEqual(report['verdict'], 'applied')
        config = self.root / '.config'
        self.assertTrue((config / 'hypr/generated/theme.lua').is_file())
        self.assertTrue((config / 'gtk-4.0/settings.ini').is_file())
        self.assertTrue((config / 'fontconfig/fonts.conf').read_text().startswith('<!--'))
        theme_pack_apply.rollback(env=self.env, run=self.run_command)
        self.assertFalse((config / 'hypr/generated/theme.lua').exists())
        self.assertFalse((config / 'gtk-4.0/settings.ini').exists())

    def test_success_then_explicit_rollback(self):
        theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        result = theme_pack_apply.rollback(env=self.env, run=self.run_command)
        self.assertEqual(result['verdict'], 'rolled-back')
        self.assertEqual(self.output.read_text(), 'old bytes\n')
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o640)
        self.assertFalse(theme_records.selection_path(self.env).exists())

    def test_rollback_refuses_to_overwrite_user_edits(self):
        theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        self.output.write_text('user edit\n')
        self.calls.clear()
        with self.assertRaisesRegex(theme_pack_apply.ApplyError, 'changed since apply'):
            theme_pack_apply.rollback(env=self.env, run=self.run_command)
        self.assertEqual(self.output.read_text(), 'user edit\n')
        self.assertEqual(self.calls, [])

    def test_rollback_refuses_stale_selection(self):
        theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        theme_records.write_selection({'schema_version': 1, 'id': 'forest-night',
                                       'engine': 'classic', 'overrides': {}}, self.env)
        with self.assertRaisesRegex(theme_pack_apply.ApplyError, 'selection changed'):
            theme_pack_apply.rollback(env=self.env, run=self.run_command)
        self.assertEqual(self.output.read_text(), 'new bytes\n')

    def test_legacy_unguarded_checkpoint_is_refused(self):
        theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        path = theme_pack_apply._checkpoint_path(self.env)
        data = json.loads(path.read_text())
        data['schema_version'] = 1
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(theme_pack_apply.ApplyError, 'invalid rollback record'):
            theme_pack_apply.rollback(env=self.env, run=self.run_command)
        self.assertEqual(self.output.read_text(), 'new bytes\n')

    def test_ipc_transport_success_without_acknowledgement_rolls_back(self):
        def unanswered(command, timeout):
            if command[0] == 'quickshell':
                return Answer(tuple(command), 0, stdout='false')
            return self.run_command(command, timeout)
        with self.assertRaisesRegex(theme_pack_apply.ApplyError, 'acknowledge'):
            theme_pack_apply.apply(self.pack, self.render, env=self.env, run=unanswered)
        self.assertEqual(self.output.read_text(), 'old bytes\n')

    def test_shell_failure_restores_files_and_record(self):
        self.fail_ipc = True
        with self.assertRaises(theme_pack_apply.ApplyError):
            theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        self.assertEqual(self.output.read_text(), 'old bytes\n')
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o640)
        self.assertFalse(theme_records.selection_path(self.env).exists())
        self.assertIn(('hyprctl', 'reload'), self.calls)

    def test_new_compositor_errors_roll_back(self):
        self.new_errors = True
        with self.assertRaisesRegex(theme_pack_apply.ApplyError, 'new problem'):
            theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        self.assertEqual(self.output.read_text(), 'old bytes\n')
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o640)
        self.assertFalse(theme_records.selection_path(self.env).exists())

    def test_dynamic_renderer_refuses_classic_shell_configuration(self):
        target = self.root / '.config/noctalia/config.toml'
        target.parent.mkdir(parents=True)
        target.write_text('user preferences\n')
        with self.assertRaisesRegex(theme_pack_apply.ApplyError, 'Classic shell'):
            theme_pack_apply.apply(self.pack, lambda docs: [('preserving', target, 'changed')],
                                   env=self.env, run=self.run_command)
        self.assertEqual('user preferences\n', target.read_text())
        self.assertEqual([], self.calls)

    def test_failed_compositor_verification_restores_previous_dynamic_theme(self):
        previous = {'schema_version': 1, 'id': 'previous-theme', 'engine': 'dynamic', 'overrides': {}}
        theme_records.write_selection(previous, self.env)
        before = theme_records.selection_path(self.env).read_bytes()
        self.new_errors = True
        with self.assertRaisesRegex(theme_pack_apply.ApplyError, 'new problem'):
            theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        self.assertEqual(before, theme_records.selection_path(self.env).read_bytes())
        self.assertEqual('old bytes\n', self.output.read_text())
        calls = [c[-2:] for c in self.calls if c[0] == 'quickshell']
        self.assertEqual([('apply', 'example-pack'), ('apply', 'previous-theme')], calls)

    def test_renderer_cannot_write_outside_configuration(self):
        target = self.root / 'outside.txt'
        with self.assertRaisesRegex(theme_pack_apply.ApplyError, 'escapes configuration'):
            theme_pack_apply.apply(self.pack, lambda docs: [('preserving', target, 'bad')],
                                   env=self.env, run=self.run_command)
        self.assertFalse(target.exists())
        self.assertEqual(self.calls, [])

    def test_renderer_cannot_escape_via_symlink_parent(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.root / '.config/link').symlink_to(outside, target_is_directory=True)
        target = self.root / '.config/link/file'
        with self.assertRaisesRegex(theme_pack_apply.ApplyError, 'escapes configuration'):
            theme_pack_apply.apply(self.pack, lambda docs: [('preserving', target, 'bad')],
                                   env=self.env, run=self.run_command)
        self.assertFalse((outside / 'file').exists())

    def test_validation_failure_never_writes(self):
        (self.pack / 'palette.json').write_text('{}')
        with self.assertRaises(ValueError):
            theme_pack_apply.apply(self.pack, self.render, env=self.env, run=self.run_command)
        self.assertEqual(self.output.read_text(), 'old bytes\n')
        self.assertEqual(self.calls, [])

    def test_unavailable_baseline_refuses_before_writes(self):
        with self.assertRaises(theme_pack_apply.ApplyError):
            theme_pack_apply.apply(self.pack, self.render, env=self.env, run=lambda *a: None)
        self.assertEqual(self.output.read_text(), 'old bytes\n')

    def test_reference_cannot_apply(self):
        with self.assertRaisesRegex(theme_pack_apply.ApplyError, 'reference'):
            theme_pack_apply.apply(ROOT / 'data/themes/dynamic-reference', self.render, env=self.env, run=self.run_command)


if __name__ == '__main__':
    unittest.main()
