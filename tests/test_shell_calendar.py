# Copyright (C) 2026 Safari — GPL-3.0-or-later
import shutil
import subprocess
import unittest
from pathlib import Path


class CalendarTests(unittest.TestCase):
    def test_month_model_leap_year_and_today(self):
        node = shutil.which('node')
        if not node: self.skipTest('node unavailable')
        path = Path(__file__).resolve().parents[1] / 'iarch/shell/services/calendar.js'
        code = '''const assert = require('assert'), c=require(process.argv[1]);
let m=c.month(2024,1,new Date(2024,1,29));
assert.equal(m.length,42); assert.equal(m.filter(x=>x.inMonth).length,29);
assert.equal(m.findIndex(x=>x.day===1),4); assert.equal(m.filter(x=>x.today).length,1);
assert.equal(m.find(x=>x.today).day,29); assert.equal(c.month(2023,1,null).filter(x=>x.inMonth).length,28);
assert.equal(c.month(99,1,null),null); assert.equal(c.month(2024,12,null),null);
'''
        result = subprocess.run([node, '-e', code, str(path)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main()
