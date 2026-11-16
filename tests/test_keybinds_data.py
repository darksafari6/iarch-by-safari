# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""data/keybinds.default.json is the source, and the Lua is generated from it.

This file used to assert the opposite -- that the JSON was a faithful extract of
a hand-written ``keybind.lua`` -- and Part 5 reversed the direction. The record
is now the single source of the keyboard map: ``iarch-keybinds`` renders
``.config/hypr/generated/keybinds.lua`` from it, ``tools/render_shortcuts.py``
renders the documentation from it, and the Shortcuts page reads it. So the
question this file asks is no longer "does the JSON match the Lua" but "is the
record sound, and is everything rendered from it current".

The generator's own logic -- the validation rules, the merge, the Lua it emits
for a fixture -- is tested in ``tests/test_iarch_keybinds.py``. What is here is
the integrity of the shipped record and the freshness of its renderings.
"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "keybinds.default.json"
GENERATED = ROOT / ".config" / "hypr" / "generated" / "keybinds.lua"
STATIC_LUA = ROOT / ".config" / "hypr" / "keybind.lua"
KEYSYM_LIST = ROOT / "data" / "reference" / "xkb-keysyms-1.7.0.txt"
ACTION_TYPES = {"exec", "shell", "dispatch", "lua", "iarch", "noctalia", "none"}


def key_string(binding):
    return " + ".join(list(binding.get("mods") or []) + [binding["key"]])


def is_bound(binding):
    return bool(binding.get("enabled")) and binding["action"].get("type") != "none"


class KeybindsData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA.read_text(encoding="utf-8"))
        cls.bindings = cls.data["bindings"]
        cls.keysyms = {name.lower() for name in
                       KEYSYM_LIST.read_text(encoding="utf-8").split()}

    def test_the_record_is_version_two(self):
        self.assertEqual(2, self.data["version"],
                         "the record is the source the generator renders from, and "
                         "version 1 was a report about a Lua file")

    def test_the_generated_lua_is_current_with_the_record(self):
        """The freshness check that replaces 'the JSON matches the Lua'."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "iarch" / "cli" / "iarch_keybinds.py"),
             "generate", "--check"],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_every_enabled_binding_is_in_the_generated_lua(self):
        """Every enabled binding is bound, in exactly one of the two files.

        A static binding is written by hand in ``keybind.lua`` on purpose -- it is
        the recovery combo, which has to work when the generated file does not -- so
        it is asserted against the static file instead, and against *not* being in
        the generated one, because a key bound in both files is two handlers racing
        and which one runs depends on require() order.
        """
        lua = GENERATED.read_text(encoding="utf-8")
        for binding in self.bindings:
            if not is_bound(binding) or binding.get("static"):
                continue
            with self.subTest(keys=key_string(binding)):
                self.assertIn(f'hl.bind("{key_string(binding)}"', lua,
                              "an enabled binding the generated file does not bind")

    def test_every_static_binding_is_hand_written_and_only_there(self):
        static = [b for b in self.bindings if b.get("static")]
        self.assertTrue(static, "the recovery combo is static by design; if there is "
                                "none, the safety net has gone missing rather than "
                                "been folded into the render")
        lua = GENERATED.read_text(encoding="utf-8")
        hand = STATIC_LUA.read_text(encoding="utf-8")
        for binding in static:
            keys = key_string(binding)
            with self.subTest(keys=keys):
                self.assertTrue(is_bound(binding),
                                "a static binding that is not enabled binds nothing "
                                "anywhere, so the record would promise a key the "
                                "session does not have")
                self.assertIn(f'hl.bind("{keys}"', hand,
                              "marked static but not hand-written in keybind.lua")
                self.assertNotIn(f'hl.bind("{keys}"', lua,
                                 "a static binding the render also emits, so two "
                                 "handlers race on one key")

    def test_the_recovery_combo_survives_a_broken_generated_file(self):
        """The safety net's whole reason for being, asserted on the require order.

        ``hyprland.lua`` requires ``generated.keybinds`` before ``keybind``, and the
        compositor's safe-require catches a module that loads and then errors, so a
        failure in the generated file still reaches the static one. If either half of
        that changes -- the order flips, or the recovery bind moves into the
        generated file -- Ctrl+Alt+R stops being a recovery and becomes another
        casualty of the breakage it exists to fix.
        """
        entry = next(b for b in self.bindings if b["id"] == "recovery.reapply-defaults")
        self.assertTrue(entry.get("static"),
                        "the recovery combo must stay hand-written: a bind inside the "
                        "file that failed cannot repair that file")
        self.assertTrue(entry["unverified"].strip(),
                        "the recovery bind calls a command the installer has not put "
                        "on PATH yet, and the record has to say so rather than imply "
                        "a working key")

        hyprland = (ROOT / ".config" / "hypr" / "hyprland.lua").read_text(encoding="utf-8")
        self.assertLess(hyprland.index('require("generated.keybinds")'),
                        hyprland.index('require("keybind")'),
                        "generated.keybinds must be required first so a render that "
                        "does not parse leaves the registry empty and the compositor's "
                        "emergency binds trip")
        self.assertIn('hl.bind("CTRL + ALT + R"',
                      STATIC_LUA.read_text(encoding="utf-8"))

    def test_no_disabled_or_reserved_binding_is_in_the_generated_lua(self):
        """A bind that is off is absent, not commented out.

        A commented-out bind in a generated file is a bind a person will hand-edit
        and then lose on the next render, so the renderer omits it entirely.
        """
        lua = GENERATED.read_text(encoding="utf-8")
        for binding in self.bindings:
            if is_bound(binding):
                continue
            with self.subTest(keys=key_string(binding)):
                self.assertNotIn(f'hl.bind("{key_string(binding)}"', lua,
                                 "a binding that is not enabled still renders a bind")

    def test_the_reserved_keys_are_declared_but_not_bound(self):
        reserved = [b for b in self.bindings if b.get("reserved")]
        self.assertTrue(reserved, "the overlay keys should still be reserved")
        for binding in reserved:
            with self.subTest(keys=key_string(binding)):
                self.assertFalse(binding["enabled"])
                self.assertEqual("none", binding["action"]["type"])

    def test_super_h_is_bound_to_the_overlay(self):
        """The whole point of Part 5: SUPER + H opens the shortcut overlay."""
        cheatsheet = [b for b in self.bindings if key_string(b) == "SUPER + H"]
        self.assertEqual(1, len(cheatsheet), "SUPER + H is not bound exactly once")
        entry = cheatsheet[0]
        self.assertTrue(entry["enabled"])
        self.assertTrue(entry["locked"],
                        "the overlay is a way back into the keyboard map, so it is "
                        "rebindable but not deletable")
        self.assertIn("unverified", entry,
                      "the overlay is not built yet and the record must say so "
                      "rather than imply a working window")

    def test_entries_are_complete_and_well_formed(self):
        for binding in self.bindings:
            with self.subTest(id=binding.get("id")):
                self.assertTrue(binding["id"].strip())
                self.assertTrue(binding["description"].strip())
                self.assertIsInstance(binding["mods"], list)
                self.assertTrue(binding["key"].strip())
                self.assertIn(binding["action"]["type"], ACTION_TYPES)
                if binding["action"]["type"] == "exec":
                    self.assertTrue(binding["action"]["command"])

    def test_no_duplicate_key_combinations(self):
        bound = [key_string(b) for b in self.bindings if is_bound(b)]
        duplicates = {k for k in bound if bound.count(k) > 1}
        self.assertEqual(set(), duplicates,
                         "two binds on one combination is two handlers, and which "
                         "runs depends on registration order")

    def test_no_duplicate_ids(self):
        ids = [b["id"] for b in self.bindings]
        duplicates = {i for i in ids if ids.count(i) > 1}
        self.assertEqual(set(), duplicates,
                         "an override file keys differences by id, so a duplicate id "
                         "makes one of them unreachable")

    def test_every_key_is_a_keysym_or_a_form_the_compositor_resolves(self):
        """The check that stops an invented key name reaching a generated file.

        A key is valid if it is a keysym in the pinned xkbcommon, a `mouse:N` button
        code, a `code:N` keycode, a bare number over 9, or one of the four wheel-axis
        event names. The events are the shape that took source to find: `mouse_up` is
        neither a keysym nor a `mouse:N` code, so both forms this project had verified
        refuse it -- and it still binds, because `CKey::isValidEvent` accepts the four
        names before any keysym lookup (`src/keybinds/Key.cpp:8-10`) and
        `CKeybindManager::onAxisEvent` dispatches a wheel delta under exactly that name
        (`src/keybinds/Manager.cpp:312-335`). Listed here rather than skipped, so an
        invented name still fails.
        """
        events = {"mouse_up", "mouse_down", "mouse_left", "mouse_right"}
        for binding in self.bindings:
            if not is_bound(binding):
                continue
            key = binding["key"]
            with self.subTest(keys=key_string(binding)):
                valid = (key.lower() in self.keysyms
                         or key in events
                         or (key.startswith("mouse:") and key[6:].isdigit())
                         or (key.startswith("code:") and key[5:].isdigit())
                         or (key.isdigit() and int(key) > 9))
                self.assertTrue(valid, f"{key!r} is not a key the compositor resolves")

    def test_the_event_names_this_file_accepts_are_the_ones_the_record_documents(self):
        """So the exception above cannot quietly grow.

        This test and the record are deliberately two independent statements of the
        same four names; if one is edited without the other, a spelling the compositor
        does not dispatch would reach a generated file and silently do nothing.
        """
        record = json.loads(
            (ROOT / "data" / "design" / "keybinds.json").read_text(encoding="utf-8"))
        forms = {f["form"]: f for f in record["key_forms"]["forms"]}
        self.assertIn("special event name", forms,
                      "the record no longer documents the wheel events as a key form, "
                      "so the exception in the test above has nothing behind it")
        documented = forms["special event name"]["meaning"]
        for name in ("mouse_up", "mouse_down", "mouse_left", "mouse_right"):
            with self.subTest(name=name):
                self.assertIn(name, documented)
        self.assertIn("Key.cpp", forms["special event name"]["source"],
                      "a key form with no source line is a second invention")
        rejected = [e["spelling"] for e in record["rejected"]]
        self.assertFalse([s for s in rejected if "mouse_up" in s],
                         "the record still lists the wheel spelling as rejected, which "
                         "contradicts key_forms")

    def test_the_two_meanings_of_locked_are_kept_apart(self):
        """Upstream's locked is a flag; this project's locked is a property."""
        for binding in self.bindings:
            if binding["category"] == "Media":
                with self.subTest(id=binding["id"]):
                    self.assertTrue((binding.get("flags") or {}).get("locked"),
                                    "a media key with no locked flag stops working on "
                                    "the lock screen")
                    self.assertFalse(binding["locked"])
        cheatsheet = next(b for b in self.bindings if b["id"] == "overlay.cheatsheet")
        self.assertTrue(cheatsheet["locked"])
        self.assertFalse((cheatsheet.get("flags") or {}).get("locked"))

    def test_the_generator_reports_zero_conflicts_on_the_defaults(self):
        """The acceptance criterion: `iarch-keybinds check` on a fresh map is clean."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "iarch" / "cli" / "iarch_keybinds.py"), "check"],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("0 conflict(s)", result.stdout)
        self.assertIn("0 error(s)", result.stdout)

    def test_no_plain_ctrl_letter_is_bound(self):
        """The key-usage rule, asserted against the shipped record itself."""
        for binding in self.bindings:
            if not is_bound(binding):
                continue
            key = binding["key"]
            with self.subTest(keys=key_string(binding)):
                self.assertFalse(binding["mods"] == ["CTRL"] and len(key) == 1
                                 and key.isalpha(),
                                 "a global Ctrl+letter takes that key from every "
                                 "application; use Ctrl+Alt or Super+Ctrl")


if __name__ == "__main__":
    unittest.main()
