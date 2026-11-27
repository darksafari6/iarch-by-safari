# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The shell runtime model keeps the last validated state on every failure."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from iarch.cli import shell_runtime, theme_records

ROOT = Path(__file__).resolve().parents[1]


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pack = self.root / 'example-pack'
        shutil.copytree(ROOT / 'data/themes/dynamic-reference', self.pack)
        for file in self.pack.rglob('*.json'):
            obj = json.loads(file.read_text())
            obj['id'] = self.pack.name
            file.write_text(json.dumps(obj))
        self.env = {'HOME': str(self.root), 'IARCH_CONFIG_DIR': str(self.root / 'config')}
        self.runtime = shell_runtime.ThemeRuntime(self.env, lambda _: self.pack)

    def test_valid_load_and_snapshot_isolation(self):
        snapshot = self.runtime.load('example-pack')
        snapshot['palette']['colors']['accent'] = '#ffffff'
        self.assertNotEqual(self.runtime.snapshot['palette']['colors']['accent'], '#ffffff')
        self.assertTrue(self.runtime.available)
        self.assertIsNone(self.runtime.error)

    def test_projection_matches_qml_validator(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is not installed')
        self.runtime.load('example-pack')
        projection = self.runtime.projection()
        javascript = ROOT / 'iarch/shell/runtime/projection.js'
        script = "const v=require(process.argv[1]); const p=JSON.parse(process.argv[2]); console.log(v.validate(p));"
        def valid(value):
            result = subprocess.run([node, '-e', script, str(javascript), json.dumps(value)],
                                    capture_output=True, text=True, check=True)
            return result.stdout.strip() == 'true'
        self.assertTrue(valid(projection))
        projection['unknown'] = True
        self.assertFalse(valid(projection))
        del projection['unknown']
        projection['palette']['accent'] = 'not-a-colour'
        self.assertFalse(valid(projection))

    def test_projection_uses_qt_alpha_order(self):
        palette = self.pack / 'palette.json'
        data = json.loads(palette.read_text())
        data['colors']['accent'] = '#11223344'
        palette.write_text(json.dumps(data))
        self.runtime.load('example-pack')
        self.assertEqual(self.runtime.projection()['palette']['accent'], '#44112233')

    def test_projection_needs_valid_state_and_quality(self):
        with self.assertRaises(shell_runtime.RuntimeError):
            self.runtime.projection()
        self.runtime.load('example-pack')
        with self.assertRaises(shell_runtime.RuntimeError):
            self.runtime.projection(quality='invented')

    def test_quality_preference_defaults_overrides_and_validation(self):
        saved = theme_records.read_overrides(self.env)
        # Existing files without the optional key remain valid.
        saved.pop('quality')
        theme_records.write_overrides(saved, self.env)
        self.runtime.load('example-pack')
        self.assertEqual(self.runtime.projection()['quality'], 'balanced')
        for level in ('ultra', 'high', 'balanced', 'low'):
            saved['quality'] = level
            theme_records.write_overrides(saved, self.env)
            self.runtime.load('example-pack')
            self.assertEqual(self.runtime.projection()['quality'], level)
            self.assertEqual(self.runtime.projection(quality='high')['quality'], 'high')
        saved['quality'] = 'invented'
        with self.assertRaises(ValueError):
            theme_records.write_overrides(saved, self.env)
        self.assertEqual(theme_records.read_overrides(self.env)['quality'], 'low')

    def test_qml_registry_rejects_bad_layout_and_actions(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is not installed')
        self.runtime.load('example-pack')
        layout = self.runtime.snapshot['layout']['surfaces']
        javascript = ROOT / 'iarch/shell/runtime/registry.js'
        script = """
const r=require(process.argv[1]); const l=JSON.parse(process.argv[2]);
const a=r.configure(l); if(!a || !a.bar.visible || !r.change(a,'bar','open').bar.visible) process.exit(1);
const closed=r.change(a,'bar','close'); if(r.configure(l,closed).bar.visible) process.exit(5);
if(r.change(a,'overview','open') !== null || r.change(a,'bar','execute') !== null) process.exit(2);
l.bar.order=['item','item']; if(r.configure(l) !== null) process.exit(3);
l.bar.order=[]; l.bar.extra=true; if(r.configure(l) !== null) process.exit(4);
"""
        result = subprocess.run([node, '-e', script, str(javascript), json.dumps(layout)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_quality_policy_restores_preference_and_checks_inputs(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is not installed')
        script = """
const q=require(process.argv[1]);
for (const level of ['low','balanced','high','ultra']) {
  if (q.resolve(level,false,false).level !== level || q.resolve(level,true,false).level !== 'low' ||
      q.resolve(level,false,true).level !== 'low' || q.resolve(level,false,false).level !== level) process.exit(1);
}
if (q.resolve('invented',false,false) !== null || q.resolve('high',1,false) !== null) process.exit(2);
if (q.resolve('low',false,false).animationScale !== 0 || q.resolve('ultra',false,false).spectrumFps !== 60) process.exit(3);
"""
        result = subprocess.run([node, '-e', script, str(ROOT / 'iarch/shell/runtime/quality.js')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_game_mode_parser_reuses_existing_record_and_rejects_corruption(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is not installed')
        script = """const p=require(process.argv[1]);
if(p.parse('{}') !== false || p.parse('{"modes":{"game":{"active":true}}}') !== true ||
   p.parse('{"modes":{"game":{"active":false}}}') !== false || p.parse('{') !== null ||
   p.parse('{"modes":{"game":{"active":"yes"}}}') !== null) process.exit(1);
if(p.reduceMotion('{}') !== false || p.reduceMotion('{"animation":{"reduce_motion":true}}') !== true ||
   p.reduceMotion('{"animation":{"reduce_motion":false}}') !== false || p.reduceMotion('{') !== null ||
   p.reduceMotion('{"animation":{"reduce_motion":"yes"}}') !== null ||
   p.reduceMotion('{"animation":null}') !== null || p.reduceMotion('[]') !== null) process.exit(2);
"""
        result = subprocess.run([node, '-e', script, str(ROOT / 'iarch/shell/services/game_mode.js')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_reduce_motion_settings_are_bound_into_theme(self):
        theme = (ROOT / 'iarch/shell/runtime/Theme.qml').read_text()
        core = (ROOT / 'iarch/shell/ShellCore.qml').read_text()
        watcher = (ROOT / 'iarch/shell/services/GameMode.qml').read_text()
        self.assertIn('tokens.reduceMotion || systemReduceMotion', theme)
        self.assertIn('property: "systemReduceMotion"; value: gameMode.reduceMotion', core)
        self.assertIn('if (motion !== null) root.reduceMotion = motion', watcher)

    def test_media_player_preference_and_deterministic_fallback(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is not installed')
        script = """const s=require(process.argv[1]);
const a={dbusName:'b',isPlaying:false}, b={dbusName:'a',isPlaying:true};
if(s.choose([a,b],'b') !== a || s.choose([a,b],'missing') !== b || s.choose([], '') !== null) process.exit(1);
b.isPlaying=false; if(s.choose([a,b],'') !== b) process.exit(2);
"""
        result = subprocess.run([node, '-e', script, str(ROOT / 'iarch/shell/services/media_selection.js')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_brightness_machine_output_validation(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is not installed')
        script = """const p=require(process.argv[1]);
let v=p.parse('panel,backlight,75,75%,100\\n');
if(!v || v.percent!==75 || v.maximum!==100) process.exit(1);
for (const x of ['bad','panel,leds,1,1%,10','panel,backlight,11,101%,10', 'panel,backlight,-1,0%,10']) if(p.parse(x)!==null) process.exit(2);
"""
        result = subprocess.run([node, '-e', script, str(ROOT / 'iarch/shell/services/brightness.js')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bad_pack_does_not_replace_previous(self):
        self.runtime.load('example-pack')
        before = self.runtime.snapshot
        self.runtime.set_surface('bar', 'open')
        path = self.pack / 'palette.json'
        path.write_text('{}')
        with self.assertRaises(shell_runtime.RuntimeError):
            self.runtime.load('example-pack')
        self.assertEqual(before, self.runtime.snapshot)
        self.assertTrue(self.runtime.surfaces['bar']['visible'])
        self.assertIsNotNone(self.runtime.error)

    def test_override_and_surface_access(self):
        override = theme_records.read_overrides(self.env)
        override['accent'] = '#123456'
        override['variants'] = {'bar': 'default'}
        theme_records.write_overrides(override, self.env)
        self.runtime.load('example-pack')
        self.assertEqual(self.runtime.snapshot['palette']['colors']['accent'], '#123456')
        self.assertEqual(self.runtime.surfaces['bar']['variant'], 'default')
        self.assertTrue(self.runtime.set_surface('bar', 'toggle'))
        self.assertFalse(self.runtime.set_surface('bar', 'close'))
        with self.assertRaises(shell_runtime.RuntimeError):
            self.runtime.set_surface('overview', 'open')

    def test_bad_override_and_bad_ids_refused(self):
        self.runtime.load('example-pack')
        before = self.runtime.snapshot
        override = theme_records.read_overrides(self.env)
        override['variants'] = {'not-a-surface': 'default'}
        theme_records.write_overrides(override, self.env)
        with self.assertRaises(shell_runtime.RuntimeError):
            self.runtime.load('example-pack')
        self.assertEqual(before, self.runtime.snapshot)
        override['variants'] = {'bar': 'unknown'}
        theme_records.write_overrides(override, self.env)
        with self.assertRaisesRegex(shell_runtime.RuntimeError, 'undeclared'):
            self.runtime.load('example-pack')
        with self.assertRaises(shell_runtime.RuntimeError):
            self.runtime.load('../escape')
        with self.assertRaises(shell_runtime.RuntimeError):
            self.runtime.set_surface('bar', 'run-command')


if __name__ == '__main__':
    unittest.main()
