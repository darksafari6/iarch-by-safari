# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The keyboard record must be checkable offline, or it is only an opinion.

``data/design/keybinds.json`` says what the pinned compositor accepts. Most of what it
says was read out of a C++ tree that is not present here and cannot be fetched in CI, so
a test cannot re-derive it. What a test *can* do is hold the record to the two things
that were committed beside it: the keysym names, which are a generated list from the
pinned xkbcommon header, and the record's own internal consistency.

That is not a small thing. The failure this prevents is the one a shortcut system is
most exposed to: a key name that looks right, is written into a defaults file, renders
into a generated Lua file, and then resolves to nothing on the machine -- because
upstream answers ``'key not found'`` both for a name that is not a keysym and for a
keysym the keyboard cannot produce (``src/keybinds/Resolver.cpp:70-84``). The first half
of that is checkable here. The second half is not, and the record says so rather than
pretending otherwise.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "data" / "design" / "keybinds.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class KeybindsRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = read_json(RECORD)
        # The record names the list it is checked against, so the two cannot drift
        # into being about different releases without the filename saying so.
        cls.keysyms = (ROOT / cls.record["keysyms"]["name_list"]).read_text(
            encoding="utf-8").split()

    # ---------------------------------------------------------- the keysym list

    def test_the_committed_keysym_list_is_the_one_the_record_describes(self):
        """Three numbers in the record describe one generated file; they must agree.

        The header declares more lines than it has distinct names, because eleven
        names are declared twice with different codes. A list built from the lines
        rather than the names would carry duplicates and a count that matched
        nothing, so all three figures are pinned and checked against the file.
        """
        distinct = set(self.keysyms)
        self.assertEqual(self.record["keysyms"]["total_names_in_that_release"],
                         len(distinct),
                         "the record's distinct-name count and the committed list disagree")
        self.assertEqual(len(self.keysyms), len(distinct),
                         "the committed list has a duplicate name in it")
        self.assertEqual(self.keysyms, sorted(self.keysyms),
                         "the committed list is not sorted, so a diff cannot show what changed")
        self.assertGreater(self.record["keysyms"]["declared_lines_in_that_release"],
                           self.record["keysyms"]["total_names_in_that_release"],
                           "more lines than names is the whole reason both are recorded")

    def test_every_keysym_the_project_says_it_uses_really_is_one(self):
        """The check that a made-up key name cannot survive."""
        used = self.record["keysyms"]["used_by_this_project"]
        unknown = sorted({name for name in used if name not in set(self.keysyms)})
        self.assertEqual([], unknown,
                         "these are recorded as keysyms and are not in the pinned "
                         "xkbcommon header, so a bind using one resolves to nothing")

    def test_the_letters_and_digits_are_all_there(self):
        """A shortcut map is mostly letters, so the letters are the first thing to check."""
        known = set(self.keysyms)
        used = set(self.record["keysyms"]["used_by_this_project"])
        for char in "abcdefghijklmnopqrstuvwxyz0123456789":
            with self.subTest(key=char):
                self.assertIn(char, known, "not a keysym in the pinned release")
                self.assertIn(char, used, "a letter or digit the map cannot bind")

    def test_punctuation_is_a_word_and_not_the_character_it_prints(self):
        """'.' is not a keysym; 'period' is. The record must say which words to use.

        This is the trap with the quietest failure: a person writes the character
        they see on the keycap, the name resolves to NoSymbol, and the compositor's
        answer is the same 'key not found' it gives for a keyboard without the key.
        """
        known = set(self.keysyms)
        for character in ".,/;'-[]\\`+=":
            with self.subTest(character=character):
                self.assertNotIn(character, known,
                                 f"{character!r} is recorded as a keysym, so a bind "
                                 "written with the character would look valid")
        for word in ("period", "comma", "slash", "semicolon", "apostrophe",
                     "bracketleft", "bracketright", "backslash", "grave",
                     "minus", "equal"):
            with self.subTest(word=word):
                self.assertIn(word, known, "the word for a punctuation key is missing")

    def test_the_mouse_wheel_spelling_is_marked_unverified_not_asserted(self):
        """``mouse_up`` is what the shipped config says and nothing verified it.

        It is not a keysym and it is not a ``mouse:N`` code, so the two key forms
        this record verified both refuse it. It is kept because replacing it with
        something certainly wrong is worse than leaving something possibly right,
        and it is marked so that nobody mistakes the keeping for a verification.
        """
        rejected = {entry["spelling"]: entry for entry in self.record["rejected"]}
        wheel = [text for text in rejected if "mouse_up" in text]
        self.assertTrue(wheel, "the wheel binds are not recorded as rejected")
        entry = rejected[wheel[0]]
        self.assertEqual("TODO(verify)", entry.get("status"),
                         "the wheel spelling is recorded as settled when it is not")
        self.assertNotIn("mouse_up", self.record["keysyms"]["used_by_this_project"],
                         "mouse_up is listed as a keysym this project uses")

    # ------------------------------------------------------- the option surface

    def test_every_bind_option_names_a_flag_upstream_sets(self):
        """An option with no BIND_FLAG behind it is an option the compositor ignores."""
        for name, option in self.record["bind"]["options"].items():
            with self.subTest(option=name):
                if "flag" in option:
                    self.assertTrue(option["flag"].startswith("BIND_FLAG_"),
                                    f"{name} names a flag that is not a BIND_FLAG")

    def test_the_exclusions_are_the_options_own_incompatibilities(self):
        """Two lists of the same three rules must not drift apart.

        ``options.*.incompatible_with`` and ``bind.exclusions`` say the same thing
        in two shapes: one is what a generator checks per option, the other is the
        message the compositor gives. A rule in one and not the other is a bind the
        generator emits and the compositor refuses at parse time -- which is a bind
        that silently does not exist.
        """
        pairwise = set()
        for name, option in self.record["bind"]["options"].items():
            for other in option.get("incompatible_with") or ():
                pairwise.add(frozenset((name, other)))
        refused = {entry["refused"] for entry in self.record["bind"]["exclusions"]}
        joined = " | ".join(sorted(refused)).lower()
        for pair in sorted(pairwise, key=lambda p: sorted(p)):
            a, b = sorted(pair)
            with self.subTest(pair=f"{a}+{b}"):
                self.assertTrue(a in joined or b in joined,
                                f"{a} and {b} are recorded as incompatible and no "
                                "exclusion names either, so the message is unknown")
        self.assertEqual(3, len(self.record["bind"]["exclusions"]),
                         "upstream refuses exactly three combinations at hl.bind")

    def test_a_mouse_bind_is_not_recorded_as_also_locked_or_repeating(self):
        """``mouse`` is exclusive, and the shipped config has two mouse binds."""
        mouse = self.record["bind"]["options"]["mouse"]
        for other in ("repeating", "release", "locked"):
            self.assertIn(other, mouse["incompatible_with"])

    def test_the_project_locked_field_is_not_confused_with_the_compositors(self):
        """Same word, two meanings, and mixing them loses a safety property.

        Upstream's ``locked`` means the bind still works while the session is
        locked. This project's ``locked`` means a person may rebind the entry but
        not delete it. Only the first may ever reach a generated file.
        """
        note = self.record["bind"]["options"]["locked"].get("note", "")
        self.assertIn("not the same thing", note.lower(),
                      "the record does not keep the two 'locked' meanings apart")

    # ------------------------------------------------------ the dispatcher tree

    def test_dispatcher_max_arguments_are_within_what_the_api_takes(self):
        for group in self.record["dispatchers"]["groups"].values():
            for name, arity in group["members"].items():
                with self.subTest(dispatcher=name):
                    self.assertLessEqual(arity, 2, "no dispatcher in hl.dsp takes more")
        for name, arity in self.record["dispatchers"]["toplevel"]["members"].items():
            with self.subTest(dispatcher=name):
                self.assertLessEqual(arity, 2)

    def test_a_dispatcher_this_project_uses_is_one_that_exists(self):
        """``used_by_this_project`` must not name a dispatcher the tree lacks."""
        # The tree is two levels: four groups with leaves, plus top-level members
        # that sit directly on hl.dsp. So the check is against fully qualified
        # paths, and a name that is in neither level is a dispatcher that does not
        # exist -- which is the invention this record is here to prevent.
        tree = set(self.record["dispatchers"]["toplevel"]["members"])
        for group_name, group in self.record["dispatchers"]["groups"].items():
            tree.update(f"{group_name}.{leaf}" for leaf in group["members"])
        for used in self.record["dispatchers"]["used_by_this_project"]:
            with self.subTest(dispatcher=used):
                self.assertTrue(used.startswith("hl.dsp."),
                                f"{used} is not written as an hl.dsp path")
                self.assertIn(used.removeprefix("hl.dsp."), tree,
                              "recorded as used and not in the verified hl.dsp tree")

    def test_used_and_not_used_do_not_overlap(self):
        used = set(self.record["dispatchers"]["used_by_this_project"])
        unused = set(self.record["dispatchers"]["not_used_and_why"])
        self.assertEqual(set(), used & unused,
                         "a dispatcher is both used and refused, so one of the two "
                         "reasons is about a different thing than it appears")

    # ------------------------------------------------------------ the exec form

    def test_a_command_is_one_string_and_the_record_says_what_that_costs(self):
        """The single most consequential fact in the record for the data model."""
        exec_ = self.record["exec"]
        self.assertEqual("one string", exec_["the_only_form"])
        self.assertIn("/bin/sh", exec_["spawned_as"])
        self.assertIn("-c", exec_["spawned_as"])
        self.assertIn("argv", exec_["consequence"]["statement"],
                      "the record does not say that there is no argv form")
        self.assertIn("shlex", exec_["consequence"]["what_this_project_does"],
                      "the record does not name how a list becomes a string")

    # --------------------------------------------------------------- the config

    def test_the_line_format_is_rejected_because_no_parser_exists(self):
        """Not a style preference: v0.57.2 cannot read it."""
        rejected = {entry["spelling"]: entry for entry in self.record["rejected"]}
        line = [text for text in rejected if text.startswith("bind=")]
        self.assertTrue(line, "the manual's line format is not recorded as rejected")
        why = rejected[line[0]]["why_rejected"]
        for citation in ("ConfigManager.cpp", "Jeremy.cpp"):
            self.assertIn(citation, why,
                          f"the rejection cites no {citation}, so it reads as a "
                          "preference rather than as something verified")
        self.assertEqual("TODO(verify)", rejected[line[0]]["status"],
                         "the flag letters are recorded as verified when the table "
                         "that mapped them belonged to a parser this release lacks")

    def test_the_generated_module_is_in_the_reload_cache_clear_list(self):
        """A generated module left in package.loaded does not re-register its binds.

        hyprland.lua clears package.loaded for the modules whose binds have to
        re-register, and a generated keybinds module has to be one of them or a
        reload keeps the previous parse's keyboard.

        Conditional on the generated file existing, and not skipped silently: a
        require() of a module with no file behind it is a config error, so wiring
        hyprland.lua before the generator has written anything would break the
        session this record exists to protect. The moment the file is committed
        this assertion becomes unconditional, which is the point of writing it now.
        """
        self.assertTrue(self.record["entry_point"]["cache_cleared_on_reload"])
        generated = ROOT / self.record["entry_point"]["generated_file"]
        hyprland = (ROOT / ".config" / "hypr" / "hyprland.lua").read_text(encoding="utf-8")
        module = self.record["entry_point"]["generated_module_name"]
        if not generated.exists():
            self.assertNotIn(f'"{module}"', hyprland,
                             f"hyprland.lua requires {module} but nothing has generated "
                             "the file, which is a config error at every login")
            return
        self.assertIn(f'"{module}"', hyprland,
                      f"hyprland.lua does not clear {module} from package.loaded, so "
                      "a reload would keep the binds from the previous parse")
        self.assertIn(f'require("{module}")', hyprland,
                      "the generated file exists and nothing loads it, so the binds in "
                      "it are not binds")

    def test_the_emergency_binds_are_recorded_as_reassigning_keys_this_project_uses(self):
        """Upstream's recovery net takes SUPER + Q away, and that must be written down.

        A person who learns that SUPER + Q closes a window and then meets a config
        that failed to parse will otherwise conclude the keyboard has broken.
        """
        emergency = self.record["recovery"]["emergency_mode"]
        keys = {bind["keys"] for bind in emergency["binds_it_registers"]}
        self.assertIn("SUPER + Q", keys)
        self.assertTrue(any("SUPER + Q" in point for point in emergency["why_it_matters"]),
                        "the record lists the emergency binds without saying that one "
                        "of them collides with this project's close-window key")
        self.assertIn("registry().empty()", emergency["tripped_when"],
                      "the trip condition is paraphrased, so the case where it does "
                      "not trip -- some binds registered, then an error -- is invisible")

    def test_validation_names_three_levels_and_what_each_cannot_answer(self):
        levels = self.record["validation"]["levels"]
        self.assertEqual(["the model", "the syntax", "the compositor"],
                         [level["level"] for level in levels])
        for level in levels:
            with self.subTest(level=level["level"]):
                self.assertTrue(level["limit"].strip(),
                                "a level with no stated limit reads as a level that "
                                "proves the file works")
        compositor = levels[2]
        self.assertIn("--verify-config", compositor["tool"])
        self.assertIn("src/main.cpp", compositor["source"])


if __name__ == "__main__":
    unittest.main()
