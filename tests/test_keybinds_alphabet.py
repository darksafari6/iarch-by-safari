# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The A to Z table and the keyboard map agree, in both directions.

`data/design/keybinds.json -> alphabet` allocates all 78 letter cells of the three
layers a letter may live in: `Super`, `Super+Shift` and `Super+Ctrl`. It is a plan
for `data/keybinds.default.json` rather than a second map, and a plan nobody checks
is a document that flatters the past, so this file is the check:

* a cell that says `bound` or `declared` names a binding that exists, at exactly
  those keys, enabled or not as the status claims;
* a cell that says `reserved` or `free` has nothing bound at that combination;
* every letter binding in the map has a cell, so a bind cannot be added to a
  letter the table has not allocated;
* every refusal cites something that exists in this repository -- a verb, a path, a
  command -- because a reservation is an argument and not a mood;
* the three keys `docs/ROADMAP.md` Part 7 reserves are still where Part 7 says.

The checker in `iarch/cli/iarch_keybinds.py` deliberately does not read the table:
an override in `~/.config/iarch/keybinds.json` may use any empty cell it likes, and
a validator that policed a person's own map would be policing the wrong file.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "data" / "design" / "keybinds.json"
DEFAULTS = ROOT / "data" / "keybinds.default.json"
ROADMAP = ROOT / "docs" / "ROADMAP.md"
SHORTCUTS = ROOT / "docs" / "SHORTCUTS.md"
LINKER = ROOT / "scripts" / "iarch-link-cli.sh"
VERBS = ROOT / "data" / "design" / "noctalia-ipc.json"

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def combo(mods: List[str], key: str) -> str:
    """A combination the way the map and the document both spell it."""
    return " + ".join(list(mods) + [key])


def is_bound(binding: Dict[str, Any]) -> bool:
    return bool(binding.get("enabled")) and binding["action"].get("type") != "none"


class TheShapeOfTheTable(unittest.TestCase):
    """What the table has to be before any of its contents mean anything."""

    @classmethod
    def setUpClass(cls):
        cls.alphabet = load(DESIGN)["alphabet"]
        cls.layers = cls.alphabet["layers"]

    def test_it_allocates_the_three_letter_layers_and_only_those(self):
        self.assertEqual([["SUPER"], ["SUPER", "SHIFT"], ["SUPER", "CTRL"]],
                         [layer["mods"] for layer in self.layers])
        self.assertEqual(["primary", "secondary", "tertiary"],
                         [layer["name"] for layer in self.layers])

    def test_super_alt_cannot_be_spelled_in_the_table(self):
        """The empty layer stays empty, and the table is not where it gets filled.

        `iarch_keybinds.layer_rule` refuses `Super+Alt` outright, so a fourth layer
        here would be a plan for a bind the checker rejects.
        """
        for layer in self.layers:
            self.assertNotEqual({"SUPER", "ALT"}, set(layer["mods"]))

    def test_every_layer_allocates_every_letter_exactly_once(self):
        for layer in self.layers:
            with self.subTest(layer=layer["name"]):
                self.assertEqual(list(LETTERS), [cell["key"] for cell in layer["cells"]])

    def test_every_cell_has_a_status_the_record_explains(self):
        statuses = self.alphabet["statuses"]
        self.assertEqual({"bound", "declared", "reserved", "free"}, set(statuses))
        for layer in self.layers:
            for cell in layer["cells"]:
                with self.subTest(cell=combo(layer["mods"], cell["key"])):
                    self.assertIn(cell["status"], statuses)
                    self.assertEqual("reserved" == cell["status"], "reason" in cell)
                    self.assertEqual(cell["status"] in ("bound", "declared"),
                                     "binding" in cell)

    def test_the_table_is_the_size_it_claims_to_be(self):
        cells = [cell for layer in self.layers for cell in layer["cells"]]
        self.assertEqual(78, len(cells), "three layers of 26 letters")
        self.assertIn("78 cells", SHORTCUTS.read_text(encoding="utf-8"),
                      "docs/SHORTCUTS.md says how many cells the table allocates, and "
                      "the renderer writes that number from the table itself")

    def test_it_says_which_debt_it_settles(self):
        """The relocation is part of the record, not only part of a changelog."""
        self.assertIn("move.next", self.alphabet["settles"])
        self.assertIn("Super+Ctrl+Alt", self.alphabet["settles"])


class TheTableAndTheMapAgree(unittest.TestCase):
    """Both directions: nothing bound that the table has not allocated, and nothing
    allocated that the map does not implement the way the cell says."""

    @classmethod
    def setUpClass(cls):
        cls.alphabet = load(DESIGN)["alphabet"]
        cls.layers = cls.alphabet["layers"]
        cls.bindings = load(DEFAULTS)["bindings"]
        cls.by_id = {b["id"]: b for b in cls.bindings}
        cls.occupied: Dict[str, str] = {}
        for binding in cls.bindings:
            key = binding.get("key", "")
            if len(key) == 1 and key.isalpha():
                cls.occupied[combo(binding.get("mods") or [], key.upper())] = binding["id"]

    def test_a_bound_cell_is_a_binding_at_exactly_those_keys(self):
        for layer in self.layers:
            for cell in layer["cells"]:
                if cell["status"] != "bound":
                    continue
                keys = combo(layer["mods"], cell["key"])
                with self.subTest(keys=keys):
                    binding = self.by_id.get(cell["binding"])
                    self.assertIsNotNone(binding, "the cell names a binding the map lacks")
                    self.assertEqual(keys, combo(binding.get("mods") or [],
                                                 binding["key"].upper()))
                    self.assertTrue(is_bound(binding),
                                    "the cell says the key does something today")

    def test_a_declared_cell_is_a_binding_that_is_not_enabled(self):
        declared = [(combo(layer["mods"], cell["key"]), cell["binding"])
                    for layer in self.layers for cell in layer["cells"]
                    if cell["status"] == "declared"]
        self.assertTrue(declared, "the two Part 7 keys are declared in the table")
        for keys, binding_id in declared:
            with self.subTest(keys=keys):
                binding = self.by_id.get(binding_id)
                self.assertIsNotNone(binding)
                self.assertEqual(keys, combo(binding.get("mods") or [],
                                             binding["key"].upper()))
                self.assertFalse(is_bound(binding),
                                 "a declared cell is a key the record has claimed and "
                                 "not bound; if it is bound, the cell should say bound")
                self.assertTrue(binding.get("reserved"))

    def test_an_empty_cell_has_nothing_bound_at_it(self):
        for layer in self.layers:
            for cell in layer["cells"]:
                if cell["status"] in ("bound", "declared"):
                    continue
                keys = combo(layer["mods"], cell["key"])
                with self.subTest(keys=keys):
                    self.assertNotIn(keys, self.occupied,
                                     f"the table leaves {keys} {cell['status']} but the "
                                     f"map binds {self.occupied.get(keys)} there")

    def test_every_letter_binding_in_the_map_has_a_cell(self):
        """The direction that stops the table becoming history: a new bind on a letter
        the table has not allocated fails here, rather than leaving a grid that looks
        complete and is not."""
        tabled = {combo(layer["mods"], cell["key"])
                  for layer in self.layers for cell in layer["cells"]}
        for binding in self.bindings:
            key = binding.get("key", "")
            if len(key) != 1 or not key.isalpha():
                continue
            keys = combo(binding.get("mods") or [], key.upper())
            with self.subTest(keys=keys, binding=binding["id"]):
                if keys not in tabled:
                    self.assertIn("System", binding.get("category", ""),
                                  f"{binding['id']} binds {keys}, which is outside the "
                                  "three layers the table allocates; only the recovery "
                                  "and system layer may hold a letter it does not know")

    def test_the_letter_binds_outside_the_table_are_the_recovery_layer(self):
        """Named, so a third one is a decision somebody has to make on purpose."""
        tabled = {combo(layer["mods"], cell["key"])
                  for layer in self.layers for cell in layer["cells"]}
        outside = sorted(
            binding["id"] for binding in self.bindings
            if len(binding.get("key", "")) == 1 and binding["key"].isalpha()
            and combo(binding.get("mods") or [], binding["key"].upper()) not in tabled)
        self.assertEqual(["recovery.reapply-defaults"], outside)

    def test_no_binding_owns_two_cells(self):
        owners = [cell["binding"] for layer in self.layers for cell in layer["cells"]
                  if cell["status"] in ("bound", "declared")]
        self.assertEqual(len(owners), len(set(owners)),
                         "one binding in two cells is a table that cannot say where the "
                         "key is")


class TheRefusalsCiteSomething(unittest.TestCase):
    """A reservation is an argument with a mechanism in it, so each one has to name a
    thing this repository has: a verb the shell answers, a file, a command something
    installs, or another identifier the records already use. The corpus is the
    repository's own records minus the table itself, because a reason that only quotes
    itself proves nothing, and common English words do not count as citations -- only
    nouns that are verbs, paths, commands or identifier-shaped tokens found in the
    corpus, so a reason cannot pass on the word "session"."""

    IDENTIFIER = re.compile(r"^[a-z0-9]+([-_.][a-z0-9]+)+$")

    @classmethod
    def setUpClass(cls):
        design = load(DESIGN)
        design.pop("alphabet", None)
        cls.alphabet = load(DESIGN)["alphabet"]
        cls.verbs = {v["verb"] for v in load(VERBS)["verbs"]}
        cls.commands = set(re.findall(r'"(iarch-[a-z-]+):', LINKER.read_text(encoding="utf-8")))
        cls.paths = {str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
                     if p.is_file() and ".git" not in p.parts}
        cls.paths |= {Path(p).name for p in cls.paths}
        cls.corpus = "\n".join([
            json.dumps(design), json.dumps(load(DEFAULTS)), json.dumps(load(VERBS)),
            LINKER.read_text(encoding="utf-8"),
            *(p.read_text(encoding="utf-8") for p in sorted((ROOT / "scripts").glob("*.sh"))),
        ])
        cls.nouns = cls.verbs | cls.commands | cls.paths
        cls.nouns |= {token for token in re.findall(r"[A-Za-z0-9_.-]{4,}", cls.corpus)
                      if cls.IDENTIFIER.match(token)}

    def citations(self, reason: str) -> List[str]:
        """The nouns in a reason. Punctuation at the edges of a token is dropped first,
        because a citation at the end of a sentence carries a full stop with it."""
        found = []
        for token in re.findall(r"[A-Za-z0-9_.-]{4,}", reason):
            candidate = token.strip("._-")
            if candidate in self.nouns and candidate not in found:
                found.append(candidate)
        return found

    def test_every_reservation_names_a_verb_a_path_or_a_command(self):
        reserved = [(combo(layer["mods"], cell["key"]), cell["reason"])
                    for layer in self.alphabet["layers"] for cell in layer["cells"]
                    if cell["status"] == "reserved"]
        self.assertGreaterEqual(len(reserved), 5,
                                "the table is supposed to record refusals, not holes")
        for keys, reason in reserved:
            with self.subTest(keys=keys):
                self.assertTrue(self.citations(reason),
                                f"{keys} is reserved for a reason that names nothing this "
                                "repository has -- no verb, no path, no command, no "
                                "identifier the records use")

    def test_the_citation_rule_would_notice_a_reason_of_nothing_but_prose(self):
        """The test above has to be able to fail, or it is decoration."""
        self.assertEqual([], self.citations("Reserved because nothing needs it yet and "
                                            "the layer is otherwise fine as it is."))
        self.assertTrue(self.citations("Reserved until the shell answers volume-mute."))

    def test_the_reasons_are_long_enough_to_be_reasons(self):
        for layer in self.alphabet["layers"]:
            for cell in layer["cells"]:
                if cell["status"] != "reserved":
                    continue
                with self.subTest(keys=combo(layer["mods"], cell["key"])):
                    self.assertGreater(len(cell["reason"]), 120,
                                       "'not yet' is not a refusal")


class TheKeysTheRoadmapReserves(unittest.TestCase):
    """Part 7 names three keys so that they are not reassigned by accident. If the map
    moves one, the sentence in the roadmap has to move with it -- which is the point of
    reading the sentence rather than writing the three combinations down here again."""

    @classmethod
    def setUpClass(cls):
        cls.bindings = load(DEFAULTS)["bindings"]
        cls.text = ROADMAP.read_text(encoding="utf-8")

    def by_keys(self, keys: str) -> Dict[str, Any]:
        wanted = [part.strip() for part in keys.split("+")]
        mods, key = wanted[:-1], wanted[-1].upper()
        found = [b for b in self.bindings
                 if [m.upper() for m in (b.get("mods") or [])] == mods
                 and b["key"].upper() == key]
        self.assertEqual(1, len(found), f"{keys} is not bound exactly once")
        return found[0]

    def test_the_three_keys_part_7_names_are_where_it_says(self):
        named = re.findall(r"`(Super\+(?:Shift\+)?[A-Z])`", self.text)
        self.assertTrue(named, "Part 7 no longer names the keys it reserves, so this "
                               "test has nothing to check the map against")
        for spelling in sorted(set(named)):
            keys = spelling.replace("Super", "SUPER").replace("Shift", "SHIFT")
            with self.subTest(keys=keys):
                binding = self.by_keys(keys)
                self.assertTrue(binding["id"].startswith(("overlay.", "planned.")),
                                f"{keys} belongs to the shortcut overlay work and is now "
                                f"{binding['id']!r}; move the sentence in "
                                "docs/ROADMAP.md Part 7 if that is deliberate")

    def test_the_document_renders_a_row_for_every_letter(self):
        text = SHORTCUTS.read_text(encoding="utf-8")
        section = text.split("## The A to Z table", 1)
        self.assertEqual(2, len(section), "docs/SHORTCUTS.md has no A to Z table; run "
                                          "python3 tools/render_shortcuts.py --write")
        rows = re.findall(r"^\| ([A-Z]) \|", section[1], re.M)
        self.assertEqual(list(LETTERS), rows)


if __name__ == "__main__":
    unittest.main()
