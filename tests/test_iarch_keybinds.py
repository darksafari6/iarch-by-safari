# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The generator's own logic: the render, the merge, and every validation rule.

``tests/test_keybinds_data.py`` asks whether the *shipped* record is sound and
its renderings are current. This file asks whether ``iarch/cli/iarch_keybinds.py``
is correct -- the part that turns a record into Lua and refuses a record that
would render cleanly and then resolve to nothing at run time.

The centrepiece is a golden file. ``tests/fixtures/keybinds.golden.json`` is a
small fixed record with one of every action type the renderer handles, and
``tests/fixtures/keybinds.golden.lua`` is the exact Lua it must produce. Pinning
the bytes rather than re-deriving them is the point: a change to how a command is
quoted, a description escaped, or a workspace rendered shows up as a diff a
person has to accept on purpose, instead of silently reaching a generated file
the session reads. The same fixture is then parsed as Lua and validated, so the
golden output is not just stable but correct.

Everything here runs as a normal user with no compositor, no display and no Lua
toolchain: the render and the rules are pure functions of the record, and the one
check that needs a Lua parser (``luac -p`` in production, ``luaparser`` here)
skips when neither is installed rather than failing a machine for what it has.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import iarch_keybinds as kb  # noqa: E402
from iarch.lib import configstore  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN_RECORD = FIXTURES / "keybinds.golden.json"
GOLDEN_LUA = FIXTURES / "keybinds.golden.lua"


def make_binding(**over: Any) -> Dict[str, Any]:
    """A minimal valid v2 binding, with any field overridden for one rule test."""
    base: Dict[str, Any] = {
        "id": "test.binding",
        "mods": ["SUPER"],
        "key": "T",
        "action": {"type": "exec", "command": ["true"]},
        "description": "A test binding",
        "category": "Test",
        "enabled": True,
        "locked": False,
    }
    base.update(over)
    return base


def severities(problems: List[kb.Problem]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for problem in problems:
        out[problem.severity] = out.get(problem.severity, 0) + 1
    return out


class GoldenRender(unittest.TestCase):
    """The generated Lua is pinned byte-for-byte against a fixed fixture."""

    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(GOLDEN_RECORD.read_text(encoding="utf-8"))
        cls.bindings = cls.record["bindings"]
        cls.lua = kb.render_lua(cls.bindings, kb.ROOT)

    def test_the_render_matches_the_golden_file(self):
        expected = GOLDEN_LUA.read_text(encoding="utf-8")
        self.assertEqual(expected, self.lua,
                         "the generated Lua drifted from tests/fixtures/keybinds.golden.lua; "
                         "if the change is intended, re-render the golden file and read the diff")

    def test_the_golden_record_is_the_shape_the_renderer_expects(self):
        self.assertEqual(2, self.record["version"])
        # One of every action type the renderer handles, so the golden file is a
        # map of the whole rendering surface and not of whichever types happened
        # to be in the record when it was written.
        types = {b["action"]["type"] for b in self.bindings}
        self.assertEqual({"exec", "shell", "dispatch", "lua", "noctalia", "iarch", "none"},
                         types, "the fixture no longer exercises every action type")

    def test_the_golden_record_validates_against_the_v2_schema(self):
        try:
            import jsonschema  # type: ignore
        except ImportError:
            self.skipTest("jsonschema is not installed")
        schema = json.loads((ROOT / "data" / "schemas" / "keybinds.schema.json")
                            .read_text(encoding="utf-8"))
        errors = list(jsonschema.Draft7Validator(schema).iter_errors(self.record))
        self.assertEqual([], [e.message for e in errors],
                         "the golden fixture must be a valid v2 record, or the golden "
                         "Lua is pinned against something the schema would refuse")

    def test_the_render_is_valid_lua(self):
        """``luac -p`` in production; ``luaparser`` where there is no toolchain.

        A generated file that does not parse leaves the registry empty and trips
        the compositor's emergency binds, which is the failure the whole validate
        -then-render order exists to prevent. So the golden output is parsed, not
        just compared.
        """
        try:
            from luaparser import ast as lua_ast  # type: ignore
        except ImportError:
            self.skipTest("no Lua parser available (luac is not installed either)")
        lua_ast.parse(self.lua)  # raises on a syntax error

    def test_the_fixture_validates_clean_apart_from_the_one_carried_wheel_bind(self):
        problems = kb.validate(self.bindings, kb.ROOT)
        counts = severities(problems)
        self.assertEqual(0, counts.get(kb.ERROR, 0), [str(p) for p in problems])
        self.assertEqual(0, counts.get(kb.CONFLICT, 0), [str(p) for p in problems])
        # The single warning is the mouse_down wheel bind, carried from v1 and
        # recorded as unverified rather than silently kept or silently changed.
        self.assertEqual(1, counts.get(kb.WARNING, 0), [str(p) for p in problems])
        self.assertIn("mouse_down", problems[0].message)

    def test_disabled_and_reserved_bindings_render_to_nothing(self):
        reserved = next(b for b in self.bindings if b.get("reserved"))
        self.assertFalse(reserved["enabled"])
        self.assertNotIn(kb.key_string(reserved), self.lua,
                         "a reserved key must not reach the generated file")
        self.assertNotIn("commented", self.lua.lower())

    def test_the_two_meanings_of_locked_reach_the_file_differently(self):
        """Upstream's locked is an hl.bind option; this project's locked is not.

        The media bind carries ``flags.locked`` and must render ``locked = true``
        into its options. The terminal bind carries entry-level ``locked`` (it may
        be rebound but not deleted) and must render no such option, because there
        is no hl.bind option for it -- emitting one would tell the compositor the
        terminal works on the lock screen, which is a different claim.
        """
        media = next(b for b in self.bindings if b["id"] == "media.mute")
        terminal = next(b for b in self.bindings if b["id"] == "app.terminal")
        self.assertTrue((media.get("flags") or {}).get("locked"))
        self.assertTrue(terminal["locked"])
        media_line = next(l for l in self.lua.splitlines() if "XF86AudioMute" in l)
        terminal_line = next(l for l in self.lua.splitlines() if "SUPER + Return" in l)
        self.assertIn("locked = true", media_line)
        self.assertNotIn("locked = true", terminal_line)


class Rendering(unittest.TestCase):
    """The small pure functions the golden file is built from."""

    def test_lua_string_escapes_the_four_characters_that_break_a_lua_string(self):
        self.assertEqual(r'"a\\b"', kb.lua_string("a\\b"))
        self.assertEqual(r'"say \"hi\""', kb.lua_string('say "hi"'))
        self.assertEqual(r'"line\nbreak"', kb.lua_string("line\nbreak"))
        self.assertEqual(r'"carriage\rreturn"', kb.lua_string("carriage\rreturn"))

    def test_lua_string_does_not_escape_a_tab_a_shell_command_may_carry(self):
        # json.dumps would turn a literal tab into \\t and change the command; the
        # renderer escapes by hand precisely so it does not.
        self.assertEqual('"a\tb"', kb.lua_string("a\tb"))

    def test_render_command_quotes_each_argument_for_one_sh_c_string(self):
        # Upstream has no argv exec: the list is joined and every argument quoted,
        # so a path with a space survives and an apostrophe is quoted the POSIX way.
        self.assertEqual("kitty", kb.render_command(["kitty"]))
        self.assertEqual("'a path with spaces'", kb.render_command(["a path with spaces"]))
        self.assertEqual("""'it'"'"'s here'""", kb.render_command(["it's here"]))

    def test_key_string_joins_modifiers_then_the_key(self):
        self.assertEqual("SUPER + SHIFT + P",
                         kb.key_string({"mods": ["SUPER", "SHIFT"], "key": "P"}))
        self.assertEqual("XF86AudioMute", kb.key_string({"mods": [], "key": "XF86AudioMute"}))

    def test_handler_for_returns_none_for_an_action_that_renders_to_no_bind(self):
        self.assertIsNone(kb.handler_for(make_binding(action={"type": "none"})))

    def test_handler_for_maps_a_workspace_number_and_a_workspace_word_differently(self):
        numeric = kb.handler_for(make_binding(
            action={"type": "dispatch", "dispatcher": "hl.dsp.focus", "workspace": "1"}))
        word = kb.handler_for(make_binding(
            action={"type": "dispatch", "dispatcher": "hl.dsp.focus", "workspace": "empty"}))
        self.assertEqual("hl.dsp.focus({ workspace = 1 })", numeric)
        self.assertEqual('hl.dsp.focus({ workspace = "empty" })', word)

    def test_options_for_always_carries_the_description(self):
        options = kb.options_for(make_binding(description="Close window"))
        self.assertIn('description = "Close window"', options)

    def test_options_for_emits_the_mouse_flag(self):
        options = kb.options_for(make_binding(flags={"mouse": True}, description="Drag"))
        self.assertIn("mouse = true", options)


class Validation(unittest.TestCase):
    """The rules that stop a clean-rendering bind resolving to nothing."""

    def validate(self, *bindings: Dict[str, Any], i_know: bool = False) -> List[kb.Problem]:
        return kb.validate(list(bindings), kb.ROOT, i_know=i_know)

    def test_a_plain_ctrl_letter_is_refused(self):
        problems = self.validate(make_binding(id="bad.ctrlc", mods=["CTRL"], key="c"))
        errors = [p for p in problems if p.severity == kb.ERROR]
        self.assertTrue(any("plain Ctrl+C" in p.message for p in errors),
                        [str(p) for p in problems])

    def test_i_know_downgrades_the_plain_ctrl_refusal_to_a_warning(self):
        problems = self.validate(make_binding(id="bad.ctrlc", mods=["CTRL"], key="c"),
                                 i_know=True)
        self.assertEqual(0, len([p for p in problems if p.severity == kb.ERROR]),
                         [str(p) for p in problems])
        self.assertTrue(any("plain Ctrl+C" in p.message and p.severity == kb.WARNING
                            for p in problems))

    def test_ctrl_alt_and_super_ctrl_letters_are_allowed(self):
        for mods in (["CTRL", "ALT"], ["SUPER", "CTRL"]):
            with self.subTest(mods=mods):
                problems = self.validate(make_binding(id="ok", mods=mods, key="c"))
                self.assertEqual(0, len([p for p in problems
                                         if p.severity in (kb.ERROR, kb.CONFLICT)]),
                                 [str(p) for p in problems])

    def test_two_binds_on_one_combination_are_a_conflict(self):
        problems = self.validate(
            make_binding(id="first", mods=["SUPER"], key="T"),
            make_binding(id="second", mods=["SUPER"], key="T"),
        )
        conflicts = [p for p in problems if p.severity == kb.CONFLICT]
        self.assertEqual(1, len(conflicts), [str(p) for p in problems])
        self.assertIn("first", conflicts[0].message)

    def test_the_same_key_under_a_different_modifier_is_not_a_conflict(self):
        problems = self.validate(
            make_binding(id="a", mods=["SUPER"], key="T"),
            make_binding(id="b", mods=["SUPER", "SHIFT"], key="T"),
        )
        self.assertEqual(0, len([p for p in problems if p.severity == kb.CONFLICT]))

    def test_a_key_that_is_not_a_keysym_is_an_error(self):
        problems = self.validate(make_binding(id="bad.key", mods=["SUPER"], key="NotAKeysym"))
        self.assertTrue(any(p.severity == kb.ERROR and "not a keysym" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_full_stop_is_refused_because_the_keysym_is_called_period(self):
        # '.' is not a keysym; the name is 'period'. A wrong name and a key the
        # keyboard cannot produce both answer 'key not found', so the record uses
        # the real name and the validator refuses the punctuation.
        problems = self.validate(make_binding(id="bad.dot", mods=["SUPER"], key="."))
        self.assertTrue(any(p.severity == kb.ERROR for p in problems))
        self.assertEqual(0, len([p for p in self.validate(
            make_binding(id="ok.period", mods=["SUPER"], key="period"))
            if p.severity == kb.ERROR]))

    def test_a_mouse_button_code_and_a_keycode_are_accepted(self):
        for key in ("mouse:272", "code:30", "10"):
            with self.subTest(key=key):
                problems = self.validate(make_binding(id="ok", mods=["SUPER"], key=key))
                self.assertEqual(0, len([p for p in problems
                                         if p.severity in (kb.ERROR, kb.CONFLICT)]),
                                 [str(p) for p in problems])

    def test_an_unknown_modifier_is_an_error(self):
        problems = self.validate(make_binding(id="bad.mod", mods=["HYPER"], key="T"))
        self.assertTrue(any(p.severity == kb.ERROR and "unknown modifier" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_repeated_modifier_is_an_error(self):
        problems = self.validate(make_binding(id="bad.rep", mods=["SUPER", "SUPER"], key="T"))
        self.assertTrue(any(p.severity == kb.ERROR and "repeated" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_binding_with_no_description_is_an_error(self):
        problems = self.validate(make_binding(id="bad.desc", description="   "))
        self.assertTrue(any(p.severity == kb.ERROR and "no description" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_an_exec_action_with_no_argv_is_an_error(self):
        problems = self.validate(make_binding(id="bad.exec", action={"type": "exec", "command": []}))
        self.assertTrue(any(p.severity == kb.ERROR and "no argv" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_dispatcher_outside_the_verified_tree_is_an_error(self):
        problems = self.validate(make_binding(
            id="bad.dsp", action={"type": "dispatch", "dispatcher": "hl.dsp.window.nope"}))
        self.assertTrue(any(p.severity == kb.ERROR and "not in the verified" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_noctalia_verb_outside_the_record_is_an_error(self):
        problems = self.validate(make_binding(
            id="bad.verb", action={"type": "noctalia", "verb": "not-a-verb"}))
        self.assertTrue(any(p.severity == kb.ERROR and "noctalia verb" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_shell_action_with_no_reason_is_an_error(self):
        problems = self.validate(make_binding(
            id="bad.shell", action={"type": "shell", "script": "a | b"}))
        self.assertTrue(any(p.severity == kb.ERROR and "no reason" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_duplicate_id_is_an_error(self):
        problems = self.validate(
            make_binding(id="same", mods=["SUPER"], key="T"),
            make_binding(id="same", mods=["SUPER"], key="Y"),
        )
        self.assertTrue(any(p.severity == kb.ERROR and "appears 2 times" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_disabled_binding_is_not_held_to_the_keysym_check(self):
        # A reserved key renders to nothing, so its key is never resolved; the
        # other two reserved keys are deliberately not keysyms anyone would bind.
        problems = self.validate(make_binding(
            id="reserved", mods=["SUPER", "SHIFT"], key="H", enabled=False,
            action={"type": "none"}, reserved=True))
        self.assertEqual(0, len([p for p in problems if p.severity == kb.ERROR]),
                         [str(p) for p in problems])


class Merge(unittest.TestCase):
    """Defaults plus a person's differences, by id."""

    def setUp(self):
        self.defaults = {"bindings": [
            make_binding(id="app.terminal", mods=["SUPER"], key="Return",
                         description="Terminal", locked=True),
            make_binding(id="app.browser", mods=["SUPER"], key="B", description="Browser"),
        ]}

    def test_a_rebind_carries_only_the_difference_and_keeps_the_rest(self):
        overrides = {"bindings": [{"id": "app.terminal", "mods": ["SUPER", "ALT"], "key": "T"}]}
        merged = {b["id"]: b for b in kb.merge(self.defaults, overrides)}
        terminal = merged["app.terminal"]
        self.assertEqual(["SUPER", "ALT"], terminal["mods"])
        self.assertEqual("T", terminal["key"])
        self.assertEqual("Terminal", terminal["description"], "the description is from the default")
        self.assertTrue(terminal["locked"], "a field the override did not mention survives")

    def test_a_binding_the_defaults_do_not_have_is_appended(self):
        overrides = {"bindings": [{"id": "user.custom", "mods": ["SUPER", "ALT"], "key": "X",
                                   "action": {"type": "exec", "command": ["true"]},
                                   "description": "Mine", "category": "Custom",
                                   "enabled": True, "locked": False}]}
        merged = kb.merge(self.defaults, overrides)
        self.assertEqual(["app.terminal", "app.browser", "user.custom"],
                         [b["id"] for b in merged])

    def test_the_default_order_is_preserved(self):
        merged = kb.merge(self.defaults, {"bindings": [{"id": "app.browser", "key": "W"}]})
        self.assertEqual(["app.terminal", "app.browser"], [b["id"] for b in merged])

    def test_no_override_file_means_the_defaults_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"IARCH_CONFIG_DIR": str(Path(tmp) / "cfg"), "HOME": tmp}
            self.assertEqual({}, kb.user_overrides(env))
            merged = kb.merge(self.defaults, kb.user_overrides(env))
            self.assertEqual([b["id"] for b in self.defaults["bindings"]],
                             [b["id"] for b in merged])

    def test_a_broken_override_file_does_not_break_the_session(self):
        """The recovery behaviour: a stray comma falls back to defaults, not a crash."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "cfg"
            cfg.mkdir(parents=True)
            (cfg / "keybinds.json").write_text("{ this is not json ,,, }", encoding="utf-8")
            env = {"IARCH_CONFIG_DIR": str(cfg), "HOME": tmp}
            self.assertEqual({}, kb.user_overrides(env),
                             "a broken user file must yield empty overrides, not raise")
            merged = kb.merge(self.defaults, kb.user_overrides(env))
            self.assertEqual(2, len(merged), "the session still has its defaults")

    def test_the_override_path_is_keybinds_json_and_not_a_double_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"IARCH_CONFIG_DIR": str(Path(tmp) / "cfg"), "HOME": tmp}
            self.assertEqual("keybinds.json", kb.user_override_path(env).name)


class ShippedRecord(unittest.TestCase):
    """The acceptance criterion: the shipped defaults are clean."""

    @classmethod
    def setUpClass(cls):
        cls.record = kb.default_record(kb.ROOT)
        cls.bindings = kb.merge(cls.record, {})

    def test_check_reports_zero_conflicts_and_zero_errors_on_the_defaults(self):
        problems = kb.validate(self.bindings, kb.ROOT)
        counts = severities(problems)
        self.assertEqual(0, counts.get(kb.CONFLICT, 0), [str(p) for p in problems])
        self.assertEqual(0, counts.get(kb.ERROR, 0), [str(p) for p in problems])

    def test_no_plain_ctrl_letter_is_bound_in_the_defaults(self):
        for binding in self.bindings:
            if not binding.get("enabled"):
                continue
            with self.subTest(id=binding["id"]):
                self.assertFalse(binding["mods"] == ["CTRL"] and len(binding["key"]) == 1
                                 and binding["key"].isalpha())

    def test_the_list_json_feed_carries_what_a_cheat_sheet_needs(self):
        """The overlay reads `list --json`; this pins the shape it will read."""
        payload = [{
            "id": b["id"], "keys": kb.key_string(b), "mods": b.get("mods") or [],
            "key": b["key"], "description": b["description"], "category": b["category"],
            "enabled": b["enabled"], "locked": b["locked"], "action": b["action"],
        } for b in self.bindings]
        self.assertTrue(payload)
        for entry in payload:
            for field in ("id", "keys", "description", "category", "enabled", "action"):
                self.assertIn(field, entry)
        # A cheat sheet groups by category and shows the combination and the description.
        terminal = next(e for e in payload if e["id"] == "applications.terminal")
        self.assertEqual("SUPER + RETURN", terminal["keys"])
        self.assertTrue(terminal["description"])


if __name__ == "__main__":
    unittest.main()
