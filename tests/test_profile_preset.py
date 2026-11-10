# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Performance preset may only lower values of keys the profile already has."""
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import profile_preset  # noqa: E402
from iarch.lib import configstore  # noqa: E402

BASE = ROOT / ".config" / "noctalia" / "config.toml"


class ProfilePreset(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.config = self.tmp / "config.toml"
        shutil.copy(BASE, self.config)
        self.env = {"IARCH_STATE_DIR": str(self.tmp / "state")}
        self.before = self.config.read_bytes()

    def model(self):
        return tomllib.loads(self.config.read_text(encoding="utf-8"))

    def test_apply_changes_only_the_overlaid_values(self):
        profile_preset.apply("performance", self.config, self.env)
        base = tomllib.loads(BASE.read_text(encoding="utf-8"))
        now = self.model()
        self.assertFalse(now["bar"]["default"]["compositor_blur"])
        self.assertFalse(now["shell"]["settings_window_translucent"])
        self.assertTrue(base["bar"]["default"]["compositor_blur"])
        for section in ("notification", "audio", "dock", "theme"):
            self.assertEqual(now[section], base[section], f"untouched section drifted: {section}")
        text = self.config.read_text(encoding="utf-8")
        self.assertIn("# ", text, "comments of the shipped profile must survive")

    def test_an_overlay_key_that_does_not_exist_is_refused(self):
        bad = ROOT / "profiles" / "_unit_bad.toml"
        self.addCleanup(bad.unlink, True)
        bad.write_text("[bar.default]\ncompositor_blur = false\nno_such_key = 1\n", encoding="utf-8")
        with self.assertRaises(profile_preset.PresetError):
            profile_preset.apply("_unit_bad", self.config, self.env)
        self.assertEqual(self.config.read_bytes(), self.before, "a refused preset must write nothing")

    def test_an_overlay_that_changes_a_type_is_refused(self):
        bad = ROOT / "profiles" / "_unit_type.toml"
        self.addCleanup(bad.unlink, True)
        bad.write_text('[bar.default]\ncompositor_blur = "glass"\n', encoding="utf-8")
        with self.assertRaises(profile_preset.PresetError):
            profile_preset.apply("_unit_type", self.config, self.env)
        self.assertEqual(self.config.read_bytes(), self.before)

    def test_backups_rotate_at_five(self):
        for _ in range(7):
            profile_preset.apply("performance", self.config, self.env)
        backups = list(configstore.backup_dir(self.env).iterdir())
        self.assertEqual(len(backups), configstore.BACKUP_LIMIT)

    def test_revert_restores_the_bytes_of_the_previous_file(self):
        profile_preset.apply("performance", self.config, self.env)
        self.assertNotEqual(self.config.read_bytes(), self.before)
        profile_preset.revert(self.config, self.env)
        self.assertEqual(self.config.read_bytes(), self.before)

    def test_revert_without_a_backup_fails_closed(self):
        with self.assertRaises(profile_preset.PresetError):
            profile_preset.revert(self.config, self.env)
        self.assertEqual(self.config.read_bytes(), self.before)


if __name__ == "__main__":
    unittest.main()
