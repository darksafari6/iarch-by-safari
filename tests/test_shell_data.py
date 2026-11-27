# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Service data parsers use synthetic samples and never require a live session."""
import unittest
from iarch.lib import shell_data as data


class ShellDataTests(unittest.TestCase):
    def test_cpu_guest_is_not_double_counted(self):
        a = data.cpu_counters('cpu 10 2 3 20 5 1 1 2 9 1\n')
        b = data.cpu_counters('cpu 20 2 3 30 5 1 1 2 10 1\n')
        self.assertEqual(a, (44, 25))
        self.assertEqual(data.cpu_percent(a, b), 50.0)
        self.assertIsNone(data.cpu_percent(b, a))
        with self.assertRaises(data.DataError):
            data.cpu_counters('cpu 1 2 bad 4')

    def test_memory(self):
        self.assertEqual(data.memory_usage('MemTotal: 100 kB\nMemAvailable: 40 kB\n'),
                         {'total': 102400, 'used': 61440})
        with self.assertRaises(data.DataError):
            data.memory_usage('MemTotal: 1 kB\nMemAvailable: 2 kB\n')

    def test_nmcli_escaped_ssid(self):
        self.assertEqual(data.wifi_networks(r'*:home\:room\\wifi:77' + '\n'),
                         [{'active': True, 'ssid': 'home:room\\wifi', 'signal': 77}])
        with self.assertRaises(data.DataError):
            data.wifi_networks('*:unsafe:101')
        with self.assertRaises(data.DataError):
            data.nmcli_fields('abc\\')

    def test_spectrum(self):
        self.assertEqual(data.spectrum('0;50;100;', maximum=100), [0.0, 0.5, 1.0])
        with self.assertRaises(data.DataError):
            data.spectrum('1;-1;')

    def test_metadata(self):
        result = data.media_metadata({'xesam:title': 'Song', 'xesam:artist': ['A', 'B'],
                                      'mpris:artUrl': 'https://example.org/image', 'mpris:length': 123})
        self.assertEqual(result['artists'], ['A', 'B'])
        self.assertEqual(result['length_us'], 123)
        with self.assertRaises(data.DataError):
            data.media_metadata({'mpris:length': float('nan')})


if __name__ == '__main__':
    unittest.main()
