#!/usr/bin/env python3
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
spec = importlib.util.spec_from_file_location('diagnostics', REPO / 'tools/diagnose.py')
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)

class DiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'config'
        self.state = Path(self.tmp.name) / 'state'
        self.root.mkdir()

    def test_missing_utilities_do_not_crash(self):
        with patch.object(diagnostics.shutil, 'which', return_value=None):
            result = diagnostics.inspect(self.root, self.state)
        self.assertTrue(any('Hyprland configuration missing' in text for _, text in result))
        self.assertTrue(any('systemctl unavailable' in text for _, text in result))

    def test_verify_config_when_advertised(self):
        (self.root / 'hypr').mkdir()
        (self.root / 'hypr/hyprland.conf').write_text('# test\n')
        calls = []
        def which(name):
            return '/mock/Hyprland' if name == 'Hyprland' else None
        def command(*args, **kwargs):
            calls.append(args)
            return (0, '--verify-config') if '--help' in args else (1, 'configuration error')
        with patch.object(diagnostics.shutil, 'which', side_effect=which), patch.object(diagnostics, 'check_command', side_effect=command), patch.dict(os.environ, {'XDG_RUNTIME_DIR': '/tmp'}):
            result = diagnostics.inspect(self.root, self.state)
        self.assertTrue(any(level == 'WARN' and 'configuration error' in text for level, text in result))
        self.assertTrue(any('--verify-config' in call for call in calls))

    def test_detect_incomplete_log_and_ddc(self):
        (self.root / 'noctalia').mkdir()
        (self.root / 'noctalia/settings.json').write_text(json.dumps({'brightness': {'enableDdcSupport': True}}))
        logs = self.state / 'minimalinux/logs'
        logs.mkdir(parents=True)
        (logs / 'install.123.log').write_text('START\nFAILED\n')
        with patch.object(diagnostics.shutil, 'which', return_value=None):
            result = diagnostics.inspect(self.root, self.state)
        self.assertTrue(any('no success marker' in text for _, text in result))
        self.assertTrue(any('ddcutil missing' in text for _, text in result))

if __name__ == '__main__':
    unittest.main()
