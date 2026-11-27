# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The bridge producer refuses bad selections and validates its entire input."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from iarch.cli import shell_projection, shell_runtime, theme_records

ROOT = Path(__file__).resolve().parents[1]


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {'HOME': str(self.root), 'IARCH_CONFIG_DIR': str(self.root / 'config')}
        self.pack = self.root / 'config/themes/example-pack'
        shutil.copytree(ROOT / 'data/themes/dynamic-reference', self.pack)
        for file in self.pack.rglob('*.json'):
            data = json.loads(file.read_text())
            data['id'] = 'example-pack'
            file.write_text(json.dumps(data))

    def test_selected_and_explicit_projection(self):
        theme_records.write_selection({'schema_version': 1, 'engine': 'dynamic',
                                       'id': 'example-pack', 'overrides': {}}, self.env)
        result = shell_projection.build(env=self.env, quality='high', reduce_motion=True)
        self.assertEqual(result['theme']['id'], 'example-pack')
        self.assertTrue(result['theme']['reduceMotion'])
        self.assertEqual(result['theme']['quality'], 'high')
        self.assertTrue(result['surfaces']['bar']['enabled'])
        self.assertEqual(result['theme']['shape']['chamfer'], 0)
        self.assertEqual(result['theme']['easing'], 'InOutCubic')
        self.assertEqual(result['theme']['transition'], 'fade')
        self.assertEqual(result['theme']['variants']['bar'], 'default')
        self.assertFalse(result['theme']['sounds']['switch']['enabled'])
        self.assertEqual(result, shell_projection.build('example-pack', self.env, 'high', True))

    def test_quality_preference_flows_through_cli_and_can_be_overridden(self):
        overrides = theme_records.read_overrides(self.env)
        overrides['quality'] = 'ultra'
        theme_records.write_overrides(overrides, self.env)
        self.assertEqual(shell_projection.build('example-pack', self.env)['theme']['quality'], 'ultra')
        env = dict(os.environ, **self.env)
        command = [sys.executable, str(ROOT / 'iarch/cli/shell_projection.py'), 'example-pack']
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['theme']['quality'], 'ultra')
        result = subprocess.run(command + ['--quality', 'low'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['theme']['quality'], 'low')

    def test_bundle_passes_both_javascript_validators(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed')
        bundle = shell_projection.build('example-pack', self.env)
        script = """const p=require(process.argv[1]), r=require(process.argv[2]);
const b=JSON.parse(process.argv[3]);
if (!p.validate(b.theme) || r.configure(b.surfaces) === null) process.exit(1);
let changed=JSON.parse(JSON.stringify(b.theme)); changed.shape.chamfer=9999; if(p.validate(changed)) process.exit(3);
changed=JSON.parse(JSON.stringify(b.theme)); changed.easing='Bad'; if(p.validate(changed)) process.exit(4);
changed=JSON.parse(JSON.stringify(b.theme)); changed.transition='Bad'; if(p.validate(changed)) process.exit(7);
changed=JSON.parse(JSON.stringify(b.theme)); changed.sounds.switch.volume=2; if(p.validate(changed)) process.exit(5);
changed=JSON.parse(JSON.stringify(b.theme)); changed.variants.bar='../bad'; if(p.validate(changed)) process.exit(6);
b.surfaces.bar.order=['same','same']; if(r.configure(b.surfaces) !== null) process.exit(2);
"""
        result = subprocess.run([node, '-e', script, str(ROOT / 'iarch/shell/runtime/projection.js'),
                                 str(ROOT / 'iarch/shell/runtime/registry.js'), json.dumps(bundle)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_reference_preview_is_explicit_and_not_applicable(self):
        bundle = shell_projection.reference_preview()
        self.assertEqual(bundle['theme']['id'], 'dynamic-reference')
        self.assertTrue(bundle['surfaces']['bar']['enabled'])
        path = ROOT / 'data/themes/dynamic-reference'
        runtime = shell_runtime.ThemeRuntime(pack_lookup=lambda _: path)
        with self.assertRaises(shell_runtime.RuntimeError):
            runtime.load('dynamic-reference')
        fake = shell_runtime.ThemeRuntime(pack_lookup=lambda _: self.pack, reference_preview=True)
        with self.assertRaises(shell_runtime.RuntimeError):
            fake.load('dynamic-reference')
        command = [sys.executable, str(ROOT / 'iarch/cli/shell_projection.py')]
        result = subprocess.run(command + ['--reference-preview'], env=dict(os.environ, **self.env), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['theme']['id'], 'dynamic-reference')

    def test_pack_transition_choice_is_validated(self):
        path = self.pack / 'motion.json'
        motion = json.loads(path.read_text())
        motion['transition'] = 'wipe'
        path.write_text(json.dumps(motion))
        self.assertEqual(shell_projection.build('example-pack', self.env)['theme']['transition'], 'wipe')
        motion['transition'] = 'invented'
        path.write_text(json.dumps(motion))
        with self.assertRaises(shell_runtime.RuntimeError):
            shell_projection.build('example-pack', self.env)

    def test_bad_selection_pack_and_overrides_are_refused(self):
        with self.assertRaises(shell_runtime.RuntimeError):
            shell_projection.build(env=self.env)
        with self.assertRaises(shell_runtime.RuntimeError):
            shell_projection.build('../example-pack', self.env)
        (self.pack / 'motion.json').write_text('{}')
        with self.assertRaises(shell_runtime.RuntimeError):
            shell_projection.build('example-pack', self.env)

    def test_cli_list_only_includes_valid_installed_packs(self):
        env = dict(os.environ, **self.env)
        command = [sys.executable, str(ROOT / 'iarch/cli/shell_projection.py'), '--list']
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('example-pack', json.loads(result.stdout))
        self.assertNotIn('dynamic-reference', json.loads(result.stdout))
        (self.pack / 'motion.json').write_text('{}')
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertNotIn('example-pack', json.loads(result.stdout))

    def test_cli_exit_output_and_no_shell_interpolation(self):
        env = dict(os.environ, **self.env)
        command = [sys.executable, str(ROOT / 'iarch/cli/shell_projection.py')]
        ok = subprocess.run(command + ['example-pack'], env=env, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)['theme']['id'], 'example-pack')
        bad = subprocess.run(command + ['$(touch HARMFUL)'], env=env, capture_output=True, text=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual(bad.stdout, '')
        self.assertFalse((ROOT / 'HARMFUL').exists())


if __name__ == '__main__':
    unittest.main()
