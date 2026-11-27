# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Network samples are cached, bounded and fail without altering the session."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from iarch.cli import shell_network
from iarch.lib import shell_data


class NetworkTests(unittest.TestCase):
    def test_proc_parser_and_validation(self):
        line = 'eth0: ' + ' '.join(str(x) for x in range(16))
        self.assertEqual(shell_data.network_counters('header\n' + line), {'eth0': {'rx': 0, 'tx': 8}})
        with self.assertRaises(shell_data.DataError):
            shell_data.network_counters(line + '\n' + line)
        with self.assertRaises(shell_data.DataError):
            shell_data.network_counters('eth0: -1 ' + '0 ' * 15)
        with self.assertRaises(shell_data.DataError):
            shell_data.network_counters('eth0: 1 2')

    def test_cached_nmcli_and_failure_behavior(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc = Path(temporary) / 'dev'
            proc.write_text('wlan0: ' + ' '.join(str(x) for x in range(16)))
            calls = []
            def run(command, **kwargs):
                calls.append((command, kwargs))
                return subprocess.CompletedProcess(command, 0, '*:House\\:Guest:73\n', '')
            result = shell_network.sample(proc, run)
            self.assertTrue(result['available'])
            self.assertEqual(result['networks'][0]['ssid'], 'House:Guest')
            self.assertEqual(result['interfaces']['wlan0']['tx'], 8)
            self.assertEqual(calls[0][0], shell_network.WIFI_COMMAND)
            self.assertEqual(calls[0][0][-2:], ('--rescan', 'no'))
            self.assertEqual(calls[0][1]['timeout'], 4)
            def absent(*args, **kwargs):
                raise FileNotFoundError('not installed')
            result = shell_network.sample(proc, absent)
            self.assertFalse(result['available'])
            self.assertIn('not installed', result['error'])
            self.assertEqual(result['interfaces']['wlan0']['tx'], 8)


if __name__ == '__main__':
    unittest.main()
