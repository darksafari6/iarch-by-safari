# Copyright (C) 2026 Safari — GPL-3.0-or-later
import shutil
import subprocess
import unittest
from pathlib import Path


class WorkspaceStateTests(unittest.TestCase):
    def test_navigation_and_indicator(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js unavailable')
        path = Path(__file__).resolve().parents[1] / 'iarch/shell/runtime/workspace_state.js'
        script = '''const assert = require('assert'), s = require(process.argv[1]);
assert.equal(s.step(10,1),1); assert.equal(s.step(1,-1),10);
assert.equal(s.step(3,22),5); assert.equal(s.step(0,1),null);
assert.equal(s.select(1,'left'),1); assert.equal(s.select(5,'right'),5);
assert.equal(s.select(3,'down'),8); assert.equal(s.select(8,'up'),3);
assert.equal(s.select(3,'invalid'),null);
let x=s.indicator(4,[1,4,4,10]); assert.equal(x.length,10);
assert.equal(x.filter(a=>a.active).length,1); assert(x[3].active && x[3].occupied);
assert.equal(s.indicator(11,[]),null); assert.equal(s.indicator(1,[0]),null);
'''
        result = subprocess.run([node, '-e', script, str(path)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
