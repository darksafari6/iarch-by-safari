# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The v1 extract is the evidence that the v2 migration lost nothing.

``tools/migrate_keybinds_v2.py`` runs once and rewrites
``data/keybinds.default.json`` in place, so after it has run there is no v1 file
left in the tree to compare against. The v1 record is still in git history, and
this test carries the two things that matter about it: the count, and the exact
set of key combinations it declared. Those are written down here rather than read
from history so that the test can run in a checkout that has been squashed, and
so that the claim "nothing was lost" is a claim about names and not about a
diff nobody re-reads.

What this file checks is deliberately narrow and deliberately strong: every key
combination v1 declared is still declared, still means the same thing, and the
eight that could not work on the pinned compositor now say what they were
replaced with. It does not check that the new keymap is a good keymap -- that is
what the acceptance tests for the map itself are for.
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

RECORD = ROOT / "data" / "keybinds.default.json"
MIGRATOR = ROOT / "tools" / "migrate_keybinds_v2.py"

#: The v1 extract, kept beside this test on purpose. It is the file the migration
#: consumes, and once the migration has run there is no v1 record anywhere in the
#: tree -- so without this copy the assertions below could only ever be run once,
#: by whoever happened to be holding the file. Keeping it also keeps the evidence:
#: this is what the shipped session actually bound, and the tables further down
#: are generated from it rather than transcribed.
SOURCE_V1 = ROOT / "tests" / "fixtures" / "keybinds.v1.json"

#: Every key combination v1 declared as bound, mapped to the description it
#: carried -- 74 entries. Written out in full rather than derived at run time,
#: because the whole point is that it is a record of what the old file said and
#: not a restatement of what the new one says. It was generated from the v1
#: record rather than transcribed by hand: the first draft of this table was
#: written from memory and 33 of its descriptions were wrong, in exactly the way
#: the test that reads it exists to catch.
V1_EVERY: Dict[str, str] = {
    "super + return": "Terminal",
    "super + e": "File manager",
    "super + c": "Code editor",
    "super + b": "Browser",
    "super + d": "Toggle launcher",
    "super + l": "Lock screen",
    "super + t": "Toggle settings",
    "super + i": "Open Control Center",
    "super + shift + i": "Open Settings",
    "super + shift + n": "Open notification center",
    "super + shift + a": "Open audio controls",
    "super + shift + w": "Open network controls",
    "super + shift + b": "Open Bluetooth controls",
    "super + shift + p": "Open power controls",
    "super + s": "Steam",
    "super + m": "Music player",
    "super + v": "Video player",
    "super + q": "Close window",
    "super + w": "Toggle floating",
    "super + f": "Toggle fullscreen",
    "super + tab": "Next workspace on monitor",
    "super + shift + tab": "Previous workspace on monitor",
    "super + left": "Focus left",
    "super + right": "Focus right",
    "super + up": "Focus up",
    "super + down": "Focus down",
    "alt + tab": "Window switcher overlay",
    "super + shift + right": "Resize window right",
    "super + shift + left": "Resize window left",
    "super + shift + up": "Resize window up",
    "super + shift + down": "Resize window down",
    "super + shift + ctrl + left": "Move or swap window left",
    "super + shift + ctrl + right": "Move or swap window right",
    "super + shift + ctrl + up": "Move or swap window up",
    "super + shift + ctrl + down": "Move or swap window down",
    "super + print": "Screenshot window",
    "alt + print": "Screenshot monitor",
    "shift + print": "Screenshot region",
    "super + a": "Annotate screenshot",
    "super + 1": "Workspace1",
    "super + 2": "Workspace2",
    "super + 3": "Workspace3",
    "super + 4": "Workspace4",
    "super + 5": "Workspace5",
    "super + 6": "Workspace6",
    "super + 7": "Workspace7",
    "super + 8": "Workspace8",
    "super + 9": "Workspace9",
    "super + shift + 1": "Move to workspace1",
    "super + shift + 2": "Move to workspace2",
    "super + shift + 3": "Move to workspace3",
    "super + shift + 4": "Move to workspace4",
    "super + shift + 5": "Move to workspace5",
    "super + shift + 6": "Move to workspace6",
    "super + shift + 7": "Move to workspace7",
    "super + shift + 8": "Move to workspace8",
    "super + shift + 9": "Move to workspace9",
    "super + 0": "Workspace 10",
    "super + shift + 0": "Move to workspace 10",
    "super + ctrl + right": "Next workspace",
    "super + ctrl + left": "Previous workspace",
    "super + ctrl + down": "Open empty workspace",
    "super + ctrl + alt + right": "Move to next workspace",
    "super + ctrl + alt + left": "Move to previous workspace",
    "super + mouse_down": "Scroll to next workspace",
    "super + mouse_up": "Scroll to previous workspace",
    "super + mouse:272": "Drag window",
    "super + mouse:273": "Resize window",
    "super + x": "Resize mode",
    "xf86audioplay": "Play or pause",
    "xf86audionext": "Next track",
    "xf86audioprev": "Previous track",
    "xf86audioraisevolume": "Volume up",
    "xf86audiolowervolume": "Volume down",
}

#: The three keys v1 carried as reserved: declared in the Lua, never bound, and
#: listed so that nothing would reassign one by accident.
V1_RESERVED: Dict[str, str] = {
    "super + h": "Shortcut overlay (Part 7)",
    "super + shift + h": "Refresh the shortcut overlay (Part 7)",
    "super + k": "Hyprland key panel (Part 7)",
}

#: The eight binds that reached for a pre-Lua dispatcher name through
#: `hyprctl dispatch`. On a Lua config that text is evaluated as
#: `hl.dispatch(resizeactive 30 0)`, which is not Lua, so none of the eight could
#: work. The replacements and their argument tables are recorded in
#: data/design/keybinds.json under `rejected`.
BROKEN_IN_V1 = (
    "super + shift + right",
    "super + shift + left",
    "super + shift + up",
    "super + shift + down",
    "super + shift + ctrl + left",
    "super + shift + ctrl + right",
    "super + shift + ctrl + up",
    "super + shift + ctrl + down",
)


class MigrationLosesNothing(unittest.TestCase):
    """Runs the migrator rather than reading its output.

    The migration rewrites ``data/keybinds.default.json`` in place, so a test that
    read that file would pass before the migration and then be testing a record
    that no longer has a v1 shape to be migrated from. Calling ``migrate()`` on
    the v1 record means the same assertions hold either side of the one-way door,
    and it tests the tool instead of trusting its output.
    """

    @classmethod
    def setUpClass(cls):
        import migrate_keybinds_v2 as migrator
        v1 = json.loads(SOURCE_V1.read_text(encoding="utf-8"))
        if v1.get("version") == 1:
            cls.record = migrator.migrate(v1)
        else:
            # Already migrated: the file itself is the v2 record, and the v1 it
            # came from is what the tables at the top of this file stand for.
            cls.record = json.loads(RECORD.read_text(encoding="utf-8"))
        cls.bindings: List[dict] = cls.record["bindings"]
        cls.by_key: Dict[str, dict] = {}
        for entry in cls.bindings:
            key = " + ".join(entry["mods"] + [entry["key"]]).lower()
            if key in cls.by_key:
                raise AssertionError(f"two entries claim the same combination: {key}")
            cls.by_key[key] = entry

    def test_the_record_is_version_two_and_says_where_it_came_from(self):
        self.assertEqual(2, self.record["version"])
        origin = self.record["migrated_from"]
        self.assertEqual(1, origin["version"])
        self.assertEqual(77, origin["bindings"],
                         "v1 declared 74 bound keys and 3 reserved ones")
        self.assertEqual(sorted(BROKEN_IN_V1), sorted(origin["rewritten"]),
                         "the record does not name the binds it rewrote, so a reader "
                         "cannot tell a deliberate change from an accident")

    def test_every_combination_v1_declared_is_still_declared(self):
        missing = sorted(set(V1_EVERY) - set(self.by_key))
        self.assertEqual([], missing,
                         "these keys were bound in the shipped session and the "
                         "migrated record does not declare them")

    def test_the_record_declares_no_combination_v1_never_had(self):
        """Except the one this part exists to add, which is named as an exception.

        A migration that adds bindings is not a migration. SUPER + H was declared
        in the Lua and never bound, and v1 carried it as reserved precisely so
        that nothing would reassign it by accident -- so binding it is a decision
        that has to be written down where the test can see it.
        """
        declared = set(V1_EVERY) | set(V1_RESERVED)
        added = sorted(set(self.by_key) - declared)
        self.assertEqual([], added, "the migration invented a binding")
        self.assertIn("super + h", self.by_key,
                      "SUPER + H is the shortcut overlay and it is still unbound")

    def test_no_description_was_reworded_on_the_way_through(self):
        """A migration that edits prose is a migration nobody can trust.

        Checked for every key v1 bound. The one description that does change is
        SUPER + H, which was reserved prose about a future part and is now the
        name of a real binding, so it is excluded by name rather than by silence.
        """
        reworded = []
        for key, description in V1_EVERY.items():
            actual = self.by_key[key]["description"]
            if actual != description:
                reworded.append((key, description, actual))
        self.assertEqual([], reworded,
                         "these descriptions changed during a migration that was "
                         "supposed to move them")
        self.assertEqual("Shortcut overlay", self.by_key["super + h"]["description"])

    def test_the_three_reserved_keys_are_still_accounted_for(self):
        """One became a binding; the other two must still say they are not bound."""
        cheatsheet = self.by_key["super + h"]
        self.assertTrue(cheatsheet["enabled"])
        self.assertTrue(cheatsheet["locked"],
                        "the overlay is a way back into the keyboard map, so it is "
                        "rebindable but not deletable")
        for key in ("super + shift + h", "super + k"):
            with self.subTest(keys=key):
                entry = self.by_key[key]
                self.assertFalse(entry["enabled"])
                self.assertTrue(entry.get("reserved"))
                self.assertEqual("none", entry["action"]["type"],
                                 "a reserved key declares an action, so it is not "
                                 "reserved in any sense the generator can see")

    def test_the_eight_broken_binds_say_what_replaced_them(self):
        for key in BROKEN_IN_V1:
            entry = self.by_key[key]
            action = entry["action"]
            with self.subTest(keys=key):
                self.assertNotEqual("lua-function", action.get("type"))
                self.assertNotIn("hyprctl dispatch", json.dumps(action),
                                 f"{key} still reaches for a pre-Lua dispatcher name")

    def test_the_four_resize_binds_use_the_verified_relative_form(self):
        """relative defaults to false, so omitting it turns 30 into '30 wide'."""
        expected = {"super + shift + right": (30, 0),
                    "super + shift + left": (-30, 0),
                    "super + shift + up": (0, -30),
                    "super + shift + down": (0, 30)}
        for key, (x, y) in expected.items():
            action = self.by_key[key]["action"]
            with self.subTest(keys=key):
                self.assertEqual("hl.dsp.window.resize", action["dispatcher"])
                self.assertEqual({"x": x, "y": y, "relative": True}, action["args"])

    def test_the_four_move_or_swap_binds_ask_the_compositor_instead_of_jq(self):
        """The old binds ran two external programs to ask a yes-or-no question.

        `hyprctl activewindow -j | jq -r .floating` piped through bash and grepped
        for the string true. hl.get_active_window().floating is a real boolean, so
        the replacement needs neither jq nor bash -- and a keybind that depends on
        a JSON processor is a keybind that breaks when one is not installed.
        """
        for key in ("super + shift + ctrl + left", "super + shift + ctrl + right",
                    "super + shift + ctrl + up", "super + shift + ctrl + down"):
            action = self.by_key[key]["action"]
            with self.subTest(keys=key):
                self.assertEqual("lua", action["type"])
                self.assertIn("hl.get_active_window()", action["lua"])
                self.assertIn("window.floating", action["lua"])
                self.assertNotIn("jq", action["lua"])
                self.assertNotIn("bash", action["lua"])
                self.assertIn("hl.dsp.window.move", action["lua"])
                self.assertIn("hl.dsp.window.swap", action["lua"])
                self.assertTrue(action["why_lua"].strip(),
                                "a bind written as a Lua function body has to say "
                                "why a dispatcher call was not enough")
                self.assertIn("direction", action["lua"],
                              "swap takes a direction word now; the old single "
                              "letters are refused by parseDirectionStr")

    def test_a_command_that_needs_the_shell_is_stored_as_a_string(self):
        """The split exists so a validator knows which commands it cannot check.

        Upstream spawns one string through /bin/sh -c either way, so this is not
        about what the compositor receives. It is about what a person edits and
        what survives the round trip. Three things make a v1 command a shell
        string rather than an argv list, and each one breaks differently if it is
        split and re-quoted:

          * a pipeline -- `grim ... | satty ...` split on whitespace is two
            programs and a literal `|` argument;
          * a tilde -- shlex.quote wraps `~` in single quotes and a tilde in
            single quotes does not expand, so `~/Scripts/x` becomes a file
            literally named `~/Scripts/x`;
          * an environment prefix -- `sh -c "'VAR=v' prog"` does not set VAR, it
            tries to run a program named `VAR=v`.

        All five of the shipped commands that lean on the shell are marked, and
        every one of them says why.
        """
        shells = [entry for entry in self.bindings
                  if entry["action"]["type"] == "shell"]
        self.assertEqual(5, len(shells),
                         "the browser launcher and the four screenshot binds are the "
                         "ones that need the shell; if this count moved, a command was "
                         "reclassified and the reason should be read before accepting it")
        for entry in shells:
            with self.subTest(id=entry["id"]):
                self.assertTrue(entry["action"]["why_shell"].strip(),
                                "a shell action with no reason is an argv list nobody split")
        by_id = {entry["id"]: entry for entry in shells}
        self.assertIn("|", by_id["screenshots.annotate-screenshot"]["action"]["script"])
        self.assertIn("~", by_id["applications.browser"]["action"]["script"])
        self.assertTrue(by_id["screenshots.screenshot"]["action"]["script"]
                        .startswith("HYPRSHOT_DIR="))

    def test_no_exec_action_carries_a_shell_feature_that_quoting_would_break(self):
        """The other half: an argv list must be a plain program and its arguments.

        This is the invariant the five shell entries exist to protect. If any exec
        command still held a tilde, a pipe or an environment prefix, the generator
        would quote it and silently change what runs -- which renders cleanly and
        fails at run time, the exact failure this record is here to prevent.
        """
        import re
        env_prefix = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
        for entry in self.bindings:
            action = entry["action"]
            if action["type"] != "exec":
                continue
            with self.subTest(id=entry["id"]):
                self.assertTrue(action["command"], "an exec action with no argv")
                for token in action["command"]:
                    self.assertNotIn("~", token, f"{entry['id']}: a tilde in an argv "
                                     "token does not survive shlex.quote")
                    for metachar in ("|", "&&", "||", "$(", "`", ";", ">", "<"):
                        self.assertNotIn(metachar, token,
                                         f"{entry['id']}: shell syntax in an argv token")
                self.assertIsNone(env_prefix.match(action["command"][0]),
                                  f"{entry['id']}: an environment prefix in an argv "
                                  "list is a program name, not an assignment")

    def test_the_mouse_binds_kept_their_mouse_flag(self):
        """`mouse` is exclusive upstream, so it cannot ride along with anything."""
        for key in ("super + mouse:272", "super + mouse:273"):
            entry = self.by_key[key]
            with self.subTest(keys=key):
                self.assertTrue((entry.get("flags") or {}).get("mouse"),
                                "a mouse bind with no mouse flag is a keyboard bind "
                                "on a key nobody has")
                self.assertFalse(entry["locked"])

    def test_the_five_media_keys_carry_the_compositors_locked_option(self):
        """Upstream's `locked` is a compositor option, so it lives in `flags`.

        It means the bind still works while the session is locked, which is why
        the media keys carry it: volume on the lock screen is exactly when it is
        most obviously needed. It is not this record's own top-level `locked`.
        """
        media = [entry for entry in self.bindings if entry["category"] == "Media"]
        self.assertEqual(5, len(media))
        for entry in media:
            with self.subTest(id=entry["id"]):
                self.assertTrue((entry.get("flags") or {}).get("locked"),
                                "a media key with no `locked` flag stops working on "
                                "the lock screen")

    def test_the_two_things_called_locked_are_not_the_same_field(self):
        """The confusion the record warns about, pinned so it cannot come back.

        Upstream's `locked` (works on the lock screen) is a compositor option and
        belongs in `flags`. This project's `locked` (rebindable but not deletable)
        is a property of the entry and belongs at the top level. A media key is
        locked in the first sense only; the cheat sheet in the second only. Were
        they one field, deleting the cheat sheet and muting the lock screen would
        be the same decision, and neither the generator nor the settings page
        could tell them apart.
        """
        by_id = {entry["id"]: entry for entry in self.bindings}
        for entry in self.bindings:
            if entry["category"] == "Media":
                with self.subTest(id=entry["id"]):
                    self.assertTrue((entry.get("flags") or {}).get("locked"))
                    self.assertFalse(entry["locked"],
                                     "a media key is marked undeletable, which is the "
                                     "other meaning of locked")
        cheatsheet = by_id["overlay.cheatsheet"]
        self.assertTrue(cheatsheet["locked"], "the overlay must be rebindable-not-deletable")
        self.assertFalse((cheatsheet.get("flags") or {}).get("locked"),
                         "the overlay does not need to work on the lock screen, and "
                         "claiming it does would put it in the compositor's locked set")

    def test_the_wheel_binds_are_carried_across_unchanged_and_are_verified_events(self):
        """`mouse_up` is neither a keysym nor a `mouse:N` code, and it still binds.

        Carried across rather than replaced, because changing a bind that might work
        into one that certainly does not is not an improvement -- and the bet paid off.
        Source settled it after the migration: `CKey::isValidEvent` accepts the four
        wheel names outright (`src/keybinds/Key.cpp:8-10`) and `onAxisEvent` dispatches
        a wheel delta under exactly that name (`src/keybinds/Manager.cpp:312-335`), so
        these binds match on an event and never reach `resolveKeycode`. This test used
        to pin the opposite -- that the record keeps them under `rejected` with a
        TODO(verify) -- and now pins that they are carried intact *and* documented in
        `key_forms`, because a rejection that source disproves has to be deleted rather
        than left beside the correction.
        """
        for key in ("super + mouse_up", "super + mouse_down"):
            entry = self.by_key[key]
            with self.subTest(keys=key):
                self.assertIn("mouse_", entry["key"])
                self.assertTrue(entry["enabled"])
        record = json.loads((ROOT / "data" / "design" / "keybinds.json").read_text(
            encoding="utf-8"))
        rejected = [item for item in record["rejected"] if "mouse_up" in item["spelling"]]
        self.assertEqual([], rejected,
                         "the record still rejects a spelling it also documents as a "
                         "key form that works")
        forms = [f for f in record["key_forms"]["forms"]
                 if f["form"] == "special event name"]
        self.assertEqual(1, len(forms),
                         "the wheel binds are carried across with nothing recording "
                         "why they are allowed to be")
        self.assertIn("mouse_up", forms[0]["meaning"])


class TheMigratorItself(unittest.TestCase):
    """The tool has to refuse to run twice and refuse to guess."""

    def test_it_refuses_a_record_that_is_already_version_two(self):
        """The migration is a one-way door, so it has to notice it has been used.

        Pointed at a temporary copy rather than at the real record: which version
        ``data/keybinds.default.json`` happens to be in is a fact about when the
        migration was run, and a test whose verdict depends on that is a test that
        starts failing on the day somebody does the work it describes.
        """
        import migrate_keybinds_v2 as migrator
        with tempfile.TemporaryDirectory() as tmp:
            already = Path(tmp) / "keybinds.json"
            already.write_text(json.dumps({"version": 2, "bindings": []}),
                               encoding="utf-8")
            original = migrator.SOURCE
            migrator.SOURCE = already
            try:
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    status = migrator.main([])
            finally:
                migrator.SOURCE = original
        self.assertEqual(1, status, "the migration ran a second time")
        self.assertIn("runs once", err.getvalue())

    def test_it_stops_on_a_lua_function_it_has_no_verified_replacement_for(self):
        """Guessing at a dispatcher name is the invention this part exists to stop."""
        sys.path.insert(0, str(ROOT / "tools"))
        import migrate_keybinds_v2 as migrator
        entry = {"keys": "SUPER + SHIFT + F9",
                 "description": "Something",
                 "category": "Planned",
                 "status": "bound",
                 "action": {"kind": "lua-function",
                            "lua": "function() hl.exec_cmd(\"hyprctl dispatch frobnicate\") end"}}
        with self.assertRaises(ValueError) as caught:
            migrator.action_for(entry)
        self.assertIn("no verified replacement", str(caught.exception))

    def test_split_keys_refuses_a_repeated_modifier(self):
        """hl.bind refuses it case-insensitively, so the record must not carry one."""
        sys.path.insert(0, str(ROOT / "tools"))
        import migrate_keybinds_v2 as migrator
        with self.assertRaises(ValueError) as caught:
            migrator.split_keys("SUPER + super + T")
        self.assertIn("repeats a modifier", str(caught.exception))

    def test_split_keys_canonicalises_and_orders(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import migrate_keybinds_v2 as migrator
        self.assertEqual((["SUPER", "CTRL"], "t"), migrator.split_keys("mod4 + control + t"))
        self.assertEqual((["ALT"], "tab"), migrator.split_keys("mod1 + tab"))
        self.assertEqual(([], "XF86AudioPlay"), migrator.split_keys("XF86AudioPlay"))

    def test_split_keys_refuses_a_combination_with_no_key_in_it(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import migrate_keybinds_v2 as migrator
        for bad in ("SUPER + ", "SUPER + SHIFT + left + right"):
            with self.subTest(keys=bad), self.assertRaises(ValueError):
                migrator.split_keys(bad)


if __name__ == "__main__":
    unittest.main()
