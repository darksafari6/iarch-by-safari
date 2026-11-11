# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""docs/SHORTCUTS.md is rendered from the keybind data and cannot drift."""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "SHORTCUTS.md"
DATA = ROOT / "data" / "keybinds.default.json"


class ShortcutsDoc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = DOC.read_text(encoding="utf-8")
        cls.data = json.loads(DATA.read_text(encoding="utf-8"))

    def test_the_document_matches_its_source(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "render_shortcuts.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_it_is_marked_generated(self):
        self.assertIn("GENERATED FILE - do not edit by hand", self.doc)
        self.assertIn("data/keybinds.default.json", self.doc)

    def test_every_bound_shortcut_is_listed(self):
        listed = set(re.findall(r"^\| `([^`]+)` \|", self.doc, re.M))
        for binding in self.data["bindings"]:
            with self.subTest(keys=binding["keys"]):
                self.assertIn(binding["keys"], listed)
        self.assertEqual(len(listed), len(self.data["bindings"]))

    def test_reserved_keys_are_marked_as_not_bound(self):
        reserved = [b for b in self.data["bindings"] if b["status"] == "reserved"]
        self.assertTrue(reserved, "expected the overlay keys to be reserved")
        section = self.doc.split("## Planned", 1)[1]
        for binding in reserved:
            with self.subTest(keys=binding["keys"]):
                line = next(l for l in section.splitlines() if f"`{binding['keys']}`" in l)
                self.assertIn("not bound yet", line)

    def test_categories_follow_the_session_configuration(self):
        headings = re.findall(r"^## (.+)$", self.doc, re.M)
        expected = []
        for binding in self.data["bindings"]:
            if binding["category"] not in expected:
                expected.append(binding["category"])
        for category in expected:
            self.assertIn(category, headings)
        self.assertIn("Contents", headings)
        self.assertIn("Changing a shortcut", headings)

    def test_relative_links_resolve(self):
        for target in re.findall(r"\]\(([^)#]+?)(?:#[^)]*)?\)", self.doc):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            with self.subTest(link=target):
                self.assertTrue((DOC.parent / target).is_file(), f"broken link in SHORTCUTS.md: {target}")

    def test_no_previous_product_name_is_shown_to_a_user(self):
        for token in ("minimaLinux", "minimaDots", "noctalia-shell"):
            self.assertNotIn(token, self.doc)


if __name__ == "__main__":
    unittest.main()
