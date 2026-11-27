# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Pure overview geometry without a compositor."""
import shutil
import subprocess
import unittest
from pathlib import Path


class OverviewLayoutTests(unittest.TestCase):
    def test_grid_and_proportional_clipping(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js unavailable')
        module = Path(__file__).resolve().parents[1] / 'iarch/shell/runtime/overview.js'
        script = r'''
const assert = require('assert'), g = require(process.argv[1]);
const cells = g.grid(540, 210, 10);
assert.equal(cells.length, 10);
assert.deepEqual(cells[0], {workspace:1,x:0,y:0,width:100,height:100});
assert.deepEqual(cells[9], {workspace:10,x:440,y:110,width:100,height:100});
assert.equal(g.grid(-1, 20, 2), null);
assert.equal(g.grid(Infinity, 20, 2), null);
const tiny = g.grid(1, 1, 100);
assert(tiny.every(x => x.width >= 0 && x.height >= 0));
let m = {x:-1920,y:0,width:1920,height:1080};
let t = {x:0,y:0,width:200,height:200};
let w = {x:-1920,y:0,width:960,height:1080};
let r = g.windowRect(m,w,t);
assert.equal(r.x, 0); assert.equal(r.width, 100); assert.equal(r.height, 112.5);
assert.equal(r.y, 43.75);
assert.equal(g.windowRect(m,{x:1,y:0,width:10,height:10},t), null);
let clipped = g.windowRect(m,{x:-2000,y:-100,width:200,height:200},t);
assert(clipped.x >= t.x && clipped.y >= t.y && clipped.width > 0);
assert.equal(g.windowRect(m,w,{x:0,y:0,width:0,height:1}), null);
'''
        result = subprocess.run([node, '-e', script, str(module)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
