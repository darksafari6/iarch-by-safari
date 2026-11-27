# Copyright (C) 2026 Safari — GPL-3.0-or-later
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from iarch.cli.shell_recorder import record


class RecorderTests(unittest.TestCase):
    def test_explicit_stop_private_output_and_fixed_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            commands, events, signals = [], [], []
            class Fake:
                def __init__(self, args, **kwargs):
                    commands.append(args)
                    Path(args[-1]).write_bytes(b'video')
                def send_signal(self, signum): signals.append(signum)
                def wait(self, timeout=None): return 0
                def poll(self): return 0
            result = record(state_dir=tmp, popen=Fake, stopping=lambda: True, notify=events.append)
            path = Path(result['path'])
            self.assertEqual(path.read_bytes(), b'video')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(commands[0][:3], ['wf-recorder', '-y', '-f'])
            self.assertEqual(signals, [signal.SIGINT])
            self.assertEqual(events, [{'status': 'started'}])
            self.assertEqual([p.name for p in path.parent.iterdir()], [path.name])

    def test_unresponsive_recorder_is_killed_and_temporary_file_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            instances = []
            class Fake:
                def __init__(self, args, **kwargs):
                    self.killed = False
                    self.signals = []
                    Path(args[-1]).write_bytes(b'partial')
                    instances.append(self)
                def send_signal(self, signum): self.signals.append(signum)
                def wait(self, timeout=None):
                    if timeout is not None:
                        raise subprocess.TimeoutExpired('wf-recorder', timeout)
                    return 0
                def kill(self): self.killed = True
                def poll(self): return 0 if self.killed else None
            clock = iter([100.0, 111.0]).__next__
            with self.assertRaisesRegex(ValueError, 'did not stop cleanly'):
                record(state_dir=tmp, popen=Fake, stopping=lambda: True, clock=clock)
            self.assertEqual(instances[0].signals, [signal.SIGINT])
            self.assertTrue(instances[0].killed)
            self.assertEqual(list((Path(tmp) / 'captures').iterdir()), [])

    def test_unexpected_exit_and_missing_tool_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            class Fake:
                def __init__(self, args, **kwargs): Path(args[-1]).write_bytes(b'video')
                def wait(self, timeout=None): return 0
                def poll(self): return 0
            with self.assertRaises(ValueError): record(state_dir=tmp, popen=Fake)
            self.assertEqual(list((Path(tmp) / 'captures').iterdir()), [])
            def missing(*args, **kwargs): raise FileNotFoundError()
            with self.assertRaises(ValueError): record(state_dir=tmp, popen=missing)
            self.assertEqual(list((Path(tmp) / 'captures').iterdir()), [])


if __name__ == '__main__': unittest.main()
