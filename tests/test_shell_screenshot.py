# Copyright (C) 2026 Safari — GPL-3.0-or-later
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from iarch.cli.shell_screenshot import capture
from iarch.lib.runner import Answer


class ScreenshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_region_and_private_unique_output(self):
        commands = []
        def selection(cmd, timeout):
            self.assertEqual((cmd, timeout), (('slurp',), 120.0))
            return Answer(cmd, 0, '-20,10 800x600\n')
        def grim(cmd, **kwargs):
            commands.append(cmd)
            kwargs['stdout'].write(b'\x89PNG\r\n\x1a\nexample')
            return subprocess.CompletedProcess(cmd, 0)
        first = Path(capture('region', state_dir=self.root, select=selection, run=grim)['path'])
        second = Path(capture('screen', state_dir=self.root, run=grim)['path'])
        self.assertNotEqual(first, second)
        self.assertEqual(first.stat().st_mode & 0o777, 0o600)
        self.assertEqual(first.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(commands[0], ['grim', '-t', 'png', '-g', '-20,10 800x600', '-'])
        self.assertEqual(commands[1], ['grim', '-t', 'png', '-'])

    def test_invalid_selection_missing_tool_and_bad_output_clean_up(self):
        for result in (None, Answer(('slurp',), 1), Answer(('slurp',), 0, '1,1 2x3;evil')):
            with self.subTest(result=result), self.assertRaises(ValueError):
                capture('region', state_dir=self.root, select=lambda *args: result)
        def bad(cmd, **kwargs):
            kwargs['stdout'].write(b'not a png')
            return subprocess.CompletedProcess(cmd, 0)
        with self.assertRaises(ValueError): capture('screen', state_dir=self.root, run=bad)
        self.assertEqual(list((self.root / 'captures').iterdir()), [])
        with self.assertRaises(ValueError): capture('screen', state_dir=self.root, run=lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
        self.assertEqual(list((self.root / 'captures').iterdir()), [])

    def test_refuses_non_private_directory_and_symlink(self):
        target = self.root / 'target'
        target.mkdir()
        (self.root / 'captures').symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError): capture('screen', state_dir=self.root)
        self.assertEqual(list(target.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
