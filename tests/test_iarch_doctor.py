# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Prove iarch-doctor asks before it claims, and never invents an answer.

There is no Noctalia in this sandbox, so the shell is faked the way
tests/test_iarch_anim.py fakes hyprctl: a script on PATH that answers
``notification-dnd-status`` with ``on``/``off`` and ``notification-show`` with
the literal ``ok`` or an ``error:`` line, exactly as the handlers in
src/app/application_ipc.cpp do at v5.4.1. Every call is logged, one argument per
line, so a test can assert what was really sent rather than what the report says
was sent.

What is asserted:

* a missing shell is a check that could not run, not a failure: exit 0, no
  probes, and the report says which binary was absent;
* Do Not Disturb on means nothing is sent at all, because a toast nobody can see
  is not a passed test — and ``--force`` sends anyway while saying so;
* the three internal probes carry the documented JSON fields, and the critical
  one asks for ``timeout_ms = 0`` because urgency alone does not make a toast
  persistent upstream;
* ``--timeout-ms`` reaches the timed probes and never the critical one;
* a daemon that answers ``error:`` fails the test with exit 1 and quotes the
  daemon's own words;
* the external probe is skipped, not failed, when notify-send is absent, and is
  sent over the documented notify-send flags when it is present;
* the process-table search reports what it found, and says "not searched" rather
  than "none seen" when pgrep is missing;
* ``dnd status`` prints exactly one word on stdout so a script can branch on it;
* ``--dry-run`` sends nothing and still prints the exact command vectors;
* ``--json`` prints one parseable object and nothing else.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import iarch_doctor as doctor  # noqa: E402

FAKE_NOCTALIA = '''#!/bin/sh
# A stand-in for `noctalia msg ...` at v5.4.1. It logs one line per argument so a
# test can read back the exact payload, then answers the way the IPC handlers do:
# "ok" on success, "error: ..." on a rejected payload, and "on"/"off" for
# notification-dnd-status.
LOG="$FAKE_BIN/calls.log"
for arg in "$@"; do printf '%s\\n' "$arg" >> "$LOG"; done
printf -- '--\\n' >> "$LOG"
case "$*" in
  *notification-dnd-status*)
    printf '%s\\n' "${DND_STATE:-off}"
    exit 0
    ;;
  *notification-show*)
    if [ -n "$SHOW_ERROR" ]; then printf 'error: %s\\n' "$SHOW_ERROR"; exit 0; fi
    printf 'ok\\n'
    exit 0
    ;;
esac
if [ -n "$MSG_EXIT" ]; then exit "$MSG_EXIT"; fi
printf 'ok\\n'
exit 0
'''

FAKE_NOTIFY_SEND = '''#!/bin/sh
LOG="$FAKE_BIN/calls.log"
for arg in "$@"; do printf '%s\\n' "$arg" >> "$LOG"; done
printf -- '--\\n' >> "$LOG"
if [ -n "$NOTIFY_SEND_FAIL" ]; then
  printf 'notify-send: %s\\n' "$NOTIFY_SEND_FAIL" >&2
  exit 1
fi
exit 0
'''

FAKE_PGREP = '''#!/bin/sh
# Only the last argument (the pattern) matters here; -x and -l are echoed into the
# log so a test can assert the search was exact and listed names.
LOG="$FAKE_BIN/calls.log"
for arg in "$@"; do printf '%s\\n' "$arg" >> "$LOG"; done
printf -- '--\\n' >> "$LOG"
if [ -n "$PGREP_FOUND" ]; then printf '%s\\n' "$PGREP_FOUND"; exit 0; fi
exit 1
'''


class Sandbox(unittest.TestCase):
    """A temporary PATH with a fake shell, per test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.fake_bin = root / 'bin'
        self.fake_bin.mkdir(parents=True)
        self.log = self.fake_bin / 'calls.log'

        for name, body in (('noctalia', FAKE_NOCTALIA),
                           ('notify-send', FAKE_NOTIFY_SEND),
                           ('pgrep', FAKE_PGREP)):
            path = self.fake_bin / name
            path.write_text(body, encoding='utf-8')
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

        # PATH holds nothing but the fake bin dir. A real pgrep, notify-send or
        # noctalia on this machine would otherwise answer for the removed fake and
        # quietly turn a "could not be checked" test into a passing one. The fakes
        # run through an absolute #!/bin/sh, so they need no PATH of their own.
        self.env: Dict[str, str] = {
            'PATH': str(self.fake_bin),
            'FAKE_BIN': str(self.fake_bin),
            'HOME': str(root),
        }
        patcher = mock.patch.dict(os.environ, self.env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def remove_binary(self, name: str) -> None:
        (self.fake_bin / name).unlink()

    def calls(self) -> List[List[str]]:
        """Every logged invocation, as its argument vector."""
        if not self.log.is_file():
            return []
        groups: List[List[str]] = []
        current: List[str] = []
        for line in self.log.read_text(encoding='utf-8').splitlines():
            if line == '--':
                groups.append(current)
                current = []
            else:
                current.append(line)
        if current:
            groups.append(current)
        return groups

    def show_payloads(self) -> List[Dict[str, Any]]:
        """The JSON payloads handed to notification-show, in order."""
        payloads = []
        for call in self.calls():
            if len(call) >= 3 and call[0] == 'msg' and call[1] == 'notification-show':
                payloads.append(json.loads(call[2]))
        return payloads

    def notify_send_calls(self) -> List[List[str]]:
        return [call for call in self.calls()
                if call and call[0].startswith('--app-name=')]

    def run_cli(self, *argv: str) -> Dict[str, Any]:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = doctor.main(list(argv))
        return {'code': code, 'stdout': out.getvalue(), 'stderr': err.getvalue()}

    def run_json(self, *argv: str) -> Dict[str, Any]:
        result = self.run_cli(*argv, '--json')
        self.assertEqual(0, len(result['stderr'].strip()), result['stderr'])
        result['report'] = json.loads(result['stdout'])
        return result


class WithoutAShell(Sandbox):
    def test_a_missing_shell_is_not_a_failure(self):
        self.remove_binary('noctalia')
        result = self.run_json('notify-test')
        self.assertEqual(0, result['code'])
        report = result['report']
        self.assertEqual('not-run', report['verdict'])
        self.assertEqual([], report['probes'])
        self.assertIn('noctalia is not installed', report['shell_ipc'])
        self.assertEqual([], [c for c in self.calls() if c and c[0] == 'msg'],
                         'nothing was sent to a shell that is not there')

    def test_a_shell_that_is_installed_but_silent_says_so(self):
        self.env['MSG_EXIT'] = '0'
        with mock.patch.dict(os.environ, {'DND_STATE': ''}), \
                mock.patch.object(doctor, 'dnd_status', return_value=(None, None)):
            result = self.run_json('notify-test')
        self.assertEqual('not-run', result['report']['verdict'])
        self.assertIn('gave no answer', result['report']['shell_ipc'])

    def test_dnd_status_prints_one_word_even_with_no_shell(self):
        self.remove_binary('noctalia')
        result = self.run_cli('dnd', 'status')
        self.assertEqual(0, result['code'])
        self.assertEqual('unknown', result['stdout'].strip())
        self.assertIn('noctalia', result['stderr'])


class TheProbes(Sandbox):
    def test_three_internal_probes_are_sent_with_the_documented_fields(self):
        result = self.run_json('notify-test', '--delay', '0')
        self.assertEqual(0, result['code'])
        report = result['report']
        self.assertEqual('sent', report['verdict'])
        # Three internal probes plus the external one, which notify-send carries.
        self.assertEqual(4, report['sent'])
        payloads = self.show_payloads()
        self.assertEqual(['low', 'normal', 'critical'],
                         [p['summary'].rsplit('—', 1)[1].strip() for p in payloads])
        for payload in payloads:
            self.assertEqual(doctor.APP_NAME, payload['app_name'])
            self.assertIn(payload['urgency'], ('low', 'normal', 'critical'))
            self.assertTrue(payload['body'].strip())
            self.assertIsInstance(payload['timeout_ms'], int)

    def test_the_critical_probe_is_persistent_because_it_asked_to_be(self):
        self.run_json('notify-test', '--delay', '0')
        critical = self.show_payloads()[2]
        self.assertEqual('critical', critical['urgency'])
        self.assertEqual(0, critical['timeout_ms'])
        # The body has to say why it stayed, or the test teaches the wrong rule.
        self.assertIn('timeout_ms = 0', critical['body'])

    def test_the_timeout_flag_moves_the_timed_probes_and_never_the_critical_one(self):
        self.run_json('notify-test', '--delay', '0', '--timeout-ms', '2500')
        low, normal, critical = self.show_payloads()
        self.assertEqual(2500, low['timeout_ms'])
        self.assertEqual(2500, normal['timeout_ms'])
        self.assertEqual(0, critical['timeout_ms'])

    def test_the_default_timeout_is_the_upstream_default(self):
        self.assertEqual(6000, doctor.DEFAULT_TIMEOUT_MS)
        self.run_json('notify-test', '--delay', '0')
        self.assertEqual(6000, self.show_payloads()[0]['timeout_ms'])

    def test_probes_are_separated_so_the_stack_is_visible(self):
        sleeps: List[float] = []
        with mock.patch.object(doctor.time, 'sleep', side_effect=sleeps.append):
            self.run_json('notify-test', '--delay', '0.25')
        # Internal low/normal/critical plus the external probe: three gaps.
        self.assertEqual([0.25, 0.25, 0.25], sleeps)

    def test_no_shell_means_no_delay_either(self):
        self.remove_binary('noctalia')
        sleeps: List[float] = []
        with mock.patch.object(doctor.time, 'sleep', side_effect=sleeps.append):
            self.run_cli('notify-test')
        self.assertEqual([], sleeps)


class DoNotDisturb(Sandbox):
    def test_dnd_on_sends_nothing(self):
        with mock.patch.dict(os.environ, {'DND_STATE': 'on'}):
            result = self.run_json('notify-test', '--delay', '0')
        self.assertEqual(0, result['code'], 'suppression is a diagnosis, not a failure')
        report = result['report']
        self.assertEqual('blocked', report['verdict'])
        self.assertIs(True, report['do_not_disturb'])
        self.assertEqual([], report['probes'])
        self.assertEqual([], self.show_payloads(), 'a suppressed session gets no toasts')
        self.assertTrue(any('--force' in note for note in report['notes']))

    def test_a_dry_run_is_not_blocked_by_suppression(self):
        """A dry run sends nothing either way, so it must still build the probes."""
        with mock.patch.dict(os.environ, {'DND_STATE': 'on'}):
            result = self.run_json('notify-test', '--dry-run')
        report = result['report']
        self.assertEqual('dry-run', report['verdict'])
        self.assertEqual(4, len(report['probes']))
        self.assertEqual([], self.show_payloads())
        self.assertTrue(any('would be blocked' in note for note in report['notes']))

    def test_force_sends_into_a_suppressed_session_and_says_so(self):
        with mock.patch.dict(os.environ, {'DND_STATE': 'on'}):
            result = self.run_json('notify-test', '--force', '--delay', '0')
        self.assertEqual('sent', result['report']['verdict'])
        self.assertEqual(3, len(self.show_payloads()))
        self.assertTrue(any('suppressed session' in note
                            for note in result['report']['notes']))

    def test_an_unreadable_dnd_state_still_sends_and_still_says_so(self):
        with mock.patch.object(doctor, 'dnd_status', return_value=(None, mock.Mock(
                **{'as_dict.return_value': {'returncode': 0, 'stdout': 'maybe'}}))):
            result = self.run_json('notify-test', '--delay', '0')
        self.assertIsNone(result['report']['do_not_disturb'])
        self.assertEqual('sent', result['report']['verdict'])
        self.assertTrue(any('could not be read' in note for note in result['report']['notes']))

    def test_status_toggle_and_set_use_the_documented_verbs(self):
        result = self.run_cli('dnd', 'status')
        self.assertEqual('off', result['stdout'].strip())

        with mock.patch.dict(os.environ, {'DND_STATE': 'on'}):
            result = self.run_cli('dnd', 'status')
        self.assertEqual('on', result['stdout'].strip())

        self.run_cli('dnd', 'toggle')
        self.run_cli('dnd', 'on')
        self.run_cli('dnd', 'off')
        verbs = [call[1] for call in self.calls() if call and call[0] == 'msg']
        self.assertEqual(['notification-dnd-status', 'notification-dnd-status',
                          'notification-dnd-toggle', 'notification-dnd-status',
                          'notification-dnd-set', 'notification-dnd-status',
                          'notification-dnd-set', 'notification-dnd-status'], verbs)
        sets = [call for call in self.calls()
                if len(call) > 2 and call[1] == 'notification-dnd-set']
        self.assertEqual([['msg', 'notification-dnd-set', 'on'],
                          ['msg', 'notification-dnd-set', 'off']], sets)

    def test_dnd_reports_that_no_schedule_exists(self):
        result = self.run_json('dnd', 'on')
        self.assertEqual('ok', result['report']['verdict'])
        self.assertIn('no DND schedule', result['report']['note'])


class WhenTheShellRefuses(Sandbox):
    def test_an_error_answer_fails_the_test_and_quotes_the_shell(self):
        with mock.patch.dict(os.environ, {'SHOW_ERROR': 'notification-show requires a summary'}):
            result = self.run_json('notify-test', '--delay', '0')
        self.assertEqual(1, result['code'])
        report = result['report']
        self.assertEqual('error', report['verdict'])
        self.assertEqual(3, len(report['errors']))
        self.assertIn('requires a summary', report['errors'][0])
        by_id = {p['id']: p for p in report['probes']}
        for probe_id in ('low', 'normal', 'critical'):
            self.assertEqual('error', by_id[probe_id]['verdict'])
        # notify-send is a different program and is unaffected by the shell's refusal.
        self.assertEqual('sent', by_id['external']['verdict'])
        self.assertNotIn('external', ' '.join(report['errors']))

    def test_a_failing_external_probe_does_not_fail_the_test(self):
        with mock.patch.dict(os.environ, {'NOTIFY_SEND_FAIL': 'unsupported option'}):
            result = self.run_json('notify-test', '--delay', '0')
        self.assertEqual(0, result['code'], 'the external probe is auxiliary')
        by_id = {p['id']: p for p in result['report']['probes']}
        self.assertEqual('sent', by_id['normal']['verdict'])
        self.assertEqual('error', by_id['external']['verdict'])
        self.assertFalse(by_id['external']['required'])


class TheExternalProbe(Sandbox):
    def test_it_is_skipped_when_notify_send_is_absent(self):
        self.remove_binary('notify-send')
        result = self.run_json('notify-test', '--delay', '0')
        ids = [p['id'] for p in result['report']['probes']]
        self.assertEqual(['low', 'normal', 'critical'], ids)
        self.assertEqual([], self.notify_send_calls())
        self.assertTrue(any('notify-send is not installed' in n
                            for n in result['report']['notes']))

    def test_it_goes_over_the_bus_rather_than_the_ipc_socket(self):
        result = self.run_json('notify-test', '--delay', '0')
        calls = self.notify_send_calls()
        self.assertEqual(1, len(calls))
        call = calls[0]
        self.assertEqual('--app-name=iArch', call[0])
        self.assertIn('--urgency=critical', call)
        self.assertIn('--expire-time=6000', call)
        self.assertIn('org.freedesktop.Notifications', call[-1])
        self.assertEqual('sent',
                         [p for p in result['report']['probes'] if p['id'] == 'external'][0]['verdict'])

    def test_the_command_vector_is_an_argv_list_with_no_shell(self):
        result = self.run_json('notify-test', '--dry-run')
        for probe in result['report']['probes']:
            self.assertIsInstance(probe['command'], list)
            self.assertTrue(all(isinstance(part, str) for part in probe['command']))
            self.assertNotIn(';', ' '.join(probe['command']))
            self.assertNotIn('|', ' '.join(probe['command']))


class TheProcessTableSearch(Sandbox):
    def test_a_competing_daemon_is_named_and_nothing_is_stopped(self):
        with mock.patch.dict(os.environ, {'PGREP_FOUND': '4242 dunst'}):
            result = self.run_json('notify-test', '--delay', '0')
        report = result['report']
        self.assertEqual(['dunst'], report['competing_daemons'])
        self.assertIs(True, report['competing_daemons_searched'])
        self.assertEqual(0, result['code'], 'another daemon is a warning, not a failure')
        self.assertTrue(any('Nothing was stopped' in n for n in report['notes']))

    def test_a_clean_process_table_says_none_seen(self):
        result = self.run_cli('notify-test', '--delay', '0')
        self.assertIn('other daemons   none seen', result['stdout'])
        self.assertNotIn('not searched', result['stdout'])

    def test_without_pgrep_it_refuses_to_claim_a_clean_table(self):
        self.remove_binary('pgrep')
        result = self.run_cli('notify-test', '--delay', '0')
        self.assertIn('other daemons   not searched', result['stdout'])
        self.assertIn('pgrep is not installed', result['stdout'])
        self.assertNotIn('none seen', result['stdout'])

    def test_the_search_is_exact_and_lists_names(self):
        doctor.competing_daemons()
        call = [c for c in self.calls() if c and c[0] == '-x']
        self.assertTrue(call, 'pgrep was not asked for an exact, listed match')
        self.assertIn('-l', call[0])
        pattern = call[0][-1]
        for name in doctor.KNOWN_NOTIFICATION_DAEMONS:
            self.assertIn(name, pattern.split('|'))

    def test_an_unusable_pgrep_answer_is_not_read_as_clean(self):
        with mock.patch.dict(os.environ, {'PGREP_FOUND': ''}), \
                mock.patch.object(doctor, '_run',
                                  return_value=doctor.Answer(('pgrep',), 2, '', 'bad pattern')):
            found = doctor.competing_daemons()
        self.assertIs(False, found['searched'])
        self.assertIn('no usable answer', found['note'])


class ReportingShapes(Sandbox):
    def test_json_is_one_object_and_nothing_else(self):
        result = self.run_cli('notify-test', '--delay', '0', '--json')
        self.assertEqual('', result['stderr'].strip())
        parsed = json.loads(result['stdout'])
        self.assertIsInstance(parsed, dict)
        self.assertEqual(result['stdout'].strip(),
                         json.dumps(parsed, indent=2, ensure_ascii=False))

    def test_dry_run_sends_nothing_but_prints_the_commands(self):
        result = self.run_json('notify-test', '--dry-run')
        self.assertEqual('dry-run', result['report']['verdict'])
        self.assertEqual([], self.show_payloads(), 'a dry run sends no toast')
        self.assertEqual([], self.notify_send_calls(), 'a dry run sends no toast')
        self.assertEqual(4, len(result['report']['probes']))
        first = result['report']['probes'][0]
        self.assertEqual(['noctalia', 'msg', 'notification-show'], first['command'][:3])
        self.assertEqual('low', json.loads(first['command'][3])['urgency'])

    def test_the_human_report_names_what_to_look_for(self):
        result = self.run_cli('notify-test', '--delay', '0')
        self.assertEqual(0, result['code'])
        for expected in ('shell IPC', 'do not disturb', 'other daemons',
                         '[OK] low', '[OK] normal', '[OK] critical',
                         'hover pausing the countdown', 'toast-only'):
            self.assertIn(expected, result['stdout'])

    def test_internal_probes_never_claim_to_reach_history(self):
        result = self.run_cli('notify-test', '--delay', '0')
        self.assertIn('cannot exercise the history panel', result['stdout'])

    def test_negative_numbers_are_a_usage_error(self):
        for argv in (('notify-test', '--timeout-ms', '-1'),
                     ('notify-test', '--delay', '-0.5')):
            with self.subTest(argv=argv):
                result = self.run_cli(*argv)
                self.assertEqual(2, result['code'])
                self.assertIn('cannot be negative', result['stderr'])

    def test_unknown_actions_are_rejected_by_the_parser(self):
        with self.assertRaises(SystemExit) as caught:
            with redirect_stderr(StringIO()):
                doctor.main(['dnd', 'maybe'])
        self.assertEqual(2, caught.exception.code)


class TheRunnerKeepsTwoKindsOfNoAnswerApart(Sandbox):
    def test_a_non_zero_exit_with_no_text_is_still_an_answer(self):
        with mock.patch.dict(os.environ, {'MSG_EXIT': '3'}):
            answer = doctor.msg('notification-dnd-toggle')
        self.assertIsNotNone(answer)
        self.assertEqual(3, answer.returncode)
        self.assertFalse(answer.ok)

    def test_a_missing_binary_is_no_answer_at_all(self):
        self.remove_binary('noctalia')
        self.assertIsNone(doctor.msg('notification-dnd-status'))

    def test_a_timeout_is_no_answer_rather_than_a_hang(self):
        with mock.patch.object(doctor.subprocess, 'run',
                               side_effect=subprocess.TimeoutExpired('noctalia', 10)):
            self.assertIsNone(doctor.msg('notification-dnd-status'))

    def test_ok_means_the_literal_ok(self):
        answer = doctor.Answer(('noctalia', 'msg', 'x'), 0, 'ok\n', '')
        self.assertTrue(answer.ok)
        self.assertFalse(doctor.Answer(('noctalia',), 0, 'okay\n', '').ok)

    def test_the_ipc_timeout_is_bounded(self):
        self.assertLessEqual(doctor.IPC_TIMEOUT_SECONDS, 30)
        self.assertGreater(doctor.IPC_TIMEOUT_SECONDS, 0)


class NoSecondDaemonIsEverStarted(Sandbox):
    def test_the_tool_only_ever_calls_the_shell_and_two_readers(self):
        """Nothing here may launch, install, enable or kill a daemon."""
        seen: List[str] = []
        real_run = subprocess.run

        def spy(command, *args, **kwargs):
            seen.append(command[0] if isinstance(command, (list, tuple)) else str(command))
            return real_run(command, *args, **kwargs)

        with mock.patch.object(doctor.subprocess, 'run', side_effect=spy):
            self.run_cli('notify-test', '--delay', '0')
            self.run_cli('dnd', 'toggle')
        self.assertTrue(seen)
        allowed = {'noctalia', 'notify-send', 'pgrep'}
        self.assertEqual(set(), set(seen) - allowed,
                         f'unexpected programs were run: {sorted(set(seen) - allowed)}')

    def test_the_known_daemon_list_is_detection_only(self):
        source = (ROOT / 'iarch' / 'cli' / 'iarch_doctor.py').read_text(encoding='utf-8')
        for verb in ('systemctl', 'kill', 'pkill', 'pacman', 'rm -'):
            self.assertNotIn(verb, source, f'{verb} has no business in a diagnostic')


if __name__ == '__main__':
    unittest.main()
