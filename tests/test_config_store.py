# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Prove the user-state rules: defaults merge, atomic writes, five backups."""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402


class ConfigStore(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(self._clean)
        self.env = {
            "IARCH_CONFIG_DIR": str(self.tmp / "config" / "iarch"),
            "IARCH_STATE_DIR": str(self.tmp / "state" / "iarch"),
        }

    def _clean(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_defaults_come_from_the_repo_and_user_values_win(self):
        merged = configstore.load("settings", ROOT, self.env)
        shipped = json.loads((ROOT / "data" / "settings.default.json").read_text())
        self.assertEqual(merged["effects"], shipped["effects"])
        own = configstore.save("settings", {**merged, "preset": "performance"}, self.env)
        again = configstore.load("settings", ROOT, self.env)
        self.assertEqual(again["preset"], "performance")
        self.assertEqual(again["effects"], shipped["effects"], "unset keys fall back to repo defaults")
        self.assertTrue(str(own).startswith(str(self.tmp)), "user state never lands in the repository")

    def test_save_rotates_to_five_backups(self):
        for round_number in range(7):
            configstore.save("settings", {"version": 1, "preset": "glass",
                                          "effects": {"blur": round_number % 2 == 0, "transparency": True,
                                                      "animations": True, "shadows": True},
                                          "round": round_number}, self.env)
        backups = list(configstore.backup_dir(self.env).iterdir())
        self.assertEqual(len(backups), configstore.BACKUP_LIMIT)

    def test_a_failed_write_leaves_the_previous_file_intact(self):
        configstore.save("settings", {"version": 1, "preset": "glass",
                                      "effects": {"blur": True, "transparency": True,
                                                  "animations": True, "shadows": True}}, self.env)
        target = configstore.user_path("settings", self.env)
        before = target.read_text()
        original_replace = os.replace
        os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("simulated rename failure"))
        try:
            with self.assertRaises(OSError):
                configstore.atomic_write(target, json.dumps({"version": 1, "broken": True}))
        finally:
            os.replace = original_replace
        self.assertEqual(target.read_text(), before)
        self.assertEqual([p for p in target.parent.iterdir() if p.name.endswith(".tmp")], [],
                         "no temp file may survive a failed write")

    def test_generated_files_use_their_own_comment_syntax(self):
        lua = self.tmp / "a.lua"
        shell = self.tmp / "b.sh"
        toml_file = self.tmp / "c.toml"
        configstore.write_generated(lua, "return {}\n", self.env)
        configstore.write_generated(shell, "exit 0\n", self.env)
        configstore.write_generated(toml_file, "x = 1\n", self.env)
        self.assertEqual(lua.read_text().splitlines()[0], configstore.GENERATED_HEADER)
        self.assertEqual(shell.read_text().splitlines()[0],
                         configstore.GENERATED_HEADER.replace("-- ", "# ", 1))
        self.assertEqual(toml_file.read_text().splitlines()[0],
                         configstore.GENERATED_HEADER.replace("-- ", "# ", 1))

    def test_generated_files_carry_the_header_and_a_backup(self):
        target = self.tmp / "hypr" / "generated" / "keybinds.lua"
        configstore.write_generated(target, "return {}\n", self.env)
        lines = target.read_text().splitlines()
        self.assertEqual(lines[0], configstore.GENERATED_HEADER)
        configstore.write_generated(target, "return { second = true }\n", self.env)
        backups = list(configstore.backup_dir(self.env).iterdir())
        self.assertEqual(len(backups), 1)
        self.assertIn("return {}", backups[0].read_text())

    def test_generated_json_keeps_the_header_as_its_first_key(self):
        target = self.tmp / "generated.json"
        configstore.write_generated(target, json.dumps({"value": 1}), self.env)
        parsed = json.loads(target.read_text())
        self.assertEqual(list(parsed)[0], "_generated")
        self.assertEqual(parsed["_generated"], configstore.GENERATED_HEADER)
        self.assertEqual(parsed["value"], 1)

    def test_symlinks_are_refused(self):
        real = self.tmp / "real.lua"
        real.write_text("x")
        link = self.tmp / "link.lua"
        link.symlink_to(real)
        with self.assertRaises(configstore.ConfigError):
            configstore.atomic_write(link, "y")
        self.assertEqual(real.read_text(), "x")


class Renderers(unittest.TestCase):
    def test_header_detection(self):
        from iarch.lib import renderers
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / "plain.lua"
            plain.write_text("return {}\n")
            stamped = Path(tmp) / "stamped.lua"
            stamped.write_text(configstore.GENERATED_HEADER + "\nreturn {}\n")
            self.assertFalse(renderers.is_generated(plain))
            self.assertTrue(renderers.is_generated(stamped))


if __name__ == "__main__":
    unittest.main()
