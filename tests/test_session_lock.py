# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Cross-process session serialization and lock-file safety tests."""
import os
import select
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from iarch.lib import session_lock


class SessionLockTests(unittest.TestCase):
    def test_other_process_cannot_enter_until_lock_is_released(self):
        with tempfile.TemporaryDirectory() as root:
            env = dict(os.environ, HOME=root, IARCH_STATE_DIR=str(Path(root) / 'state'))
            code = ('from iarch.lib.session_lock import session_lock; '
                    'print("ready", flush=True); '
                    'exec("with session_lock():\\n print(\\\"entered\\\", flush=True)")')
            with session_lock.session_lock(env):
                child = subprocess.Popen([sys.executable, '-c', code], env=env,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    self.assertEqual('ready', child.stdout.readline().strip())
                    self.assertEqual([], select.select([child.stdout], [], [], 0.2)[0])
                except BaseException:
                    child.kill(); child.communicate(timeout=5)
                    raise
            out, err = child.communicate(timeout=5)
            self.assertEqual(0, child.returncode, err)
            self.assertIn('entered', out)

    def test_hardlinked_lock_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            env = {'HOME': root, 'IARCH_STATE_DIR': str(Path(root) / 'state')}
            directory = Path(env['IARCH_STATE_DIR']); directory.mkdir()
            target = directory / 'target'; target.write_text('unchanged')
            os.link(target, directory / 'shell-switch.lock')
            with self.assertRaises(ValueError):
                with session_lock.session_lock(env): pass
            self.assertEqual('unchanged', target.read_text())


if __name__ == '__main__': unittest.main()
