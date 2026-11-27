# Copyright (C) 2026 Safari — GPL-3.0-or-later
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iarch.cli import shell_sound
from iarch.lib.runner import Answer


class SoundTests(unittest.TestCase):
    def test_disabled_and_unknown_never_call_player(self):
        doc = {'sounds': {'events': {'volume': {'enabled': False, 'file': 'sounds/a.ogg', 'volume': 0.4}}},
               'user_overrides': {'sounds_enabled': None, 'volume': None}}
        calls = []
        with patch.object(shell_sound.shell_runtime.ThemeRuntime, 'load', return_value=doc):
            result = shell_sound.play('test', 'volume', lookup=lambda _: Path('/test'), run=lambda *a, **k: calls.append(a))
            self.assertEqual(result['reason'], 'disabled')
            with self.assertRaises(ValueError):
                shell_sound.play('test', 'bogus', lookup=lambda _: Path('/test'))
        self.assertEqual(calls, [])

    def test_player_fallback_override_and_failure(self):
        doc = {'sounds': {'events': {'volume': {'enabled': True, 'file': 'sounds/a.ogg', 'volume': 0.4}}},
               'user_overrides': {'sounds_enabled': None, 'volume': 0.25}}
        calls = []
        def fake(command, timeout, env=None):
            calls.append((command, timeout))
            return None if command[0] == 'pw-play' else Answer(command, 0)
        with patch.object(shell_sound.shell_runtime.ThemeRuntime, 'load', return_value=doc):
            result = shell_sound.play('test', 'volume', lookup=lambda _: Path('/test'), run=fake)
            self.assertTrue(result['played'])
            self.assertEqual(calls[0], (('pw-play', '--volume', '0.25', '/test/sounds/a.ogg'), 10.0))
            self.assertEqual(calls[1][0], ('paplay', '--volume=16384', '/test/sounds/a.ogg'))
            calls.clear()
            def fail(command, timeout, env=None):
                calls.append(command)
                return Answer(command, 1)
            with self.assertRaises(ValueError):
                shell_sound.play('test', 'volume', lookup=lambda _: Path('/test'), run=fail)
            self.assertEqual(len(calls), 1)
            doc['user_overrides']['sounds_enabled'] = False
            self.assertFalse(shell_sound.play('test', 'volume', lookup=lambda _: Path('/test'), run=fail)['played'])


if __name__ == '__main__':
    unittest.main()
