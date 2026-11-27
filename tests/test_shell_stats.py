# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Local stats sample and graceful per-source failures."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from iarch.cli import shell_stats

ROOT = Path(__file__).resolve().parents[1]


class StatsTests(unittest.TestCase):
    def test_synthetic_sample_and_missing_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proc = root / 'proc'
            proc.mkdir()
            (proc / 'stat').write_text('cpu 10 1 2 50 3 0 0 0\n')
            (proc / 'meminfo').write_text('MemTotal: 100 kB\nMemAvailable: 40 kB\n')
            zone = root / 'thermal/thermal_zone0'
            zone.mkdir(parents=True)
            (zone / 'temp').write_text('42500\n')
            result = shell_stats.sample(proc, zone.parent, root)
            self.assertEqual(result['cpu'], (66, 53))
            self.assertEqual(result['memory'], {'total': 102400, 'used': 61440})
            self.assertEqual(result['temperature'], 42.5)
            self.assertGreater(result['disk']['total'], 0)
            (proc / 'stat').write_text('bad')
            (zone / 'temp').write_text('bad')
            result = shell_stats.sample(proc, zone.parent, root / 'missing')
            self.assertIsNone(result['cpu'])
            self.assertIsNone(result['disk'])
            self.assertIsNone(result['temperature'])
            self.assertEqual(set(result['errors']), {'cpu', 'disk', 'temperature'})
            self.assertIsNotNone(result['memory'])

    def test_cli_emits_json_and_adapter_pauses(self):
        result = subprocess.run([sys.executable, str(ROOT / 'iarch/cli/shell_stats.py')],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('errors', json.loads(result.stdout))
        adapter = (ROOT / 'iarch/shell/services/Stats.qml').read_text()
        self.assertIn('running: root.active', adapter)
        self.assertIn('reader.running = false', adapter)
        self.assertNotIn('sh -c', adapter)


if __name__ == '__main__':
    unittest.main()
