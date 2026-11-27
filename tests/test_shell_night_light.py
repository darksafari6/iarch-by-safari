# Copyright (C) 2026 Safari — GPL-3.0-or-later
import unittest
from iarch.cli.shell_night_light import operate
from iarch.lib.runner import Answer


class NightLightTests(unittest.TestCase):
    def test_read_set_and_disable_fixed_commands(self):
        calls = []
        def run(command, timeout):
            calls.append((command, timeout))
            response = {'get': 'false', 'temperature': '4200'}.get(command[-1], 'ok')
            return Answer(command, 0, response)
        self.assertEqual(operate('set', 4200, run), {'enabled': True, 'temperature': 4200})
        self.assertEqual(calls[0], (('hyprctl', 'hyprsunset', 'temperature', '4200'), 5.0))
        calls.clear()
        operate('disable', run=run)
        self.assertEqual(calls[0][0], ('hyprctl', 'hyprsunset', 'identity'))
        calls.clear()
        with self.assertRaises(ValueError): operate('set', '$(touch x)', run)
        self.assertEqual(calls, [])

    def test_missing_rejected_or_malformed(self):
        with self.assertRaises(ValueError): operate('read', run=lambda *a: None)
        with self.assertRaises(ValueError): operate('disable', run=lambda c, t: Answer(c, 0, 'error'))
        with self.assertRaises(ValueError): operate('read', run=lambda c, t: Answer(c, 0, 'malformed'))


if __name__ == '__main__':
    unittest.main()
