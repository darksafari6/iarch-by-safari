# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Raw spectrum parsing and on-demand process behavior."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VisualizerTests(unittest.TestCase):
    def test_parser_validates_frame_shape_and_values(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js unavailable')
        code = """const p=require(process.argv[1]);
let x=p.parse('0;500;1000;',3,1000);
if(!x || x[0]!==0 || x[1]!==0.5 || x[2]!==1) process.exit(1);
for(const s of ['1;2','1;2;1001','-1;0;0','1;bad;0']) if(p.parse(s,3,1000)!==null) process.exit(2);
"""
        result = subprocess.run([node, '-e', code, str(ROOT / 'iarch/shell/services/spectrum.js')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cava_is_argument_list_and_disabled_when_hidden(self):
        qml = (ROOT / 'iarch/shell/services/Visualizer.qml').read_text()
        config = (ROOT / 'iarch/shell/services/cava.ini').read_text()
        self.assertIn('["cava", "-p", configPath]', qml)
        self.assertIn('process.running = false', qml)
        self.assertIn('data_format = ascii', config)
        self.assertIn('raw_target = /dev/stdout', config)


if __name__ == '__main__':
    unittest.main()
