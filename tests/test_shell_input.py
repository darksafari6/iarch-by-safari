# Copyright (C) 2026 Safari — GPL-3.0-or-later
import json
import unittest
from iarch.cli.shell_input import request
from iarch.lib.runner import Answer


class InputTests(unittest.TestCase):
    def test_only_explicit_existing_pointer_and_fixed_lua(self):
        calls = []
        def run(cmd, timeout):
            calls.append((cmd, timeout))
            out = json.dumps({'mice': [{'name': 'my-touchpad'}, {'name': 'bad"name'}]}) if 'devices' in cmd else 'ok'
            return Answer(cmd, 0, out)
        self.assertEqual(request('list', run=run), {'pointers': ['my-touchpad']})
        self.assertEqual(request('device', False, 'my-touchpad', run), {'requested': True, 'verified': False})
        self.assertEqual(calls[-1][0], ('hyprctl', 'eval', 'hl.device({name = "my-touchpad", enabled = false})'))
        request('raw', True, run=run)
        self.assertEqual(calls[-1][0], ('hyprctl', 'eval', 'hl.config({input = {force_no_accel = true}})'))
        for name in ['missing', 'bad"name', 'x;evil', 'x\nother']:
            with self.subTest(name=name), self.assertRaises(ValueError): request('device', False, name, run)
        with self.assertRaises(ValueError): request('raw', 'yes', run=run)

    def test_exit_zero_error_is_not_success(self):
        def error(cmd, timeout): return Answer(cmd, 0, 'unknown request')
        with self.assertRaises(ValueError): request('raw', True, run=error)
        with self.assertRaises(ValueError): request('list', run=error)
        with self.assertRaises(ValueError): request('raw', True, run=lambda *a: None)


if __name__ == '__main__': unittest.main()
