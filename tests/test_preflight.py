#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preflight', REPO / 'tools/preflight.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)

class PreflightTest(unittest.TestCase):
    def test_optional_commands_missing(self):
        with patch.object(preflight, 'command', return_value=None), patch.object(preflight.shutil, 'which', return_value=None):
            report = preflight.collect(network=True)
        self.assertEqual(report['graphics'], [])
        self.assertIn('Unknown', report['graphics_status'])
        self.assertIn('Unknown', report['network'])
        self.assertEqual(report['hyprland_command'], 'Not found')

    def test_nvidia_detected_without_assuming_driver(self):
        def fake(*args, **kwargs):
            return {'lspci': '01:00.0 VGA compatible controller: NVIDIA Device [10de:1234]',
                    'lscpu': 'Model name: Example CPU'}.get(args[0])
        with patch.object(preflight, 'command', side_effect=fake), patch.object(preflight.shutil, 'which', return_value=None):
            report = preflight.collect(network=False)
        self.assertTrue(report['nvidia'])
        self.assertEqual(report['nvidia_driver'], 'Not detected by nvidia-smi')
        self.assertEqual(report['cpu'], 'Example CPU')

    def test_derivative_not_supported(self):
        with patch.object(preflight, 'read', return_value='ID=endeavouros\nID_LIKE=arch\nPRETTY_NAME="EndeavourOS"'):
            info = preflight.os_info()
        self.assertEqual(info['ID'], 'endeavouros')
        self.assertEqual(info['ID_LIKE'], 'arch')

if __name__ == '__main__':
    unittest.main()
