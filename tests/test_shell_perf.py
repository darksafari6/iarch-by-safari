# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Process performance sampling never confuses replaced or unrelated PIDs."""
import json
import tempfile
import unittest
from pathlib import Path
from iarch.cli import iarch_shell_perf as perf
from iarch.lib.runner import Answer


class PerfTests(unittest.TestCase):
    def test_named_instance_cpu_rss_and_pid_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proc = root / '42'
            proc.mkdir()
            def write(ticks, started=123):
                fields = ['S'] + ['0'] * 10 + [str(ticks), '0'] + ['0'] * 6 + [str(started)]
                (proc / 'stat').write_text('42 (name with ) parentheses) ' + ' '.join(fields))
                (proc / 'status').write_text('Name: quickshell\nVmRSS:\t1024 kB\n')
            write(100)
            def run(command, timeout):
                return Answer(tuple(command), 0, stdout=json.dumps([{'pid': 42}, {'pid': 'unsafe'}]))
            ticks_per_second = __import__('os').sysconf('SC_CLK_TCK')
            result = perf.report(run=run, proc=root, clock=iter([10.0, 11.0]).__next__,
                                 sleep=lambda _: write(100 + ticks_per_second))
            self.assertEqual(result['status'], 'sampled')
            self.assertEqual(result['processes'][0]['cpu_percent'], 100)
            self.assertEqual(result['processes'][0]['resident_bytes'], 1048576)
            self.assertIsNone(result['frame_time_ms'])
            result = perf.report(run=run, proc=root, clock=iter([10.0, 11.0]).__next__,
                                 sleep=lambda _: write(200, started=999))
            self.assertEqual(result['processes'], [])

    def test_opt_in_frame_sample_and_bad_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); proc = root / '42'; proc.mkdir()
            fields = ['S'] + ['0'] * 10 + ['10', '0'] + ['0'] * 6 + ['123']
            (proc / 'stat').write_text('42 (shell) ' + ' '.join(fields))
            (proc / 'status').write_text('VmRSS: 100 kB\n')
            def run(command, timeout):
                if 'list' in command: return Answer(tuple(command), 0, '[{"pid":42}]')
                if 'start' in command: return Answer(tuple(command), 0, 'true')
                if 'finish' in command: return Answer(tuple(command), 0, '{"frames": 10, "average_ms": 16.4, "max_ms": 20}')
                return None
            result = perf.report(run=run, proc=root, clock=iter([1., 2.]).__next__, sleep=lambda _: None)
            self.assertEqual(result['frame_time_ms'], 16.4)
            self.assertIn('not GPU render time', result['frame_time_note'])
            def bad(command, timeout):
                answer = run(command, timeout)
                return Answer(tuple(command), 0, '{"frames":10,"average_ms":NaN,"max_ms":2}') if 'finish' in command else answer
            result = perf.report(run=bad, proc=root, clock=iter([1., 2.]).__next__, sleep=lambda _: None)
            self.assertIsNone(result['frame_time_ms'])

    def test_absent_instance_does_not_sample(self):
        result = perf.report(run=lambda *args: None)
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['processes'], [])


if __name__ == '__main__':
    unittest.main()
