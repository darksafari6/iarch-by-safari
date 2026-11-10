# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""ARCHITECTURE.md must state the user-state rules and carry a valid diagram."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DOC = ROOT / "docs" / "ARCHITECTURE.md"
from iarch.lib import configstore  # noqa: E402


class ArchitectureDoc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")
        cls.diagram = re.search(r"```mermaid\n(.*?)```", cls.text, re.S)

    def test_the_state_rules_are_documented(self):
        for phrase in (
            "~/.config/iarch/",
            "data/settings.default.json",
            "~/.local/state/iarch/backups/",
            "last five backups",
            "atomic",
            "Never write inside the repository at runtime",
        ):
            self.assertIn(phrase, self.text, f"ARCHITECTURE.md no longer documents: {phrase}")

    def test_the_generated_header_is_quoted_verbatim(self):
        self.assertIn(configstore.GENERATED_HEADER, self.text)

    def test_the_diagram_exists_and_is_structurally_valid(self):
        self.assertIsNotNone(self.diagram, "ARCHITECTURE.md lost its Mermaid diagram")
        body = self.diagram.group(1)
        self.assertTrue(body.startswith("flowchart"))
        self.assertEqual(len(re.findall(r"^\s*subgraph ", body, re.M)),
                         len(re.findall(r"^\s*end\s*$", body, re.M)),
                         "every subgraph needs an end")
        self.assertEqual(body.count("["), body.count("]"), "unbalanced node brackets")
        self.assertEqual(body.count('"') % 2, 0, "unbalanced quotes in a node label")

    def test_the_diagram_names_the_four_stages(self):
        body = self.diagram.group(1)
        for stage, needle in (
            ("settings app", "settings-app"),
            ("config store", "configstore.py"),
            ("generators", "renderers.py"),
            ("Hyprland reload", "Hyprland"),
            ("Noctalia reload", "Noctalia"),
        ):
            self.assertIn(needle, body, f"diagram no longer shows the {stage}")

    def test_every_node_used_in_an_edge_is_declared(self):
        body = self.diagram.group(1)
        # A declaration is any indented "NAME[" — inside a subgraph it is deeper.
        declared = set(re.findall(r"^\s+([A-Z][A-Z0-9]*)\s*\[", body, re.M))
        used = set()
        for line in body.splitlines():
            if "-->" not in line:
                continue
            edge = re.sub(r'\|[^|]*\|', "", line)  # drop the edge captions
            used.update(re.findall(r"\b([A-Z][A-Z0-9]*)\b", edge))
        self.assertEqual(set(), used - declared,
                         "an edge names a node the diagram never declares")

    def test_documented_directories_exist(self):
        for relative in ("iarch/lib", "iarch/cli", "iarch/settings-app", "data", "data/design",
                         "data/schemas", "profiles", "assets/wallpapers"):
            self.assertTrue((ROOT / relative).is_dir(), f"documented directory is missing: {relative}")


if __name__ == "__main__":
    unittest.main()
