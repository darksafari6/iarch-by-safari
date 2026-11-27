# Copyright (C) 2026 Safari — GPL-3.0-or-later
import shutil
import subprocess
import unittest
from pathlib import Path


class KeyboardTests(unittest.TestCase):
    def test_snapshot_parser(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node unavailable')
        module = Path(__file__).resolve().parents[1] / 'iarch/shell/services/keyboard.js'
        code = '''const assert=require('assert'), k=require(process.argv[1]);
let d={keyboards:[{name:'keyboard one',main:false,active_keymap:'A'},
                 {name:'keyboard two',main:true,active_keymap:'English (US)',capsLock:true,numLock:false}]};
assert.deepEqual(k.parse(JSON.stringify(d)),{name:'keyboard two',layout:'English (US)',capsLock:true,numLock:false});
assert.equal(k.parse('{oops'),null); d.keyboards[0].main=true;
assert.equal(k.parse(JSON.stringify(d)),null); assert.equal(k.parse('{}'),null);
assert.equal(k.parse(' '.repeat(1048577)),null);
'''
        result = subprocess.run([node, '-e', code, str(module)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_only_fixed_switch_arguments(self):
        qml = (Path(__file__).resolve().parents[1] / 'iarch/shell/services/Keyboard.qml').read_text()
        self.assertIn('["hyprctl", "switchxkblayout", "current", direction]', qml)
        self.assertIn('direction !== "next" && direction !== "prev"', qml)
        self.assertIn('enabled: root.active', qml)


if __name__ == '__main__':
    unittest.main()
