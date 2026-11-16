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

import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
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


def list_json() -> List[Dict[str, Any]]:
    """The real ``list --json`` payload, with no override file in the way.

    ``cmd_list`` reads the environment itself, so the override directory is pointed
    at an empty temporary one: a test that merges whatever happens to be in the
    developer's ``~/.config/iarch`` passes on one machine and fails on another.
    """
    with tempfile.TemporaryDirectory() as empty:
        previous = os.environ.get("IARCH_CONFIG_DIR")
        os.environ["IARCH_CONFIG_DIR"] = empty
        try:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = kb.cmd_list(argparse.Namespace(json=True, category=None))
        finally:
            if previous is None:
                os.environ.pop("IARCH_CONFIG_DIR", None)
            else:
                os.environ["IARCH_CONFIG_DIR"] = previous
    if code != 0:
        raise AssertionError(f"list --json exited {code}")
    return json.loads(buffer.getvalue())


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

    def test_the_fixture_validates_completely_clean(self):
        """Every key in the fixture resolves, the wheel event among them.

        ``mouse_down`` used to be the one warning this fixture was allowed to carry,
        on the grounds that it is neither a keysym nor a ``mouse:N`` code and nothing
        had proved it bound. Source settled it: ``CKey::isValidEvent`` accepts the four
        wheel names outright (``src/keybinds/Key.cpp:8-10``) and ``onAxisEvent``
        dispatches a wheel delta under exactly that name
        (``src/keybinds/Manager.cpp:312-335``), so the bind never reaches the resolver.
        It is recorded in ``key_forms`` and the fixture is now expected to be clean --
        a baseline that carries a permanent warning is not a baseline, because the next
        real one hides inside it.
        """
        problems = kb.validate(self.bindings, kb.ROOT)
        counts = severities(problems)
        self.assertEqual(0, counts.get(kb.ERROR, 0), [str(p) for p in problems])
        self.assertEqual(0, counts.get(kb.CONFLICT, 0), [str(p) for p in problems])
        self.assertEqual(0, counts.get(kb.WARNING, 0), [str(p) for p in problems])

    def test_a_wheel_event_binds_and_an_upper_case_spelling_of_it_does_not(self):
        """``isValidEvent`` compares the four names with ``==``, so case is not free
        here in the way it is for a keysym name."""
        self.assertTrue(kb._key_is_valid("mouse_down", set()))
        self.assertTrue(kb._key_is_valid("mouse_left", set()))
        for spelling in ("MOUSE_DOWN", "Mouse_down", "mouse_scroll", "mousewheel"):
            with self.subTest(spelling=spelling):
                self.assertFalse(kb._key_is_valid(spelling, set()),
                                 "an event name the compositor does not dispatch was "
                                 "accepted, so a bind on it would silently do nothing")

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

    def test_super_ctrl_letters_are_allowed(self):
        problems = self.validate(make_binding(id="ok", mods=["SUPER", "CTRL"], key="c"))
        self.assertEqual(0, len([p for p in problems
                                 if p.severity in (kb.ERROR, kb.CONFLICT)]),
                         [str(p) for p in problems])

    def test_ctrl_alt_letters_belong_to_the_system_layer_only(self):
        """Ctrl+Alt used to be offered as the remedy for a plain Ctrl+letter.

        It is not any more: the layer rule reserves it for recovery and system
        actions, so a checker that still suggested it would send the person into
        its own next refusal. Both halves are asserted, because the interesting
        failure is a rule whose remedy the following rule rejects.
        """
        refused = self.validate(make_binding(id="app", mods=["CTRL", "ALT"], key="c"))
        self.assertTrue(any(p.severity == kb.ERROR and "recovery and system layer"
                            in p.message for p in refused),
                        [str(p) for p in refused])

        allowed = self.validate(make_binding(id="sys", mods=["CTRL", "ALT"], key="c",
                                             category="System"))
        self.assertEqual(0, len([p for p in allowed
                                 if p.severity in (kb.ERROR, kb.CONFLICT)]),
                         [str(p) for p in allowed])

    def test_the_plain_ctrl_remedy_is_one_the_checker_would_accept(self):
        """The message must not recommend a layer the layer rule then refuses."""
        problems = self.validate(make_binding(id="bad.ctrlc", mods=["CTRL"], key="c"))
        message = next(p.message for p in problems if "plain Ctrl+C" in p.message)
        self.assertNotIn("Ctrl+Alt", message,
                         "the refusal recommends Ctrl+Alt, which the layer rule "
                         "reserves for recovery -- a remedy this checker rejects")
        for offered, mods in (("Super+Ctrl", ["SUPER", "CTRL"]),
                              ("Super+Shift", ["SUPER", "SHIFT"])):
            self.assertIn(offered, message)
            follow_up = self.validate(make_binding(id="remedy", mods=mods, key="c"))
            self.assertEqual(0, len([p for p in follow_up
                                     if p.severity in (kb.ERROR, kb.CONFLICT)]),
                             f"{offered}+C is recommended and then refused: "
                             f"{[str(p) for p in follow_up]}")

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

    def test_a_locked_binding_cannot_be_disabled(self):
        """``locked`` means rebindable but not deletable, and turning one off is how an
        override would delete it -- so this is an error, not a warning, and it is
        reported even though a disabled binding skips every other key check."""
        problems = self.validate(make_binding(
            id="applications.terminal", mods=["SUPER"], key="RETURN",
            enabled=False, locked=True, locked_reason="a shell"))
        errors = [p for p in problems if p.severity == kb.ERROR]
        self.assertEqual(1, len(errors), [str(p) for p in problems])
        self.assertIn("locked and disabled", errors[0].message)

    def test_a_locked_binding_that_is_enabled_is_fine(self):
        problems = self.validate(make_binding(
            id="applications.terminal", mods=["SUPER"], key="RETURN",
            enabled=True, locked=True))
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
        """The overlay reads `list --json`; this pins the shape it will read.

        Taken from the real command rather than rebuilt here, because a hand-copy of
        the payload is a second opinion that drifts the first time a field is added --
        and the overlay is exactly the consumer that would then render blanks.
        """
        payload = list_json()
        self.assertTrue(payload)
        for entry in payload:
            for field in ("id", "keys", "description", "category", "enabled", "action",
                          "locked", "static", "reserved"):
                self.assertIn(field, entry)
        # A cheat sheet groups by category and shows the combination and the description.
        terminal = next(e for e in payload if e["id"] == "applications.terminal")
        self.assertEqual("SUPER + RETURN", terminal["keys"])
        self.assertTrue(terminal["description"])

    def test_the_json_feed_marks_the_static_and_reserved_bindings(self):
        """The overlay has to tell a hand-written bind from a rendered one.

        A cheat sheet that lists Ctrl+Alt+R as an ordinary bind is not wrong about
        the key, but it cannot say that the bind lives in a different file and calls
        a command the installer has not shipped yet -- which is the part a person
        troubleshooting a dead shortcut needs.
        """
        payload = {e["id"]: e for e in list_json()}
        recovery = payload["recovery.reapply-defaults"]
        self.assertTrue(recovery["static"])
        self.assertTrue(recovery["enabled"])
        self.assertFalse(payload["reserved.ctrl-alt-backspace"]["enabled"])
        self.assertTrue(payload["reserved.ctrl-alt-backspace"]["reserved"])
        self.assertFalse(payload["applications.terminal"]["static"])


class ConfirmationRule(unittest.TestCase):
    """Nothing that ends a session or the machine goes on a key without a menu.

    A key that logs out is a key that logs out by accident: a mistyped combination,
    a child, a cat. The rule is not "never bind these" but "bind the confirmation",
    and the shell already draws one, so both halves are asserted -- the refusal and
    the thing that is allowed instead.
    """

    def errors(self, action: Dict[str, Any]) -> List[kb.Problem]:
        problems = kb.validate(
            [make_binding(id="destructive", mods=["SUPER", "SHIFT"], key="E",
                          action=action)], kb.ROOT)
        return [p for p in problems if p.severity == kb.ERROR]

    def test_the_compositor_exit_dispatcher_is_refused(self):
        errors = self.errors({"type": "dispatch", "dispatcher": "exit"})
        self.assertTrue(any("hl.dsp.exit" in p.message for p in errors),
                        [str(p) for p in errors])

    def test_every_spelling_of_a_destructive_session_action_is_refused(self):
        """The same mistake is reachable three ways, so all three are covered."""
        for action in (
            {"type": "noctalia", "verb": "session", "args": ["logout"]},
            {"type": "noctalia", "verb": "session", "args": ["shutdown"]},
            {"type": "noctalia", "verb": "session", "args": ["reboot"]},
            {"type": "exec", "command": ["noctalia", "msg", "session", "logout"]},
            {"type": "exec", "command": ["systemctl", "poweroff", "-i"]},
            {"type": "exec", "command": ["loginctl", "terminate-session"]},
            {"type": "exec", "command": ["hyprctl", "dispatch", "exit"]},
            {"type": "exec", "command": ["/usr/bin/reboot"]},
        ):
            with self.subTest(action=action):
                errors = self.errors(action)
                self.assertTrue(any("the moment the key goes down" in p.message
                                    for p in errors),
                                f"not refused: {[str(p) for p in errors]}")

    def test_the_session_menu_is_allowed_because_the_menu_is_the_confirmation(self):
        for action in (
            {"type": "noctalia", "verb": "panel-toggle", "args": ["session"]},
            {"type": "exec", "command": ["noctalia", "msg", "panel-toggle", "session"]},
        ):
            with self.subTest(action=action):
                self.assertEqual([], [str(p) for p in self.errors(action)],
                                 "the menu that asks before ending a session was "
                                 "refused by the rule that exists to make people use it")

    def test_lock_and_suspend_are_not_treated_as_destructive(self):
        """Both are undoable: logging back in, or waking the machine."""
        for action in (
            {"type": "exec", "command": ["noctalia", "msg", "session", "lock"]},
            {"type": "noctalia", "verb": "session", "args": ["suspend"]},
            {"type": "noctalia", "verb": "session", "args": ["lock-and-suspend"]},
        ):
            with self.subTest(action=action):
                self.assertEqual([], [str(p) for p in self.errors(action)])

    def test_the_shipped_record_binds_the_menu_and_not_the_action(self):
        bindings = kb.default_record(kb.ROOT)["bindings"]
        exit_entry = next(b for b in bindings if b["id"] == "session.exit-menu")
        self.assertEqual([], [str(p) for p in self.errors(exit_entry["action"])])
        self.assertEqual(["session"], exit_entry["action"].get("args"),
                         "Super+Shift+E must open the shell's own session panel, which "
                         "is a builtin panel id in noctalia v5.4.1 "
                         "(src/launcher/panel_catalog.cpp), rather than run logout")


class LayerRule(unittest.TestCase):
    """The modifier layers, kept for what each one is for."""

    def problems(self, **over: Any) -> List[kb.Problem]:
        return kb.validate([make_binding(id="layer", key="c", **over)], kb.ROOT)

    def test_super_alt_is_empty_on_purpose(self):
        problems = self.problems(mods=["SUPER", "ALT"], category="Test")
        self.assertTrue(any(p.severity == kb.ERROR and "kept empty on purpose"
                            in p.message for p in problems),
                        [str(p) for p in problems])

    def test_bare_ctrl_alt_outside_the_system_layer_is_an_error(self):
        """An error, not a warning: the recovery combo lives on this exact layer."""
        problems = self.problems(mods=["CTRL", "ALT"], category="Applications")
        self.assertTrue(any(p.severity == kb.ERROR and "safety net" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_bare_ctrl_alt_inside_the_system_layer_is_clean(self):
        problems = self.problems(mods=["CTRL", "ALT"], category="System")
        self.assertEqual(0, len([p for p in problems
                                 if p.severity in (kb.ERROR, kb.CONFLICT)]),
                         [str(p) for p in problems])

    def test_super_ctrl_alt_outside_the_system_layer_is_reported(self):
        """A warning, and the message names the layer to use instead.

        Not an error, because a bind in this layer still works: reporting it is not the
        same thing as refusing it. The shipped map has nothing here any more -- the two
        workspace moves the v1 map carried into it moved to Super+Ctrl+N and
        Super+Ctrl+P -- so what this rule guards now is the next bind that reaches for
        the recovery layer, and the remedy it prints has to be one the checker accepts.
        """
        problems = self.problems(mods=["SUPER", "CTRL", "ALT"],
                                 category="Move Window Across Workspaces")
        matching = [p for p in problems if "Super+Ctrl+Alt" in p.message]
        self.assertEqual(1, len(matching), [str(p) for p in problems])
        self.assertEqual(kb.WARNING, matching[0].severity)
        self.assertIn("Super+Ctrl+N", matching[0].message,
                      "the warning has to say where the two moves went, or the next "
                      "person to see it has to go and read the record to find out")

    def test_the_shipped_map_is_clean_now_that_the_layer_debt_is_settled(self):
        """Nothing at all: no error, no conflict and no warning.

        This test used to pin the debt -- two warnings, named, printed on every run --
        because the two workspace moves the v1 map carried into ``Super+Ctrl+Alt`` both
        worked and every sensible destination key was taken. Allocating all 78 letter
        cells found the destination: ``Super+Ctrl+N`` and ``Super+Ctrl+P``, the layer the
        checker itself offers when it refuses a plain ``Ctrl+letter`` and the layer that
        already owns workspace navigation on the arrows. So the assertion is now that the
        shipped map is silent, and a warning from it means something moved back into the
        recovery layer rather than that a known exception is still being printed.
        """
        bindings = kb.merge(kb.default_record(kb.ROOT), {})
        self.assertEqual([], [str(p) for p in kb.validate(bindings, kb.ROOT)],
                         "the shipped map reports a problem; the layer debt it used to "
                         "carry was settled by moving the two workspace moves")

        moves = {b["id"]: b for b in bindings if b["id"] in ("move.next", "move.previous")}
        self.assertEqual({"move.next": "N", "move.previous": "P"},
                         {name: b["key"] for name, b in moves.items()})
        for name, binding in sorted(moves.items()):
            with self.subTest(binding=name):
                self.assertEqual(["SUPER", "CTRL"], binding["mods"])
                self.assertEqual("SUPER + CTRL + ALT + " + ("right" if name.endswith("next")
                                                            else "left"),
                                 binding.get("relocated_from"),
                                 "the row has to say where it came from: the person whose "
                                 "hands still reach for the old combination is the one who "
                                 "needs it written down")
        self.assertEqual([], [b["id"] for b in bindings
                              if b.get("mods") == ["SUPER", "CTRL", "ALT"]],
                         "the recovery layer is empty again")

    def test_the_primary_and_secondary_layers_are_ungoverned(self):
        for mods in (["SUPER"], ["SUPER", "SHIFT"], ["SUPER", "CTRL"]):
            with self.subTest(mods=mods):
                problems = self.problems(mods=mods, category="Applications")
                self.assertEqual(0, len([p for p in problems
                                         if p.severity in (kb.ERROR, kb.CONFLICT)]),
                                 [str(p) for p in problems])


class StaticBindings(unittest.TestCase):
    """A bind described in the record and implemented by hand in keybind.lua."""

    def temp_root(self, hand_written: str) -> Path:
        """A root with the files render_lua and the cross-check read."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".config" / "hypr").mkdir(parents=True)
        (tmp / "data" / "design").mkdir(parents=True)
        (tmp / ".config" / "hypr" / "keybind.lua").write_text(hand_written,
                                                              encoding="utf-8")
        (tmp / "data" / "design" / "keybinds.json").write_bytes(
            (kb.ROOT / "data" / "design" / "keybinds.json").read_bytes())
        return tmp

    def binding(self, **over: Any) -> Dict[str, Any]:
        base = make_binding(id="recovery.test", mods=["CTRL", "ALT"], key="R",
                            category="System", static=True,
                            action={"type": "exec",
                                    "command": ["iarch-keybinds", "reset", "--all"]},
                            unverified="Carried as unverified by the test that reads it.")
        base.update(over)
        return base

    def test_the_render_skips_a_static_binding(self):
        rendered = kb.render_lua([self.binding()], kb.ROOT, "test")
        self.assertNotIn('hl.bind("CTRL + ALT + R"', rendered,
                         "a static binding the render also emits is two handlers on "
                         "one key, and which runs depends on require() order")

    def test_the_shipped_record_and_the_static_file_agree(self):
        bindings = kb.merge(kb.default_record(kb.ROOT), {})
        self.assertEqual([], [str(p) for p in kb.static_bindings_agree(bindings, kb.ROOT)])

    def test_a_static_binding_missing_from_the_file_is_an_error(self):
        root = self.temp_root("-- nothing hand-written here\nreturn true\n")
        problems = kb.static_bindings_agree([self.binding()], root)
        self.assertTrue(any(p.severity == kb.ERROR and "has no hl.bind" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_static_binding_running_a_different_command_is_an_error(self):
        """The drift that matters: both files valid, disagreeing about the key."""
        root = self.temp_root('hl.bind("CTRL + ALT + R", function() end)\nreturn true\n')
        problems = kb.static_bindings_agree([self.binding()], root)
        self.assertTrue(any(p.severity == kb.ERROR and "disagree" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_missing_static_file_is_an_error_not_a_silence(self):
        root = self.temp_root("return true\n")
        (root / ".config" / "hypr" / "keybind.lua").unlink()
        problems = kb.static_bindings_agree([self.binding()], root)
        self.assertTrue(any(p.severity == kb.ERROR and "is missing" in p.message
                            for p in problems), [str(p) for p in problems])

    def test_a_non_static_binding_is_not_held_to_the_static_file(self):
        root = self.temp_root("return true\n")
        plain = self.binding(static=False, unverified=None)
        plain.pop("unverified")
        self.assertEqual([], [str(p) for p in kb.static_bindings_agree([plain], root)])


class IsolatedHome(unittest.TestCase):
    """A temporary HOME, so a mutating command is tested against a real file layout.

    These commands write two files and back up a third, which is not something a
    mock can prove: the interesting failures are a backup that was not kept, a
    session file written to the repository instead, and a refusal that changed
    something anyway.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        (self.home / ".config" / "iarch").mkdir(parents=True)
        self.override = self.home / ".config" / "iarch" / "keybinds.json"
        self.session_lua = self.home / ".config" / "hypr" / "generated" / "keybinds.lua"
        self.backups = self.home / ".local" / "state" / "iarch" / "backups"
        self._saved = {k: os.environ.get(k) for k in ("HOME", "IARCH_CONFIG_DIR")}

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def write_override(self, payload: Dict[str, Any]) -> None:
        self.override.write_text(json.dumps(payload), encoding="utf-8")

    def run_cli(self, *argv: str) -> int:
        os.environ["HOME"] = str(self.home)
        os.environ.pop("IARCH_CONFIG_DIR", None)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            try:
                code = kb.main(list(argv))
            except SystemExit as exc:
                # argparse's own refusal for a missing or contradictory flag,
                # which is a real outcome of bad input and exits 2 like a UserError.
                code = exc.code if isinstance(exc.code, int) else 2
        self.output = buffer.getvalue()
        return code

    def saved_entries(self):
        """The ids in the override file, or None when there is no override file."""
        if not self.override.is_file():
            return None
        document = json.loads(self.override.read_text(encoding="utf-8"))
        return [e["id"] for e in document["bindings"]]

    def answer(self, reply: str, *, is_tty: bool = True):
        """Make the confirmation prompt readable, as though a person were there."""
        fake = unittest.mock.Mock()
        fake.isatty.return_value = is_tty
        fake.readline.return_value = reply
        return unittest.mock.patch.object(kb.sys, "stdin", fake)


class Reset(IsolatedHome):
    """`reset` is what the recovery combo runs, so it is tested as a command."""

    def test_reset_all_drops_the_override_and_keeps_a_backup(self):
        self.write_override({"bindings": [{"id": "window.close", "key": "Y",
                                           "description": "mine"}]})
        self.assertEqual(0, self.run_cli("reset", "--all", "--yes"))
        self.assertFalse(self.override.exists(), "the override survived a reset --all")
        self.assertTrue(self.session_lua.is_file(), "no session file was written")
        self.assertIn('hl.bind("SUPER + Q"', self.session_lua.read_text(encoding="utf-8"),
                      "the shipped default for close-window did not come back")
        self.assertEqual(1, len(list(self.backups.glob("*keybinds.json*.bak"))),
                         "the person's map was deleted with no way back")

    def test_reset_writes_the_session_copy_and_not_the_repository_artifact(self):
        """The file the compositor reads is a copy, so fixing the repo fixes nothing."""
        self.write_override({"bindings": [{"id": "window.close", "key": "Y",
                                           "description": "mine"}]})
        before = kb.GENERATED.read_bytes()
        self.assertEqual(0, self.run_cli("reset", "--all", "--yes"))
        self.assertEqual(before, kb.GENERATED.read_bytes(),
                         "reset rewrote the checked-in artifact CI keeps fresh")
        self.assertTrue(self.session_lua.is_file())

    def test_reset_by_id_leaves_the_other_differences_alone(self):
        self.write_override({"bindings": [
            {"id": "window.close", "key": "Y", "description": "mine"},
            {"id": "applications.terminal", "key": "Return", "mods": ["SUPER", "CTRL"],
             "description": "also mine"},
        ]})
        self.assertEqual(0, self.run_cli("reset", "window.close"))
        kept = [e["id"] for e in json.loads(self.override.read_text(encoding="utf-8"))["bindings"]]
        self.assertEqual(["applications.terminal"], kept,
                         "a targeted reset must drop exactly the named difference")

    def test_an_id_the_shipped_map_does_not_have_is_refused(self):
        self.write_override({"bindings": [{"id": "window.close", "key": "Y",
                                           "description": "mine"}]})
        self.assertEqual(2, self.run_cli("reset", "not.a.binding"))
        self.assertTrue(self.override.exists(),
                        "an unknown id changed the person's map")

    def test_reset_with_no_target_says_what_it_needs(self):
        self.assertEqual(2, self.run_cli("reset", ))
        self.assertIn("--all", self.output)

    def test_a_reset_that_would_not_validate_changes_nothing(self):
        """The safety is the ordering: refuse before touching, not undo after."""
        self.write_override({"bindings": [{"id": "window.close", "key": "Y",
                                           "description": "mine"}]})
        with unittest.mock.patch.object(kb, "default_record",
                                        return_value=self.broken_record()) as patched:
            self.assertEqual(1, self.run_cli("reset", "--all"))
            self.assertTrue(patched.called)
        self.assertTrue(self.override.exists(),
                        "the override was dropped even though the reset was refused")
        self.assertIn("nothing was changed", self.output)
        self.assertFalse(self.session_lua.exists(),
                         "a refused reset still wrote a session file")

    @staticmethod
    def broken_record() -> Dict[str, Any]:
        record = kb.default_record(kb.ROOT)
        record["bindings"][0]["key"] = "NotAKeysym"
        return record


class Confirmation(IsolatedHome):
    """Destructive means "discards more than you named", and only that asks.

    ``reset --all`` drops everything; a targeted reset drops what was named and
    keeps a backup, which is what makes it reversible without a prompt. The
    interesting failures are a prompt with nobody to answer it being treated as a
    yes, and a cancellation that changed something anyway.
    """

    def save_one(self):
        self.write_override({"bindings": [{"id": "window.close", "key": "Y",
                                           "description": "mine"}]})

    def test_reset_all_refuses_when_there_is_nobody_to_ask(self):
        self.save_one()
        self.assertEqual(2, self.run_cli("reset", "--all"))
        self.assertTrue(self.override.exists(),
                        "a refusal with no answer available still dropped the override")
        self.assertIn("--yes", self.output)
        self.assertIn("not a terminal", self.output)

    def test_reset_all_is_cancelled_by_no(self):
        self.save_one()
        with self.answer("n\n"):
            self.assertEqual(1, self.run_cli("reset", "--all"))
        self.assertTrue(self.override.exists(), "a cancelled reset changed the file")
        self.assertIn("cancelled", self.output)
        self.assertFalse(self.session_lua.exists(),
                         "a cancelled reset wrote a session file")

    def test_reset_all_proceeds_on_yes_at_a_prompt(self):
        self.save_one()
        with self.answer("y\n"):
            self.assertEqual(0, self.run_cli("reset", "--all"))
        self.assertFalse(self.override.exists())
        self.assertTrue(self.session_lua.is_file())

    def test_anything_that_is_not_yes_is_no(self):
        """The default of [y/N] has to be the one that keeps the person's map."""
        for reply in ("", "\n", "maybe\n", "YESSS\n", "sure\n"):
            with self.subTest(reply=reply):
                self.save_one()
                with self.answer(reply):
                    self.assertEqual(1, self.run_cli("reset", "--all"))
                self.assertTrue(self.override.exists())

    def test_a_targeted_reset_does_not_ask(self):
        self.save_one()
        self.assertEqual(0, self.run_cli("reset", "window.close"))
        self.assertIsNone(self.saved_entries(),
                          "the only difference was the one named, so the file goes")

    def test_reset_all_with_nothing_saved_does_not_ask(self):
        """Asking to confirm discarding nothing is a prompt that teaches people --yes."""
        self.assertEqual(0, self.run_cli("reset", "--all"))
        self.assertIn("dropped every difference", self.output)


class Mutating(IsolatedHome):
    """`set`, `add`, `disable`, `enable`, `export` and `import`."""

    def session_binds(self):
        return self.session_lua.read_text(encoding="utf-8")

    # ------------------------------------------------------------------ set

    def test_set_changes_one_field_and_keeps_the_rest_from_the_default(self):
        self.assertEqual(0, self.run_cli("set", "applications.terminal",
                                         "--mods", "SUPER,SHIFT", "--key", "T"))
        entry = json.loads(self.override.read_text(encoding="utf-8"))["bindings"][0]
        self.assertEqual({"id": "applications.terminal", "mods": ["SUPER", "SHIFT"],
                          "key": "T"}, entry,
                         "a difference that restates the action stops a later update "
                         "to that action from ever reaching this machine")
        self.assertIn('hl.bind("SUPER + SHIFT + T"', self.session_binds())
        self.assertNotIn('hl.bind("SUPER + RETURN"', self.session_binds())

    def test_the_modifiers_are_canonicalised_into_the_order_the_record_uses(self):
        self.assertEqual(0, self.run_cli("set", "applications.terminal",
                                         "--mods", "shift+ctrl+super", "--key", "T"))
        entry = json.loads(self.override.read_text(encoding="utf-8"))["bindings"][0]
        self.assertEqual(["SUPER", "SHIFT", "CTRL"], entry["mods"])

    def test_two_sets_on_one_binding_accumulate(self):
        self.assertEqual(0, self.run_cli("set", "applications.terminal", "--key", "G"))
        self.assertEqual(0, self.run_cli("set", "applications.terminal",
                                         "--description", "A shell"))
        entry = json.loads(self.override.read_text(encoding="utf-8"))["bindings"][0]
        self.assertEqual("G", entry["key"], "the second set dropped the first")
        self.assertEqual("A shell", entry["description"])

    def test_set_preserves_a_difference_on_another_binding(self):
        self.write_override({"bindings": [{"id": "window.close", "key": "Y",
                                           "description": "mine"}]})
        self.assertEqual(0, self.run_cli("set", "applications.terminal", "--key", "G"))
        self.assertEqual(["window.close", "applications.terminal"], self.saved_entries())

    def test_set_refuses_an_id_that_does_not_ship(self):
        self.assertEqual(2, self.run_cli("set", "not.a.binding", "--key", "T"))
        self.assertIn("`add`", self.output)
        self.assertFalse(self.override.exists(), "a refusal wrote a file")

    def test_set_refuses_a_key_that_is_not_a_keysym_and_says_what_to_use(self):
        self.assertEqual(2, self.run_cli("set", "applications.terminal", "--key", "."))
        self.assertIn("period", self.output)
        self.assertFalse(self.override.exists())

    def test_a_key_in_the_wrong_case_is_snapped_to_the_pinned_spelling(self):
        """The compositor resolves key names case-insensitively, so one key must not
        end up written two ways in the same map."""
        for typed, pinned in (("Backspace", "BackSpace"), ("RETURN", "Return"),
                              ("escape", "Escape")):
            with self.subTest(typed=typed):
                self.assertEqual(0, self.run_cli("set", "applications.terminal",
                                                 "--key", typed))
                entry = json.loads(
                    self.override.read_text(encoding="utf-8"))["bindings"][0]
                self.assertEqual(pinned, entry["key"])
                self.override.unlink()

    def test_a_key_already_in_the_pinned_list_is_kept_exactly(self):
        """Both cases of a letter are keysyms in their own right, so neither is
        canonicalised away -- only a spelling the list does not contain is snapped."""
        for typed in ("G", "g"):
            with self.subTest(typed=typed):
                self.assertEqual(0, self.run_cli("set", "applications.terminal",
                                                 "--key", typed))
                entry = json.loads(
                    self.override.read_text(encoding="utf-8"))["bindings"][0]
                self.assertEqual(typed, entry["key"])

    def test_two_spellings_of_one_key_are_a_conflict_not_two_binds(self):
        """The hole an exact comparison leaves: the compositor folds case, so these
        are one key with two handlers on it."""
        problems = kb.validate([
            make_binding(id="first", mods=["SUPER"], key="Left"),
            make_binding(id="second", mods=["SUPER"], key="left"),
        ], kb.ROOT)
        conflicts = [p for p in problems if p.severity == kb.CONFLICT]
        self.assertEqual(1, len(conflicts), [str(p) for p in problems])
        self.assertIn("case-insensitively", conflicts[0].message)

    def test_set_refuses_a_modifier_the_compositor_does_not_have(self):
        self.assertEqual(2, self.run_cli("set", "applications.terminal",
                                         "--mods", "HYPER", "--key", "T"))
        self.assertIn("SUPER", self.output)

    def test_set_refuses_a_repeated_modifier(self):
        self.assertEqual(2, self.run_cli("set", "applications.terminal",
                                         "--mods", "SUPER,SUPER", "--key", "T"))
        self.assertIn("repeated", self.output)

    def test_set_with_nothing_to_change_is_refused_rather_than_a_no_op_write(self):
        self.assertEqual(2, self.run_cli("set", "applications.terminal"))
        self.assertIn("nothing to change", self.output)
        self.assertFalse(self.override.exists())

    def test_set_refuses_a_key_another_binding_already_has(self):
        """The collision check, reached through the command a person actually runs."""
        self.assertEqual(1, self.run_cli("set", "applications.terminal",
                                         "--mods", "SUPER", "--key", "E"))
        self.assertIn("already bound by", self.output)
        self.assertIn("nothing was changed", self.output)
        self.assertFalse(self.override.exists(),
                         "a refused set left a difference behind")

    def test_set_cannot_disable_a_locked_safety_net_binding(self):
        self.assertEqual(2, self.run_cli("set", "window.close", "--disable"))
        self.assertIn("locked", self.output)
        self.assertFalse(self.override.exists())

    def test_set_can_rebind_a_locked_safety_net_binding(self):
        """Locked means rebindable but not deletable, so this has to work."""
        self.assertEqual(0, self.run_cli("set", "window.close", "--key", "BackSpace"))
        self.assertIn('hl.bind("SUPER + BackSpace"', self.session_binds())

    # ------------------------------------------------------------------ add

    def test_add_creates_a_binding_of_your_own(self):
        self.assertEqual(0, self.run_cli(
            "add", "custom.scratchpad", "--mods", "SUPER,SHIFT", "--key", "T",
            "--description", "Dropdown terminal", "--category", "Custom",
            "--exec", "kitty --class scratch"))
        entry = json.loads(self.override.read_text(encoding="utf-8"))["bindings"][0]
        self.assertEqual("custom.scratchpad", entry["id"])
        self.assertEqual({"type": "exec", "command": ["kitty", "--class", "scratch"]},
                         entry["action"])
        self.assertIn('hl.bind("SUPER + SHIFT + T"', self.session_binds())

    def test_add_accepts_a_dispatch_and_a_noctalia_verb(self):
        self.assertEqual(0, self.run_cli(
            "add", "custom.close", "--mods", "SUPER", "--key", "BackSpace",
            "--description", "Close", "--category", "Custom",
            "--dispatch", "window.close"))
        self.assertEqual(0, self.run_cli(
            "add", "custom.panel", "--mods", "SUPER", "--key", "F14",
            "--description", "Panel", "--category", "Custom",
            "--noctalia", "panel-toggle", "--noctalia-arg", "launcher"))
        lua = self.session_binds()
        self.assertIn("hl.dsp.window.close()", lua)
        self.assertIn("noctalia msg panel-toggle launcher", lua)

    def test_add_refuses_an_id_the_shipped_map_already_has(self):
        self.assertEqual(2, self.run_cli(
            "add", "window.close", "--mods", "SUPER", "--key", "F13",
            "--description", "x", "--category", "Custom", "--exec", "true"))
        self.assertIn("`set`", self.output)

    def test_add_refuses_an_id_that_is_not_category_dot_subject(self):
        for bad in ("My Binding", "custom", "Custom.Thing", "custom..thing"):
            with self.subTest(id=bad):
                self.assertEqual(2, self.run_cli(
                    "add", bad, "--mods", "SUPER", "--key", "F13",
                    "--description", "x", "--category", "Custom", "--exec", "true"))

    def test_add_refuses_two_actions_and_no_action(self):
        with self.subTest(which="two"):
            self.assertEqual(2, self.run_cli(
                "add", "custom.x", "--mods", "SUPER", "--key", "F13",
                "--description", "x", "--category", "Custom",
                "--exec", "true", "--dispatch", "window.close"))
        with self.subTest(which="none"):
            self.assertEqual(2, self.run_cli(
                "add", "custom.x", "--mods", "SUPER", "--key", "F13",
                "--description", "x", "--category", "Custom"))
        self.assertFalse(self.override.exists())

    def test_add_refuses_a_dispatcher_outside_the_verified_tree(self):
        """Refused at parse time with a suggestion, not at validation with a verdict."""
        self.assertEqual(2, self.run_cli(
            "add", "custom.x", "--mods", "SUPER", "--key", "F13",
            "--description", "x", "--category", "Custom",
            "--dispatch", "window.explode"))
        self.assertIn("not in the verified", self.output)
        self.assertFalse(self.override.exists(),
                         "an action the compositor cannot resolve was written anyway")

    def test_a_dispatcher_leaf_is_expanded_to_the_path_the_record_stores(self):
        self.assertEqual("hl.dsp.window.close", kb.parse_dispatcher("window.close"))
        self.assertEqual("hl.dsp.window.close",
                         kb.parse_dispatcher("hl.dsp.window.close"))

    def test_a_dispatcher_refusal_names_a_real_alternative(self):
        with self.assertRaises(kb.UserError) as caught:
            kb.parse_dispatcher("window.fullscreen_toggle")
        self.assertIn("hl.dsp.window.fullscreen", str(caught.exception),
                      "a refusal that does not name something real leaves the person "
                      "guessing at the vocabulary")

    def test_add_refuses_a_blank_description_or_category(self):
        for flag, other in (("--description", ["--category", "Custom"]),
                            ("--category", ["--description", "x"])):
            with self.subTest(flag=flag):
                self.assertEqual(2, self.run_cli(
                    "add", "custom.x", "--mods", "SUPER", "--key", "F13",
                    flag, "   ", *other, "--exec", "true"))
                self.assertIn(flag.lstrip("-"), self.output)
                self.assertFalse(self.override.exists())

    # ------------------------------------------------------- disable / enable

    def test_disable_turns_a_binding_off_and_enable_turns_it_back_on(self):
        self.assertEqual(0, self.run_cli("disable", "applications.code-editor"))
        self.assertNotIn('hl.bind("SUPER + C"', self.session_binds())
        self.assertEqual([{"id": "applications.code-editor", "enabled": False}],
                         json.loads(self.override.read_text(encoding="utf-8"))["bindings"])
        self.assertEqual(0, self.run_cli("enable", "applications.code-editor"))
        self.assertIn('hl.bind("SUPER + C"', self.session_binds())

    def test_disable_keeps_a_rebind_and_only_clears_the_flag(self):
        self.write_override({"bindings": [{"id": "applications.code-editor", "key": "G",
                                           "description": "mine"}]})
        self.assertEqual(0, self.run_cli("disable", "applications.code-editor"))
        entry = json.loads(self.override.read_text(encoding="utf-8"))["bindings"][0]
        self.assertEqual("G", entry["key"], "disabling threw away the rebind")
        self.assertFalse(entry["enabled"])

    def test_disable_refuses_the_locked_static_and_reserved_bindings(self):
        for binding_id, why in (("window.close", "locked"),
                                ("recovery.reapply-defaults", "hand-written"),
                                ("reserved.ctrl-alt-backspace", "reserved")):
            with self.subTest(id=binding_id):
                self.assertEqual(2, self.run_cli("disable", binding_id))
                self.assertIn(why, self.output)

    def test_disable_refuses_an_unknown_id(self):
        self.assertEqual(2, self.run_cli("disable", "not.a.binding"))
        self.assertFalse(self.override.exists())

    def test_a_batch_is_refused_as_a_whole_if_any_id_is_unknown(self):
        """One change, so it lands whole or not at all -- no half-disabled batch."""
        self.assertEqual(2, self.run_cli("disable", "applications.code-editor",
                                         "not.a.binding"))
        self.assertFalse(self.override.exists(),
                         "a half-applied batch left the first binding off")

    def test_disabling_two_bindings_is_one_change_to_both_files(self):
        self.assertEqual(0, self.run_cli("disable", "applications.code-editor",
                                         "applications.browser"))
        self.assertEqual(["applications.code-editor", "applications.browser"],
                         self.saved_entries())
        lua = self.session_binds()
        self.assertNotIn('hl.bind("SUPER + C"', lua)
        self.assertNotIn('hl.bind("SUPER + B"', lua)
        self.assertIn('hl.bind("SUPER + RETURN"', lua,
                      "an unrelated binding was dropped too")

    # --------------------------------------------------------- export / import

    def test_export_writes_the_differences_by_default(self):
        self.write_override({"bindings": [{"id": "window.close", "key": "Y",
                                           "description": "mine"}]})
        self.assertEqual(0, self.run_cli("export"))
        payload = json.loads(self.output.split("export:")[0])
        self.assertEqual(["window.close"], [e["id"] for e in payload["bindings"]])
        self.assertNotIn("version", payload)

    def test_export_all_writes_the_effective_map(self):
        self.assertEqual(0, self.run_cli("export", "--all"))
        payload = json.loads(self.output.split("export:")[0])
        self.assertEqual(2, payload["version"])
        self.assertEqual(len(kb.default_record(kb.ROOT)["bindings"]),
                         len(payload["bindings"]),
                         "--all exports the whole effective map, so its length is the "
                         "record's and not a number written down here")

    def test_export_says_so_when_there_is_nothing_of_yours(self):
        self.assertEqual(0, self.run_cli("export"))
        self.assertIn("shipped map unchanged", self.output)

    def test_export_to_a_file(self):
        target = Path(self.tmp.name) / "mine.json"
        self.assertEqual(0, self.run_cli("export", str(target)))
        self.assertTrue(target.is_file())
        self.assertEqual({"bindings": []}, json.loads(target.read_text(encoding="utf-8")))

    def test_import_merges_into_the_differences_already_saved(self):
        self.write_override({"bindings": [{"id": "window.close", "key": "Y",
                                           "description": "mine"}]})
        incoming = Path(self.tmp.name) / "incoming.json"
        incoming.write_text(json.dumps({"bindings": [
            {"id": "applications.code-editor", "key": "G", "description": "theirs"}]}),
            encoding="utf-8")
        self.assertEqual(0, self.run_cli("import", str(incoming)))
        self.assertEqual(["window.close", "applications.code-editor"],
                         self.saved_entries())

    def test_import_replace_asks_and_a_no_keeps_what_was_there(self):
        self.write_override({"bindings": [{"id": "window.close", "key": "Y",
                                           "description": "mine"}]})
        incoming = Path(self.tmp.name) / "incoming.json"
        incoming.write_text(json.dumps({"bindings": [
            {"id": "applications.code-editor", "key": "G", "description": "theirs"}]}),
            encoding="utf-8")
        with self.answer("n\n"):
            self.assertEqual(1, self.run_cli("import", str(incoming), "--replace"))
        self.assertEqual(["window.close"], self.saved_entries(),
                         "--replace discarded the saved difference after a no")
        with self.answer("y\n"):
            self.assertEqual(0, self.run_cli("import", str(incoming), "--replace"))
        self.assertEqual(["applications.code-editor"], self.saved_entries())

    def test_import_refuses_a_whole_exported_map_that_would_freeze_the_defaults(self):
        self.assertEqual(0, self.run_cli("export", "--all",
                                         str(Path(self.tmp.name) / "whole.json")))
        self.assertEqual(2, self.run_cli("import", str(Path(self.tmp.name) / "whole.json")))
        self.assertIn("freeze", self.output)
        self.assertIn("--all", self.output)
        self.assertFalse(self.override.exists())

    def test_import_accepts_a_whole_map_when_told_that_is_what_it_is(self):
        whole = Path(self.tmp.name) / "whole.json"
        self.assertEqual(0, self.run_cli("export", "--all", str(whole)))
        self.assertEqual(0, self.run_cli("import", str(whole), "--all", "--yes"))
        self.assertEqual(len(kb.default_record(kb.ROOT)["bindings"]),
                         len(self.saved_entries()))

    def test_import_refuses_a_file_that_is_not_json_or_not_a_document(self):
        broken = Path(self.tmp.name) / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        self.assertEqual(2, self.run_cli("import", str(broken)))
        self.assertIn("does not parse", self.output)

        not_a_document = Path(self.tmp.name) / "list.json"
        not_a_document.write_text("[]", encoding="utf-8")
        self.assertEqual(2, self.run_cli("import", str(not_a_document)))
        self.assertIn("'bindings'", self.output)

        self.assertEqual(2, self.run_cli("import", str(Path(self.tmp.name) / "absent.json")))
        self.assertIn("not a file", self.output)

    def test_import_refuses_an_entry_that_would_not_validate(self):
        incoming = Path(self.tmp.name) / "bad.json"
        incoming.write_text(json.dumps({"bindings": [
            {"id": "applications.code-editor", "key": "E", "description": "collides"}]}),
            encoding="utf-8")
        self.assertEqual(1, self.run_cli("import", str(incoming)))
        self.assertIn("already bound by", self.output)
        self.assertFalse(self.override.exists(),
                         "an import that would collide was written anyway")

    # --------------------------------------------------------------- failure

    def test_a_write_failure_half_way_through_puts_both_files_back(self):
        """Validation cannot cover the disk being full, so the backups have to.

        The failure is made to land on the *second* write, after the override has
        already been replaced on disk. Failing the first write instead would prove
        nothing at all: there would be nothing to put back, and this test would pass
        with the whole restore branch deleted.
        """
        self.write_override({"bindings": [{"id": "window.close", "key": "Y",
                                           "description": "mine"}]})
        self.assertEqual(0, self.run_cli("set", "applications.terminal", "--key", "G"))
        settled_override = self.override.read_bytes()
        settled_session = self.session_lua.read_bytes()

        real_write = kb.configstore.atomic_write
        written: List[Path] = []

        def fails_on_the_second(path, text, **kwargs):
            written.append(Path(path))
            if len(written) == 1:
                return real_write(path, text, **kwargs)
            raise OSError(28, "No space left on device")

        with unittest.mock.patch.object(kb.configstore, "atomic_write",
                                        side_effect=fails_on_the_second):
            self.assertEqual(1, self.run_cli("set", "applications.terminal",
                                             "--key", "F13"))
        self.assertEqual(2, len(written),
                         "the override was never replaced, so nothing needed restoring")
        self.assertIn("restored", self.output)
        self.assertEqual(settled_override, self.override.read_bytes(),
                         "the override was left holding the map that failed to write")
        self.assertEqual(settled_session, self.session_lua.read_bytes(),
                         "the session file changed even though the write failed")

    def test_a_write_failure_before_anything_changed_leaves_nothing_behind(self):
        self.write_override({"bindings": [{"id": "window.close", "key": "Y",
                                           "description": "mine"}]})
        self.assertEqual(0, self.run_cli("set", "applications.terminal", "--key", "G"))
        settled = self.override.read_bytes()
        with unittest.mock.patch.object(kb.configstore, "atomic_write",
                                        side_effect=OSError(28, "No space left")):
            self.assertEqual(1, self.run_cli("set", "applications.terminal",
                                             "--key", "F13"))
        self.assertIn("No space left", self.output,
                      "the reason has to reach the person, not just the status")
        self.assertEqual(settled, self.override.read_bytes())
        self.assertEqual(["window.close", "applications.terminal"], self.saved_entries())


    def test_config_home_moves_both_files_and_neither_is_written_elsewhere(self):
        """The flag used to reach only the generated Lua.

        ``commit_change`` was handed ``config_home`` for the session file while the
        override path came from an environment that still named the real ``HOME``, so
        one command wrote two homes and reported one change. Both files have to move
        together, and the real home has to stay untouched.
        """
        # --config-home names the .config directory, the way theme.py means it.
        config_root = self.home.parent / "elsewhere" / ".config"
        real_override = self.override
        self.assertFalse(real_override.exists())

        self.assertEqual(0, self.run_cli("set", "applications.browser", "--key", "G",
                                         "--config-home", str(config_root)))
        moved = config_root / "iarch" / "keybinds.json"
        self.assertTrue(moved.is_file(), "the override was not written under --config-home")
        self.assertEqual(["applications.browser"],
                         [e["id"] for e in json.loads(moved.read_text())["bindings"]])
        self.assertTrue((config_root / "hypr" / "generated" / "keybinds.lua").is_file(),
                        "the session file was not written under --config-home")
        self.assertFalse(real_override.exists(),
                         "--config-home still wrote the home the process was started in")
        self.assertFalse((self.home / ".config" / "hypr").exists())

    def test_config_home_beats_an_exported_config_dir(self):
        """Otherwise the command reads one directory and writes another."""
        config_root = self.home.parent / "elsewhere" / ".config"
        exported = self.home.parent / "exported" / "iarch"
        exported.mkdir(parents=True)
        os.environ["IARCH_CONFIG_DIR"] = str(exported)
        self.addCleanup(os.environ.pop, "IARCH_CONFIG_DIR", None)
        try:
            self.assertEqual(0, self.run_cli("set", "applications.browser", "--key", "G",
                                             "--config-home", str(config_root)))
        finally:
            os.environ.pop("IARCH_CONFIG_DIR", None)
        self.assertTrue((config_root / "iarch" / "keybinds.json").is_file())
        self.assertEqual([], list(exported.iterdir()),
                         "an inherited IARCH_CONFIG_DIR beat the explicit flag")

    def test_a_read_only_command_still_reads_the_home_it_was_started_in(self):
        """Only the mutating commands take --config-home; the ones that merely read
        must keep reading the home the process was started in."""
        self.write_override({"bindings": [{"id": "applications.browser", "key": "G"}]})
        self.assertEqual(0, self.run_cli("list"))
        self.assertIn("SUPER + G", self.output,
                      "a read-only command stopped reading the person's own map")


if __name__ == "__main__":
    unittest.main()
