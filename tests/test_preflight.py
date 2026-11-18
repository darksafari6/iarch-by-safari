#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The read-only report install.sh runs before its first privileged step.

The interesting half is not that the probes work -- they are reads of /proc, /sys
and four reporting commands -- but where the line sits between a blocker and a
warning. A blocker is a fact that makes the run certain to fail; anything that
needs a judgement this tool has no evidence for is a warning, and the tests below
pin both halves so the line cannot move by accident.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preflight', REPO / 'tools/preflight.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)

class PreflightTest(unittest.TestCase):
    def test_optional_commands_missing(self):
        with patch.object(preflight, 'command', return_value=None), patch.object(preflight.shutil, 'which', return_value=None):
            report = preflight.collect(network=True)
        self.assertEqual(report['graphics'], [])
        self.assertIn('Unknown', report['graphics_status'])
        self.assertIn('Unknown', report['network'])
        self.assertEqual(report['hyprland_command'], 'Not found')

    def test_nvidia_detected_without_assuming_driver(self):
        def fake(*args, **kwargs):
            return {'lspci': '01:00.0 VGA compatible controller: NVIDIA Device [10de:1234]',
                    'lscpu': 'Model name: Example CPU'}.get(args[0])
        with patch.object(preflight, 'command', side_effect=fake), patch.object(preflight.shutil, 'which', return_value=None):
            report = preflight.collect(network=False)
        self.assertTrue(report['nvidia'])
        self.assertEqual(report['nvidia_driver'], 'Not detected by nvidia-smi')
        self.assertEqual(report['cpu'], 'Example CPU')

    def test_derivative_not_supported(self):
        with patch.object(preflight, 'read', return_value='ID=endeavouros\nID_LIKE=arch\nPRETTY_NAME="EndeavourOS"'):
            info = preflight.os_info()
        self.assertEqual(info['ID'], 'endeavouros')
        self.assertEqual(info['ID_LIKE'], 'arch')


def report(**over):
    """A report of the shape collect() returns, with any field overridden."""
    base = {
        'os': 'Arch Linux', 'os_id': 'arch', 'official_arch': True,
        'architecture': 'x86_64', 'cpu': 'Example CPU', 'memory': 'MemTotal: 16 GB',
        'home_free_bytes': 40 * 1024 ** 3, 'root_free_bytes': 40 * 1024 ** 3,
        'device': 'Desktop (DMI reported)', 'graphics': [], 'graphics_status': 'Detected',
        'nvidia': False, 'nvidia_driver': 'Not applicable / unknown',
        'nvidia_module_loaded': False, 'nvidia_packages': [],
        'display_session': 'tty', 'desktop': '', 'hyprland_command': '/usr/bin/Hyprland',
        'pacman': 'Local package database readable', 'pacman_lock': False,
        'sudo': 'Available', 'network': 'GitHub reachable',
    }
    base.update(over)
    return base


class FindingsTest(unittest.TestCase):
    """What stops an install, what only warns, and why the two are not the same."""

    def kinds(self, **over):
        return [kind for kind, _ in preflight.findings(report(**over))]

    def texts(self, **over):
        return [text for _, text in preflight.findings(report(**over))]

    def test_a_machine_that_can_run_this_installer_has_nothing_to_report(self):
        self.assertEqual([], preflight.findings(report()))

    def test_a_derivative_is_a_blocker_and_not_a_warning(self):
        self.assertIn('BLOCKER', self.kinds(official_arch=False, os='EndeavourOS'))
        self.assertIn('EndeavourOS', self.texts(official_arch=False, os='EndeavourOS')[0])

    def test_a_held_pacman_lock_is_a_blocker_that_names_the_lock(self):
        texts = self.texts(pacman_lock=True)
        self.assertIn('BLOCKER', self.kinds(pacman_lock=True))
        self.assertTrue(any('/var/lib/pacman/db.lck' in text for text in texts),
                        'a blocker that does not name the file it found leaves a person '
                        'guessing which lock to look at')

    def test_no_pacman_is_a_blocker_and_a_failed_database_read_is_only_a_warning(self):
        self.assertIn('BLOCKER', self.kinds(pacman='Missing or local database query failed'))
        self.assertEqual(['WARN'], self.kinds(pacman='Local package database query failed'))

    def test_the_network_probe_warns_and_names_what_the_first_step_actually_fetches(self):
        kinds = self.kinds(network='GitHub check failed (network, DNS, proxy or policy)')
        texts = self.texts(network='GitHub check failed (network, DNS, proxy or policy)')
        self.assertEqual(['WARN'], kinds,
                         'a probe that reaches GitHub is not a probe of the two hosts the '
                         'first step needs, so it cannot refuse the run')
        for host in preflight.FIRST_STEP_NEEDS:
            self.assertIn(host, texts[0])

    def test_a_probe_that_never_ran_says_so_rather_than_staying_quiet(self):
        self.assertEqual(['WARN'], self.kinds(network='Unknown (curl not installed)'))

    def test_nvidia_without_a_module_warns_without_claiming_a_driver_change(self):
        texts = self.texts(nvidia=True, nvidia_module_loaded=False)
        self.assertEqual(['WARN'], self.kinds(nvidia=True, nvidia_module_loaded=False))
        self.assertIn('changes no driver', texts[0])

    def test_nvidia_with_its_module_loaded_has_nothing_to_say(self):
        self.assertEqual([], preflight.findings(report(nvidia=True, nvidia_module_loaded=True)))

    def test_missing_sudo_warns_because_the_installer_drops_privileges_with_it(self):
        self.assertIn('sudo -u', self.texts(sudo='Not found')[0])

    def test_no_free_space_floor_is_invented(self):
        """The report prints both free spaces; a threshold nobody measured would cry wolf."""
        tiny = 200 * 1024 ** 2
        self.assertEqual([], preflight.findings(report(root_free_bytes=tiny,
                                                       home_free_bytes=tiny)))

    def run_main(self, argv):
        """main() prints its findings; a test that lets them out is a noisy test."""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = preflight.main(argv)
        return code, buffer.getvalue()

    def test_blockers_exits_one_on_a_blocker_and_zero_on_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocked = Path(tmp) / 'blocked.json'
            blocked.write_text(json.dumps(report(pacman_lock=True)), encoding='utf-8')
            warned = Path(tmp) / 'warned.json'
            warned.write_text(json.dumps(report(sudo='Not found')), encoding='utf-8')
            code, out = self.run_main(['--blockers', '--from-report', str(blocked)])
            self.assertEqual(1, code)
            self.assertIn('BLOCKER: /var/lib/pacman/db.lck', out)
            code, out = self.run_main(['--blockers', '--from-report', str(warned)])
            self.assertEqual(0, code, 'a warning alone must not stop an install')
            self.assertIn('WARN: sudo is not installed', out)

    def test_a_machine_with_nothing_to_say_says_that_rather_than_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / 'clean.json'
            clean.write_text(json.dumps(report()), encoding='utf-8')
            code, out = self.run_main(['--blockers', '--from-report', str(clean)])
            self.assertEqual(0, code)
            self.assertIn('none', out, 'silence and a clean report are the same output, '
                                       'and only one of them can be told from a crash')

    def test_a_report_it_cannot_read_is_a_usage_error_not_a_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / 'nope.json'
            self.assertEqual(2, self.run_main(['--blockers', '--from-report', str(missing)])[0])

    def test_the_two_hosts_the_first_step_needs_are_the_two_the_installer_names(self):
        """A warning that names hosts the installer does not fetch from is decoration."""
        text = (REPO / 'install.sh').read_text(encoding='utf-8')
        for host in preflight.FIRST_STEP_NEEDS:
            self.assertIn(host, text)


if __name__ == '__main__':
    unittest.main()
