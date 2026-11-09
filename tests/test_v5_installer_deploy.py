"""Exercise only the v5 deploy function with isolated files and mocked privilege."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class V5InstallerDeploy(unittest.TestCase):
    def run_deploy(self, installer, root, fail_backup=False):
        source = (ROOT / installer).read_text()
        start = source.index('deploy_configs() {')
        end = source.index('\nupdate_hypr_startup_config() {', start)
        function = source[start:end]
        mock_mv = 'mv() { return 42; }\n' if fail_backup else ''
        script = '''#!/usr/bin/env bash
sudo() { shift 2; "$@"; }
chown() { printf '%s\\n' "$*" >> "$MOCK_LOG"; }
''' + mock_mv + function + '\ndeploy_configs\n'
        env = dict(os.environ, REPO_DIR=str(ROOT), CONFIG_DIR=str(root / 'config'),
                   ACTUAL_USER='mock-user', DDCUTIL_ENABLED='0', MOCK_LOG=str(root / 'chown.log'))
        return subprocess.run(['bash'], input=script, text=True, capture_output=True, env=env, timeout=20)

    def test_deployment_stages_v5_and_preserves_backups(self):
        for installer in ('install.sh', 'fedora_install.sh'):
            with self.subTest(installer=installer), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                config = root / 'config'
                (config / 'hypr').mkdir(parents=True)
                (config / 'hypr/custom').write_text('old hypr')
                (config / 'noctalia').mkdir()
                (config / 'noctalia/custom').write_text('old shell')
                (config / 'unrelated').mkdir()
                (config / 'unrelated/data').write_text('keep')
                result = self.run_deploy(installer, root)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue((config / 'hypr/hyprland.lua').is_file())
                self.assertFalse((config / 'hypr/hyprland.conf').exists())
                self.assertFalse((config / 'noctalia/settings.json').exists())
                self.assertEqual((next(config.glob('hypr.bak.*')) / 'custom').read_text(), 'old hypr')
                self.assertEqual((next(config.glob('noctalia.bak.*')) / 'custom').read_text(), 'old shell')
                self.assertEqual((config / 'unrelated/data').read_text(), 'keep')
                self.assertNotIn(str(config / 'unrelated'), (root / 'chown.log').read_text())

    def test_backup_failure_does_not_copy_over_config(self):
        for installer in ('install.sh', 'fedora_install.sh'):
            with self.subTest(installer=installer), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                config = root / 'config'
                (config / 'hypr').mkdir(parents=True)
                (config / 'hypr/custom').write_text('old hypr')
                result = self.run_deploy(installer, root, fail_backup=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((config / 'hypr/custom').read_text(), 'old hypr')
                self.assertFalse((config / 'hypr/hyprland.lua').exists())
                self.assertFalse((config / 'noctalia').exists())


if __name__ == '__main__':
    unittest.main()
