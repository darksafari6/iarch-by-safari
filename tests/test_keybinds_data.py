# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""data/keybinds.default.json must stay a faithful extract of keybind.lua."""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "keybinds.default.json"
SOURCE = ROOT / ".config" / "hypr" / "keybind.lua"
KINDS = {"exec", "dispatcher", "lua-function", "reserved"}


class KeybindsData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA.read_text(encoding="utf-8"))

    def test_json_matches_the_lua_source(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "extract_keybinds.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_every_runtime_bind_is_present(self):
        calls = len(re.findall(r"hl\.bind\(", SOURCE.read_text(encoding="utf-8")))
        bound = [b for b in self.data["bindings"] if b["status"] == "bound"]
        # two of the calls are the workspace loop, which expands to 18 binds
        self.assertEqual(calls - 2 + 18, len(bound))

    def test_reserved_shortcuts_are_declared_but_not_bound(self):
        reserved = {b["keys"] for b in self.data["bindings"] if b["status"] == "reserved"}
        self.assertEqual({"SUPER + H", "SUPER + SHIFT + H", "SUPER + K"}, reserved)
        lua = SOURCE.read_text(encoding="utf-8")
        for name in ("CHEATSHEET_TOGGLE", "CHEATSHEET_REFRESH", "HYPR_KEYS_PANEL"):
            self.assertNotIn(f"hl.bind(KEY.{name}", lua, f"{name} is still unbound in Lua; keep it reserved")

    def test_entries_are_complete_and_well_formed(self):
        for entry in self.data["bindings"]:
            with self.subTest(keys=entry.get("keys")):
                self.assertTrue(entry["keys"].strip())
                self.assertTrue(entry["description"].strip())
                self.assertIn(entry["action"]["kind"], KINDS)
                if entry["action"]["kind"] == "exec":
                    self.assertTrue(entry["action"]["command"].strip())
                if entry["status"] == "bound":
                    self.assertNotEqual("reserved", entry["action"]["kind"])

    def test_no_duplicate_key_combinations(self):
        keys = [b["keys"] for b in self.data["bindings"] if b["status"] == "bound"]
        self.assertEqual(len(keys), len(set(keys)), "a key may only be bound once")


if __name__ == "__main__":
    unittest.main()
