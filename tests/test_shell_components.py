# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Static and optional offscreen validation of the pure QtQuick components."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / 'iarch/shell/components'
EXPECTED = {'Avatar', 'CalendarMonth', 'Card', 'Chip', 'ContextMenu', 'CoverArt',
            'Dialog', 'Icon', 'IconButton', 'KeyboardKey', 'Keycap',
            'NotificationCard', 'PillButton', 'ProgressBar', 'RingGauge',
            'RoundIconButton', 'SearchPill', 'Segmented', 'Slider', 'Spectrum',
            'Surface', 'Tabs', 'TextField', 'Toast', 'TodoList', 'ToggleCircle',
            'ToggleTile', 'Tooltip', 'WindowTile', 'WorkspaceDots', 'WorkspaceIndicator', 'ThemeTransition'}


class ComponentTests(unittest.TestCase):
    def test_inventory_and_pure_imports(self):
        self.assertEqual({p.stem for p in COMPONENTS.glob('*.qml')}, EXPECTED)
        for path in COMPONENTS.rglob('*.qml'):
            text = path.read_text()
            self.assertTrue(text.startswith('// Copyright (C) 2026 Safari'))
            self.assertNotIn('import Quickshell', text)
            self.assertLess(len(text.splitlines()), 400)

    def test_gallery_references_every_component(self):
        gallery = (ROOT / 'iarch/shell/Gallery.qml').read_text()
        for name in EXPECTED:
            self.assertIn('C.' + name + ' {', gallery)
        self.assertIn('signal themeRequested(string themeId)', gallery)
        self.assertNotIn('import Quickshell', gallery)

    def test_surface_host_has_six_lazy_loaders_and_stays_guarded(self):
        host = (ROOT / 'iarch/shell/services/SurfaceHost.qml').read_text()
        for name in ('bar', 'overview', 'sidebar-right', 'sidebar-left', 'dock', 'osk'):
            self.assertIn('root.shown("' + name + '")', host)
        self.assertEqual(host.count('activeAsync:'), 6)
        shell = (ROOT / 'iarch/shell/shell.qml').read_text()
        core = (ROOT / 'iarch/shell/ShellCore.qml').read_text()
        self.assertIn('IARCH_SHELL_SKELETON_NOT_READY', shell)
        self.assertIn('ShellCore { preview: false }', shell)
        self.assertIn('Services.StartupTheme', core)

    def test_status_view_is_pure_and_service_demand_is_visibility_gated(self):
        view = (ROOT / 'iarch/shell/services/SurfaceContent.qml').read_text()
        self.assertNotIn('import Quickshell', view)
        for label in ('Battery unavailable', 'Network unavailable', 'Audio unavailable',
                      'No media player', 'CPU unavailable', 'Tasks unavailable'):
            self.assertIn(label, view)
        core = (ROOT / 'iarch/shell/ShellCore.qml').read_text()
        for snippet in ('active: shell.shown("sidebar-right")',
                        'active: shell.shown("bar") || shell.shown("sidebar-right")',
                        'active: shell.shown("sidebar-left")'):
            self.assertIn(snippet, core)
        self.assertIn('IARCH_SHELL_SKELETON_NOT_READY', (ROOT / 'iarch/shell/shell.qml').read_text())

    def test_motion_inventory_and_clock(self):
        names = {p.stem for p in (COMPONENTS / 'motion').glob('*.qml')}
        self.assertEqual(names, {'ChamferReveal', 'CrossFade', 'HoverLift', 'NumberRoll', 'PressSquish',
                                 'RingSweep', 'ScaleIn', 'ShimmerLoading', 'SlideIn',
                                 'SpectrumSmoothing', 'Stagger'})
        clock = ROOT / 'iarch/shell/services/Clock.qml'
        self.assertIn('running: root.active', clock.read_text())

    def test_qmllint_when_available(self):
        tool = shutil.which('pyside6-qmllint') or shutil.which('qmllint')
        if tool is None:
            self.skipTest('qmllint is not installed')
        paths = sorted(COMPONENTS.rglob('*.qml')) + [ROOT / 'iarch/shell/services/Clock.qml',
                ROOT / 'iarch/shell/services/SurfaceContent.qml',
                ROOT / 'iarch/shell/runtime/ThemeRuntime.qml', ROOT / 'iarch/shell/runtime/SurfaceRegistry.qml',
                ROOT / 'iarch/shell/Gallery.qml']
        result = subprocess.run([tool, '-W', '0', *map(str, paths)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Singleton files linted directly do not resolve their own qmldir; ignore
        # only that import warning while keeping all other warnings fatal.
        result = subprocess.run([tool, '-W', '0', '--import', 'disable',
                                 str(ROOT / 'iarch/shell/runtime/Theme.qml')],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_offscreen_load_when_qt_runtime_available(self):
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QSG_RHI_BACKEND='software')
        probe = subprocess.run(['python3', '-c', 'from PySide6.QtGui import QGuiApplication'],
                               capture_output=True, text=True, env=env, timeout=20)
        if probe.returncode:
            self.skipTest('PySide6 or native Qt runtime libraries unavailable')
        script = '''
import sys
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine, QQmlComponent
app = QGuiApplication([])
engine = QQmlEngine()
for p in sorted(Path(sys.argv[1]).rglob("*.qml")) + [Path(p) for p in sys.argv[2:]]:
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(p.resolve())))
    obj = component.create()
    if obj is None:
        print(p, *[e.toString() for e in component.errors()], file=sys.stderr)
        sys.exit(1)
    obj.deleteLater()
'''
        result = subprocess.run(['python3', '-c', script, str(COMPONENTS), str(ROOT / 'iarch/shell/Gallery.qml'),
                                 str(ROOT / 'iarch/shell/services/SurfaceContent.qml')], capture_output=True,
                                text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_offscreen_theme_runtime_atomic_swap_when_qt_available(self):
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QSG_RHI_BACKEND='software')
        probe = subprocess.run(['python3', '-c', 'from PySide6.QtGui import QGuiApplication'],
                               capture_output=True, text=True, env=env, timeout=20)
        if probe.returncode:
            self.skipTest('PySide6 or native Qt runtime libraries unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            env.update(HOME=temporary, IARCH_CONFIG_DIR=str(Path(temporary) / 'config'))
            projection = subprocess.run(['python3', str(ROOT / 'iarch/cli/shell_projection.py'), '--reference-preview'],
                                        capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(projection.returncode, 0, projection.stderr)
            qml = '''import QtQuick
import %s as R
Item {
    property color background: R.Theme.background
    property color foreground: R.Theme.accentForeground
    property var registry: R.SurfaceRegistry { id: registry }
    property var runtime: R.ThemeRuntime { id: runtime; surfaceRegistry: registry }
    function apply(text) { return runtime.acceptBundle(JSON.parse(text), true) }
    function applyAnimated(text) { return runtime.acceptBundle(JSON.parse(text), false) }
    function barVisible() { return registry.surfaces.bar.visible }
}
''' % json.dumps((ROOT / 'iarch/shell/runtime').as_uri())
            script = '''
import json, sys
from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine, QQmlComponent
app = QGuiApplication([])
engine = QQmlEngine()
component = QQmlComponent(engine)
component.setData(sys.argv[1].encode(), QUrl())
obj = component.create()
if obj is None:
    raise RuntimeError(str(component.errors()))
bundle = json.loads(sys.argv[2])
assert obj.apply(json.dumps(bundle)) and obj.barVisible()
bundle['theme']['palette']['background'] = '#123456'
bundle['theme']['palette']['onAccent'] = '#abcdef'
assert obj.apply(json.dumps(bundle))
assert obj.property('background').name() == '#123456'
assert obj.property('foreground').name() == '#abcdef'
bundle['theme']['palette']['background'] = '#456789'
bundle['theme']['palette']['onAccent'] = '#fedcba'
assert obj.applyAnimated(json.dumps(bundle))
loop = QEventLoop()
QTimer.singleShot(600, loop.quit)
loop.exec()
assert obj.property('background').name() == '#456789'
assert obj.property('foreground').name() == '#fedcba'
bundle['theme']['palette']['background'] = 'invalid'
bundle['surfaces']['bar']['enabled'] = False
assert not obj.apply(json.dumps(bundle))
assert obj.property('background').name() == '#456789' and obj.barVisible()
'''
            result = subprocess.run(['python3', '-c', script, qml, projection.stdout],
                                    capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
