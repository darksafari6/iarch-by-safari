# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The QML sample boundary rejects malformed helper responses."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SampleValidationTests(unittest.TestCase):
    def test_statistics_and_network_payload_shapes(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed')
        code = '''
const assert = require('assert'), v = require(process.argv[1]);
const stats = {cpu:[100,50], memory:{total:100,used:50}, disk:null, temperature:42.5, errors:{}};
assert(v.stats(stats));
assert(!v.stats({errors:{}}));
assert(!v.stats({...stats,cpu:[10,11]}));
assert(!v.stats({...stats,memory:{total:3,used:4}}));
assert(!v.stats({...stats,temperature:Infinity}));
assert(!v.stats({...stats,errors:[]}));
assert(v.stats({cpu:null,memory:null,disk:null,temperature:null,errors:{cpu:'unavailable'}}));
const net = {timestamp:1,interfaces:{wlan0:{rx:2,tx:3}}, networks:[{active:true,ssid:'home',signal:70}],available:true,error:null};
assert(v.network(net));
assert(!v.network({...net,timestamp:NaN}));
assert(!v.network({...net,interfaces:{wlan0:{rx:'1',tx:0}}}));
assert(!v.network({...net,networks:[{active:true,ssid:'home',signal:101}]}));
assert(!v.network({...net,available:'yes'}));
'''
        result = subprocess.run([node, '-e', code, str(ROOT / 'iarch/shell/services/sample_validation.js')],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__': unittest.main()
